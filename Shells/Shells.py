import json
import math
import os
import random
import sys
import numpy as np
import pygame

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
W, H = 1280, 720
FPS = 60
GRAVITY = 520.0
PLAYER_FIRE_COOLDOWN = 1.0 / 3.0
ENEMY_FIRE_INTERVAL = 1.0 * 1.4
PLAYER_MAX_HP = 10
WIN_RATIO_START = 0.50
WIN_RATIO_STEP = 0.10
WIN_RATIO_MAX = 1.00
ACCURACY_STEP = 0.05
GROUND_Y = H - 70
HITS_TO_DROP = 5
ENEMY_CANNONS_MIN = 2
ENEMY_CANNONS_MAX = 5
ENEMY_HIT_EVERY = 3.5 * 2.0
ENEMY_HIT_CHANCE = 1.0 / ENEMY_HIT_EVERY
FRIENDLY_STOP = 3
FIRES_PER_HIT = 4
PLAYER_BOMBS = 3
DEMO_BOMBS = 6
TOPPLE_CHANCE = 0.10
IDLE_BEFORE_DEMO = 10.0
SR = 22050
MIN_WIN_W, MIN_WIN_H = 640, 360

POWER_LEVELS = {1: 430.0, 2: 640.0, 3: 920.0}

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shells_window.json")

def load_window_geom():
    data = {"x": 80, "y": 60, "w": W, "h": H}
    try:
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        for k in data:
            if k in saved:
                data[k] = int(saved[k])
    except Exception:
        pass
    data["w"] = max(MIN_WIN_W, data["w"])
    data["h"] = max(MIN_WIN_H, data["h"])
    return data

def save_window_geom():
    try:
        ww, hh = screen.get_size()
        try:
            xx, yy = pygame.display.get_window_position()
        except Exception:
            xx, yy = window_geom["x"], window_geom["y"]
        with open(CONFIG_PATH, "w") as f:
            json.dump({"x": int(xx), "y": int(yy), "w": int(ww), "h": int(hh)}, f)
    except Exception:
        pass

window_geom = load_window_geom()
os.environ["SDL_VIDEO_WINDOW_POS"] = "{0},{1}".format(window_geom["x"], window_geom["y"])

pygame.init()
pygame.mixer.init(frequency=SR, size=-16, channels=2)
pygame.mixer.set_num_channels(24)
screen = pygame.display.set_mode((window_geom["w"], window_geom["h"]), pygame.RESIZABLE)
pygame.display.set_caption("Hill Cannon — Level the City")
game = pygame.Surface((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 20)
bigfont = pygame.font.SysFont("consolas", 48, bold=True)

round_num = 1
demo_mode = False
idle_time = 0.0
paused = False
unlimited_bombs = False
player_exploded = False
demo_focus = None
demo_shots_stale = 0
demo_loft = 0

def current_win_ratio():
    return min(WIN_RATIO_MAX, WIN_RATIO_START + WIN_RATIO_STEP * (round_num - 1))

def enemy_acc_mult():
    return 1.0 + ACCURACY_STEP * (round_num - 1)

def accuracy_for(b):
    s = float(max(1, b.stories))
    if s >= 40:
        m = 0.98
    elif s >= 20:
        m = 0.50 + (0.98 - 0.50) * (s - 20.0) / 20.0
    elif s >= 10:
        m = 0.25 + (0.50 - 0.25) * (s - 10.0) / 10.0
    else:
        m = 0.12 + (0.25 - 0.12) * (s - 1.0) / 9.0
    return min(1.0, ENEMY_HIT_CHANCE * m * enemy_acc_mult())

def _env(n, attack=0.004):
    e = np.ones(n, dtype=np.float32)
    a = max(1, int(SR * attack))
    e[:a] *= np.linspace(0.0, 1.0, a)
    e *= np.linspace(1.0, 0.0, n) ** 1.6
    return e

def _to_sound(wave, vol=0.5):
    wave = np.clip(wave * vol, -1.0, 1.0)
    pcm = (wave * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((pcm, pcm)))

def make_cannon(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(280, 420)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    boom = np.sin(2 * np.pi * rng.uniform(48, 72) * t)
    boom += 0.55 * np.sin(2 * np.pi * rng.uniform(28, 42) * t)
    boom += 0.25 * np.sin(2 * np.pi * rng.uniform(90, 130) * t)
    noise = rng.uniform(-1, 1, n)
    crack_n = max(2, int(SR * rng.uniform(0.025, 0.045)))
    crack = np.zeros(n)
    crack[:crack_n] = rng.uniform(-1, 1, crack_n) * np.linspace(1, 0, crack_n)
    ring = np.sin(2 * np.pi * rng.uniform(380, 560) * t) * np.exp(-t * rng.uniform(8, 14))
    body = boom * _env(n, 0.003) + noise * _env(n, 0.002) * 0.45 + crack * 0.9 + ring * 0.12
    return _to_sound(body, rng.uniform(0.42, 0.55))

def make_explosion(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(520, 820)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    rumble = np.sin(2 * np.pi * rng.uniform(32, 52) * t + rng.uniform(0, 3))
    rumble += 0.7 * np.sin(2 * np.pi * rng.uniform(18, 28) * t)
    rumble += 0.35 * np.sin(2 * np.pi * rng.uniform(70, 110) * t)
    noise = rng.normal(0, 1, n)
    crack_n = int(SR * rng.uniform(0.04, 0.07))
    crack = np.zeros(n)
    crack[:crack_n] = rng.normal(0, 1, crack_n) * np.linspace(1, 0, crack_n) ** 0.5
    debris = rng.normal(0, 1, n) * np.exp(-t * rng.uniform(3.5, 6.0))
    body = rumble * _env(n, 0.006) * 0.85 + noise * _env(n, 0.004) * 0.5 + crack * 0.8 + debris * 0.25
    return _to_sound(body, rng.uniform(0.48, 0.62))

def make_rumble(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(900, 1400)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    bass = np.sin(2 * np.pi * rng.uniform(16, 28) * t) * np.exp(-t * 1.6)
    mid = np.sin(2 * np.pi * rng.uniform(40, 70) * t) * np.exp(-t * 2.4)
    grind = rng.normal(0, 1, n) * np.exp(-t * 1.8)
    return _to_sound(bass * 0.8 + mid * 0.45 + grind * 0.55, 0.62)

def make_collapse(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(700, 1100)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    grind = rng.normal(0, 1, n) * np.exp(-t * 2.2)
    thud = np.sin(2 * np.pi * rng.uniform(24, 40) * t) * np.exp(-t * 3.0)
    return _to_sound(grind * 0.7 + thud * 0.6, 0.5)

def make_crack(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(70, 130)
    n = int(SR * ms / 1000.0)
    noise = rng.normal(0, 1, n) * _env(n, 0.001)
    snap = np.sin(2 * np.pi * rng.uniform(180, 320) * np.linspace(0, ms / 1000.0, n, False))
    return _to_sound(noise * 0.7 + snap * 0.3, 0.35)

def make_arc(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(220, 420)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    buzz = np.sign(np.sin(2 * np.pi * rng.uniform(900, 1600) * t))
    buzz *= 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * rng.uniform(40, 90) * t))
    hiss = rng.normal(0, 1, n)
    pops = np.zeros(n)
    for _ in range(int(rng.integers(4, 10))):
        i = int(rng.random() * (n - 80))
        pops[i:i + 40] += rng.normal(0, 1, 40) * np.linspace(1, 0, 40)
    body = (buzz * 0.35 + hiss * 0.45 + pops * 0.7) * _env(n, 0.002)
    return _to_sound(body, rng.uniform(0.28, 0.4))

def make_hitme(seed=None):
    rng = np.random.default_rng(seed)
    n = int(SR * 0.38)
    t = np.linspace(0, 0.38, n, False)
    body = np.sin(2 * np.pi * 36 * t) * _env(n) + rng.normal(0, 1, n) * _env(n, 0.002) * 0.6
    return _to_sound(body, 0.55)

def make_fireball(seed=None):
    rng = np.random.default_rng(seed)
    ms = rng.uniform(500, 750)
    n = int(SR * ms / 1000.0)
    t = np.linspace(0, ms / 1000.0, n, False)
    whoosh = rng.normal(0, 1, n) * np.exp(-t * 2.8)
    bass = np.sin(2 * np.pi * rng.uniform(40, 60) * t) * np.exp(-t * 4)
    return _to_sound(whoosh * 0.65 + bass * 0.5, 0.5)

def make_airraid():
    dur = 3.2
    n = int(SR * dur)
    t = np.linspace(0, dur, n, False)
    sweep = 0.5 + 0.5 * np.sin(2 * np.pi * t / dur)
    freq = 420 + 380 * sweep
    phase = np.cumsum(freq) / SR * 2 * np.pi
    wave = 0.55 * np.sin(phase) + 0.25 * np.sin(phase * 2)
    fade = int(SR * 0.04)
    wave[:fade] *= np.linspace(0, 1, fade)
    wave[-fade:] *= np.linspace(1, 0, fade)
    return _to_sound(wave, 0.32)

def bank(factory, n=6):
    return [factory(seed=1000 + i * 17 + random.randint(0, 99)) for i in range(n)]

SND_CANNON = bank(make_cannon, 7)
SND_BOOM = bank(make_explosion, 7)
SND_COLLAPSE = bank(make_collapse, 5)
SND_RUMBLE = bank(make_rumble, 5)
SND_CRACK = bank(make_crack, 6)
SND_ARC = bank(make_arc, 7)
SND_HIT_ME = bank(make_hitme, 4)
SND_FIREBALL = bank(make_fireball, 5)
SND_AIRRAID = make_airraid()
SND_WIN = make_cannon(3)
SND_LOSE = make_explosion(9)
SIREN_CH = pygame.mixer.Channel(7)

def play(bank_or_sound, vol=None):
    snd = random.choice(bank_or_sound) if isinstance(bank_or_sound, list) else bank_or_sound
    snd.set_volume(vol if vol is not None else random.uniform(0.78, 1.0))
    snd.play()

def start_airraid():
    SND_AIRRAID.set_volume(0.34)
    SIREN_CH.play(SND_AIRRAID, loops=-1)

def stop_airraid():
    SIREN_CH.stop()

class Particle:
    def __init__(self, x, y, vx, vy, life, color, size=3, gravity=True):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = life
        self.max = life
        self.color = color
        self.size = size
        self.gravity = gravity

    def update(self, dt):
        self.vy += (GRAVITY * 0.55 * dt) if self.gravity else -40 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, s):
        a = max(0.0, self.life / self.max)
        col = tuple(max(0, min(255, int(c * (0.4 + 0.6 * a)))) for c in self.color)
        pygame.draw.circle(s, col, (int(self.x), int(self.y)), max(1, int(self.size * a)))

class Ember:
    def __init__(self, building, lx, ly, life):
        self.b = building
        self.lx, self.ly = lx, ly
        self.life = life

    def update(self, dt):
        self.life -= dt
        return self.life > 0 and self.b.alive

    def pos(self):
        return (self.b.x + self.lx, self.b.y + self.b.fall + self.ly)

class Bolt:
    def __init__(self, pts, life=0.18):
        self.pts = pts
        self.life = life
        self.max = life

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, s):
        a = max(0.0, self.life / self.max)
        col = (int(180 * a + 70), int(200 * a + 40), int(255 * a))
        if len(self.pts) >= 2:
            pygame.draw.lines(s, col, False, self.pts, 2)
            pygame.draw.lines(s, (255, 255, 255), False, self.pts, 1)

class Chunk:
    def __init__(self, x, y, w, h, color, vx, vy, spin):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.color = color
        self.vx, self.vy = vx, vy
        self.angle = 0.0
        self.spin = spin
        self.life = random.uniform(1.8, 3.2)
        self.settled = False

    def update(self, dt):
        if not self.settled:
            self.vy += GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.angle += self.spin * dt
            self.vx *= 0.995
            if self.y + self.h >= GROUND_Y:
                self.y = GROUND_Y - self.h
                self.vy *= -0.18
                self.vx *= 0.55
                self.spin *= 0.4
                if abs(self.vy) < 40:
                    self.settled = True
                    self.vy = 0
        self.life -= dt * (0.25 if self.settled else 1.0)
        if random.random() < 0.4:
            particles.append(Particle(
                self.x + random.uniform(0, self.w), self.y + random.uniform(0, self.h),
                random.uniform(-50, 50), random.uniform(-110, -10),
                random.uniform(0.4, 1.0),
                random.choice([(90, 90, 90), (160, 150, 130), (50, 50, 50)]),
                random.randint(3, 8), gravity=False
            ))
        return self.life > 0 or not self.settled

    def draw(self, s):
        surf = pygame.Surface((max(2, int(self.w)), max(2, int(self.h))), pygame.SRCALPHA)
        surf.fill(self.color + (230,))
        rot = pygame.transform.rotate(surf, math.degrees(self.angle))
        s.blit(rot, rot.get_rect(center=(int(self.x + self.w / 2), int(self.y + self.h / 2))))

particles = []
embers = []
bolts = []
chunks = []

def burst(x, y, n=18, color=(180, 160, 120), speed=180, life=0.7, gravity=True):
    for _ in range(n):
        ang = random.uniform(0, math.tau)
        sp = random.uniform(40, speed)
        particles.append(Particle(
            x, y, math.cos(ang) * sp, math.sin(ang) * sp - (80 if gravity else 20),
            random.uniform(life * 0.5, life), color, random.randint(2, 6), gravity
        ))

def fire_burst(x, y, n=40):
    cols = [(255, 220, 80), (255, 140, 30), (230, 50, 10), (80, 80, 80)]
    for _ in range(n):
        ang = random.uniform(0, math.tau)
        sp = random.uniform(60, 320)
        c = random.choice(cols)
        particles.append(Particle(
            x, y, math.cos(ang) * sp, math.sin(ang) * sp,
            random.uniform(0.5, 1.3), c, random.randint(3, 8), gravity=(c[0] < 120)
        ))

def jagged_bolt(x0, y0, x1, y1, segs=8):
    pts = [(x0, y0)]
    for i in range(1, segs):
        t = i / float(segs)
        pts.append((x0 + (x1 - x0) * t + random.uniform(-10, 10),
                    y0 + (y1 - y0) * t + random.uniform(-8, 8)))
    pts.append((x1, y1))
    return pts

def explode_player_cannon():
    global player_exploded
    if player_exploded:
        return
    player_exploded = True
    hx, hy = hill_peak
    play(SND_RUMBLE)
    play(SND_FIREBALL)
    play(SND_LOSE)
    fire_burst(hx, hy, 70)
    burst(hx, hy, 40, (255, 160, 40), 360, 1.2, False)
    for _ in range(10):
        chunks.append(Chunk(
            hx + random.uniform(-12, 12), hy + random.uniform(-8, 8),
            random.randint(8, 18), random.randint(6, 14),
            random.choice([(50, 48, 44), (80, 78, 70), (30, 30, 28)]),
            random.uniform(-180, 180), random.uniform(-220, -40),
            random.uniform(-3, 3)
        ))

ON, OFF, DIM, FLICK = 0, 1, 2, 3

class WinLite:
    __slots__ = ("state", "dim")
    def __init__(self):
        self.state = ON if random.random() < 0.72 else OFF
        self.dim = 1.0

class Building:
    def __init__(self, x, w, stories, color):
        self.x, self.w, self.stories = x, w, stories
        self.story_h = 14
        self.h = stories * self.story_h
        self.y = GROUND_Y - self.h
        self.color = color
        self.hits = 0
        self.fall = 0.0
        self.fall_speed = 0.0
        self.alive = True
        self.has_gun = False
        self.has_siren = False
        self.counted_double = False
        self.gun_cd = random.uniform(0.2, 1.0)
        self.gun_angle = math.pi
        self.gun_target_angle = math.pi
        self.force_level = 2
        self.friendly_hits = 0
        self.held = False
        self.fiery = False
        self.cols = max(1, self.w // 12)
        self.windows = [[WinLite() for _ in range(self.cols)] for _ in range(stories)]
        self.arcing = False
        self.arc_cd = 0.0
        self.arc_fires = 0

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y + self.fall), self.w, int(max(1, self.h - self.fall)))

    def roof_xy(self):
        return (self.x + self.w / 2.0, self.y + self.fall + 6)

    def muzzle(self):
        cx, cy = self.roof_xy()
        return (cx + math.cos(self.gun_angle) * 18, cy + math.sin(self.gun_angle) * 18 - 8)

    def gun_rect(self):
        cx, cy = self.roof_xy()
        return pygame.Rect(int(cx - 10), int(cy - 16), 20, 22)

    def siren_rect(self):
        cx, cy = self.roof_xy()
        return pygame.Rect(int(cx - 11), int(cy - 26), 22, 24)

    def aim_point(self):
        if self.has_siren:
            cx, cy = self.roof_xy()
            return (cx, cy - 16)
        if self.has_gun:
            cx, cy = self.roof_xy()
            return (cx, cy - 8)
        return (self.x + self.w / 2.0, self.y + min(40, self.h * 0.25))

    def hit_row_col(self, hx, hy):
        r = self.rect
        row = int((hy - r.y) / max(1, self.story_h))
        col = int((hx - r.x) / max(1, 12))
        return max(0, min(self.stories - 1, row)), max(0, min(self.cols - 1, col))

    def blackout_all(self):
        for row in self.windows:
            for w in row:
                w.state, w.dim = OFF, 0.0

    def blackout_floors(self, start_row, n):
        for r in range(start_row, min(self.stories, start_row + n)):
            for w in self.windows[r]:
                w.state, w.dim = OFF, 0.0

    def damage_lights(self, hx, hy):
        row, col = self.hit_row_col(hx, hy)
        remain = HITS_TO_DROP - self.hits
        all_out_p = 0.08
        if remain <= 2:
            all_out_p = 0.38
        if remain <= 1:
            all_out_p = 0.55
        if random.random() < all_out_p:
            self.blackout_all()
            return
        if random.random() < 0.35:
            self.blackout_floors(max(0, row - 1), random.randint(2, 5))
        for dr in range(-3, 4):
            for dc in range(-3, 4):
                rr, cc = row + dr, col + dc
                if 0 <= rr < self.stories and 0 <= cc < self.cols:
                    dist = math.hypot(dr, dc)
                    w = self.windows[rr][cc]
                    if dist <= 1.6 and random.random() < 0.75:
                        w.state, w.dim = OFF, 0.0
                    elif random.random() < 0.5:
                        if random.random() < 0.4:
                            w.state, w.dim = FLICK, random.uniform(0.25, 0.75)
                        else:
                            w.state, w.dim = DIM, random.uniform(0.25, 0.75)

    def maybe_start_arc(self):
        if self.hits >= 1 and self.alive and random.random() < 0.22:
            self.arcing = True
            self.arc_cd = random.uniform(0.4, 1.2)

    def smash_neighbors(self, direction, power=3):
        ordered = sorted(buildings, key=lambda b: b.x + b.w * 0.5)
        try:
            idx = ordered.index(self)
        except ValueError:
            return
        for j, b in enumerate(ordered):
            if b is self or not b.alive:
                continue
            steps = j - idx
            if steps * direction <= 0:
                continue
            dist = abs(steps)
            hx = b.x + b.w / 2.0
            hy = b.y + b.h * random.uniform(0.25, 0.65)
            if dist == 1:
                hits = max(3, power)
                for _ in range(hits):
                    if not b.alive:
                        break
                    b.hit_body(hx, hy + random.uniform(-20, 20))
                if b.alive and power >= 5 and random.random() < 0.4:
                    b.begin_destroy(topple=True, direction=direction)
            elif dist in (2, 3):
                if random.random() < 0.55:
                    b.add_arc_fire(hx, hy)
                    b.add_arc_fire(hx + random.uniform(-8, 8), hy + random.uniform(-12, 12))
                else:
                    b.hit_body(hx, hy)

    def spawn_topple_chunks(self, direction):
        slab = max(16, self.story_h * 2)
        y = self.y
        while y < GROUND_Y:
            hh = min(slab, GROUND_Y - y)
            if hh < 6:
                break
            height_factor = 1.0 - (y - self.y) / max(1, self.h)
            vx = direction * random.uniform(90, 210) * (0.35 + height_factor)
            vy = random.uniform(-100, 30) - height_factor * 50
            spin = direction * random.uniform(0.5, 2.2) * (0.4 + height_factor)
            shade = tuple(max(0, min(255, c + random.randint(-18, 12))) for c in self.color)
            chunks.append(Chunk(self.x + random.uniform(-6, 6), y, self.w * random.uniform(0.7, 1.0), hh, shade, vx, vy, spin))
            y += hh
        cx = self.x + self.w / 2
        for _ in range(50 + self.stories):
            burst(cx + random.uniform(-self.w, self.w), GROUND_Y - 10, 1,
                  random.choice([(80, 80, 80), (160, 150, 130), (40, 40, 40)]), 240, 1.5, False)
        fire_burst(cx, self.y + self.h * 0.3, 22)

    def begin_destroy(self, cause="hits", hx=None, hy=None, topple=False, direction=None):
        global demo_shots_stale
        if not self.alive:
            return
        demo_shots_stale = 0
        was_siren = self.has_siren
        if direction is None:
            if hx is not None:
                direction = -1 if hx < self.x + self.w / 2 else 1
            else:
                left = sum(1 for b in buildings if b.alive and b.x < self.x)
                right = sum(1 for b in buildings if b.alive and b.x > self.x)
                direction = 1 if right >= left else -1
        self.alive = False
        self.hits = HITS_TO_DROP
        self.arcing = False
        self.has_gun = False
        if was_siren:
            self.has_siren = False
            stop_airraid()
        cx = self.x + self.w / 2.0
        cy = hy if hy is not None else (self.y + self.h * 0.35)
        if hx is None:
            hx = cx
        if topple:
            play(SND_RUMBLE)
            play(SND_BOOM)
            self.spawn_topple_chunks(direction)
            smash_pow = 5 if cause == "bomb" else 3
            if was_siren:
                smash_pow *= 2
            self.smash_neighbors(direction, power=smash_pow)
            self.fall = self.h
        else:
            fiery = (cause in ("cannon", "bomb", "siren")) or (random.random() < 0.25)
            self.fiery = fiery
            if fiery:
                play(SND_FIREBALL)
                fire_burst(hx, cy, 55)
            else:
                play(SND_COLLAPSE)
                burst(cx, GROUND_Y - 8, 28, (160, 140, 110), 260, 1.1)
            self.fall_speed = 80

    def destroy(self, cause="hits", hx=None, hy=None):
        topple = cause in ("bomb", "siren") or random.random() < TOPPLE_CHANCE
        self.begin_destroy(cause, hx, hy, topple=topple)

    def apply_shell_hit(self):
        self.hits += 1
        if self.hits >= HITS_TO_DROP:
            self.destroy("hits")

    def add_arc_fire(self, hx, hy):
        self.arc_fires += 1
        if random.random() < 0.8:
            lx = max(4, min(self.w - 4, hx - self.x))
            ly = max(6, min(self.h - 8, hy - self.y))
            embers.append(Ember(self, lx, ly, random.uniform(5.0, 10.0)))
        if self.arc_fires >= FIRES_PER_HIT:
            self.arc_fires = 0
            self.apply_shell_hit()
            self.damage_lights(hx, hy)
            self.maybe_start_arc()

    def hit_body(self, hx, hy):
        if not self.alive:
            return
        play(SND_CRACK)
        burst(hx, hy, 10, (90, 90, 90), 120, 0.4)
        self.damage_lights(hx, hy)
        if random.random() < 0.55:
            lx = max(4, min(self.w - 4, hx - self.x + random.uniform(-8, 8)))
            ly = max(6, min(self.h - 8, hy - self.y + random.uniform(-10, 10)))
            embers.append(Ember(self, lx, ly, random.uniform(5.0, 10.0)))
        self.apply_shell_hit()
        self.maybe_start_arc()

    def hit_cannon(self, hx, hy):
        if not self.alive:
            return
        play(SND_BOOM)
        self.destroy("cannon", hx, hy)

    def hit_bomb(self, hx, hy):
        if not self.alive:
            return
        play(SND_RUMBLE)
        play(SND_FIREBALL)
        fire_burst(hx, hy, 48)
        direction = -1 if hx < self.x + self.w / 2 else 1
        self.begin_destroy("bomb", hx, hy, topple=True, direction=direction)

    def hit_siren(self, hx, hy):
        if not self.alive:
            return
        play(SND_RUMBLE)
        play(SND_BOOM)
        direction = -1 if hx < self.x + self.w / 2 else 1
        self.begin_destroy("siren", hx, hy, topple=True, direction=direction)

    def fire_arc(self):
        nbrs = [b for b in buildings if b is not self and b.alive
                and abs((b.x + b.w / 2) - (self.x + self.w / 2)) <= (self.w + b.w) * 0.5 + 36]
        if not nbrs:
            return
        tgt = random.choice(nbrs)
        x0 = self.x + random.uniform(4, max(5, self.w - 4))
        y0 = self.y + self.fall + random.uniform(10, max(12, self.h * 0.6))
        x1 = tgt.x + random.uniform(4, max(5, tgt.w - 4))
        y1 = tgt.y + tgt.fall + random.uniform(8, max(10, tgt.h * 0.5))
        bolts.append(Bolt(jagged_bolt(x0, y0, x1, y1)))
        play(SND_ARC)
        if random.random() < 0.72:
            tgt.add_arc_fire(x1, y1)
            fire_burst(x1, y1, 8)

    def update(self, dt):
        if self.has_gun and self.alive:
            da = (self.gun_target_angle - self.gun_angle + math.pi) % math.tau - math.pi
            self.gun_angle += max(-2.8 * dt, min(2.8 * dt, da))
            self.gun_angle %= math.tau
        if self.arcing and self.alive:
            self.arc_cd -= dt
            if self.arc_cd <= 0:
                self.fire_arc()
                self.arc_cd = random.uniform(3.0, 5.0)
        if (self.hits >= HITS_TO_DROP or not self.alive) and self.fall < self.h:
            self.fall_speed += 420 * dt
            self.fall += self.fall_speed * dt
            if self.fall >= self.h:
                self.fall = self.h
                self.alive = False
                self.has_gun = False
                self.arcing = False
                if self.has_siren:
                    self.has_siren = False
                    stop_airraid()

    def draw(self, s):
        if self.fall >= self.h:
            return
        r = self.rect
        if r.h <= 1:
            return
        pygame.draw.rect(s, self.color, r)
        shade = tuple(max(0, c - 30) for c in self.color)
        pygame.draw.rect(s, shade, (r.x + r.w - 6, r.y, 6, r.h))
        for row_i, row in enumerate(self.windows):
            wy = r.y + 4 + row_i * self.story_h
            if wy < r.y or wy > r.bottom - 8:
                continue
            for col_i, win in enumerate(row):
                wx = r.x + 4 + col_i * 12
                if wx + 6 >= r.right - 4:
                    continue
                if win.state == OFF:
                    col = (28, 32, 40)
                elif win.state == FLICK:
                    flick = 0.25 + 0.75 * abs(math.sin(pygame.time.get_ticks() * 0.02 + row_i + col_i))
                    d = win.dim * flick
                    col = (int(220 * d), int(210 * d), int(140 * d))
                else:
                    d = win.dim if win.state == DIM else 1.0
                    col = (int(220 * d), int(210 * d), int(140 * d))
                pygame.draw.rect(s, col, (wx, wy, 6, 8))
        if 0 < self.hits < HITS_TO_DROP and self.alive:
            for k in range(self.hits):
                y0 = r.y + 8 + k * 10
                pygame.draw.line(s, (40, 30, 20), (r.x + 3, y0), (r.right - 4, y0 + 12), 2)
        if self.has_siren and self.alive:
            cx, cy = self.roof_xy()
            pulse = 0.55 + 0.45 * abs(math.sin(pygame.time.get_ticks() * 0.012))
            pygame.draw.rect(s, (50, 20, 20), (int(cx - 7), int(cy - 8), 14, 10))
            pygame.draw.circle(s, (int(255 * pulse), 30, 20), (int(cx), int(cy - 16)), 8)
            pygame.draw.circle(s, (255, 220, 180), (int(cx), int(cy - 16)), 3)
        if self.has_gun and self.alive:
            cx, cy = self.roof_xy()
            pygame.draw.circle(s, (40, 40, 44), (int(cx), int(cy - 4)), 8)
            mx, my = self.muzzle()
            pygame.draw.line(s, (22, 22, 24), (cx, cy - 6), (mx, my), 6)
            pygame.draw.circle(s, (190, 170, 70), (int(mx), int(my)), 3)

class Shell:
    def __init__(self, x, y, vx, vy, friendly=True, owner=None, bomb=False):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.friendly, self.owner, self.bomb = friendly, owner, bomb
        self.alive = True
        self.trail = []

    def update(self, dt):
        self.vy += GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.trail.append((self.x, self.y))
        if len(self.trail) > 14:
            self.trail.pop(0)
        if self.bomb and random.random() < 0.6:
            particles.append(Particle(
                self.x, self.y, random.uniform(-20, 20), random.uniform(-30, 10),
                0.35, random.choice([(80, 255, 70), (255, 255, 120), (40, 180, 40)]),
                random.randint(2, 4), gravity=False
            ))
        if self.x < -40 or self.x > W + 40 or self.y > H + 40:
            self.alive = False

    def draw(self, s):
        if self.bomb:
            pulse = 0.65 + 0.35 * abs(math.sin(pygame.time.get_ticks() * 0.02))
            for i, (tx, ty) in enumerate(self.trail):
                pygame.draw.circle(s, (40, int(180 * i / max(1, len(self.trail))), 30), (int(tx), int(ty)), 2 + i // 3)
            pygame.draw.circle(s, (30, 80, 20), (int(self.x), int(self.y)), 12)
            pygame.draw.circle(s, (80, int(255 * pulse), 40), (int(self.x), int(self.y)), 8)
            pygame.draw.circle(s, (230, 255, 140), (int(self.x), int(self.y)), 4)
            return
        col = (255, 180, 60) if self.friendly else (255, 80, 80)
        core = (255, 240, 180) if self.friendly else (255, 140, 140)
        for i, (tx, ty) in enumerate(self.trail):
            pygame.draw.circle(s, col, (int(tx), int(ty)), max(1, i // 3))
        pygame.draw.circle(s, core, (int(self.x), int(self.y)), 4)

def make_city():
    buildings = []
    x = 210
    palette = [(92, 98, 120), (70, 86, 110), (110, 100, 90), (80, 90, 80), (100, 80, 90), (60, 70, 90)]
    while x < W - 30:
        w = random.randint(22, 48)
        stories = random.randint(1, 40)
        buildings.append(Building(x, w, stories, random.choice(palette)))
        x += w + random.randint(4, 14)
    tall = [b for b in buildings if b.stories >= 12] or buildings
    random.choice(tall).has_siren = True
    start_airraid()
    return buildings

buildings = []
shells = []
hill_peak = (90, GROUND_Y - 210)
cannon_angle = -0.55
force_level = 2
player_hp = PLAYER_MAX_HP
player_cd = 0.0
bombs_left = PLAYER_BOMBS
game_over = False
won = False
flash = 0.0

def standing():
    return [b for b in buildings if b.alive and b.fall < b.h * 0.2]

def destroyed_ratio():
    if not buildings:
        return 0.0
    pts = 0.0
    for b in buildings:
        if (not b.alive) or b.fall >= b.h:
            pts += 2.0 if b.counted_double else 1.0
    return pts / float(len(buildings))

def target_cannon_count():
    wr = current_win_ratio() or 0.50
    r = min(1.0, destroyed_ratio() / wr)
    return int(round(ENEMY_CANNONS_MIN + (ENEMY_CANNONS_MAX - ENEMY_CANNONS_MIN) * r))

def ensure_cannons():
    alive = standing()
    current = [b for b in alive if b.has_gun]
    need = target_cannon_count() - len(current)
    if need <= 0:
        return
    candidates = [b for b in alive if not b.has_gun]
    candidates.sort(key=lambda b: b.h, reverse=True)
    for b in candidates[:need]:
        b.has_gun = True
        b.gun_cd = random.uniform(4.0, 8.0)
        b.gun_angle = math.pi
        b.gun_target_angle = math.pi
        b.force_level = random.randint(1, 3)
        b.friendly_hits = 0
        b.held = False

def aims_at_player(ang, origin):
    px, py = math.cos(ang), math.sin(ang)
    dx, dy = hill_peak[0] - origin[0], hill_peak[1] - origin[1]
    mag = math.hypot(dx, dy) or 1.0
    return (px * dx + py * dy) / mag > 0.05

def trajectory_result(ox, oy, vx, vy, ignore, max_t=3.2):
    x, y, dt, t = ox, oy, 1.0 / 90.0, 0.0
    hx, hy = hill_peak
    while t < max_t:
        vy += GRAVITY * dt
        x += vx * dt
        y += vy * dt
        t += dt
        if (x - hx) ** 2 + (y - hy) ** 2 < 36 ** 2:
            return "player"
        if y >= GROUND_Y or x < -20 or x > W + 20:
            return "miss"
        for bld in buildings:
            if bld is ignore or not bld.alive:
                continue
            if bld.rect.collidepoint(x, y):
                return "city"
    return "miss"

def solutions_for(b):
    cx, cy = b.roof_xy()
    tx, ty = hill_peak
    found = []
    for force in (1, 2, 3):
        spd = POWER_LEVELS[force]
        for tflight in (0.45, 0.7, 1.0, 1.35, 1.8, 2.3):
            dx, dy = tx - cx, ty - (cy - 8)
            vx, vy = dx / tflight, (dy - 0.5 * GRAVITY * tflight * tflight) / tflight
            need = math.hypot(vx, vy)
            if abs(need - spd) > 140:
                continue
            scale = spd / max(1.0, need)
            vx, vy = vx * scale, vy * scale
            ang = math.atan2(vy, vx) % math.tau
            if not aims_at_player(ang, (cx, cy)):
                continue
            ox = cx + math.cos(ang) * 18
            oy = cy + math.sin(ang) * 18 - 8
            found.append((trajectory_result(ox, oy, vx, vy, b), force, ang, vx, vy))
        for deg in range(0, 360, 12):
            ang = math.radians(deg)
            if not aims_at_player(ang, (cx, cy)):
                continue
            vx, vy = math.cos(ang) * spd, math.sin(ang) * spd
            ox = cx + math.cos(ang) * 18
            oy = cy + math.sin(ang) * 18 - 8
            found.append((trajectory_result(ox, oy, vx, vy, b), force, ang, vx, vy))
    return found

def best_clear_shot(b):
    opts = solutions_for(b)
    hits = [o for o in opts if o[0] == "player"]
    clear = [o for o in opts if o[0] != "city"]
    if hits:
        return min(hits, key=lambda o: abs(o[1] - 2))
    if clear:
        return clear[0]
    if opts:
        return min(opts, key=lambda o: o[4])
    cx, cy = b.roof_xy()
    ang = math.atan2(hill_peak[1] - cy, hill_peak[0] - cx) % math.tau
    return ("miss", 2, ang, math.cos(ang) * POWER_LEVELS[2], math.sin(ang) * POWER_LEVELS[2])

def note_friendly_hit(owner):
    if owner is None or not owner.has_gun:
        return
    owner.friendly_hits += 1
    if owner.friendly_hits >= FRIENDLY_STOP:
        owner.held = True

def aim_and_maybe_fire(b):
    shot = best_clear_shot(b)
    res, force, ang, vx, vy = shot
    if not aims_at_player(ang, b.roof_xy()):
        ang = math.atan2(hill_peak[1] - b.roof_xy()[1], hill_peak[0] - b.roof_xy()[0]) % math.tau
        b.gun_target_angle = ang
        return
    b.force_level = force
    b.gun_target_angle = ang
    if res == "city":
        return
    da = (ang - b.gun_angle + math.pi) % math.tau - math.pi
    if abs(da) > 0.14:
        return
    if b.held and res != "player":
        return
    if b.held and res == "player":
        b.held = False
        b.friendly_hits = 0
    accurate = random.random() < accuracy_for(b)
    if accurate and res == "player":
        fvx, fvy = vx, vy
    else:
        jitter = random.uniform(-0.35, 0.35)
        fang = ang + jitter
        if not aims_at_player(fang, b.roof_xy()):
            fang = ang
        spd = POWER_LEVELS[force] * random.uniform(0.85, 1.12)
        fvx, fvy = math.cos(fang) * spd, math.sin(fang) * spd
        if trajectory_result(*b.muzzle(), fvx, fvy, b) == "city":
            return
    ox, oy = b.muzzle()
    shells.append(Shell(ox, oy, fvx, fvy, False, owner=b))
    play(SND_CANNON, random.uniform(0.45, 0.7))

def player_muzzle():
    return (
        hill_peak[0] + math.cos(cannon_angle) * 42,
        hill_peak[1] + math.sin(cannon_angle) * 42,
    )

def best_player_solution(tx, ty, loft_bias=0):
    ox, oy = hill_peak
    best = None
    best_err = 1e9
    times = (0.35, 0.5, 0.7, 0.95, 1.2, 1.5, 1.9, 2.3, 2.8)
    if loft_bias:
        times = times[loft_bias:] + times[:loft_bias]
    for force, spd in POWER_LEVELS.items():
        for tflight in times:
            dx, dy = tx - ox, ty - oy
            vx = dx / tflight
            vy = (dy - 0.5 * GRAVITY * tflight * tflight) / tflight
            need = math.hypot(vx, vy)
            err = abs(need - spd)
            ang = math.atan2(vy, vx)
            if err < best_err:
                best_err = err
                scale = spd / max(1.0, need)
                best = (ang, force, vx * scale, vy * scale)
    return best

def pick_demo_target():
    global demo_focus, demo_shots_stale, demo_loft
    live = [b for b in buildings if b.alive]
    if not live:
        demo_focus = None
        return None
    if demo_focus is not None and demo_focus.alive:
        if demo_shots_stale < 5:
            return demo_focus
        demo_loft = (demo_loft + 1) % 6
        demo_shots_stale = 0
        demo_focus = None
    siren = [b for b in live if b.has_siren]
    guns = [b for b in live if b.has_gun]
    if siren:
        demo_focus = siren[0]
    elif guns:
        demo_focus = max(guns, key=lambda b: b.stories)
    else:
        demo_focus = max(live, key=lambda b: (b.stories, -b.hits))
    return demo_focus

def demo_think(dt):
    global cannon_angle, force_level, demo_shots_stale
    tgt = pick_demo_target()
    if tgt is None:
        return
    tx, ty = tgt.aim_point()
    if demo_shots_stale >= 3:
        ty += 18 * demo_loft
        tx += random.choice((-12, 0, 12))
    sol = best_player_solution(tx, ty, loft_bias=demo_loft)
    if sol is None:
        demo_shots_stale += 1
        return
    ang, force, vx, vy = sol
    force_level = force
    da = (ang - cannon_angle + math.pi) % math.tau - math.pi
    cannon_angle += max(-3.0 * dt, min(3.0 * dt, da))
    if abs(da) < 0.08 and player_cd <= 0:
        use_bomb = bombs_left > 0 and (tgt.has_siren or tgt.has_gun or tgt.stories >= 12)
        launch_player(use_bomb)
        demo_shots_stale += 1

def launch_player(bomb=False):
    global player_cd, bombs_left
    if player_cd > 0 or game_over or paused:
        return
    if bomb:
        if not unlimited_bombs:
            if bombs_left <= 0:
                return
            bombs_left -= 1
    player_cd = PLAYER_FIRE_COOLDOWN
    power = POWER_LEVELS[force_level]
    vx = math.cos(cannon_angle) * power
    vy = math.sin(cannon_angle) * power
    mx, my = player_muzzle()
    shells.append(Shell(mx, my, vx, vy, True, bomb=bomb))
    play(SND_CANNON)
    if bomb:
        burst(mx, my, 12, (90, 255, 70), 130, 0.35)
    else:
        burst(mx, my, 6, (255, 200, 80), 80, 0.25)

def reset_campaign_difficulty():
    global round_num
    round_num = 1

def collide():
    global player_hp, flash, game_over, won
    for sh in shells:
        if not sh.alive:
            continue
        if sh.y >= GROUND_Y:
            sh.alive = False
            burst(sh.x, GROUND_Y, 14, (140, 130, 110), 160, 0.5)
            play(SND_BOOM, random.uniform(0.35, 0.55))
            continue
        hx, hy = hill_peak
        if (sh.x - hx) ** 2 + (sh.y - hy) ** 2 < 38 ** 2 and not sh.friendly:
            sh.alive = False
            player_hp -= 1
            flash = 0.25
            play(SND_HIT_ME)
            burst(hx, hy, 20, (255, 80, 40), 200, 0.6)
            if player_hp <= 0:
                game_over = True
                won = False
                stop_airraid()
                explode_player_cannon()
                reset_campaign_difficulty()
            continue
        hit_something = False
        for b in buildings:
            if not b.alive:
                continue
            if b.has_siren and b.siren_rect().collidepoint(sh.x, sh.y):
                sh.alive = False
                b.counted_double = True
                b.hit_siren(sh.x, sh.y)
                hit_something = True
                break
            if b.has_gun and b.gun_rect().collidepoint(sh.x, sh.y) and not sh.bomb:
                sh.alive = False
                b.hit_cannon(sh.x, sh.y)
                play(SND_BOOM)
                hit_something = True
                break
            if b.rect.collidepoint(sh.x, sh.y):
                sh.alive = False
                if not sh.friendly:
                    note_friendly_hit(sh.owner)
                if sh.bomb:
                    if b.has_siren:
                        b.counted_double = True
                    b.hit_bomb(sh.x, sh.y)
                else:
                    b.hit_body(sh.x, sh.y)
                    burst(sh.x, sh.y, 16, (200, 160, 80), 180, 0.55)
                    play(SND_BOOM)
                hit_something = True
                break
        if hit_something:
            ensure_cannons()
    if not game_over and destroyed_ratio() >= current_win_ratio():
        game_over = True
        won = True
        stop_airraid()
        play(SND_WIN)

def begin_siege(reset_campaign=False, as_demo=False):
    global buildings, shells, particles, embers, bolts, chunks
    global player_hp, player_cd, bombs_left, cannon_angle, force_level
    global game_over, won, flash, demo_mode, idle_time, player_exploded
    global demo_focus, demo_shots_stale, demo_loft, paused
    stop_airraid()
    if reset_campaign:
        reset_campaign_difficulty()
    demo_mode = as_demo
    idle_time = 0.0
    paused = False
    player_exploded = False
    demo_focus = None
    demo_shots_stale = 0
    demo_loft = 0
    buildings = make_city()
    shells = []
    particles = []
    embers = []
    bolts = []
    chunks = []
    player_hp = PLAYER_MAX_HP
    player_cd = 0.0
    bombs_left = DEMO_BOMBS if as_demo else PLAYER_BOMBS
    cannon_angle = -0.55
    force_level = 2
    game_over = False
    won = False
    flash = 0.0
    ensure_cannons()

def after_round_end():
    if demo_mode:
        if (not won) or current_win_ratio() >= WIN_RATIO_MAX - 1e-6:
            begin_siege(reset_campaign=True, as_demo=False)
        else:
            global round_num
            round_num += 1
            begin_siege(reset_campaign=False, as_demo=True)

def human_continue_or_retry():
    global round_num
    if demo_mode:
        begin_siege(reset_campaign=True, as_demo=False)
        return
    if won:
        if current_win_ratio() < WIN_RATIO_MAX:
            round_num += 1
        begin_siege(reset_campaign=False, as_demo=False)
    else:
        begin_siege(reset_campaign=True, as_demo=False)

def draw_bg(s):
    for i in range(H):
        t = i / float(H)
        pygame.draw.line(s, (int(20 + 40 * t), int(30 + 50 * t), int(70 + 40 * t)), (0, i), (W, i))
    random.seed(3)
    for i in range(40):
        hh = random.randint(20, 90)
        pygame.draw.rect(s, (25, 32, 50), (200 + i * 28, GROUND_Y - 40 - hh, 22, hh))
    random.seed()
    pygame.draw.rect(s, (46, 62, 40), (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.rect(s, (70, 90, 50), (0, GROUND_Y, W, 6))
    pygame.draw.polygon(
        s, (72, 88, 48),
        [(0, H), (0, GROUND_Y - 40), (40, GROUND_Y - 160), hill_peak, (150, GROUND_Y - 80), (200, GROUND_Y), (200, H)]
    )

def low_health():
    return player_hp <= 3 or player_hp / float(PLAYER_MAX_HP) < 0.40

def draw_cannon(s):
    hx, hy = hill_peak
    if not player_exploded:
        pygame.draw.circle(s, (50, 48, 44), (hx, hy + 10), 22)
        pygame.draw.circle(s, (80, 78, 70), (hx, hy + 10), 16)
        ex = hx + math.cos(cannon_angle) * 40
        ey = hy + math.sin(cannon_angle) * 40
        pygame.draw.line(s, (30, 30, 28), (hx, hy), (ex, ey), 10)
        pygame.draw.circle(s, (200, 180, 80), (int(ex), int(ey)), 4)
    bar_w, bar_h = 160, 14
    bx, by = 12, 10
    pygame.draw.rect(s, (40, 30, 30), (bx, by, bar_w, bar_h))
    frac = max(0.0, player_hp / float(PLAYER_MAX_HP))
    danger = low_health()
    blink = (pygame.time.get_ticks() // 180) % 2 == 0
    if danger:
        col = (255, 30, 30) if blink else (120, 10, 10)
    else:
        col = (50, 200, 70) if frac > 0.7 else (230, 190, 50)
    pygame.draw.rect(s, col, (bx, by, int(bar_w * frac), bar_h))
    pygame.draw.rect(s, (230, 230, 220), (bx, by, bar_w, bar_h), 1)
    s.blit(font.render("HP {}/{}".format(max(0, player_hp), PLAYER_MAX_HP), True, (240, 240, 230)), (bx + bar_w + 8, by - 2))
    s.blit(font.render("Force", True, (220, 220, 210)), (12, 28))
    for i in range(1, 4):
        col = (240, 200, 70) if i <= force_level else (50, 50, 45)
        pygame.draw.rect(s, col, (70 + (i - 1) * 18, 30, 14, 14))
        if i == force_level:
            pygame.draw.rect(s, (255, 255, 220), (70 + (i - 1) * 18, 30, 14, 14), 2)
    s.blit(font.render("A-bombs", True, (140, 255, 120)), (12, 48))
    if unlimited_bombs:
        s.blit(font.render("INF", True, (180, 255, 80)), (100, 48))
    else:
        nshow = DEMO_BOMBS if demo_mode else PLAYER_BOMBS
        for i in range(nshow):
            col = (90, 220, 70) if i < bombs_left else (40, 50, 40)
            pygame.draw.rect(s, col, (100 + i * 16, 50, 12, 12))

def draw_embers(s):
    for em in embers:
        x, y = em.pos()
        flick = random.randint(-2, 3)
        pygame.draw.circle(s, (255, 160, 40), (int(x), int(y - 2)), 4 + flick // 2)
        pygame.draw.polygon(s, (255, 90, 20), [(x - 4, y + 3), (x + 4, y + 3), (x, y - 8 - flick)])

def present():
    win_w, win_h = screen.get_size()
    if (win_w, win_h) == (W, H):
        screen.blit(game, (0, 0))
    else:
        screen.blit(pygame.transform.smoothscale(game, (win_w, win_h)), (0, 0))
    pygame.display.flip()

begin_siege(reset_campaign=True, as_demo=False)

running = True
save_timer = 0.0
demo_end_pause = 0.0
while running:
    dt = clock.tick(FPS) / 1000.0
    activity = False
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif e.type == pygame.VIDEORESIZE:
            nw, nh = max(MIN_WIN_W, e.w), max(MIN_WIN_H, e.h)
            screen = pygame.display.set_mode((nw, nh), pygame.RESIZABLE)
            window_geom["w"], window_geom["h"] = nw, nh
            save_window_geom()
        elif hasattr(pygame, "WINDOWMOVED") and e.type == pygame.WINDOWMOVED:
            window_geom["x"], window_geom["y"] = e.x, e.y
            save_window_geom()
        elif e.type == pygame.KEYDOWN:
            activity = True
            if e.key == pygame.K_ESCAPE:
                running = False
            elif e.key == pygame.K_p:
                paused = not paused
            elif e.key == pygame.K_u:
                unlimited_bombs = not unlimited_bombs
            elif demo_mode:
                begin_siege(reset_campaign=True, as_demo=False)
            elif game_over and e.key == pygame.K_r:
                human_continue_or_retry()
            elif not game_over and not paused:
                if e.key == pygame.K_1:
                    force_level = 1
                if e.key == pygame.K_2:
                    force_level = 2
                if e.key == pygame.K_3:
                    force_level = 3
                if e.key == pygame.K_SPACE:
                    launch_player(False)
                if e.key == pygame.K_b:
                    launch_player(True)

    keys = pygame.key.get_pressed()
    if any(keys) or pygame.mouse.get_pressed()[0]:
        activity = True
    if activity:
        idle_time = 0.0
    elif game_over and not demo_mode and not paused:
        idle_time += dt
        if idle_time >= IDLE_BEFORE_DEMO:
            begin_siege(reset_campaign=True, as_demo=True)

    if paused:
        draw_bg(game)
        for b in buildings:
            b.draw(game)
        for c in chunks:
            c.draw(game)
        draw_embers(game)
        for z in bolts:
            z.draw(game)
        for sh in shells:
            sh.draw(game)
        for p in particles:
            p.draw(game)
        draw_cannon(game)
        msg = bigfont.render("PAUSED", True, (240, 230, 120))
        sub = font.render("P resume    U unlimited bombs", True, (220, 220, 210))
        game.blit(msg, msg.get_rect(center=(W // 2, 80)))
        game.blit(sub, sub.get_rect(center=(W // 2, 130)))
        present()
        continue

    if not game_over and not demo_mode:
        if keys[pygame.K_LEFT] or keys[pygame.K_UP]:
            cannon_angle -= 2.2 * dt
        if keys[pygame.K_RIGHT] or keys[pygame.K_DOWN]:
            cannon_angle += 2.2 * dt
        cannon_angle = (cannon_angle + math.pi) % math.tau - math.pi

    player_cd = max(0.0, player_cd - dt)
    flash = max(0.0, flash - dt)

    if not game_over:
        if demo_mode:
            demo_think(dt)
        ensure_cannons()
        for b in buildings:
            b.update(dt)
            if b.has_gun and b.alive and b.fall < 8:
                shot = best_clear_shot(b)
                if shot and aims_at_player(shot[2], b.roof_xy()):
                    b.force_level = shot[1]
                    b.gun_target_angle = shot[2]
                else:
                    b.gun_target_angle = math.atan2(
                        hill_peak[1] - b.roof_xy()[1],
                        hill_peak[0] - b.roof_xy()[0]
                    ) % math.tau
                b.gun_cd -= dt
                if b.gun_cd <= 0:
                    if not b.held:
                        aim_and_maybe_fire(b)
                    elif shot and shot[0] == "player":
                        b.held = False
                        b.friendly_hits = 0
                        aim_and_maybe_fire(b)
                    b.gun_cd = ENEMY_FIRE_INTERVAL
        for sh in shells:
            sh.update(dt)
        collide()
        shells[:] = [sh for sh in shells if sh.alive]
        if game_over and demo_mode:
            demo_end_pause = 1.2
    else:
        for b in buildings:
            b.update(dt)
        if demo_mode:
            demo_end_pause -= dt
            if demo_end_pause <= 0:
                after_round_end()

    embers[:] = [em for em in embers if em.update(dt)]
    particles[:] = [p for p in particles if p.update(dt)]
    bolts[:] = [z for z in bolts if z.update(dt)]
    chunks[:] = [c for c in chunks if c.update(dt)]

    draw_bg(game)
    for b in buildings:
        b.draw(game)
    for c in chunks:
        c.draw(game)
    draw_embers(game)
    for z in bolts:
        z.draw(game)
    for sh in shells:
        sh.draw(game)
    for p in particles:
        p.draw(game)
    draw_cannon(game)

    wr = current_win_ratio()
    hud = font.render(
        "Need {:0.0f}%   Have {:5.1f}%   Round {}   Guns {}   Acc +{:.0f}%   Bombs {}".format(
            wr * 100, destroyed_ratio() * 100, round_num,
            sum(1 for b in buildings if b.has_gun and b.alive),
            (enemy_acc_mult() - 1.0) * 100,
            "INF" if unlimited_bombs else bombs_left
        ), True, (230, 230, 220)
    )
    game.blit(hud, (12, H - 28))

    if demo_mode:
        tag = bigfont.render("DEMO — PERFECT PLAYER", True, (240, 220, 90))
        game.blit(tag, tag.get_rect(center=(W // 2, 36)))
        sub = font.render("6 A-bombs    hunts guns & siren    any key = new player game", True, (220, 220, 200))
        game.blit(sub, sub.get_rect(center=(W // 2, 78)))

    if flash > 0:
        overlay = pygame.Surface((W, H))
        overlay.set_alpha(int(140 * flash / 0.25))
        overlay.fill((180, 20, 10))
        game.blit(overlay, (0, 0))

    if game_over and not demo_mode:
        msg = "CITY SURRENDERS — YOU WIN" if won else "CANNON DESTROYED — YOU LOSE"
        t = bigfont.render(msg, True, (220, 230, 120) if won else (230, 80, 70))
        extra = "R: next siege (+10% city, +5% enemy acc)" if won else "R: new siege from 50% / base accuracy"
        if won and current_win_ratio() >= WIN_RATIO_MAX:
            extra = "R: another 100% siege"
        sub = font.render(extra + "    idle 10s = demo    P pause    U bombs    ESC", True, (220, 220, 210))
        game.blit(t, t.get_rect(center=(W // 2, 80)))
        game.blit(sub, sub.get_rect(center=(W // 2, 130)))

    present()
    save_timer += dt
    if save_timer > 2.0:
        save_window_geom()
        save_timer = 0.0

stop_airraid()
save_window_geom()
pygame.quit()
sys.exit()