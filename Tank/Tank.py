"""
Tank Territory
Z/X or Left/Right — treads
A/S or Down/Up — reverse / forward
B/M — turret
SPACE — toggle auto-fire
P — pause
T — toggle buildings / fight
G — toggle god mode
1–6 — formations
7 — recall stuck tanks
8 — hold fort walls (when lead is inside)
9 — damaged fall back
K/L — volume down/up
- / + — zoom out/in
F4 — save to tankDemo.dat
F5 — load tankDemo.dat
R — restart / start from start or demo
ESC — quit

Forts spawn ~1 per 20 buildings, never on top of each other, never respawn.
Walls take 1200–2000 hits; damage shows after 750.
Start (20s) and demo (30s) alternate until R.
1/3–2/3 of red tanks storm gates. Helicopter rockets ignore walls.
Repair in 60s. Damaged tanks stay near the lead.
"""

import array
import json
import math
import os
import pickle
import random
import sys

import pygame

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tank_config.json")
SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tankDemo.dat")
CHUNK = 560
TANK_R = 20
TANK_LEN = 32
SHELL_SPEED = 520
SHELL_RANGE = SHELL_SPEED * 1.5
ROCKET_RANGE = SHELL_RANGE * 2
ROCKET_START = SHELL_SPEED * 0.55
ROCKET_PEAK = SHELL_SPEED * 1.5
PLAYER_SPEED = 128
FOLLOW_SPEED = 150
ENEMY_SPEED = 96
HELI_SPEED = 115
WAVE_SIZES = (2, 3, 5, 10, 15, 20)
MAX_BLUE_REFILL = 20
FORM_NAMES = {1: "line", 2: "tight circle", 3: "loose ring", 4: "triangle", 5: "square", 6: "scatter"}
BUILDING_PAY = {"factory": 5, "power": 10, "command": 15}
OFFSCREEN_LIMIT = 300.0
REPAIR_TIME = 60.0
FORT_SIZE = int(CHUNK * 0.6)
GATE = 72
BUILDING_CHANCE = 0.24
ZAP_RANGE = 280
MIN_FORT_DIST = 50 * TANK_LEN

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def ang_diff(a, b):
    return (a - b + math.pi) % math.tau - math.pi

def load_config():
    default = {"w": 1100, "h": 700, "x": None, "y": None}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        default.update({k: data[k] for k in default if k in data})
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return default

def save_config(w, h, x, y):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"w": int(w), "h": int(h), "x": x, "y": y}, f)
    except OSError:
        pass

def get_window_pos():
    try:
        info = pygame.display.get_wm_info()
        hwnd = info.get("window")
        if hwnd and sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            return int(rect.left), int(rect.top)
    except Exception:
        pass
    return None, None

def set_window_pos(x, y):
    if x is None or y is None:
        return
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{int(x)},{int(y)}"

def make_tone(freq, duration, volume=0.22, decay=True):
    rate = 44100
    n = max(1, int(rate * duration))
    buf = array.array("h")
    for i in range(n):
        env = 1.0 - (i / n) if decay else 1.0
        sample = int(volume * 32767 * env * math.sin(2 * math.pi * freq * i / rate))
        buf.append(sample)
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf)

def make_boom(duration=0.55, volume=0.7):
    rate = 44100
    n = max(1, int(rate * duration))
    buf = array.array("h")
    level = volume * 32767
    phase = 0.0
    for i in range(n):
        t = i / n
        env = (1.0 - t) ** 1.4
        phase += 0.08 + t * 0.4
        thud = math.sin(phase) * 0.55 + math.sin(phase * 0.37) * 0.25
        grit = random.uniform(-1, 1) * 0.5
        sample = int(clamp((thud + grit * 0.4) * level * env, -32767, 32767))
        buf.append(sample)
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf)

def make_hit():
    rate = 44100
    n = int(rate * 0.12)
    buf = array.array("h")
    level = 0.4 * 32767
    for i in range(n):
        env = 1.0 - i / n
        sample = int(clamp((math.sin(i * 0.4) * 0.3 + random.uniform(-1, 1) * 0.7) * level * env, -32767, 32767))
        buf.append(sample)
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf)

def perimeter_point(slot, count, verts):
    edge = ((slot - 1) % max(1, count)) / max(1, count) * len(verts)
    i = int(edge) % len(verts)
    f = edge - int(edge)
    a, b = verts[i], verts[(i + 1) % len(verts)]
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)

class Bullet:
    def __init__(self, x, y, angle, owner, friendly, rocket=False, small=False):
        self.x, self.y = x, y
        self.angle = angle
        self.owner = owner
        self.friendly = friendly
        self.rocket = rocket
        self.small = small
        self.alive = True
        self.dist = 0.0
        if rocket:
            self.speed = ROCKET_START
            self.max_dist = ROCKET_RANGE
        else:
            self.speed = SHELL_SPEED * (0.7 if small else 1.0)
            self.max_dist = SHELL_RANGE * (0.7 if small else 1.0)

    def update(self, dt):
        if self.rocket:
            half = self.max_dist * 0.5
            self.speed = ROCKET_PEAK if self.dist >= half else ROCKET_START + (ROCKET_PEAK - ROCKET_START) * (self.dist / max(1, half))
        step = self.speed * dt
        self.x += math.cos(self.angle) * step
        self.y += math.sin(self.angle) * step
        self.dist += step
        if self.dist >= self.max_dist:
            self.alive = False

    def draw(self, surf, particles, zoom, to_screen):
        sx, sy = to_screen(self.x, self.y)
        if self.rocket:
            bx = sx - math.cos(self.angle) * 16 * zoom
            by = sy - math.sin(self.angle) * 16 * zoom
            tip = (sx + math.cos(self.angle) * 10 * zoom, sy + math.sin(self.angle) * 10 * zoom)
            pygame.draw.line(surf, (70, 70, 78), (bx, by), tip, max(1, int(5 * zoom)))
            pygame.draw.circle(surf, (255, 160, 40), (int(bx), int(by)), max(2, int(4 * zoom)))
            if random.random() < 0.5:
                particles.append(Particle(self.x - math.cos(self.angle) * 14, self.y - math.sin(self.angle) * 14, (255, 120, 30), 18, 0.16, 3))
        else:
            pygame.draw.circle(surf, (255, 200, 100) if self.small else (255, 236, 160), (int(sx), int(sy)), max(1, int((2 if self.small else 3) * zoom)))

class Bolt:
    def __init__(self, x1, y1, x2, y2, life=0.1):
        self.pts = [(x1, y1)]
        for i in range(1, 5):
            t = i / 5
            self.pts.append((x1 + (x2 - x1) * t + random.uniform(-8, 8), y1 + (y2 - y1) * t + random.uniform(-8, 8)))
        self.pts.append((x2, y2))
        self.life = life

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf, to_screen, zoom):
        pts = [to_screen(x, y) for x, y in self.pts]
        if len(pts) > 1:
            pygame.draw.lines(surf, (180, 230, 255), False, pts, max(1, int(2 * zoom)))

class Particle:
    def __init__(self, x, y, color, speed, life, radius, gravity=0, kind="spark"):
        ang = random.random() * math.tau
        spd = random.uniform(0.3, 1.0) * speed
        self.x, self.y = x, y
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd
        self.color = color
        self.life = life
        self.max_life = max(0.01, life)
        self.radius = radius
        self.gravity = gravity
        self.kind = kind

    def update(self, dt):
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf, to_screen, zoom):
        a = clamp(self.life / self.max_life, 0, 1)
        col = tuple(int(c * (0.35 + 0.65 * a)) for c in self.color)
        r = max(1, int(self.radius * (0.45 + 0.55 * a) * zoom))
        sx, sy = to_screen(self.x, self.y)
        pygame.draw.circle(surf, col, (int(sx), int(sy)), r + (2 if self.kind == "smoke" else 0))

class Shockwave:
    def __init__(self, x, y):
        self.x, self.y, self.life, self.max_life = x, y, 0.4, 0.4

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf, to_screen, zoom):
        a = self.life / self.max_life
        sx, sy = to_screen(self.x, self.y)
        pygame.draw.circle(surf, (255, int(150 * a), 30), (int(sx), int(sy)), int((18 + (1 - a) * 80) * zoom), max(1, int(3 * zoom)))

class Block:
    def __init__(self, x, y, w, h, kind):
        self.rect = pygame.Rect(x, y, w, h)
        self.kind = kind

    def blocks_fire(self):
        return self.kind == "block"

    def draw(self, surf, to_screen, zoom):
        r = self.rect
        sx, sy = to_screen(r.x, r.y)
        sr = pygame.Rect(sx, sy, r.w * zoom, r.h * zoom)
        if self.kind == "block":
            pygame.draw.rect(surf, (92, 96, 102), sr)
            pygame.draw.rect(surf, (48, 50, 56), sr, 2)
        elif self.kind == "rock":
            pygame.draw.ellipse(surf, (110, 108, 100), sr)
        else:
            pygame.draw.circle(surf, (46, 110, 52), (int(sx + r.w * zoom / 2), int(sy + r.h * zoom / 2)), max(4, int(max(8, r.w // 3) * zoom)))

class Fort:
    def __init__(self, x, y):
        self.size = FORT_SIZE
        self.rect = pygame.Rect(x, y, self.size, self.size)
        self.gate = random.choice(["n", "s", "e", "w"])
        self.walls = []
        t = 14
        s = self.size
        gap0 = (s - GATE) // 2
        sides = {
            "n": (x, y, s, t),
            "s": (x, y + s - t, s, t),
            "w": (x, y, t, s),
            "e": (x + s - t, y, t, s),
        }
        for name, (wx, wy, ww, wh) in sides.items():
            if name == self.gate:
                if name in ("n", "s"):
                    self.walls.append(pygame.Rect(wx, wy, gap0, wh))
                    self.walls.append(pygame.Rect(wx + gap0 + GATE, wy, ww - gap0 - GATE, wh))
                else:
                    self.walls.append(pygame.Rect(wx, wy, ww, gap0))
                    self.walls.append(pygame.Rect(wx, wy + gap0 + GATE, ww, wh - gap0 - GATE))
            else:
                self.walls.append(pygame.Rect(wx, wy, ww, wh))
        self.max_hp = random.randint(1200, 2000)
        self.hp = self.max_hp
        self.hits = 0
        self.breached = False

    def contains(self, x, y, pad=0):
        return self.rect.inflate(-pad, -pad).collidepoint(x, y)

    def gate_rect(self):
        r = self.rect
        g = GATE
        if self.gate == "n":
            return pygame.Rect(r.centerx - g // 2, r.top - 4, g, 22)
        if self.gate == "s":
            return pygame.Rect(r.centerx - g // 2, r.bottom - 18, g, 22)
        if self.gate == "w":
            return pygame.Rect(r.left - 4, r.centery - g // 2, 22, g)
        return pygame.Rect(r.right - 18, r.centery - g // 2, 22, g)

    def gate_center(self):
        gr = self.gate_rect()
        return gr.centerx, gr.centery

    def take_hit(self, particles):
        if self.breached:
            return
        self.hits += 1
        self.hp -= 1
        if self.hits >= 750 and random.random() < 0.3:
            particles.append(Particle(self.rect.centerx + random.uniform(-self.size/2, self.size/2),
                                      self.rect.centery + random.uniform(-self.size/2, self.size/2),
                                      (90, 70, 50), 30, 0.4, 4, kind="smoke"))
        if self.hp <= 0:
            self.breached = True
            self.walls = []

    def blocks_bullet(self, x, y, friendly, from_inside, is_rocket=False):
        if self.breached or (is_rocket and not friendly):
            return False
        hit_wall = any(w.collidepoint(x, y) for w in self.walls)
        if not hit_wall:
            return False
        if friendly:
            if from_inside:
                return False
            return random.random() < 0.20
        else:
            if from_inside:
                return False
            if self.gate_rect().collidepoint(x, y):
                return False
            return True

    def blocks_tank(self, box):
        if self.breached:
            return False
        return any(box.colliderect(w) for w in self.walls)

    def nudge_in(self, tank, amount=40):
        cx, cy = self.rect.center
        dx, dy = cx - tank.x, cy - tank.y
        d = math.hypot(dx, dy) or 1
        tank.x += dx / d * amount
        tank.y += dy / d * amount
        tank.last_x, tank.last_y = tank.x, tank.y

    def edge_slots(self, count):
        inner = self.rect.inflate(-50, -50)
        pts = []
        n = max(1, count)
        for i in range(n):
            t = i / n
            side = int(t * 4) % 4
            f = (t * 4) % 1
            if side == 0:
                pts.append((inner.left + f * inner.w, inner.top))
            elif side == 1:
                pts.append((inner.right, inner.top + f * inner.h))
            elif side == 2:
                pts.append((inner.right - f * inner.w, inner.bottom))
            else:
                pts.append((inner.left, inner.bottom - f * inner.h))
        return pts

    def draw(self, surf, to_screen, zoom, particles):
        sx, sy = to_screen(self.rect.x, self.rect.y)
        pygame.draw.rect(surf, (40, 70, 48), (sx, sy, self.size * zoom, self.size * zoom))
        if self.breached:
            return
        damage = self.hits / max(1, self.max_hp)
        base_col = (130, 118, 82)
        if self.hits >= 750:
            base_col = (110 - int(damage * 40), 90 - int(damage * 30), 60)
        for w in self.walls:
            wx, wy = to_screen(w.x, w.y)
            pygame.draw.rect(surf, base_col, (wx, wy, w.w * zoom, w.h * zoom))
            pygame.draw.rect(surf, (70, 58, 40), (wx, wy, w.w * zoom, w.h * zoom), 2)
            if self.hits >= 750 and random.random() < 0.05 * damage:
                pygame.draw.line(surf, (60, 40, 30), (wx + random.randint(0, int(w.w*zoom)), wy),
                                 (wx + random.randint(0, int(w.w*zoom)), wy + int(w.h*zoom)), 1)

class Rubble:
    def __init__(self, building):
        self.pieces = []
        r = building.rect
        for _ in range(7):
            w, h = random.randint(14, 32), random.randint(10, 20)
            self.pieces.append({
                "rect": pygame.Rect(r.x + random.randint(0, max(1, r.w - w)), r.y + random.randint(0, max(1, r.h - h)), w, h),
                "life": 120.0 + random.uniform(0, 10),
            })

    def update(self, dt):
        for p in self.pieces:
            p["life"] -= dt
        self.pieces = [p for p in self.pieces if p["life"] > 0]
        return bool(self.pieces)

    def blocks(self, box):
        return any(box.colliderect(p["rect"]) for p in self.pieces)

    def draw(self, surf, to_screen, zoom):
        for p in self.pieces:
            r = p["rect"]
            sx, sy = to_screen(r.x, r.y)
            pygame.draw.rect(surf, (72, 64, 54), (sx, sy, r.w * zoom, r.h * zoom))

class Building:
    def __init__(self, x, y, kind):
        self.kind = kind
        self.rect = pygame.Rect(x, y, random.randint(100, 140), random.randint(44, 62))
        self.hp = 20
        self.max_hp = 20
        self.alive = True

    def draw(self, surf, to_screen, zoom, font, particles):
        r = self.rect
        sx, sy = to_screen(r.x, r.y)
        sr = pygame.Rect(sx, sy, r.w * zoom, r.h * zoom)
        body = {"factory": (78, 82, 88), "power": (92, 86, 62), "command": (62, 74, 96)}[self.kind]
        pygame.draw.rect(surf, body, sr)
        pygame.draw.rect(surf, (30, 32, 36), sr, 2)
        for i in range(3):
            wx = sx + 12 * zoom + i * max(10, (r.w - 36) / 2) * zoom
            pygame.draw.rect(surf, (150, 190, 210), (wx, sy + 12 * zoom, 16 * zoom, 10 * zoom))
        if self.hp < self.max_hp and random.random() < 0.3 * (1 - self.hp / self.max_hp):
            particles.append(Particle(self.rect.centerx, self.rect.y, random.choice([(255, 130, 30), (70, 70, 70)]), 24, 0.4, 4, gravity=-16, kind="flame"))
        surf.blit(font.render(f"{self.kind[:4].upper()} {self.hp}", True, (230, 230, 220)), (sx + 4, sy + r.h * zoom - 16))

class Robot:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.hp = random.randint(12, 30)
        self.alive = True
        self.phase = random.random() * math.tau
        self.arm = 0.0
        self.remove = False

    def update(self, dt, tanks):
        self.arm += dt * 14
        self.phase += dt * 7
        foes = [t for t in tanks if t.friendly and t.alive and not t.exploding]
        if not foes:
            return None
        target = min(foes, key=lambda t: math.hypot(t.x - self.x, t.y - self.y))
        desired = math.atan2(target.y - self.y, target.x - self.x)
        self.x += math.cos(desired + math.sin(self.phase) * 0.55) * 230 * dt
        self.y += math.sin(desired + math.sin(self.phase) * 0.55) * 230 * dt
        if math.hypot(target.x - self.x, target.y - self.y) < 22:
            return target
        return None

    def draw(self, surf, to_screen, zoom):
        px, py = to_screen(self.x, self.y)
        pygame.draw.rect(surf, (150, 90, 40), (px - 7 * zoom, py - 8 * zoom, 14 * zoom, 16 * zoom))
        pygame.draw.circle(surf, (190, 120, 50), (int(px), int(py - 12 * zoom)), max(3, int(6 * zoom)))
        swing = math.sin(self.arm) * 10 * zoom
        pygame.draw.line(surf, (90, 50, 30), (px - 7 * zoom, py - 2 * zoom), (px - 18 * zoom, py - 12 * zoom + swing), 2)
        pygame.draw.line(surf, (90, 50, 30), (px + 7 * zoom, py - 2 * zoom), (px + 18 * zoom, py - 12 * zoom - swing), 2)

class Helicopter:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.hp = random.randint(5, 10)
        self.alive = True
        self.rotor = 0.0
        self.remove = False
        self.cooldown = random.uniform(0.3, 0.9)

    def update(self, dt, tanks, bullets):
        self.rotor += dt * 18
        self.cooldown = max(0.0, self.cooldown - dt)
        foes = [t for t in tanks if t.friendly and t.alive and not t.exploding]
        if not foes:
            return
        target = min(foes, key=lambda t: math.hypot(t.x - self.x, t.y - self.y))
        desired = math.atan2(target.y - self.y, target.x - self.x)
        dist = math.hypot(target.x - self.x, target.y - self.y)
        if dist > 150:
            self.x += math.cos(desired) * HELI_SPEED * dt
            self.y += math.sin(desired) * HELI_SPEED * dt
        if dist < 600 and self.cooldown <= 0:
            self.cooldown = random.uniform(0.6, 1.1)
            bullets.append(Bullet(self.x, self.y, desired, self, False, rocket=True))

    def draw(self, surf, to_screen, zoom):
        px, py = to_screen(self.x, self.y)
        pygame.draw.ellipse(surf, (160, 40, 40), (px - 16 * zoom, py - 8 * zoom, 32 * zoom, 16 * zoom))
        rx = math.cos(self.rotor) * 18 * zoom
        ry = math.sin(self.rotor) * 6 * zoom
        pygame.draw.line(surf, (20, 20, 20), (px - rx, py - 10 * zoom - ry), (px + rx, py - 10 * zoom + ry), 2)

class Tank:
    def __init__(self, x, y, friendly, player=False, rocket=False, garrison=False):
        self.x, self.y = float(x), float(y)
        self.angle = -math.pi / 2
        self.turret = self.angle
        self.friendly = friendly
        self.player = player
        self.rocket = rocket
        self.garrison = garrison
        self.max_hp = 110 if friendly else 70
        self.hp = self.max_hp
        self.alive = True
        self.exploding = False
        self.explode_t = 0.0
        self.cooldown = 0.0
        self.left_pow = self.right_pow = 0.0
        self.follow_slot = 0
        self.remove = False
        self.flash = 0.0
        self.stuck = 0.0
        self.detour = None
        self.detour_t = 0.0
        self.last_x, self.last_y = x, y
        self.scatter = None
        self.wave_id = 0
        self.zap_cd = 0.0
        self.offscreen = 0.0
        self.retreat = False
        self.home_fort = None
        self.attack_gate = False

    def muzzle(self):
        return self.x + math.cos(self.turret) * 28, self.y + math.sin(self.turret) * 28

    def hit(self, dmg, particles, waves, force_kill=False, god=False):
        if not self.alive or self.exploding:
            return
        if self.friendly and god:
            return
        self.hp -= dmg
        self.flash = 0.08
        for _ in range(4):
            particles.append(Particle(self.x, self.y, (80, 80, 80), 50, 0.3, 3, kind="smoke"))
        if force_kill or self.hp <= 0:
            self.exploding = True
            self.explode_t = random.uniform(2.0, 7.0)
            self.alive = False
            waves.append(Shockwave(self.x, self.y))

    def kill(self, particles, waves, god=False):
        self.hit(999, particles, waves, force_kill=True, god=god)

    def update_motion(self, dt, speed):
        forward = (self.left_pow + self.right_pow) * 0.5
        self.angle += (self.right_pow - self.left_pow) * 1.9 * dt
        self.x += math.cos(self.angle) * forward * speed * dt
        self.y += math.sin(self.angle) * forward * speed * dt
        self.left_pow *= 0.78
        self.right_pow *= 0.78

    def update(self, dt, particles, speed):
        self.cooldown = max(0.0, self.cooldown - dt)
        self.zap_cd = max(0.0, self.zap_cd - dt)
        self.flash = max(0.0, self.flash - dt)
        if self.friendly and self.alive and self.hp < self.max_hp:
            self.hp = min(self.max_hp, self.hp + self.max_hp / REPAIR_TIME * dt)
        if self.exploding:
            self.explode_t -= dt
            burn = 0.95 if not self.friendly else 0.55
            if random.random() < burn:
                particles.append(Particle(self.x + random.uniform(-10, 10), self.y, random.choice([(255, 170, 40), (255, 70, 20)]), 50, 0.35, 6, gravity=-32, kind="flame"))
            if self.explode_t <= 0:
                self.remove = True
            return
        if self.alive and self.hp < self.max_hp * 0.85 and random.random() < (1 - self.hp / self.max_hp) * 0.3:
            particles.append(Particle(self.x, self.y - 8, (70, 70, 70), 14, 0.55, 5, gravity=-8, kind="smoke"))
        self.update_motion(dt, speed)

    def draw(self, surf, to_screen, zoom):
        if self.remove:
            return
        px, py = to_screen(self.x, self.y)
        if self.exploding:
            pygame.draw.circle(surf, (255, 90, 20), (int(px), int(py)), max(4, int(12 * zoom)))
            pygame.draw.circle(surf, (255, 200, 60), (int(px), int(py)), max(2, int(6 * zoom)))
            return
        if self.rocket and self.friendly:
            body = (90, 150, 90)
        elif self.player:
            body = (120, 190, 255)
        elif self.friendly:
            body = (70, 130, 220)
        else:
            body = (200, 60, 60)
        if self.flash:
            body = (255, 230, 160)
        c, s = math.cos(self.angle), math.sin(self.angle)
        pts = [(px + dx * c * zoom - dy * s * zoom, py + dx * s * zoom + dy * c * zoom) for dx, dy in ((-15, -11), (16, -11), (16, 11), (-15, 11))]
        pygame.draw.polygon(surf, body, pts)
        pygame.draw.polygon(surf, (20, 22, 28), pts, 2)
        pygame.draw.circle(surf, body, (int(px), int(py)), max(3, int(8 * zoom)))
        pygame.draw.line(surf, (28, 30, 36), (px, py), (px + math.cos(self.turret) * 24 * zoom, py + math.sin(self.turret) * 24 * zoom), max(1, int(4 * zoom)))
        if self.rocket:
            pygame.draw.line(surf, (50, 50, 58), (px - c * 6 * zoom, py - s * 6 * zoom), (px - c * 18 * zoom, py - s * 18 * zoom), max(1, int(4 * zoom)))

class Game:
    def __init__(self):
        cfg = load_config()
        if cfg["x"] is not None:
            set_window_pos(cfg["x"], cfg["y"])
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        self.w, self.h = max(640, cfg["w"]), max(480, cfg["h"])
        self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
        pygame.display.set_caption("Tank Territory")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.small = pygame.font.SysFont("consolas", 14)
        self.big = pygame.font.SysFont("consolas", 48, bold=True)
        self.sounds = {
            "fire": make_tone(170, 0.06, 0.16),
            "rocket": make_boom(0.18, 0.35),
            "hit": make_hit(),
            "explode": make_boom(0.6, 0.75),
            "toggle": make_tone(640, 0.05, 0.2, decay=False),
            "switch": make_tone(420, 0.1, 0.22),
            "wave": make_tone(520, 0.16, 0.24),
            "zap": make_tone(900, 0.03, 0.14, decay=False),
        }
        self.volume = 0.7
        self.apply_volume()
        self.zoom = 1.0
        self.chunks = {}
        self.target_counts = {}
        self.mode = "start"
        self.gameover_timer = 0.0
        self.demo_timer = 0.0
        self.attract_timer = 20.0
        self.demo_files = []
        self.building_count = 0
        self.forts_spawned = 0
        self.scan_demos()
        self.reset()

    def scan_demos(self):
        base = os.path.dirname(os.path.abspath(__file__))
        self.demo_files = [os.path.join(base, f"tankDemo{i}.dat") for i in range(1, 10) if os.path.exists(os.path.join(base, f"tankDemo{i}.dat"))]

    def apply_volume(self):
        for s in self.sounds.values():
            s.set_volume(self.volume)

    def reset(self):
        self.player = Tank(0, 0, True, player=True)
        self.tanks = [self.player]
        for i in range(5):
            mate = Tank((i - 2) * 46, 36, True)
            mate.follow_slot = i + 1
            self.tanks.append(mate)
        self.formation = 1
        self.assign_formation()
        self.bullets, self.particles, self.waves_fx, self.bolts = [], [], [], []
        self.robots, self.buildings, self.helis, self.rubble, self.forts = [], [], [], [], []
        self.cam = [0.0, 0.0]
        self.shake = 0.0
        self.auto_fire = True
        self.paused = False
        self.siege = False
        self.god = False
        self.hold_fort = False
        self.kills = 0
        self.wave_index = 0
        self.wave_serial = 0
        self.between = random.uniform(30, 60)
        self.heli_between = self.between / 2
        self.cleared = set()
        self.built = set()
        self.fort_built = set()
        self.loss_timer = 3.0
        self.red_pressure = 0.0
        self.robot_timer = 14.0
        self.build_timer = 60.0
        self.reinforce = 32.0
        self.building_count = 0
        self.forts_spawned = 0
        self.notice = "Forts spawn ~1 per 20 buildings, never respawn."
        self.notice_t = 3.0
        self.chunks.clear()
        self.ensure_chunks()
        self.spawn_wave()
        self.mode = "play"

    def blue_count(self):
        return sum(1 for t in self.tanks if t.friendly and t.alive and not t.exploding)

    def allies(self):
        return [t for t in self.tanks if t.friendly and t.alive and not t.exploding]

    def followers(self):
        return [t for t in self.tanks if t.friendly and t.alive and not t.player]

    def enemies(self):
        return [t for t in self.tanks if not t.friendly and t.alive and not t.exploding]

    def to_screen(self, x, y):
        if self.player:
            return (x - self.player.x) * self.zoom + self.w / 2, (y - self.player.y) * self.zoom + self.h / 2
        return (x - self.cam[0]) * self.zoom + self.w / 2, (y - self.cam[1]) * self.zoom + self.h / 2

    def on_screen(self, x, y):
        margin = 80 / max(0.2, self.zoom)
        if self.player:
            return abs(x - self.player.x) < self.w / self.zoom / 2 + margin and abs(y - self.player.y) < self.h / self.zoom / 2 + margin
        return True

    def group_center(self):
        blues = self.allies()
        if not blues:
            return (self.player.x, self.player.y) if self.player else (0, 0)
        return (sum(t.x for t in blues) / len(blues), sum(t.y for t in blues) / len(blues))

    def fort_at(self, x, y):
        for f in self.forts:
            if not f.breached and f.contains(x, y, 6):
                return f
        return None

    def nearest_fort(self, x, y):
        best, best_d = None, 1e9
        for f in self.forts:
            if f.breached:
                continue
            d = math.hypot(f.rect.centerx - x, f.rect.centery - y)
            if d < best_d:
                best, best_d = f, d
        return best

    def fort_too_close(self, x, y):
        for f in self.forts:
            if math.hypot(f.rect.centerx - x, f.rect.centery - y) < MIN_FORT_DIST:
                return True
        return False

    def try_spawn_fort(self, bx, by):
        if self.building_count // 20 <= self.forts_spawned:
            return
        fx = bx + random.randint(-120, 120)
        fy = by + random.randint(-120, 120)
        if self.fort_too_close(fx + FORT_SIZE / 2, fy + FORT_SIZE / 2):
            return
        fort = Fort(fx, fy)
        self.forts.append(fort)
        self.forts_spawned += 1
        for i in range(20):
            ang = (i / 20) * math.tau
            dist = random.uniform(40, FORT_SIZE * 0.35)
            gx = fort.rect.centerx + math.cos(ang) * dist
            gy = fort.rect.centery + math.sin(ang) * dist
            g = Tank(gx, gy, False, garrison=True)
            g.home_fort = fort
            g.angle = ang
            g.turret = ang
            self.tanks.append(g)
        self.notice = "Fort established nearby."
        self.notice_t = 1.6

    def pick_enemy(self, tank, limit=700):
        foes = [e for e in self.enemies() if math.hypot(e.x - tank.x, e.y - tank.y) < limit]
        if not foes:
            return None
        if self.player:
            close = [e for e in foes if math.hypot(e.x - self.player.x, e.y - self.player.y) < 80]
            if close:
                return min(close, key=lambda e: math.hypot(e.x - tank.x, e.y - tank.y))
        foes.sort(key=lambda e: (self.target_counts.get(id(e), 0), math.hypot(e.x - tank.x, e.y - tank.y)))
        chosen = foes[0]
        self.target_counts[id(chosen)] = self.target_counts.get(id(chosen), 0) + 1
        return chosen

    def reinforce_interval(self):
        base = max(8.0, 32.0 - len(self.cleared) * 1.4)
        if self.enemies():
            base = max(base, 32.0) + self.red_pressure
        return clamp(base, 8.0, 64.0)

    def wave_plan(self):
        blue = self.blue_count()
        base = WAVE_SIZES[min(self.wave_index, len(WAVE_SIZES) - 1)]
        if blue < 40:
            return base, random.uniform(30, 60)
        if blue >= 200:
            return max(2, int(blue * 0.35)), random.uniform(7, 18)
        if blue >= 100:
            return 50 + int((blue - 100) * 0.2), random.uniform(7, 18)
        frac = (blue - 40) / 60.0
        return max(2, int(base + (50 - base) * frac)), random.uniform(30 - frac * 23, 60 - frac * 42)

    def chunk_key(self, x, y):
        return int(math.floor(x / CHUNK)), int(math.floor(y / CHUNK))

    def build_chunk(self, cx, cy):
        rng = random.Random((cx * 91823 + cy * 44111) & 0xFFFFFFFF)
        items = []
        if abs(cx) <= 1 and abs(cy) <= 1:
            return items
        for _ in range(rng.randint(1, 3)):
            kind = rng.choice(["tree", "rock", "block", "block"])
            w = rng.randint(34, 76) if kind == "block" else rng.randint(24, 40)
            h = rng.randint(26, 56) if kind == "block" else rng.randint(24, 40)
            items.append(Block(cx * CHUNK + rng.randint(20, CHUNK - 100), cy * CHUNK + rng.randint(20, CHUNK - 90), w, h, kind))
        return items

    def ensure_chunks(self):
        if not self.player:
            return
        x0, y0 = self.chunk_key(self.player.x - CHUNK * 2, self.player.y - CHUNK * 2)
        x1, y1 = self.chunk_key(self.player.x + CHUNK * 2, self.player.y + CHUNK * 2)
        for cy in range(y0 - 1, y1 + 2):
            for cx in range(x0 - 1, x1 + 2):
                self.chunks.setdefault((cx, cy), self.build_chunk(cx, cy))
                far = abs(cx) + abs(cy)
                if (cx, cy) not in self.built and far > 1:
                    self.built.add((cx, cy))
                    if random.random() < BUILDING_CHANCE:
                        kind = random.choice(["factory", "factory", "power", "command"])
                        bx = cx * CHUNK + random.randint(60, 360)
                        by = cy * CHUNK + random.randint(60, 360)
                        self.buildings.append(Building(bx, by, kind))
                        self.building_count += 1
                        self.try_spawn_fort(bx, by)
        self.chunks = {k: v for k, v in self.chunks.items() if abs(k[0] - x0) < 8 and abs(k[1] - y0) < 8}

    def solid_blocks(self):
        blocks = []
        if not self.player:
            return blocks
        x0, y0 = self.chunk_key(self.player.x - CHUNK, self.player.y - CHUNK)
        x1, y1 = self.chunk_key(self.player.x + CHUNK, self.player.y + CHUNK)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                blocks.extend(i for i in self.chunks.get((cx, cy), []) if isinstance(i, Block))
        return blocks

    def tank_blocked(self, tank, blocks):
        box = pygame.Rect(tank.x - 14, tank.y - 12, 28, 24)
        if any(b.kind == "block" and box.colliderect(b.rect.inflate(-4, -4)) for b in blocks):
            return True
        if any(box.colliderect(b.rect) for b in self.buildings if b.alive):
            return True
        if any(r.blocks(box) for r in self.rubble):
            return True
        return any(f.blocks_tank(box) for f in self.forts)

    def fire(self, tank, quiet=False):
        if tank.cooldown > 0 or not tank.alive or tank.exploding:
            return
        rocket = tank.friendly and tank.rocket
        tank.cooldown = 8.0 if rocket else (0.34 if tank.player else 0.48)
        mx, my = tank.muzzle()
        self.bullets.append(Bullet(mx, my, tank.turret, tank, tank.friendly, rocket))
        if not quiet:
            self.sounds["rocket" if rocket else "fire"].play()

    def nearest_heli(self, tank, limit=ZAP_RANGE + 80):
        best, best_d = None, limit
        for h in self.helis:
            if h.alive:
                d = math.hypot(h.x - tank.x, h.y - tank.y)
                if d < best_d:
                    best, best_d = h, d
        return best

    def nearest_robot(self, tank, limit=ZAP_RANGE):
        best, best_d = None, limit
        for r in self.robots:
            if r.alive:
                d = math.hypot(r.x - tank.x, r.y - tank.y)
                if d < best_d:
                    best, best_d = r, d
        return best

    def nearest_building(self, tank, limit=640):
        best, best_d = None, limit
        for b in self.buildings:
            if b.alive:
                d = math.hypot(b.rect.centerx - tank.x, b.rect.centery - tank.y)
                if d < best_d:
                    best, best_d = b, d
        return best

    def assign_formation(self):
        for i, t in enumerate(sorted(self.followers(), key=lambda t: t.follow_slot), start=1):
            t.follow_slot = i
            if self.formation == 6 and t.scatter is None:
                ang = random.random() * math.tau
                dist = random.uniform(40, self.w * 0.5)
                t.scatter = (math.cos(ang) * dist, math.sin(ang) * dist)

    def set_formation(self, mode):
        self.hold_fort = False
        self.formation = mode
        for t in self.followers():
            t.retreat = False
            if mode == 6:
                t.scatter = None
        self.assign_formation()
        self.notice = f"Formation {mode}: {FORM_NAMES[mode]}."
        self.notice_t = 1.3

    def formation_point(self, tank):
        p = self.player
        if not p:
            return tank.x, tank.y
        slot, count = tank.follow_slot, max(1, len(self.followers()))
        c, s = math.cos(p.angle), math.sin(p.angle)
        if self.formation == 1:
            side = ((slot + 1) // 2) * 46 * (1 if slot % 2 else -1)
            return p.x - c * 28 - s * side, p.y - s * 28 + c * side
        if self.formation in (2, 3):
            radius = 58 if self.formation == 2 else 150
            ang = (slot - 1) / count * math.tau + p.angle
            return p.x + math.cos(ang) * radius, p.y + math.sin(ang) * radius
        if self.formation == 4:
            r = 110
            verts = [(p.x + math.cos(p.angle - math.pi / 2 + i * math.tau / 3) * r, p.y + math.sin(p.angle - math.pi / 2 + i * math.tau / 3) * r) for i in range(3)]
            return perimeter_point(slot, count, verts)
        if self.formation == 5:
            return perimeter_point(slot, count, [(p.x - 100, p.y - 100), (p.x + 100, p.y - 100), (p.x + 100, p.y + 100), (p.x - 100, p.y + 100)])
        if tank.scatter is None:
            ang = random.random() * math.tau
            dist = random.uniform(40, self.w * 0.5)
            tank.scatter = (math.cos(ang) * dist, math.sin(ang) * dist)
        return p.x + tank.scatter[0], p.y + tank.scatter[1]

    def drive_toward(self, tank, tx, ty, match=None):
        desired = math.atan2(ty - tank.y, tx - tank.x)
        diff = ang_diff(desired, tank.angle)
        if math.hypot(tx - tank.x, ty - tank.y) < 16:
            tank.left_pow = tank.right_pow = 0.0
            if match is not None:
                tank.angle += clamp(ang_diff(match, tank.angle), -0.08, 0.08)
            return
        tank.left_pow = tank.right_pow = 1.0
        if diff > 0.12:
            tank.right_pow, tank.left_pow = 1.0, 0.0
        elif diff < -0.12:
            tank.left_pow, tank.right_pow = 1.0, 0.0

    def clear_detour(self, tank):
        tank.detour, tank.detour_t = None, 0.0

    def aim_fire(self, tank, dt, tx, ty):
        desired = math.atan2(ty - tank.y, tx - tank.x)
        tank.turret += clamp(ang_diff(desired, tank.turret), -2.4 * dt, 2.4 * dt)
        if abs(ang_diff(desired, tank.turret)) < 0.22:
            self.fire(tank, quiet=not tank.player)

    def zap(self, tank, target, robot=False):
        if tank.zap_cd > 0 or not getattr(target, "alive", True):
            return
        if math.hypot(target.x - tank.x, target.y - tank.y) > ZAP_RANGE:
            return
        tank.zap_cd = 0.22 if robot else 0.35
        mx, my = tank.muzzle()
        self.bolts.append(Bolt(mx, my, target.x, target.y, 0.012 if robot else 0.1))
        self.sounds["zap"].play()
        target.hp -= 1
        if target.hp <= 0:
            target.alive = False
            target.remove = True
            self.waves_fx.append(Shockwave(target.x, target.y))
            self.sounds["explode"].play()

    def rest_turret(self, tank, dt):
        if self.player:
            desired = math.atan2(tank.y - self.player.y, tank.x - self.player.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -1.5 * dt, 1.5 * dt)

    def order_hold(self):
        fort = self.fort_at(self.player.x, self.player.y) if self.player else None
        if not fort:
            self.notice = "8 only works when the lead tank is inside a fort."
            self.notice_t = 1.5
            return
        self.hold_fort = True
        self.notice = "Defending the fort walls."
        self.notice_t = 2.0

    def order_fallback(self):
        n = 0
        for t in self.followers():
            if t.hp < t.max_hp * 0.8:
                t.retreat = True
                n += 1
        self.notice = f"{n} damaged tanks moving toward the lead."
        self.notice_t = 1.3

    def update_follower(self, tank, dt, blocks):
        if not self.player or not self.player.alive:
            return
        if tank.hp < tank.max_hp * 0.7:
            tank.retreat = True
        fort = self.fort_at(self.player.x, self.player.y)
        if tank.retreat and not self.hold_fort:
            self.drive_toward(tank, self.player.x, self.player.y)
        elif self.hold_fort and fort and fort.contains(self.player.x, self.player.y, 4):
            slots = fort.edge_slots(max(1, len(self.followers())))
            tx, ty = slots[(tank.follow_slot - 1) % len(slots)]
            self.drive_toward(tank, tx, ty)
        else:
            home = self.formation_point(tank)
            moved = math.hypot(tank.x - tank.last_x, tank.y - tank.last_y)
            blocked = self.tank_blocked(tank, blocks)
            if math.hypot(home[0] - tank.x, home[1] - tank.y) > 40 and (moved < 8 * dt or blocked):
                tank.stuck += dt
            else:
                tank.stuck = max(0.0, tank.stuck - dt * 2)
            if tank.detour is not None and tank.detour_t > 0:
                tank.detour_t -= dt
                self.drive_toward(tank, tank.detour[0], tank.detour[1])
                if tank.detour_t <= 0 or math.hypot(tank.detour[0] - tank.x, tank.detour[1] - tank.y) < 24:
                    self.clear_detour(tank)
            elif tank.stuck > 0.5 or blocked:
                tank.stuck = 0.15
                ang = self.player.angle + (1 if tank.follow_slot % 2 else -1) * random.uniform(0.7, 1.5)
                tank.detour = (tank.x + math.cos(ang) * 100, tank.y + math.sin(ang) * 100)
                tank.detour_t = 0.75
                tank.left_pow = tank.right_pow = -0.8
            else:
                self.drive_toward(tank, home[0], home[1], self.player.angle)
        tank.last_x, tank.last_y = tank.x, tank.y
        robot = self.nearest_robot(tank)
        if robot:
            desired = math.atan2(robot.y - tank.y, robot.x - tank.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -2.8 * dt, 2.8 * dt)
            if abs(ang_diff(desired, tank.turret)) < 0.45:
                self.zap(tank, robot, robot=True)
            return
        heli = self.nearest_heli(tank)
        if heli:
            desired = math.atan2(heli.y - tank.y, heli.x - tank.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -2.4 * dt, 2.4 * dt)
            if abs(ang_diff(desired, tank.turret)) < 0.35:
                if tank.rocket:
                    self.fire(tank, quiet=True)
                else:
                    self.zap(tank, heli)
            return
        if self.siege:
            b = self.nearest_building(tank)
            if b:
                self.aim_fire(tank, dt, b.rect.centerx, b.rect.centery)
                return
        e = self.pick_enemy(tank)
        if e:
            self.aim_fire(tank, dt, e.x, e.y)
        else:
            self.rest_turret(tank, dt)

    def update_garrison(self, tank, dt):
        fort = tank.home_fort
        if not fort:
            fort = self.fort_at(tank.x, tank.y)
            tank.home_fort = fort
        if not fort or fort.breached:
            return
        if not fort.contains(tank.x, tank.y, -20):
            self.drive_toward(tank, fort.rect.centerx, fort.rect.centery)
            return
        foes = self.allies()
        target = min(foes, key=lambda f: math.hypot(f.x - tank.x, f.y - tank.y)) if foes else None
        if target:
            desired = math.atan2(target.y - tank.y, target.x - tank.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -2.0 * dt, 2.0 * dt)
            if abs(ang_diff(desired, tank.turret)) < 0.25:
                self.fire(tank, quiet=True)
        tank.left_pow = tank.right_pow = 0.0

    def update_enemy(self, tank, dt, blocks):
        if tank.garrison:
            self.update_garrison(tank, dt)
            return
        if not self.player:
            return
        if not self.on_screen(tank.x, tank.y):
            tank.offscreen += dt
            if tank.offscreen >= OFFSCREEN_LIMIT:
                tank.remove = True
                tank.alive = False
                return
        else:
            tank.offscreen = 0.0
        if math.hypot(tank.x - tank.last_x, tank.y - tank.last_y) < 10 * dt or self.tank_blocked(tank, blocks):
            tank.stuck += dt
        else:
            tank.stuck = 0.0
        tank.last_x, tank.last_y = tank.x, tank.y
        if tank.stuck >= 30:
            self.relocate_enemy(tank)
            return

        target_pos = None
        if tank.attack_gate and self.player:
            fort = self.fort_at(self.player.x, self.player.y) or self.nearest_fort(self.player.x, self.player.y)
            if fort and not fort.breached:
                gx, gy = fort.gate_center()
                if not fort.contains(tank.x, tank.y, 8):
                    target_pos = (gx, gy)
                else:
                    target_pos = (self.player.x, self.player.y)

        foes = self.allies()
        target = min(foes, key=lambda f: math.hypot(f.x - tank.x, f.y - tank.y)) if foes else None
        if target_pos:
            self.drive_toward(tank, target_pos[0], target_pos[1])
            desired = math.atan2(target_pos[1] - tank.y, target_pos[0] - tank.x)
        elif target:
            desired = math.atan2(target.y - tank.y, target.x - tank.x)
            if math.hypot(target.x - tank.x, target.y - tank.y) > 190:
                self.drive_toward(tank, target.x, target.y)
        else:
            tank.left_pow = tank.right_pow = 0.45
            return

        tank.turret += clamp(ang_diff(desired, tank.turret), -2.1 * dt, 2.1 * dt)
        if abs(ang_diff(desired, tank.turret)) < 0.22:
            self.fire(tank, quiet=True)

    def relocate_enemy(self, tank):
        if not self.player or tank.garrison:
            tank.stuck = 0.0
            return
        ang = random.random() * math.tau
        dist = math.hypot(self.w, self.h) * 0.55 + 80
        tank.x = self.player.x + math.cos(ang) * dist
        tank.y = self.player.y + math.sin(ang) * dist
        tank.stuck = 0.0
        tank.offscreen = 0.0

    def pull_stuck(self):
        if not self.player:
            return
        n = 0
        for t in self.followers():
            home = self.formation_point(t)
            if t.stuck > 0.2 or t.detour or math.hypot(home[0] - t.x, home[1] - t.y) > 80:
                t.x, t.y = home
                t.stuck = 0.0
                self.clear_detour(t)
                fort = self.fort_at(t.x, t.y)
                if fort and fort.blocks_tank(pygame.Rect(t.x - 12, t.y - 12, 24, 24)):
                    fort.nudge_in(t)
                n += 1
        self.notice = f"Recalled {n} tanks."
        self.notice_t = 1.2

    def make_blue(self, x, y):
        rocket = self.blue_count() >= 100 and random.random() < 0.35
        t = Tank(x, y, True, rocket=rocket)
        if self.player:
            t.angle = self.player.angle
        return t

    def grant_building(self, n, kind):
        if not self.player:
            return
        for _ in range(n):
            self.tanks.append(self.make_blue(self.player.x + random.uniform(-20, 20), self.player.y + 40))
        self.assign_formation()
        self.sounds["wave"].play()
        self.notice = f"{kind} down. +{n}."
        self.notice_t = 2.0

    def destroy_building(self, b):
        b.alive = False
        self.rubble.append(Rubble(b))
        self.waves_fx.append(Shockwave(b.rect.centerx, b.rect.centery))
        self.sounds["explode"].play()
        self.shake = 12
        for _ in range(random.randint(2, 5)):
            self.robots.append(Robot(b.rect.centerx, b.rect.centery))
        self.grant_building(BUILDING_PAY[b.kind], b.kind)

    def claim_territory(self):
        if not self.player or not self.player.alive:
            return
        key = self.chunk_key(self.player.x, self.player.y)
        if key not in self.cleared and not any(self.chunk_key(e.x, e.y) == key for e in self.enemies()):
            self.cleared.add(key)

    def lose_territory(self):
        if self.cleared and self.player:
            key = min(self.cleared, key=lambda k: math.hypot(k[0] * CHUNK - self.player.x, k[1] * CHUNK - self.player.y))
            self.cleared.discard(key)
        self.red_pressure = min(32.0, self.red_pressure + 2.0)

    def add_blue(self, n, reason):
        if not self.player:
            return
        room = MAX_BLUE_REFILL - self.blue_count()
        if room <= 0:
            return
        for _ in range(min(n, room)):
            self.tanks.append(self.make_blue(self.player.x, self.player.y + 36))
        self.assign_formation()
        self.sounds["wave"].play()

    def spawn_wave(self):
        if not self.player or not self.player.alive:
            return
        n, wait = self.wave_plan()
        self.wave_serial += 1
        base = self.player.angle + math.pi
        attackers = int(n * random.uniform(1/3, 2/3))
        for i in range(n):
            ang = base + (i - (n - 1) / 2) * 0.1
            dist = random.uniform(660, 920)
            e = Tank(self.player.x + math.cos(ang) * dist, self.player.y + math.sin(ang) * dist, False)
            e.wave_id = self.wave_serial
            e.angle = math.atan2(self.player.y - e.y, self.player.x - e.x)
            e.turret = e.angle
            e.attack_gate = i < attackers
            self.tanks.append(e)
        self.wave_index += 1
        self.between = wait
        self.heli_between = max(4.0, wait / 2)
        self.notice = f"Wave {self.wave_index}: {n} red ({attackers} storming gates)."
        self.notice_t = 1.6

    def spawn_heli_swarm(self):
        if not self.player:
            return
        count = random.randint(6, 10)
        base_ang = random.random() * math.tau
        for i in range(count):
            ang = base_ang + (i - count / 2) * 0.14
            dist = random.uniform(680, 820)
            self.helis.append(Helicopter(self.player.x + math.cos(ang) * dist, self.player.y + math.sin(ang) * dist))

    def switch_player(self):
        nxt = next((t for t in self.tanks if t.friendly and t.alive and not t.exploding and t is not self.player), None)
        if self.player:
            self.player.player = False
        if not nxt:
            self.player = None
            self.notice = "All tanks lost."
            self.notice_t = 15
            self.mode = "gameover"
            self.gameover_timer = 15.0
            return
        nxt.player = True
        nxt.follow_slot = 0
        nxt.retreat = False
        self.player = nxt
        fort = self.fort_at(nxt.x, nxt.y)
        if fort:
            fort.nudge_in(nxt, 50)
        self.assign_formation()
        self.sounds["switch"].play()

    def save_game(self, path=None):
        path = path or SAVE_PATH
        state = {
            "tanks": [(t.x, t.y, t.angle, t.turret, t.friendly, t.player, t.rocket, t.hp, t.max_hp, t.follow_slot, t.wave_id, t.retreat, t.garrison, id(t.home_fort) if t.home_fort else None, t.attack_gate) for t in self.tanks if not t.remove],
            "buildings": [(b.rect.x, b.rect.y, b.kind, b.hp) for b in self.buildings if b.alive],
            "forts": [(f.rect.x, f.rect.y, f.gate, id(f), f.hp, f.max_hp, f.hits, f.breached) for f in self.forts],
            "cleared": list(self.cleared),
            "wave_index": self.wave_index,
            "wave_serial": self.wave_serial,
            "between": self.between,
            "heli_between": getattr(self, "heli_between", 15),
            "kills": self.kills,
            "god": self.god,
            "siege": self.siege,
            "formation": self.formation,
            "hold_fort": self.hold_fort,
            "zoom": self.zoom,
            "volume": self.volume,
            "building_count": self.building_count,
            "forts_spawned": self.forts_spawned,
        }
        try:
            with open(path, "wb") as f:
                pickle.dump(state, f)
            self.notice = f"Saved to {os.path.basename(path)}."
            self.notice_t = 1.8
        except OSError:
            self.notice = "Save failed."
            self.notice_t = 1.5

    def load_game(self, path=None):
        path = path or SAVE_PATH
        try:
            with open(path, "rb") as f:
                state = pickle.load(f)
        except (OSError, pickle.PickleError):
            self.notice = "Load failed."
            self.notice_t = 1.5
            return False
        fort_map = {}
        self.forts = []
        for item in state.get("forts", []):
            if len(item) >= 8:
                x, y, gate, fid, hp, max_hp, hits, breached = item[:8]
            else:
                x, y, gate, fid = item[:4]
                hp = max_hp = random.randint(1200, 2000)
                hits = 0
                breached = False
            if self.fort_too_close(x + FORT_SIZE/2, y + FORT_SIZE/2):
                continue
            f = Fort(x, y)
            f.gate = gate
            f.hp = hp
            f.max_hp = max_hp
            f.hits = hits
            f.breached = breached
            if breached:
                f.walls = []
            self.forts.append(f)
            fort_map[fid] = f
        self.tanks = []
        self.player = None
        for data in state["tanks"]:
            if len(data) >= 15:
                x, y, ang, tur, fr, pl, rk, hp, mhp, slot, wid, ret, gar, fort_id, atk = data[:15]
            else:
                x, y, ang, tur, fr, pl, rk, hp, mhp, slot, wid, ret = data[:12]
                gar = data[12] if len(data) > 12 else False
                fort_id = data[13] if len(data) > 13 else None
                atk = False
            t = Tank(x, y, fr, pl, rk, gar)
            t.angle, t.turret = ang, tur
            t.hp, t.max_hp = hp, mhp
            t.follow_slot = slot
            t.wave_id = wid
            t.retreat = ret
            t.attack_gate = atk
            if gar and fort_id in fort_map:
                t.home_fort = fort_map[fort_id]
            self.tanks.append(t)
            if pl:
                self.player = t
        if not self.player and self.allies():
            self.player = self.allies()[0]
            self.player.player = True
        self.buildings = []
        for x, y, kind, hp in state.get("buildings", []):
            b = Building(x, y, kind)
            b.hp = hp
            self.buildings.append(b)
        self.cleared = set(tuple(k) for k in state.get("cleared", []))
        self.wave_index = state.get("wave_index", 0)
        self.wave_serial = state.get("wave_serial", 0)
        self.between = state.get("between", 30)
        self.heli_between = state.get("heli_between", self.between / 2)
        self.kills = state.get("kills", 0)
        self.god = state.get("god", False)
        self.siege = state.get("siege", False)
        self.formation = state.get("formation", 1)
        self.hold_fort = state.get("hold_fort", False)
        self.zoom = state.get("zoom", 1.0)
        self.volume = state.get("volume", 0.7)
        self.building_count = state.get("building_count", 0)
        self.forts_spawned = state.get("forts_spawned", len([f for f in self.forts if not f.breached]))
        self.apply_volume()
        self.robots = []
        self.helis = []
        self.rubble = []
        self.bullets = []
        self.particles = []
        self.waves_fx = []
        self.bolts = []
        self.mode = "play"
        self.notice = f"Loaded {os.path.basename(path)}."
        self.notice_t = 1.8
        self.ensure_chunks()
        return True

    def start_demo(self):
        if not self.demo_files:
            return False
        path = random.choice(self.demo_files)
        if self.load_game(path):
            self.mode = "demo"
            self.demo_timer = 30.0
            self.notice = f"Demo: {os.path.basename(path)}"
            self.notice_t = 2.0
            return True
        return False

    def update(self, dt, keys):
        if self.mode == "gameover":
            self.gameover_timer -= dt
            if self.gameover_timer <= 0:
                self.mode = "start"
                self.attract_timer = 20.0
            return
        if self.mode == "demo":
            self.demo_timer -= dt
            if self.demo_timer <= 0:
                self.mode = "start"
                self.attract_timer = 20.0
                return
        if self.mode == "start":
            self.attract_timer -= dt
            if self.attract_timer <= 0 and self.demo_files:
                self.start_demo()
            return

        p = self.player
        blocks = self.solid_blocks()
        self.target_counts = {}
        if self.hold_fort and p and not self.fort_at(p.x, p.y):
            self.hold_fort = False
        if p and p.alive and self.mode == "play":
            if keys[pygame.K_z] or keys[pygame.K_LEFT]:
                p.left_pow = 1
            if keys[pygame.K_x] or keys[pygame.K_RIGHT]:
                p.right_pow = 1
            if keys[pygame.K_a] or keys[pygame.K_DOWN]:
                p.left_pow = p.right_pow = -1
            if keys[pygame.K_s] or keys[pygame.K_UP]:
                p.left_pow = max(p.left_pow, 1)
                p.right_pow = max(p.right_pow, 1)
            if keys[pygame.K_b]:
                p.turret -= 2.2 * dt
            if keys[pygame.K_m]:
                p.turret += 2.2 * dt
            robot = self.nearest_robot(p)
            heli = self.nearest_heli(p)
            if robot and self.auto_fire and not (keys[pygame.K_b] or keys[pygame.K_m]):
                desired = math.atan2(robot.y - p.y, robot.x - p.x)
                p.turret += clamp(ang_diff(desired, p.turret), -2.8 * dt, 2.8 * dt)
                if abs(ang_diff(desired, p.turret)) < 0.45:
                    self.zap(p, robot, robot=True)
            elif heli and self.auto_fire and not (keys[pygame.K_b] or keys[pygame.K_m]):
                desired = math.atan2(heli.y - p.y, heli.x - p.x)
                p.turret += clamp(ang_diff(desired, p.turret), -2.4 * dt, 2.4 * dt)
                if abs(ang_diff(desired, p.turret)) < 0.35:
                    self.fire(p) if p.rocket else self.zap(p, heli)
            elif self.siege and self.auto_fire and not (keys[pygame.K_b] or keys[pygame.K_m]):
                b = self.nearest_building(p)
                if b:
                    self.aim_fire(p, dt, b.rect.centerx, b.rect.centery)
            elif self.auto_fire and not (keys[pygame.K_b] or keys[pygame.K_m]):
                e = self.pick_enemy(p, 700)
                if e:
                    self.aim_fire(p, dt, e.x, e.y)
                else:
                    self.rest_turret(p, dt)
            if self.blue_count() < MAX_BLUE_REFILL:
                self.reinforce -= dt
                if self.reinforce <= 0:
                    self.reinforce = self.reinforce_interval()
                    self.add_blue(1, "Reinforcement.")
            else:
                self.reinforce = self.reinforce_interval()

        for t in list(self.tanks):
            if t.remove:
                continue
            ox, oy = t.x, t.y
            if t.player and t.alive:
                t.update(dt, self.particles, PLAYER_SPEED)
            elif t.friendly:
                if t.alive:
                    self.update_follower(t, dt, blocks)
                t.update(dt, self.particles, FOLLOW_SPEED)
            else:
                if t.alive:
                    self.update_enemy(t, dt, blocks)
                if t.alive or t.exploding:
                    t.update(dt, self.particles, ENEMY_SPEED)
            if t.alive and self.tank_blocked(t, blocks):
                t.x, t.y = ox, oy
                t.stuck += dt
                fort = self.fort_at(ox, oy)
                if fort and t.player:
                    fort.nudge_in(t, 20)

        for h in self.helis:
            if h.alive:
                h.update(dt, self.tanks, self.bullets)

        lost = False
        for b in self.bullets:
            b.update(dt)
            if not b.alive:
                continue
            from_inside = False
            for fort in self.forts:
                if fort.contains(b.x, b.y, 4):
                    from_inside = True
                    break
            for fort in self.forts:
                if fort.blocks_bullet(b.x, b.y, b.friendly, from_inside, b.rocket):
                    fort.take_hit(self.particles)
                    b.alive = False
                    break
            if not b.alive:
                continue
            for block in blocks:
                if block.blocks_fire() and block.rect.collidepoint(b.x, b.y):
                    b.alive = False
                    break
            if not b.alive:
                continue
            if b.friendly:
                for h in self.helis:
                    if h.alive and b.rocket and math.hypot(h.x - b.x, h.y - b.y) < 26:
                        h.alive = False
                        h.remove = True
                        b.alive = False
                        self.sounds["explode"].play()
                        break
            if not b.alive:
                continue
            if b.friendly and self.siege:
                for building in self.buildings:
                    if building.alive and building.rect.collidepoint(b.x, b.y):
                        building.hp -= 2 if b.rocket else 1
                        b.alive = False
                        self.sounds["hit"].play()
                        if building.hp <= 0:
                            self.destroy_building(building)
                        break
            if not b.alive:
                continue
            for t in self.tanks:
                if t.remove or t.exploding or not t.alive or t is b.owner or t.friendly == b.friendly:
                    continue
                if math.hypot(t.x - b.x, t.y - b.y) < TANK_R:
                    if not b.friendly and t.friendly and not b.rocket:
                        inside = any(f.contains(t.x, t.y, 8) and not f.breached for f in self.forts)
                        if inside and not any(f.gate_rect().collidepoint(b.x, b.y) for f in self.forts):
                            b.alive = False
                            continue
                    one_shot = b.rocket and b.friendly and not t.friendly and random.random() < 0.9
                    t.hit(70 if one_shot else 30, self.particles, self.waves_fx, force_kill=one_shot, god=self.god)
                    b.alive = False
                    self.sounds["hit"].play()
                    if t.exploding:
                        self.sounds["explode"].play()
                        if not t.friendly:
                            self.kills += 1
                        if t.player:
                            lost = True
                    break
        if lost and self.mode == "play":
            self.switch_player()

        for robot in list(self.robots):
            if robot.alive:
                victim = robot.update(dt, self.tanks)
                if victim:
                    victim.kill(self.particles, self.waves_fx, god=self.god)
                    robot.alive = False
                    robot.remove = True
                    self.sounds["explode"].play()
                    if victim.player and not victim.alive and self.mode == "play":
                        self.switch_player()
        self.robots = [r for r in self.robots if not r.remove]
        self.helis = [h for h in self.helis if not h.remove]
        self.rubble = [r for r in self.rubble if r.update(dt)]
        self.robot_timer -= dt
        if self.robot_timer <= 0 and self.player:
            self.robot_timer = random.uniform(14, 30)
            if random.random() < 0.4:
                ang = random.random() * math.tau
                self.robots.append(Robot(self.player.x + math.cos(ang) * 620, self.player.y + math.sin(ang) * 620))
        if self.player:
            self.heli_between -= dt
            if self.heli_between <= 0 and self.blue_count() >= 80:
                self.heli_between = max(4.0, self.between / 2)
                self.spawn_heli_swarm()
        self.build_timer -= dt
        if self.build_timer <= 0 and self.player:
            self.build_timer = 60.0
            ang = random.random() * math.tau
            dist = random.uniform(280, 520)
            bx = self.player.x + math.cos(ang) * dist
            by = self.player.y + math.sin(ang) * dist
            kind = random.choice(["factory", "power", "command"])
            self.buildings.append(Building(bx, by, kind))
            self.building_count += 1
            self.try_spawn_fort(bx, by)
            self.notice = "A building appeared nearby."
            self.notice_t = 1.4

        self.bullets = [b for b in self.bullets if b.alive]
        self.particles = [p for p in self.particles if p.update(dt)]
        self.waves_fx = [w for w in self.waves_fx if w.update(dt)]
        self.bolts = [b for b in self.bolts if b.update(dt)]
        self.buildings = [b for b in self.buildings if b.alive]
        self.tanks = [t for t in self.tanks if not t.remove]
        self.shake = max(0.0, self.shake - dt * 28)
        self.claim_territory()
        if self.enemies():
            self.red_pressure = min(32.0, self.red_pressure + dt * 0.35)
            self.loss_timer -= dt
            if self.loss_timer <= 0:
                self.loss_timer = 1.5 if len({e.wave_id for e in self.enemies()}) > 1 else 3.0
                self.lose_territory()
        else:
            self.red_pressure = max(0.0, self.red_pressure - dt)
            self.loss_timer = 3.0
        if self.player and self.player.alive:
            self.between = max(0.0, self.between - dt)
            if self.between <= 0 and self.mode in ("play", "demo"):
                self.spawn_wave()
            self.cam[0] = self.player.x - self.w / 2
            self.cam[1] = self.player.y - self.h / 2
        if self.shake:
            self.cam[0] += random.uniform(-self.shake, self.shake)
            self.cam[1] += random.uniform(-self.shake, self.shake)
        self.ensure_chunks()
        self.notice_t = max(0.0, self.notice_t - dt)
        if self.mode == "play" and not self.allies():
            self.mode = "gameover"
            self.gameover_timer = 15.0

    def draw(self):
        if self.mode == "start":
            self.screen.fill((20, 30, 24))
            title = self.big.render("TANK TERRITORY", True, (140, 200, 160))
            self.screen.blit(title, (self.w // 2 - title.get_width() // 2, 140))
            lines = [
                "SPACE or ENTER or R — start",
                "F5 — load tankDemo.dat",
                "F4 — save (while playing)",
                "K/L volume   -/+ zoom",
                f"Demo in {int(max(0, self.attract_timer))}s" if self.demo_files else "No demos found",
            ]
            for i, line in enumerate(lines):
                self.screen.blit(self.font.render(line, True, (200, 210, 190)), (self.w // 2 - 220, 260 + i * 28))
            return
        self.screen.fill((52, 74, 46))
        to = self.to_screen
        z = self.zoom
        for key in self.cleared:
            sx, sy = to(key[0] * CHUNK, key[1] * CHUNK)
            pygame.draw.rect(self.screen, (42, 78, 62), (sx, sy, CHUNK * z, CHUNK * z))
        for fort in self.forts:
            fort.draw(self.screen, to, z, self.particles)
        for block in self.solid_blocks():
            if block.kind != "block":
                block.draw(self.screen, to, z)
        for rub in self.rubble:
            rub.draw(self.screen, to, z)
        for b in self.buildings:
            b.draw(self.screen, to, z, self.small, self.particles)
        for block in self.solid_blocks():
            if block.kind == "block":
                block.draw(self.screen, to, z)
        for r in self.robots:
            r.draw(self.screen, to, z)
        for t in self.tanks:
            if not t.player:
                t.draw(self.screen, to, z)
        if self.player:
            self.player.draw(self.screen, to, z)
        for h in self.helis:
            if h.alive:
                h.draw(self.screen, to, z)
        for b in self.bullets:
            b.draw(self.screen, self.particles, z, to)
        for bolt in self.bolts:
            bolt.draw(self.screen, to, z)
        for p in self.particles:
            p.draw(self.screen, to, z)
        for w in self.waves_fx:
            w.draw(self.screen, to, z)
        hp = max(0, int(self.player.hp)) if self.player and self.player.alive else 0
        lines = [
            "ZXAS/arrows drive  B/M turret  T buildings  G god  K/L vol  -/+ zoom  F4 save  F5 load  8 fort",
            f"HP {hp}{' GOD' if self.god else ''}  blue {self.blue_count()}  red {len(self.enemies())}  heli {len([h for h in self.helis if h.alive])}  bots {len(self.robots)}  zoom {self.zoom:.1f}  vol {int(self.volume*100)}%  next {int(self.between)}s",
        ]
        for i, line in enumerate(lines):
            self.screen.blit(self.font.render(line, True, (235, 235, 220)), (12, 8 + i * 20))
        if self.notice_t > 0:
            self.screen.blit(self.font.render(self.notice, True, (255, 220, 120)), (12, 52))
        if self.mode == "gameover":
            label = self.big.render("ALL LOST", True, (255, 80, 60))
            self.screen.blit(label, (self.w // 2 - label.get_width() // 2, self.h // 2 - 40))
            sub = self.font.render(f"Returning in {int(self.gameover_timer)}s   R to restart", True, (255, 220, 140))
            self.screen.blit(sub, (self.w // 2 - sub.get_width() // 2, self.h // 2 + 20))
        if self.mode == "demo":
            sub = self.font.render(f"DEMO {int(self.demo_timer)}s  R to start", True, (255, 220, 140))
            self.screen.blit(sub, (self.w - 220, 12))
        if self.paused and self.mode == "play":
            label = self.big.render("PAUSED", True, (255, 230, 140))
            self.screen.blit(label, (self.w // 2 - label.get_width() // 2, self.h // 2 - 24))

    def run(self):
        running = True
        while running:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.w, self.h = max(640, event.w), max(480, event.h)
                    self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r and self.mode in ("start", "gameover", "demo"):
                        self.reset()
                    elif self.mode == "start":
                        if event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r):
                            self.reset()
                        elif event.key == pygame.K_F5:
                            self.load_game()
                    elif self.mode == "play":
                        if event.key == pygame.K_p:
                            self.paused = not self.paused
                        elif self.paused:
                            continue
                        elif event.key == pygame.K_SPACE:
                            self.auto_fire = not self.auto_fire
                        elif event.key == pygame.K_t:
                            self.siege = not self.siege
                            self.notice = "Targeting buildings." if self.siege else "Targeting enemies."
                            self.notice_t = 1.2
                        elif event.key == pygame.K_g:
                            self.god = not self.god
                            self.notice = "God mode on." if self.god else "God mode off."
                            self.notice_t = 1.2
                            self.sounds["toggle"].play()
                        elif event.key == pygame.K_k:
                            self.volume = max(0.0, self.volume - 0.1)
                            self.apply_volume()
                            self.notice = f"Volume {int(self.volume * 100)}%"
                            self.notice_t = 0.8
                        elif event.key == pygame.K_l:
                            self.volume = min(1.0, self.volume + 0.1)
                            self.apply_volume()
                            self.notice = f"Volume {int(self.volume * 100)}%"
                            self.notice_t = 0.8
                        elif event.key == pygame.K_MINUS or event.key == pygame.K_KP_MINUS:
                            self.zoom = max(0.4, self.zoom - 0.15)
                            self.notice = f"Zoom {self.zoom:.1f}"
                            self.notice_t = 0.6
                        elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS or event.key == pygame.K_KP_PLUS:
                            self.zoom = min(2.5, self.zoom + 0.15)
                            self.notice = f"Zoom {self.zoom:.1f}"
                            self.notice_t = 0.6
                        elif event.key == pygame.K_F4:
                            self.save_game()
                        elif event.key == pygame.K_F5:
                            self.load_game()
                        elif event.key in (pygame.K_1, pygame.K_KP1):
                            self.set_formation(1)
                        elif event.key in (pygame.K_2, pygame.K_KP2):
                            self.set_formation(2)
                        elif event.key in (pygame.K_3, pygame.K_KP3):
                            self.set_formation(3)
                        elif event.key in (pygame.K_4, pygame.K_KP4):
                            self.set_formation(4)
                        elif event.key in (pygame.K_5, pygame.K_KP5):
                            self.set_formation(5)
                        elif event.key in (pygame.K_6, pygame.K_KP6):
                            self.set_formation(6)
                        elif event.key in (pygame.K_7, pygame.K_KP7):
                            self.pull_stuck()
                        elif event.key in (pygame.K_8, pygame.K_KP8):
                            self.order_hold()
                        elif event.key in (pygame.K_9, pygame.K_KP9):
                            self.order_fallback()
            if self.mode in ("play", "demo") and not self.paused:
                self.update(dt, pygame.key.get_pressed())
            elif self.mode == "gameover":
                self.update(dt, {})
            elif self.mode == "start":
                self.update(dt, {})
            self.draw()
            pygame.display.flip()
        x, y = get_window_pos()
        save_config(self.w, self.h, x, y)
        pygame.quit()

if __name__ == "__main__":
    Game().run()