"""
Sky Raid 1942 — vertical shooter
pip install pygame numpy

Arrows/WASD move, Space shoot, U unlimited lives, Enter/Space start,
Esc quit.
"""

import json
import math
import os
import platform
import random
import subprocess
import sys
import tempfile
import threading
import wave

import numpy as np
import pygame

IS_MAC = platform.system() == "Darwin"
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skyraid_save.json")
SFX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".skyraid_sfx")
VW, VH = 480, 720
FPS = 60
SCORE_SCREEN_MS = 20000
AUDIO_SR = 22050

DEFAULT_SCORES = [
    ("REX", 25000), ("NOVA", 18000), ("KAI", 12000), ("MIRA", 9000),
    ("JON", 7000), ("VAL", 5000), ("ASH", 3500), ("REN", 2000),
    ("PIO", 1000), ("ACE", 500),
]


def load_save():
    data = {
        "width": VW, "height": VH, "x": None, "y": None,
        "highscores": [list(s) for s in DEFAULT_SCORES],
    }
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        data.update(raw)
        hs = []
        for row in data.get("highscores", []):
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                hs.append([str(row[0])[:8], int(row[1])])
        while len(hs) < 10:
            hs.append(list(DEFAULT_SCORES[len(hs)]))
        data["highscores"] = sorted(hs, key=lambda r: -r[1])[:10]
    except Exception:
        pass
    return data


def write_save(data):
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


SAVE = load_save()


def get_sdl_window():
    if IS_MAC:
        return None
    try:
        from pygame._sdl2.video import Window
        return Window.from_display_module()
    except Exception:
        return None


def read_window_geom(win_w, win_h):
    pos = None
    sdl = get_sdl_window()
    if sdl is not None:
        try:
            pos = tuple(sdl.position)
        except Exception:
            pos = None
    if pos is None:
        try:
            pos = pygame.display.get_window_position()
        except Exception:
            pos = None
    SAVE["width"] = win_w
    SAVE["height"] = win_h
    if pos and pos[0] is not None:
        SAVE["x"], SAVE["y"] = int(pos[0]), int(pos[1])
    write_save(SAVE)


# Display first. Do not re-init mixer on macOS (bus error in CoreAudio).
pygame.init()

start_w = max(360, int(SAVE.get("width") or VW))
start_h = max(480, int(SAVE.get("height") or VH))
if SAVE.get("x") is not None and SAVE.get("y") is not None:
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{int(SAVE['x'])},{int(SAVE['y'])}"

screen = pygame.display.set_mode((start_w, start_h), pygame.RESIZABLE)
pygame.display.set_caption("Sky Raid 1942")
clock = pygame.time.Clock()
game_surf = pygame.Surface((VW, VH))

if not IS_MAC:
    sdl_win = get_sdl_window()
    if sdl_win is not None and SAVE.get("x") is not None:
        try:
            sdl_win.position = (int(SAVE["x"]), int(SAVE["y"]))
        except Exception:
            pass


def _font(name, size, bold=False):
    try:
        return pygame.font.SysFont(name, size, bold=bold)
    except Exception:
        return pygame.font.Font(None, size)


FONT = _font("consolas", 18)
FONT_SM = _font("consolas", 14)
BIG = _font("consolas", 36, True)
CRAWL = _font("consolas", 22, True)
TITLEF = _font("consolas", 28, True)
win_w, win_h = start_w, start_h


def letterbox_blit(dest, src):
    dw, dh = dest.get_size()
    scale = min(dw / VW, dh / VH)
    tw, th = max(1, int(VW * scale)), max(1, int(VH * scale))
    dest.fill((0, 0, 0))
    dest.blit(pygame.transform.smoothscale(src, (tw, th)), ((dw - tw) // 2, (dh - th) // 2))


# ---------------------------------------------------------------------------
# Audio: WAV files on disk. macOS uses afplay (no pygame mixer).
# Other OS uses pygame.mixer.Sound(filename).
# ---------------------------------------------------------------------------
def _tone_wave(freq, ms, vol=0.25, kind="square", decay=True):
    n = max(1, int(AUDIO_SR * ms / 1000.0))
    t = np.arange(n, dtype=np.float32) / float(AUDIO_SR)
    if kind == "square":
        wave_a = np.sign(np.sin(2 * np.pi * freq * t))
    elif kind == "noise":
        wave_a = np.random.default_rng(1).uniform(-1.0, 1.0, n).astype(np.float32)
    else:
        wave_a = np.sin(2 * np.pi * freq * t)
    if decay:
        wave_a = wave_a * np.linspace(1.0, 0.02, n, dtype=np.float32)
    return np.clip(wave_a * vol, -1.0, 1.0)


def _music_wave():
    notes = [
        (196, 0.35), (247, 0.35), (294, 0.45), (392, 0.7),
        (370, 0.25), (392, 0.55), (330, 0.4), (294, 0.5),
        (262, 0.35), (294, 0.35), (330, 0.45), (392, 0.8),
        (349, 0.4), (330, 0.4), (294, 1.0),
        (220, 0.3), (247, 0.3), (262, 0.4), (330, 0.7),
        (294, 0.35), (262, 0.9),
    ]
    chunks = []
    for f, dur in notes:
        n = max(1, int(AUDIO_SR * dur))
        t = np.arange(n, dtype=np.float32) / float(AUDIO_SR)
        env = np.minimum(1.0, t * 18.0) * np.exp(-t * 1.6)
        w = 0.22 * np.sin(2 * np.pi * f * t)
        w += 0.08 * np.sin(2 * np.pi * f * 2 * t)
        w += 0.05 * np.sin(2 * np.pi * (f / 2) * t)
        chunks.append(w * env)
    chunks.append(np.zeros(int(AUDIO_SR * 0.35), dtype=np.float32))
    return np.clip(np.concatenate(chunks), -1.0, 1.0)


def write_wav(path, samples):
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(AUDIO_SR)
        wf.writeframes(pcm.tobytes())
    return path


class _Silent:
    def play(self, *a, **k):
        return None

    def stop(self):
        return None


class AfplaySound:
    """macOS-safe playback via /usr/bin/afplay."""
    _live = []
    _lock = threading.Lock()

    def __init__(self, path, volume=0.5):
        self.path = path
        self.volume = str(volume)
        self._stop = threading.Event()
        self._thread = None
        self._proc = None

    @classmethod
    def _reap(cls):
        with cls._lock:
            alive = []
            for p in cls._live:
                if p.poll() is None:
                    alive.append(p)
            cls._live = alive

    def play(self, loops=0):
        self.stop()
        if loops == -1:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop_forever, daemon=True)
            self._thread.start()
            return
        self._spawn()

    def _spawn(self):
        self._reap()
        with self._lock:
            if len(self._live) >= 8:
                return
        try:
            proc = subprocess.Popen(
                ["/usr/bin/afplay", "-v", self.volume, self.path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return
        with self._lock:
            self._live.append(proc)
        self._proc = proc

    def _loop_forever(self):
        while not self._stop.is_set():
            try:
                proc = subprocess.Popen(
                    ["/usr/bin/afplay", "-v", self.volume, self.path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                break
            self._proc = proc
            while proc.poll() is None:
                if self._stop.is_set():
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    break
                pygame.time.wait(40)

    def stop(self):
        self._stop.set()
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None


def _pygame_sound(path):
    try:
        return pygame.mixer.Sound(path)
    except Exception:
        return _Silent()


def build_sound(name, samples, volume=0.5):
    path = os.path.join(SFX_DIR, name + ".wav")
    try:
        write_wav(path, samples)
    except Exception:
        return _Silent()
    if IS_MAC:
        return AfplaySound(path, volume=volume)
    return _pygame_sound(path)


if not IS_MAC:
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=1024)
    except Exception as e:
        print("mixer init failed:", e)

SND_SHOT = build_sound("shot", _tone_wave(880, 60, 0.22, "square"), 0.35)
SND_ENEMY_SHOT = build_sound("eshot", _tone_wave(220, 80, 0.18, "sine"), 0.30)
SND_EXPLODE = build_sound("boom", _tone_wave(80, 280, 0.35, "noise"), 0.45)
SND_HIT = build_sound("hit", _tone_wave(160, 90, 0.22, "noise"), 0.35)
SND_POWER = build_sound("power", _tone_wave(660, 180, 0.22, "sine"), 0.40)
SND_BOSS = build_sound("boss", _tone_wave(110, 400, 0.28, "square"), 0.45)
SND_PLAYER_DIE = build_sound("die", _tone_wave(70, 500, 0.36, "noise"), 0.50)
MUSIC = build_sound("theme", _music_wave(), 0.28)
music_playing = False


def start_music():
    global music_playing
    if music_playing:
        return
    try:
        MUSIC.play(loops=-1)
        music_playing = True
    except TypeError:
        try:
            MUSIC.play(-1)
            music_playing = True
        except Exception:
            pass
    except Exception:
        pass


def stop_music():
    global music_playing
    try:
        MUSIC.stop()
    except Exception:
        pass
    music_playing = False


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def draw_ship(surf, x, y, w, h, colors, flip=False):
    body, wing, cockpit, accent = colors
    if not flip:
        pts = [(x + w // 2, y), (x + w, y + h * 0.7), (x + w * 0.7, y + h),
               (x + w * 0.3, y + h), (x, y + h * 0.7)]
        wing_l = [(x, y + h * 0.45), (x - w * 0.35, y + h * 0.75), (x + w * 0.15, y + h * 0.65)]
        wing_r = [(x + w, y + h * 0.45), (x + w + w * 0.35, y + h * 0.75), (x + w * 0.85, y + h * 0.65)]
        cock = pygame.Rect(x + w * 0.35, y + h * 0.25, w * 0.3, h * 0.28)
    else:
        pts = [(x + w // 2, y + h), (x + w, y + h * 0.3), (x + w * 0.7, y),
               (x + w * 0.3, y), (x, y + h * 0.3)]
        wing_l = [(x, y + h * 0.55), (x - w * 0.35, y + h * 0.25), (x + w * 0.15, y + h * 0.35)]
        wing_r = [(x + w, y + h * 0.55), (x + w + w * 0.35, y + h * 0.25), (x + w * 0.85, y + h * 0.35)]
        cock = pygame.Rect(x + w * 0.35, y + h * 0.45, w * 0.3, h * 0.28)
    pygame.draw.polygon(surf, wing, wing_l)
    pygame.draw.polygon(surf, wing, wing_r)
    pygame.draw.polygon(surf, body, pts)
    pygame.draw.polygon(surf, accent, pts, 1)
    pygame.draw.ellipse(surf, cockpit, cock)


class Particle:
    def __init__(self, x, y, kind="spark"):
        self.x, self.y = float(x), float(y)
        self.kind = kind
        ang = random.uniform(0, math.tau)
        if kind == "spark":
            spd = random.uniform(2, 8)
            self.vx, self.vy = math.cos(ang) * spd, math.sin(ang) * spd
            self.life = random.randint(12, 28)
            self.color = random.choice([(255, 220, 80), (255, 180, 40), (255, 255, 200)])
            self.size = random.randint(1, 3)
        elif kind == "fire":
            self.vx = random.uniform(-1.2, 1.2)
            self.vy = random.uniform(-3.5, -0.5)
            self.life = random.randint(18, 40)
            self.color = random.choice([(255, 80, 10), (255, 140, 20), (255, 200, 40)])
            self.size = random.randint(3, 7)
        elif kind == "smoke":
            self.vx = random.uniform(-0.6, 0.6)
            self.vy = random.uniform(-1.5, -0.2)
            self.life = random.randint(25, 50)
            self.color = random.choice([(60, 60, 60), (90, 90, 90), (40, 40, 40)])
            self.size = random.randint(4, 10)
        else:
            spd = random.uniform(1, 6)
            self.vx, self.vy = math.cos(ang) * spd, math.sin(ang) * spd
            self.life = random.randint(20, 45)
            self.color = random.choice([(200, 200, 200), (180, 80, 40), (120, 120, 140)])
            self.size = random.randint(2, 5)
        self.max_life = self.life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.kind == "fire":
            self.vy -= 0.04
            self.size = max(1, self.size - 0.08)
        if self.kind == "smoke":
            self.size += 0.08
            self.vy -= 0.02
        self.life -= 1
        return self.life > 0

    def draw(self, surf):
        a = self.life / self.max_life
        c = tuple(int(clamp(ch * a, 0, 255)) for ch in self.color)
        if self.kind == "spark":
            pygame.draw.line(surf, c, (self.x, self.y), (self.x - self.vx, self.y - self.vy), 1)
        else:
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), max(1, int(self.size)))


class StarField:
    def __init__(self):
        self.stars = [[random.randrange(VW), random.randrange(VH),
                       random.uniform(1.2, 5.5), random.randint(80, 255)] for _ in range(90)]
        self.clouds = [[random.randrange(VW), random.randrange(VH),
                        random.randint(40, 90), random.uniform(0.4, 1.1)] for _ in range(8)]

    def update(self):
        for s in self.stars:
            s[1] += s[2]
            if s[1] > VH:
                s[0] = random.randrange(VW)
                s[1] = -2
        for c in self.clouds:
            c[1] += c[3]
            if c[1] > VH + 40:
                c[0] = random.randrange(VW)
                c[1] = -50

    def draw(self, surf):
        surf.fill((8, 10, 28))
        for c in self.clouds:
            pygame.draw.ellipse(surf, (18, 22, 48), (c[0] - c[2], c[1], c[2] * 2, 28))
        for x, y, spd, col in self.stars:
            pygame.draw.circle(surf, (col, col, min(255, col + 20)), (int(x), int(y)), 1 if spd < 3 else 2)


class Bullet:
    def __init__(self, x, y, vy, color, dmg=1, friendly=True, vx=0, w=3, h=10):
        self.x, self.y = float(x), float(y)
        self.vx, self.vy = vx, vy
        self.color = color
        self.dmg = dmg
        self.friendly = friendly
        self.w, self.h = w, h
        self.alive = True

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y), self.w, self.h)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.y < -20 or self.y > VH + 20 or self.x < -20 or self.x > VW + 20:
            self.alive = False

    def draw(self, surf):
        r = self.rect
        pygame.draw.rect(surf, self.color, r, border_radius=2)
        glow = tuple(min(255, c + 60) for c in self.color)
        pygame.draw.rect(surf, glow, r.inflate(-2, -4))


POWER_TYPES = ["multi", "rapid", "shield", "life", "spread"]
POWER_COLORS = {
    "multi": (80, 180, 255), "rapid": (255, 200, 40), "shield": (80, 255, 160),
    "life": (255, 80, 120), "spread": (200, 120, 255),
}


class PowerUp:
    def __init__(self, x, y, kind=None):
        self.x, self.y = float(x), float(y)
        self.kind = kind or random.choice(POWER_TYPES)
        self.vy = 1.6
        self.alive = True
        self.t = 0

    @property
    def rect(self):
        return pygame.Rect(int(self.x - 11), int(self.y - 11), 22, 22)

    def update(self):
        self.y += self.vy
        self.t += 1
        if self.y > VH + 20:
            self.alive = False

    def draw(self, surf):
        c = POWER_COLORS[self.kind]
        s = 10 + int(2 * math.sin(self.t * 0.2))
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), s)
        pygame.draw.circle(surf, (255, 255, 255), (int(self.x), int(self.y)), s, 2)
        txt = FONT.render(self.kind[0].upper(), True, (10, 10, 20))
        surf.blit(txt, txt.get_rect(center=(int(self.x), int(self.y))))


class Player:
    def __init__(self):
        self.w, self.h = 28, 32
        self.x = VW / 2
        self.y = VH - 80
        self.speed = 5.2
        self.cooldown = 0
        self.fire_delay = 10
        self.multi = 1
        self.spread = False
        self.shield = 0
        self.lives = 3
        self.invuln = 0
        self.unlimited = False
        self.alive = True
        self.score = 0
        self.colors = ((40, 200, 255), (20, 90, 180), (180, 255, 255), (255, 255, 255))

    def max_upgrades(self):
        self.multi = 4
        self.spread = True
        self.fire_delay = 4
        self.shield = 20000
        self.speed = 6.4
        self.lives = 9

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y - self.h / 2), self.w, self.h)

    def update(self, keys, demo_dx=0, demo_dy=0, demo_fire=False):
        if keys is not None:
            dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
            dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        else:
            dx, dy = demo_dx, demo_dy
        self.x = clamp(self.x + dx * self.speed, 16, VW - 16)
        self.y = clamp(self.y + dy * self.speed, 40, VH - 20)
        if self.cooldown > 0:
            self.cooldown -= 1
        if self.invuln > 0:
            self.invuln -= 1
        if self.shield > 0:
            self.shield -= 1
        fire_trail(self.x, self.y + self.h / 2, 1)
        return demo_fire or (keys is not None and keys[pygame.K_SPACE])

    def shoot(self, bullets):
        if self.cooldown > 0:
            return
        self.cooldown = self.fire_delay
        SND_SHOT.play()
        if self.multi == 1:
            xs = [0]
        elif self.multi == 2:
            xs = [-8, 8]
        elif self.multi == 3:
            xs = [-12, 0, 12]
        else:
            xs = [-16, -6, 6, 16]
        for ox in xs:
            bullets.append(Bullet(self.x + ox, self.y - 16, -11, (80, 255, 255), 1, True))
        if self.spread:
            bullets.append(Bullet(self.x, self.y - 10, -9, (180, 255, 80), 1, True, vx=-3.2))
            bullets.append(Bullet(self.x, self.y - 10, -9, (180, 255, 80), 1, True, vx=3.2))

    def hit(self):
        if self.invuln > 0:
            return False
        if self.shield > 0:
            self.shield = max(0, self.shield - 90)
            burst(self.x, self.y, 12, ("spark",))
            SND_HIT.play()
            return False
        burst(self.x, self.y, 40, ("fire", "spark", "debris", "smoke"))
        SND_PLAYER_DIE.play()
        if not self.unlimited:
            self.lives -= 1
        self.invuln = 90
        self.multi = max(1, self.multi - 1)
        self.spread = False
        self.fire_delay = min(10, self.fire_delay + 2)
        if self.lives <= 0 and not self.unlimited:
            self.alive = False
        return True

    def apply_power(self, kind):
        SND_POWER.play()
        if kind == "multi":
            self.multi = min(4, self.multi + 1)
        elif kind == "rapid":
            self.fire_delay = max(4, self.fire_delay - 2)
        elif kind == "shield":
            self.shield = 360
        elif kind == "life":
            self.lives += 1
        elif kind == "spread":
            self.spread = True

    def draw(self, surf):
        if self.invuln > 0 and (self.invuln // 3) % 2 == 0:
            return
        r = self.rect
        draw_ship(surf, r.x, r.y, r.w, r.h, self.colors, flip=False)
        if self.shield > 0:
            rad = 22 + int(2 * math.sin(pygame.time.get_ticks() * 0.02))
            pygame.draw.circle(surf, (80, 255, 180), (int(self.x), int(self.y)), rad, 2)


ENEMY_PALETTES = [
    ((255, 70, 70), (160, 20, 40), (255, 200, 200), (255, 220, 80)),
    ((255, 160, 40), (180, 80, 10), (255, 230, 160), (80, 255, 120)),
    ((180, 80, 255), (90, 20, 160), (230, 180, 255), (255, 80, 200)),
    ((80, 255, 140), (20, 140, 70), (180, 255, 200), (255, 255, 80)),
    ((255, 80, 180), (160, 20, 90), (255, 180, 220), (80, 200, 255)),
    ((80, 160, 255), (20, 50, 160), (180, 220, 255), (255, 200, 40)),
]
KINDS = ["scout", "fighter", "tank", "bomber", "interceptor"]


class Enemy:
    def __init__(self, kind, x, y, path="down"):
        self.kind = kind
        self.x, self.y = float(x), float(y)
        self.path = path
        self.t = 0
        self.alive = True
        self.flash = 0
        self.palette = random.choice(ENEMY_PALETTES)
        self.base_x = x
        stats = {
            "scout": (22, 22, 1, 50, 3.2),
            "fighter": (26, 26, 2, 80, 2.4),
            "tank": (34, 30, 5, 160, 1.5),
            "bomber": (40, 28, 4, 140, 1.8),
        }
        self.w, self.h, self.hp, self.score, self.spd = stats.get(kind, (24, 24, 2, 70, 2.6))
        self.max_hp = self.hp
        self.shoot_cd = random.randint(40, 120)

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y - self.h / 2), self.w, self.h)

    def update(self, bullets, player):
        self.t += 1
        if self.path == "down":
            self.y += self.spd
        elif self.path == "sine":
            self.y += self.spd
            self.x = self.base_x + math.sin(self.t * 0.08) * 70
        elif self.path == "zag":
            self.y += self.spd
            self.x += math.cos(self.t * 0.12) * 3
        elif self.path == "dive":
            self.y += self.spd + 1.4
            if player:
                self.x += (player.x - self.x) * 0.02
        elif self.path.startswith("circle"):
            self.x = self.base_x + math.cos(self.t * 0.06) * 60
            self.y += 1.2
        self.x = clamp(self.x, 12, VW - 12)
        if self.y > VH + 40:
            self.alive = False
        if self.flash:
            self.flash -= 1
        if self.hp < self.max_hp * 0.45 and random.random() < 0.35:
            fire_trail(self.x, self.y + 6, 1)
        self.shoot_cd -= 1
        if self.shoot_cd <= 0 and 0 < self.y < VH - 80 and player:
            self.shoot_cd = random.randint(50, 140)
            self.fire(bullets, player)

    def fire(self, bullets, player):
        SND_ENEMY_SHOT.play()
        if self.kind == "scout":
            bullets.append(Bullet(self.x, self.y + 10, 5.5, (255, 80, 80), 1, False, h=8))
        elif self.kind == "fighter":
            bullets.append(Bullet(self.x - 6, self.y + 8, 5.2, (255, 120, 40), 1, False))
            bullets.append(Bullet(self.x + 6, self.y + 8, 5.2, (255, 120, 40), 1, False))
        elif self.kind == "tank":
            dx, dy = player.x - self.x, player.y - self.y
            dist = max(1, math.hypot(dx, dy))
            bullets.append(Bullet(self.x, self.y + 8, 4.2 * dy / dist, (255, 60, 180), 1, False,
                                  vx=4.2 * dx / dist, w=5, h=8))
        elif self.kind == "bomber":
            for vx in (-2, 0, 2):
                bullets.append(Bullet(self.x, self.y + 10, 4.0, (255, 200, 40), 1, False, vx=vx, w=6, h=6))
        else:
            bullets.append(Bullet(self.x, self.y + 8, 5, (255, 100, 200), 1, False))

    def hurt(self, dmg):
        self.hp -= dmg
        self.flash = 4
        burst(self.x, self.y, 6, ("spark",))
        SND_HIT.play()
        if self.hp <= 0:
            self.alive = False
            burst(self.x, self.y, 28, ("fire", "spark", "debris", "smoke"))
            SND_EXPLODE.play()
            return True
        return False

    def draw(self, surf):
        r = self.rect
        cols = ((255, 255, 255),) * 4 if self.flash else self.palette
        draw_ship(surf, r.x, r.y, r.w, r.h, cols, flip=True)
        if self.max_hp > 2:
            pygame.draw.rect(surf, (40, 0, 0), (r.x, r.y - 6, self.w, 3))
            pygame.draw.rect(surf, (80, 255, 80), (r.x, r.y - 6, int(self.w * self.hp / self.max_hp), 3))


class Boss:
    def __init__(self, level):
        self.level = level
        self.x = VW / 2
        self.y = -80
        self.w = 90 + level * 8
        self.h = 60 + level * 4
        self.hp = 40 + level * 25
        self.max_hp = self.hp
        self.t = 0
        self.alive = True
        self.entering = True
        self.shoot_cd = 30
        self.flash = 0
        pals = [
            ((220, 40, 60), (90, 10, 20), (255, 180, 180), (255, 220, 60)),
            ((40, 80, 220), (10, 20, 90), (160, 200, 255), (80, 255, 200)),
            ((200, 160, 20), (90, 60, 0), (255, 240, 140), (255, 80, 40)),
            ((160, 40, 200), (50, 0, 80), (230, 160, 255), (80, 255, 160)),
        ]
        self.palette = pals[(level - 1) % len(pals)]
        self.score = 1500 * level
        SND_BOSS.play()

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w / 2), int(self.y - self.h / 2), self.w, self.h)

    def update(self, bullets, player, enemies):
        self.t += 1
        if self.entering:
            self.y += 1.6
            if self.y >= 110:
                self.entering = False
            return
        self.x = VW / 2 + math.sin(self.t * 0.025) * (140 + self.level * 8)
        self.y = 110 + math.sin(self.t * 0.04) * 18
        if self.flash:
            self.flash -= 1
        if self.hp < self.max_hp * 0.5:
            fire_trail(self.x - 20, self.y + 20, 2)
            fire_trail(self.x + 20, self.y + 20, 2)
        self.shoot_cd -= 1
        if self.shoot_cd <= 0 and player:
            self.fire(bullets, player, enemies)
            self.shoot_cd = max(16, 50 - self.level * 4)

    def fire(self, bullets, player, enemies):
        pattern = (self.t // 90 + self.level) % 4
        if pattern == 0:
            for i in range(-3, 4):
                bullets.append(Bullet(self.x + i * 12, self.y + 28, 5, (255, 60, 60), 1, False))
        elif pattern == 1:
            for a in range(8):
                ang = a * math.pi / 7 + self.t * 0.02
                bullets.append(Bullet(self.x, self.y + 20, 4.2 * math.sin(ang) + 2,
                                      (255, 140, 40), 1, False, vx=4.2 * math.cos(ang)))
        elif pattern == 2:
            dx, dy = player.x - self.x, max(40, player.y - self.y)
            dist = math.hypot(dx, dy)
            for k in (-1, 0, 1):
                bullets.append(Bullet(self.x + k * 18, self.y + 24, 6 * dy / dist,
                                      (255, 80, 220), 1, False, vx=6 * dx / dist + k * 0.6))
        else:
            if len(enemies) < 10:
                enemies.append(Enemy(random.choice(["scout", "fighter"]),
                                     self.x + random.choice([-40, 40]), self.y + 30, "dive"))
            for i in (-2, 2):
                bullets.append(Bullet(self.x + i * 20, self.y + 20, 4.5, (80, 255, 200), 1, False, vx=i * 0.8))

    def hurt(self, dmg):
        self.hp -= dmg
        self.flash = 3
        burst(self.x + random.uniform(-30, 30), self.y + random.uniform(-10, 20), 8, ("spark", "fire"))
        if self.hp <= 0:
            self.alive = False
            for _ in range(8):
                burst(self.x + random.uniform(-40, 40), self.y + random.uniform(-20, 20),
                      22, ("fire", "spark", "debris", "smoke"))
            SND_EXPLODE.play()
            return True
        return False

    def draw(self, surf):
        r = self.rect
        cols = ((255, 255, 255),) * 4 if self.flash else self.palette
        pygame.draw.ellipse(surf, cols[1], r.inflate(20, 8))
        draw_ship(surf, r.x + 10, r.y, r.w - 20, r.h, cols, flip=True)
        pygame.draw.polygon(surf, cols[0], [(r.x, r.centery), (r.x - 28, r.bottom), (r.x + 10, r.bottom - 8)])
        pygame.draw.polygon(surf, cols[0], [(r.right, r.centery), (r.right + 28, r.bottom), (r.right - 10, r.bottom - 8)])
        pygame.draw.rect(surf, (40, 0, 0), (40, 12, VW - 80, 10))
        pygame.draw.rect(surf, (255, 60, 60), (40, 12, int((VW - 80) * self.hp / self.max_hp), 10))
        pygame.draw.rect(surf, (255, 255, 255), (40, 12, VW - 80, 10), 1)
        surf.blit(FONT.render(f"BOSS {self.level}", True, (255, 220, 80)), (40, 24))


def spawn_formation(wave, enemies):
    style = wave % 7
    if style == 0:
        kind = "fighter" if wave > 2 else "scout"
        for i in range(7):
            enemies.append(Enemy(kind, VW // 2 + (i - 3) * 36, -30 - abs(i - 3) * 22, "sine"))
    elif style == 1:
        for i in range(8):
            enemies.append(Enemy("scout", 50, -20 - i * 28, "zag"))
            enemies.append(Enemy("scout", VW - 50, -20 - i * 28, "zag"))
    elif style == 2:
        kind = "tank" if wave > 4 else "fighter"
        for i in range(6):
            enemies.append(Enemy(kind, 50 + i * 70, -40 - (i % 2) * 20, "down"))
    elif style == 3:
        for i in range(6):
            e = Enemy("interceptor", VW // 2, -40 - i * 18, "circle")
            e.t = i * 12
            enemies.append(e)
    elif style == 4:
        for i in range(5):
            enemies.append(Enemy("bomber", 80 + i * 70, -60 - i * 25, "dive"))
    elif style == 5:
        for i in range(10):
            enemies.append(Enemy(KINDS[i % len(KINDS)], VW // 2 + ((-1) ** i) * 30, -20 - i * 22, "sine"))
    else:
        for i in range(5):
            enemies.append(Enemy("fighter", 30, -20 - i * 30, "dive"))
            enemies.append(Enemy("fighter", VW - 30, -20 - i * 30, "dive"))
        enemies.append(Enemy("tank", VW // 2, -80, "down"))


particles = []


def burst(x, y, n=18, kinds=("spark", "fire", "debris")):
    for _ in range(n):
        particles.append(Particle(x, y, random.choice(kinds)))


def fire_trail(x, y, n=3):
    for _ in range(n):
        particles.append(Particle(x + random.uniform(-4, 4), y, "fire"))
        if random.random() < 0.4:
            particles.append(Particle(x, y, "smoke"))


STORY_TITLE = "SKY RAID"
STORY_EPISODE = "A long time into the war..."
STORY_LINES = [
    "",
    "The outer colonies have gone dark.",
    "From the rust-red moons of Vesper to the",
    "ice docks of Faraday, every beacon has",
    "been swallowed by a fleet that does not",
    "negotiate and does not leave survivors.",
    "",
    "They call themselves the Crimson Armada.",
    "Their carriers blot out suns. Their",
    "fighters move in living flocks, stitched",
    "together by a single cold intelligence",
    "buried in the flagship NEMESIS.",
    "",
    "Earth is next.",
    "",
    "The last squadrons burned in orbit.",
    "The admiralty is ash. All that remains",
    "is one patched interceptor, a handful of",
    "stolen warheads, and a pilot who refused",
    "the order to retreat.",
    "",
    "You are that pilot.",
    "",
    "Climb the well. Cut through the flocks.",
    "Break their captains. When the sky itself",
    "catches fire, keep climbing.",
    "",
    "If Nemesis reaches the blue world below,",
    "there will be no second story.",
    "",
    "The raid begins now.",
]
LINE_GAP = 28
CRAWL_START_SCALE = 1.0
CRAWL_END_SCALE = CRAWL_START_SCALE / 8.0
VANISH_Y = 78


def line_scale(base_y):
    p = clamp((VH - 50 - base_y) / max(1, (VH - 50 - VANISH_Y)), 0, 1)
    return CRAWL_START_SCALE * (1 - p) + CRAWL_END_SCALE * p


class StoryCrawl:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t = 0
        self.origin = VH + 30

    def last_line_index(self):
        last = 0
        for i, line in enumerate(STORY_LINES):
            if line.strip():
                last = i
        return last

    def finished(self):
        last_y = self.origin + self.last_line_index() * LINE_GAP
        return line_scale(last_y) <= CRAWL_END_SCALE + 0.002 and last_y < VH - 40

    def update(self):
        self.t += 1
        self.origin -= 0.85

    def draw(self, surf):
        title = TITLEF.render(STORY_TITLE, True, (255, 220, 80))
        ta = max(0, 255 - self.t * 0.7)
        if ta > 8:
            tcopy = title.copy()
            tcopy.set_alpha(int(ta))
            surf.blit(tcopy, tcopy.get_rect(center=(VW // 2, 44)))
        ep = FONT_SM.render(STORY_EPISODE, True, (255, 230, 140))
        ea = max(0, 220 - self.t * 0.65)
        if ea > 8:
            ecopy = ep.copy()
            ecopy.set_alpha(int(ea))
            surf.blit(ecopy, ecopy.get_rect(center=(VW // 2, 72)))
        for i, line in enumerate(STORY_LINES):
            if not line.strip():
                continue
            base_y = self.origin + i * LINE_GAP
            if base_y > VH + 30 or base_y < VANISH_Y - 16:
                continue
            scale = line_scale(base_y)
            fade = 1.0
            if base_y < VANISH_Y + 70:
                fade = clamp((base_y - VANISH_Y) / 70, 0, 1)
            if base_y > VH - 70:
                fade *= clamp((VH + 8 - base_y) / 80, 0, 1)
            txt = CRAWL.render(line, True, (255, 210, 70))
            tw, th = txt.get_size()
            nw, nh = max(1, int(tw * scale)), max(1, int(th * scale))
            scaled = pygame.transform.smoothscale(txt, (nw, nh))
            scaled.set_alpha(int(255 * fade))
            surf.blit(scaled, scaled.get_rect(center=(VW // 2, int(base_y))))
        hint = FONT_SM.render("PRESS SPACE / ENTER TO START", True, (180, 200, 255))
        hint.set_alpha(160 + int(80 * math.sin(self.t * 0.08)))
        surf.blit(hint, hint.get_rect(center=(VW // 2, VH - 28)))


class Session:
    def __init__(self, demo=False, demo_upgraded=False):
        self.demo = demo
        self.stars = StarField()
        self.player = Player()
        if demo:
            self.player.unlimited = True
            if demo_upgraded:
                self.player.max_upgrades()
        self.bullets = []
        self.enemies = []
        self.powers = []
        self.boss = None
        self.wave = 1
        self.wave_timer = 0
        self.next_wave_in = 30
        self.state = "play"
        self.boss_seen = False
        spawn_formation(self.wave, self.enemies)

    def demo_brain(self):
        p = self.player
        dx = dy = 0
        left_threat = right_threat = 0
        imminent = False
        for b in self.bullets:
            if b.friendly or b.vy <= 0:
                continue
            tframes = (p.y - 8 - b.y) / b.vy
            if 0 <= tframes <= 28:
                fx = b.x + b.vx * tframes
                if abs(fx - p.x) < 26:
                    imminent = True
                    if fx >= p.x:
                        right_threat += 2 if tframes < 12 else 1
                    else:
                        left_threat += 2 if tframes < 12 else 1
        for e in self.enemies:
            if e.y > p.y - 50 and abs(e.x - p.x) < 36 and e.y < p.y + 10:
                imminent = True
                if e.x >= p.x:
                    right_threat += 2
                else:
                    left_threat += 2
        best_pw = None
        best_pw_score = -1e9
        for pw in self.powers:
            if pw.y > p.y + 24:
                continue
            frames_to_x = abs(pw.x - p.x) / max(0.1, p.speed)
            future_y = pw.y + pw.vy * frames_to_x
            if future_y > VH + 10:
                continue
            reach = 220 - abs(pw.x - p.x) - max(0, p.y - future_y) * 0.35
            if pw.kind in ("multi", "spread", "rapid", "shield"):
                reach += 40
            if reach > best_pw_score:
                best_pw_score = reach
                best_pw = pw
        target = None
        best_t = 1e9
        if self.boss and self.boss.alive:
            target = self.boss
        else:
            for e in self.enemies:
                if e.y < -8 or e.y > p.y - 18:
                    continue
                d = abs(e.x - p.x) * 1.35 + max(0, p.y - e.y) * 0.25
                if e.kind in ("tank", "bomber"):
                    d *= 0.65
                if d < best_t:
                    best_t = d
                    target = e
        pickup = best_pw is not None and best_pw_score > 40
        if imminent:
            if right_threat > left_threat:
                dx = -1
            elif left_threat > right_threat:
                dx = 1
            else:
                dx = -1 if p.x > VW / 2 else 1
            if p.x < 36:
                dx = 1
            if p.x > VW - 36:
                dx = -1
            dy = -1 if p.y > VH - 160 else 0
        elif pickup:
            if best_pw.x < p.x - 3:
                dx = -1
            elif best_pw.x > p.x + 3:
                dx = 1
            intercept_y = min(VH - 60, max(80, best_pw.y + 8))
            if p.y < intercept_y - 6:
                dy = 1
            elif p.y > intercept_y + 10:
                dy = -1
        elif target is not None:
            aim_x = target.x
            if hasattr(target, "path") and target.path in ("sine", "zag", "circle"):
                aim_x += math.cos(target.t * 0.08) * 10
            if aim_x < p.x - 4:
                dx = -1
            elif aim_x > p.x + 4:
                dx = 1
            desired_y = clamp(target.y + 200, VH - 210, VH - 64)
            if p.y < desired_y - 8:
                dy = 1
            elif p.y > desired_y + 8:
                dy = -1
        else:
            if abs(p.x - VW / 2) > 20:
                dx = -1 if p.x > VW / 2 else 1
            if p.y < VH - 110:
                dy = 1
        if p.x <= 18:
            dx = 1
        if p.x >= VW - 18:
            dx = -1
        return dx, dy, True

    def update(self, keys):
        self.stars.update()
        for pt in particles[:]:
            if not pt.update():
                particles.remove(pt)
        if self.player.alive:
            if self.demo:
                ddx, ddy, fire = self.demo_brain()
                want = self.player.update(None, ddx, ddy, fire)
            else:
                want = self.player.update(keys)
            if want:
                self.player.shoot(self.bullets)
        for b in self.bullets[:]:
            b.update()
            if not b.alive:
                self.bullets.remove(b)
        for e in self.enemies[:]:
            e.update(self.bullets, self.player if self.player.alive else None)
            if not e.alive:
                self.enemies.remove(e)
        if self.boss:
            self.boss.update(self.bullets, self.player if self.player.alive else None, self.enemies)
            if not self.boss.entering:
                self.boss_seen = True
            if not self.boss.alive:
                self.player.score += self.boss.score
                for _ in range(3):
                    self.powers.append(PowerUp(self.boss.x + random.uniform(-30, 30),
                                               self.boss.y, random.choice(POWER_TYPES)))
                self.boss = None
                self.state = "between"
                self.next_wave_in = 90
                self.wave += 1
        for pw in self.powers[:]:
            pw.update()
            if not pw.alive:
                self.powers.remove(pw)
        for b in self.bullets[:]:
            if not b.friendly:
                continue
            hit = False
            for e in self.enemies:
                if e.alive and b.rect.colliderect(e.rect):
                    b.alive = False
                    if e.hurt(b.dmg):
                        self.player.score += e.score
                        if random.random() < 0.12:
                            self.powers.append(PowerUp(e.x, e.y))
                    hit = True
                    break
            if hit:
                continue
            if self.boss and self.boss.alive and b.rect.colliderect(self.boss.rect):
                b.alive = False
                self.boss.hurt(b.dmg)
        if self.player.alive and self.player.invuln == 0:
            pr = self.player.rect.inflate(-8, -8)
            for b in self.bullets:
                if not b.friendly and b.rect.colliderect(pr):
                    b.alive = False
                    self.player.hit()
            for e in self.enemies:
                if e.rect.colliderect(pr):
                    self.player.hit()
                    e.hurt(2)
            if self.boss and self.boss.rect.inflate(-20, -10).colliderect(pr):
                self.player.hit()
        if self.player.alive:
            for pw in self.powers[:]:
                if pw.rect.colliderect(self.player.rect):
                    self.player.apply_power(pw.kind)
                    pw.alive = False
                    self.powers.remove(pw)
        if self.state == "play":
            if not self.enemies:
                self.wave_timer += 1
                if self.wave_timer > 50:
                    self.wave_timer = 0
                    self.wave += 1
                    if self.wave % 4 == 0:
                        self.state = "boss"
                        self.boss = Boss(self.wave // 4)
                    else:
                        spawn_formation(self.wave, self.enemies)
        elif self.state == "between":
            self.next_wave_in -= 1
            if self.next_wave_in <= 0:
                self.state = "play"
                spawn_formation(self.wave, self.enemies)
        if not self.player.alive:
            self.state = "gameover"

    def draw(self, surf):
        self.stars.draw(surf)
        for pt in particles:
            pt.draw(surf)
        for pw in self.powers:
            pw.draw(surf)
        for e in self.enemies:
            e.draw(surf)
        if self.boss:
            self.boss.draw(surf)
        for b in self.bullets:
            b.draw(surf)
        if self.player.alive or self.player.invuln > 0:
            self.player.draw(surf)
        lives = "INF" if self.player.unlimited else str(self.player.lives)
        txt = FONT.render(
            f"SCORE {self.player.score:07d}   LIVES {lives}   WAVE {self.wave}",
            True, (220, 230, 255))
        surf.blit(txt, (8, VH - 22))
        if self.demo:
            d = BIG.render("DEMO", True, (255, 220, 80))
            d.set_alpha(140 + int(80 * math.sin(pygame.time.get_ticks() * 0.006)))
            surf.blit(d, d.get_rect(center=(VW // 2, 36)))
            h = FONT_SM.render("PRESS SPACE / ENTER TO START", True, (200, 220, 255))
            surf.blit(h, h.get_rect(center=(VW // 2, 64)))


def is_high_score(score):
    hs = SAVE["highscores"]
    return score > 0 and (len(hs) < 10 or score > hs[-1][1])


def insert_score(name, score):
    SAVE["highscores"].append([name[:8].upper() or "ACE", int(score)])
    SAVE["highscores"] = sorted(SAVE["highscores"], key=lambda r: -r[1])[:10]
    write_save(SAVE)


def draw_high_scores(surf, tics):
    title = BIG.render("HALL OF ACES", True, (255, 210, 70))
    surf.blit(title, title.get_rect(center=(VW // 2, 70)))
    sub = FONT.render("Those who climbed the well", True, (160, 180, 220))
    surf.blit(sub, sub.get_rect(center=(VW // 2, 108)))
    y = 150
    for i, (name, score) in enumerate(SAVE["highscores"][:10], 1):
        col = (255, 230, 120) if i == 1 else (200, 220, 255)
        line = FONT.render(f"{i:2d}   {name:<8}   {score:08d}", True, col)
        surf.blit(line, line.get_rect(center=(VW // 2, y)))
        y += 32
    hint = FONT_SM.render("PRESS SPACE / ENTER TO START", True, (180, 200, 255))
    hint.set_alpha(160 + int(80 * math.sin(tics * 0.08)))
    surf.blit(hint, hint.get_rect(center=(VW // 2, VH - 28)))


def draw_name_entry(surf, initials, idx, score, tics):
    t = BIG.render("NEW HIGH SCORE", True, (255, 210, 70))
    surf.blit(t, t.get_rect(center=(VW // 2, 180)))
    s = FONT.render(f"{score:08d}", True, (255, 255, 255))
    surf.blit(s, s.get_rect(center=(VW // 2, 230)))
    prompt = FONT.render("Enter initials  -  arrows / type, Enter confirm", True, (180, 200, 230))
    surf.blit(prompt, prompt.get_rect(center=(VW // 2, 290)))
    x0 = VW // 2 - 60
    for i, ch in enumerate(initials):
        col = (255, 255, 255) if i == idx and (tics // 10) % 2 == 0 else (255, 220, 80)
        g = BIG.render(ch, True, col)
        surf.blit(g, g.get_rect(center=(x0 + i * 60, 360)))
        pygame.draw.line(surf, col, (x0 + i * 60 - 16, 390), (x0 + i * 60 + 16, 390), 2)


def main():
    global screen, win_w, win_h, particles
    mode = "story"
    attract_t = 0
    session = None
    stars_bg = StarField()
    crawl = StoryCrawl()
    initials = ["A", "A", "A"]
    init_idx = 0
    pending_score = 0
    last_geom_save = 0
    running = True
    start_music()

    while running:
        dt = clock.tick(FPS)
        attract_t += dt
        last_geom_save += dt
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.VIDEORESIZE:
                win_w, win_h = max(360, ev.w), max(480, ev.h)
                screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
                read_window_geom(win_w, win_h)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                if ev.key == pygame.K_u and session and mode == "play":
                    session.player.unlimited = not session.player.unlimited
                    if session.player.unlimited:
                        session.player.alive = True
                        if session.player.lives < 1:
                            session.player.lives = 1
                if mode == "enter":
                    if ev.key == pygame.K_LEFT:
                        init_idx = (init_idx - 1) % 3
                    elif ev.key == pygame.K_RIGHT:
                        init_idx = (init_idx + 1) % 3
                    elif ev.key in (pygame.K_UP, pygame.K_DOWN):
                        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                        cur = alphabet.find(initials[init_idx])
                        if cur < 0:
                            cur = 0
                        cur = (cur + (1 if ev.key == pygame.K_UP else -1)) % len(alphabet)
                        initials[init_idx] = alphabet[cur]
                    elif ev.key == pygame.K_BACKSPACE:
                        initials[init_idx] = "A"
                        init_idx = max(0, init_idx - 1)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        insert_score("".join(initials), pending_score)
                        mode = "story"
                        attract_t = 0
                        crawl.reset()
                        start_music()
                    elif ev.unicode and ev.unicode.isalnum():
                        initials[init_idx] = ev.unicode.upper()
                        init_idx = min(2, init_idx + 1)
                elif ev.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER):
                    if mode in ("story", "scores", "demo", "gameover"):
                        particles.clear()
                        session = Session(demo=False)
                        mode = "play"
                        stop_music()
        keys = pygame.key.get_pressed()
        if mode == "story":
            stars_bg.update()
            crawl.update()
            if crawl.finished():
                mode = "scores"
                attract_t = 0
        elif mode == "scores":
            stars_bg.update()
            if attract_t >= SCORE_SCREEN_MS:
                particles.clear()
                session = Session(demo=True, demo_upgraded=(random.random() < 0.5))
                mode = "demo"
                attract_t = 0
                stop_music()
        elif mode == "demo":
            if session:
                session.update(None)
                if session.boss_seen or session.state == "gameover":
                    particles.clear()
                    session = None
                    mode = "story"
                    attract_t = 0
                    crawl.reset()
                    start_music()
        elif mode == "play":
            if session:
                session.update(keys)
                if session.state == "gameover":
                    pending_score = session.player.score
                    if is_high_score(pending_score):
                        mode = "enter"
                        initials[:] = ["A", "A", "A"]
                        init_idx = 0
                    else:
                        mode = "story"
                        attract_t = 0
                        crawl.reset()
                        start_music()
                    session = None
                    particles.clear()
        if mode == "story":
            stars_bg.draw(game_surf)
            crawl.draw(game_surf)
        elif mode == "scores":
            stars_bg.draw(game_surf)
            draw_high_scores(game_surf, pygame.time.get_ticks() // 16)
        elif mode == "enter":
            stars_bg.update()
            stars_bg.draw(game_surf)
            draw_name_entry(game_surf, initials, init_idx, pending_score, pygame.time.get_ticks() // 16)
        elif mode in ("demo", "play") and session:
            session.draw(game_surf)
        else:
            stars_bg.draw(game_surf)
        letterbox_blit(screen, game_surf)
        pygame.display.flip()
        if last_geom_save > 1500:
            last_geom_save = 0
            read_window_geom(win_w, win_h)
    stop_music()
    read_window_geom(win_w, win_h)
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()