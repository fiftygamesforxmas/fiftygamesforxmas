"""
Tank Territory
Z / X  — treads forward
A / S  — treads reverse
B / M  — turret
SPACE  — toggle auto-fire
P      — pause
T      — during a wave, toggle buildings / red tanks
1–6    — formations
7      — pull stuck blue tanks in (last 3s before a raid)
R      — restart
ESC    — quit
"""

import array
import json
import math
import os
import random
import sys

import pygame

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tank_config.json")
CHUNK = 520
TANK_R = 20
BULLET_SPEED = 520
PLAYER_SPEED = 128
FOLLOW_SPEED = 150
ENEMY_SPEED = 96
WAVE_SIZES = (2, 3, 5, 10, 15, 20)
MAX_BLUE = 20
FORM_NAMES = {1: "line", 2: "tight circle", 3: "loose ring", 4: "triangle", 5: "square", 6: "scatter"}
BUILDING_PAY = {"factory": 5, "power": 10, "command": 15}

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

def make_noise(duration, volume=0.45):
    rate = 44100
    n = max(1, int(rate * duration))
    buf = array.array("h")
    level = volume * 32767
    for i in range(n):
        level *= 0.9978
        thud = math.sin(2 * math.pi * 60 * i / rate) * level * 0.45
        sample = int(clamp(random.uniform(-level, level) * 0.7 + thud, -32767, 32767))
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
    def __init__(self, x, y, angle, owner, friendly):
        self.x, self.y = x, y
        self.vx = math.cos(angle) * BULLET_SPEED
        self.vy = math.sin(angle) * BULLET_SPEED
        self.owner = owner
        self.friendly = friendly
        self.alive = True
        self.life = 1.5

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, cam):
        pygame.draw.circle(surf, (255, 236, 160), (int(self.x - cam[0]), int(self.y - cam[1])), 3)

class Bolt:
    def __init__(self, x1, y1, x2, y2):
        self.pts = [(x1, y1)]
        steps = 6
        for i in range(1, steps):
            t = i / steps
            self.pts.append((x1 + (x2 - x1) * t + random.uniform(-10, 10), y1 + (y2 - y1) * t + random.uniform(-10, 10)))
        self.pts.append((x2, y2))
        self.life = 0.12

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf, cam):
        pts = [(int(x - cam[0]), int(y - cam[1])) for x, y in self.pts]
        if len(pts) > 1:
            pygame.draw.lines(surf, (180, 230, 255), False, pts, 3)
            pygame.draw.lines(surf, (255, 255, 220), False, pts, 1)

class Particle:
    def __init__(self, x, y, color, speed, life, radius, gravity=0, drag=0.0, kind="spark"):
        ang = random.random() * math.tau
        spd = random.uniform(0.35, 1.0) * speed
        self.x, self.y = x, y
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd
        self.color = color
        self.life = life
        self.max_life = max(0.01, life)
        self.radius = radius
        self.gravity = gravity
        self.drag = drag
        self.kind = kind

    def update(self, dt):
        self.vx *= 1.0 - self.drag * dt
        self.vy *= 1.0 - self.drag * dt
        self.vy += self.gravity * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surf, cam):
        a = clamp(self.life / self.max_life, 0, 1)
        col = tuple(int(c * (0.35 + 0.65 * a)) for c in self.color)
        pos = (int(self.x - cam[0]), int(self.y - cam[1]))
        r = max(1, int(self.radius * (0.4 + 0.6 * a)))
        if self.kind == "smoke":
            pygame.draw.circle(surf, col, pos, r + 2)
        elif self.kind == "debris":
            pygame.draw.rect(surf, col, (pos[0] - r, pos[1] - r // 2, r * 2, r))
        else:
            pygame.draw.circle(surf, col, pos, r)

class Shockwave:
    def __init__(self, x, y):
        self.x, self.y, self.life, self.max_life = x, y, 0.38, 0.38

    def update(self, dt):
        self.life -= dt
        return self.life > 0

    def draw(self, surf, cam):
        a = self.life / self.max_life
        pygame.draw.circle(surf, (255, int(180 * a), int(60 * a)), (int(self.x - cam[0]), int(self.y - cam[1])), int(18 + (1 - a) * 78), 3)

class Block:
    def __init__(self, x, y, w, h, kind):
        self.rect = pygame.Rect(x, y, w, h)
        self.kind = kind

    def blocks_fire(self):
        return self.kind == "block"

    def draw(self, surf, cam):
        r = self.rect.move(-cam[0], -cam[1])
        if self.kind == "block":
            pygame.draw.rect(surf, (92, 96, 102), r)
            pygame.draw.rect(surf, (48, 50, 56), r, 3)
        elif self.kind == "rock":
            pygame.draw.ellipse(surf, (110, 108, 100), r)
        else:
            pygame.draw.rect(surf, (86, 58, 36), (r.centerx - 3, r.bottom - 14, 6, 14))
            pygame.draw.circle(surf, (46, 110, 52), (r.centerx, r.centery - 4), max(8, r.w // 3))

class Building:
    def __init__(self, x, y, kind):
        self.kind = kind
        self.w = random.randint(118, 168)
        self.h = random.randint(48, 68)
        self.rect = pygame.Rect(x, y, self.w, self.h)
        self.hp = 20
        self.alive = True

    def draw(self, surf, cam, font):
        r = self.rect.move(-cam[0], -cam[1])
        body = {"factory": (78, 82, 88), "power": (92, 86, 62), "command": (62, 74, 96)}[self.kind]
        pygame.draw.rect(surf, body, r)
        pygame.draw.rect(surf, (30, 32, 36), r, 3)
        for i in range(3):
            wx = r.x + 14 + i * (r.w - 28) / 2
            pygame.draw.rect(surf, (150, 190, 210), (wx, r.y + 14, 18, 12))
            pygame.draw.rect(surf, (40, 50, 60), (wx, r.y + 14, 18, 12), 1)
        if self.kind == "power":
            pygame.draw.line(surf, (230, 190, 60), (r.centerx, r.y), (r.centerx, r.y - 16), 3)
        elif self.kind == "command":
            pygame.draw.circle(surf, (80, 160, 220), (r.centerx, r.y - 8), 6)
        label = {"factory": "PLANT", "power": "POWER", "command": "C2"}[self.kind]
        surf.blit(font.render(f"{label} {self.hp}", True, (230, 230, 220)), (r.x + 6, r.y + r.h - 18))

class Robot:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.hp = 3
        self.alive = True
        self.phase = random.random() * math.tau
        self.arm = 0.0
        self.remove = False

    def update(self, dt, tanks):
        self.arm += dt * 9
        self.phase += dt * 4
        foes = [t for t in tanks if t.friendly and t.alive and not t.exploding]
        if not foes:
            return None
        target = min(foes, key=lambda t: math.hypot(t.x - self.x, t.y - self.y))
        desired = math.atan2(target.y - self.y, target.x - self.x)
        wobble = math.sin(self.phase) * 1.4
        self.x += math.cos(desired + wobble) * 78 * dt
        self.y += math.sin(desired + wobble) * 78 * dt
        if math.hypot(target.x - self.x, target.y - self.y) < 22:
            return target
        return None

    def draw(self, surf, cam):
        px, py = int(self.x - cam[0]), int(self.y - cam[1])
        pygame.draw.rect(surf, (150, 90, 40), (px - 7, py - 8, 14, 16))
        pygame.draw.circle(surf, (190, 120, 50), (px, py - 12), 6)
        swing = math.sin(self.arm) * 8
        pygame.draw.line(surf, (90, 50, 30), (px - 7, py - 2), (px - 16, py - 10 + swing), 3)
        pygame.draw.line(surf, (90, 50, 30), (px + 7, py - 2), (px + 16, py - 10 - swing), 3)

class Tank:
    def __init__(self, x, y, friendly, player=False):
        self.x, self.y = float(x), float(y)
        self.angle = -math.pi / 2
        self.turret = self.angle
        self.friendly = friendly
        self.player = player
        self.hp = 110 if friendly else 70
        self.alive = True
        self.fire_level = 0.0
        self.exploding = False
        self.explode_t = 0.0
        self.cooldown = random.uniform(0.0, 0.3)
        self.left_pow = self.right_pow = 0.0
        self.follow_slot = 0
        self.ai_timer = random.uniform(0.3, 0.9)
        self.remove = False
        self.flash = 0.0
        self.stuck = 0.0
        self.detour = None
        self.detour_t = 0.0
        self.last_x, self.last_y = x, y
        self.scatter = None
        self.wave_id = 0
        self.zap_cd = 0.0

    def muzzle(self):
        return self.x + math.cos(self.turret) * 28, self.y + math.sin(self.turret) * 28

    def hit(self, dmg, particles, waves):
        if not self.alive or self.exploding:
            return
        self.hp -= dmg
        self.fire_level = min(1.0, self.fire_level + 0.55)
        self.flash = 0.08
        for _ in range(8):
            particles.append(Particle(self.x, self.y, random.choice([(255, 220, 120), (255, 90, 30)]), 150, 0.18, 2, drag=2.5))
        if self.hp <= 0:
            self.exploding = True
            self.explode_t = 0.4
            self.alive = False
            waves.append(Shockwave(self.x, self.y))

    def kill(self, particles, waves):
        if self.exploding or not self.alive:
            return
        self.hp = 0
        self.exploding = True
        self.explode_t = 0.28
        self.alive = False
        waves.append(Shockwave(self.x, self.y))
        for _ in range(16):
            particles.append(Particle(self.x, self.y, (255, 140, 40), 220, 0.35, 4))

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
        if self.exploding:
            self.explode_t -= dt
            if self.explode_t <= 0:
                self.remove = True
                for _ in range(18):
                    particles.append(Particle(self.x, self.y, random.choice([(255, 200, 80), (80, 80, 80)]), 240, 0.4, 4))
            return
        if self.fire_level > 0:
            self.fire_level = max(0.0, self.fire_level - dt * 0.22)
        self.update_motion(dt, speed)

    def draw(self, surf, cam):
        if self.remove:
            return
        px, py = int(self.x - cam[0]), int(self.y - cam[1])
        body = (120, 190, 255) if self.player else ((70, 130, 220) if self.friendly else (200, 60, 60))
        if self.flash > 0:
            body = (255, 230, 160)
        if self.exploding:
            body = (255, 120, 30)
        c, s = math.cos(self.angle), math.sin(self.angle)
        pts = [(px + dx * c - dy * s, py + dx * s + dy * c) for dx, dy in ((-15, -11), (16, -11), (16, 11), (-15, 11))]
        pygame.draw.polygon(surf, body, pts)
        pygame.draw.polygon(surf, (20, 22, 28), pts, 2)
        if not self.exploding:
            pygame.draw.circle(surf, body, (px, py), 8)
            pygame.draw.line(surf, (28, 30, 36), (px, py), (px + math.cos(self.turret) * 24, py + math.sin(self.turret) * 24), 4)

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
            "hit": make_noise(0.09, 0.28),
            "explode": make_noise(0.42, 0.62),
            "toggle": make_tone(640, 0.05, 0.2, decay=False),
            "switch": make_tone(420, 0.1, 0.22),
            "wave": make_tone(520, 0.16, 0.24),
            "zap": make_tone(880, 0.05, 0.18, decay=False),
        }
        self.chunks = {}
        self.reset()

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
        self.robots, self.buildings = [], []
        self.cam = [0.0, 0.0]
        self.shake = 0.0
        self.auto_fire = True
        self.paused = False
        self.siege = False
        self.kills = 0
        self.wave_index = 0
        self.wave_serial = 0
        self.between = random.uniform(30, 60)
        self.cleared = set()
        self.built = set()
        self.loss_timer = 3.0
        self.red_pressure = 0.0
        self.robot_timer = random.uniform(18, 40)
        self.reinforce = 32.0
        self.notice = "T toggles buildings only while a red wave is on the field."
        self.notice_t = 3.2
        self.chunks.clear()
        self.ensure_chunks()
        self.spawn_wave()

    def wave_count(self):
        return WAVE_SIZES[min(self.wave_index, len(WAVE_SIZES) - 1)]

    def blue_count(self):
        return sum(1 for t in self.tanks if t.friendly and t.alive and not t.exploding)

    def allies(self):
        return [t for t in self.tanks if t.friendly and t.alive and not t.exploding]

    def followers(self):
        return [t for t in self.tanks if t.friendly and t.alive and not t.player]

    def enemies(self):
        return [t for t in self.tanks if not t.friendly and t.alive and not t.exploding]

    def under_attack(self):
        return bool(self.enemies())

    def leftover_waves(self):
        return len({e.wave_id for e in self.enemies()}) > 1

    def reinforce_interval(self):
        base = max(8.0, 32.0 - len(self.cleared) * 1.4)
        if self.enemies():
            base = max(base, 32.0) + self.red_pressure
        return clamp(base, 8.0, 64.0)

    def chunk_key(self, x, y):
        return int(math.floor(x / CHUNK)), int(math.floor(y / CHUNK))

    def build_chunk(self, cx, cy):
        rng = random.Random((cx * 73417 + cy * 99173) & 0xFFFFFFFF)
        items = []
        if abs(cx) <= 1 and abs(cy) <= 1:
            return items
        for _ in range(rng.randint(1, 3)):
            kind = rng.choice(["tree", "rock", "block", "block"])
            w = rng.randint(36, 80) if kind == "block" else rng.randint(26, 42)
            h = rng.randint(28, 60) if kind == "block" else rng.randint(26, 42)
            items.append(Block(cx * CHUNK + rng.randint(16, CHUNK - 90), cy * CHUNK + rng.randint(16, CHUNK - 80), w, h, kind))
        return items

    def ensure_chunks(self):
        x0, y0 = self.chunk_key(self.cam[0] - CHUNK, self.cam[1] - CHUNK)
        x1, y1 = self.chunk_key(self.cam[0] + self.w + CHUNK, self.cam[1] + self.h + CHUNK)
        for cy in range(y0 - 1, y1 + 2):
            for cx in range(x0 - 1, x1 + 2):
                self.chunks.setdefault((cx, cy), self.build_chunk(cx, cy))
                if (cx, cy) not in self.built and not (abs(cx) <= 1 and abs(cy) <= 1):
                    self.built.add((cx, cy))
                    if random.random() < 0.55:
                        kind = random.choice(["factory", "factory", "factory", "power", "command"])
                        self.buildings.append(Building(cx * CHUNK + random.randint(40, 280), cy * CHUNK + random.randint(40, 300), kind))
        self.chunks = {k: v for k, v in self.chunks.items() if abs(k[0] - x0) < 7 and abs(k[1] - y0) < 7}
        self.buildings = [b for b in self.buildings if b.alive and abs(self.chunk_key(b.rect.x, b.rect.y)[0] - x0) < 8]

    def solid_blocks(self):
        blocks = []
        x0, y0 = self.chunk_key(self.cam[0] - CHUNK, self.cam[1] - CHUNK)
        x1, y1 = self.chunk_key(self.cam[0] + self.w + CHUNK, self.cam[1] + self.h + CHUNK)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                blocks.extend(i for i in self.chunks.get((cx, cy), []) if isinstance(i, Block))
        return blocks

    def tank_blocked(self, tank, blocks):
        box = pygame.Rect(tank.x - 14, tank.y - 12, 28, 24)
        if any(b.kind == "block" and box.colliderect(b.rect.inflate(-6, -6)) for b in blocks):
            return True
        return any(box.colliderect(b.rect) for b in self.buildings if b.alive)

    def fire(self, tank, quiet=False):
        if tank.cooldown > 0 or not tank.alive or tank.exploding:
            return
        tank.cooldown = 0.34 if tank.player else 0.48
        mx, my = tank.muzzle()
        self.bullets.append(Bullet(mx, my, tank.turret, tank, tank.friendly))
        if tank.player and not quiet:
            self.sounds["fire"].play()

    def nearest_enemy(self, tank, limit=680):
        best, best_d = None, limit
        for e in self.enemies():
            d = math.hypot(e.x - tank.x, e.y - tank.y)
            if d < best_d:
                best, best_d = e, d
        return best

    def nearest_robot(self, tank, limit=520):
        best, best_d = None, limit
        for r in self.robots:
            if not r.alive:
                continue
            d = math.hypot(r.x - tank.x, r.y - tank.y)
            if d < best_d:
                best, best_d = r, d
        return best

    def nearest_building(self, tank, limit=640):
        best, best_d = None, limit
        for b in self.buildings:
            if not b.alive:
                continue
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
        self.formation = mode
        if mode == 6:
            for t in self.followers():
                t.scatter = None
        self.assign_formation()
        self.notice = f"Formation {mode}: {FORM_NAMES[mode]}."
        self.notice_t = 1.6

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
            r = 100
            return perimeter_point(slot, count, [(p.x - r, p.y - r), (p.x + r, p.y - r), (p.x + r, p.y + r), (p.x - r, p.y + r)])
        if tank.scatter is None:
            ang, dist = random.random() * math.tau, random.uniform(40, self.w * 0.5)
            tank.scatter = (math.cos(ang) * dist, math.sin(ang) * dist)
        return p.x + tank.scatter[0], p.y + tank.scatter[1]

    def drive_toward(self, tank, tx, ty, match=None):
        desired = math.atan2(ty - tank.y, tx - tank.x)
        diff = ang_diff(desired, tank.angle)
        if math.hypot(tx - tank.x, ty - tank.y) < 18:
            tank.left_pow = tank.right_pow = 0.0
            if match is not None:
                tank.angle += clamp(ang_diff(match, tank.angle), -0.08, 0.08)
            return
        tank.left_pow = tank.right_pow = 1.0
        if diff > 0.1:
            tank.right_pow, tank.left_pow = 1.0, 0.0
        elif diff < -0.1:
            tank.left_pow, tank.right_pow = 1.0, 0.0

    def clear_detour(self, tank):
        tank.detour, tank.detour_t = None, 0.0

    def aim_fire(self, tank, dt, tx, ty):
        desired = math.atan2(ty - tank.y, tx - tank.x)
        tank.turret += clamp(ang_diff(desired, tank.turret), -2.4 * dt, 2.4 * dt)
        if abs(ang_diff(desired, tank.turret)) < 0.22:
            self.fire(tank, quiet=not tank.player)

    def zap(self, tank, robot):
        if tank.zap_cd > 0 or not robot.alive:
            return
        tank.zap_cd = 0.45
        mx, my = tank.muzzle()
        self.bolts.append(Bolt(mx, my, robot.x, robot.y))
        self.sounds["zap"].play()
        robot.hp -= 1
        if robot.hp <= 0:
            robot.alive = False
            robot.remove = True
            self.waves_fx.append(Shockwave(robot.x, robot.y))
            for _ in range(10):
                self.particles.append(Particle(robot.x, robot.y, (120, 220, 255), 140, 0.3, 3))

    def update_follower(self, tank, dt, blocks):
        if not self.player or not self.player.alive:
            return
        home = self.formation_point(tank)
        moved = math.hypot(tank.x - tank.last_x, tank.y - tank.last_y)
        blocked = self.tank_blocked(tank, blocks)
        if math.hypot(home[0] - tank.x, home[1] - tank.y) > 36 and (moved < 8 * dt or blocked):
            tank.stuck += dt
        else:
            tank.stuck = max(0.0, tank.stuck - dt * 2)
        tank.last_x, tank.last_y = tank.x, tank.y
        if tank.detour is not None and tank.detour_t > 0:
            tank.detour_t -= dt
            dx, dy = tank.detour
            self.drive_toward(tank, dx, dy)
            if tank.detour_t <= 0 or math.hypot(dx - tank.x, dy - tank.y) < 24:
                self.clear_detour(tank)
        elif tank.stuck > 0.45 or blocked:
            tank.stuck = 0.15
            ang = self.player.angle + (1 if tank.follow_slot % 2 else -1) * random.uniform(0.8, 1.6)
            tank.detour = (tank.x + math.cos(ang) * 90, tank.y + math.sin(ang) * 90)
            tank.detour_t = 0.7
            tank.left_pow = tank.right_pow = -0.8
        else:
            self.drive_toward(tank, home[0], home[1], self.player.angle)
        robot = self.nearest_robot(tank)
        if robot:
            desired = math.atan2(robot.y - tank.y, robot.x - tank.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -2.6 * dt, 2.6 * dt)
            if abs(ang_diff(desired, tank.turret)) < 0.3:
                self.zap(tank, robot)
            return
        if self.under_attack() and self.siege:
            b = self.nearest_building(tank)
            if b:
                self.aim_fire(tank, dt, b.rect.centerx, b.rect.centery)
                return
        e = self.nearest_enemy(tank)
        if e:
            self.aim_fire(tank, dt, e.x, e.y)
        else:
            tank.turret += clamp(ang_diff(self.player.angle, tank.turret), -2.0 * dt, 2.0 * dt)

    def relocate_enemy(self, tank):
        if not self.player:
            tank.stuck = 0.0
            return
        ang = random.random() * math.tau
        dist = math.hypot(self.w, self.h) * 0.55 + 70
        tank.x = self.player.x + math.cos(ang) * dist
        tank.y = self.player.y + math.sin(ang) * dist
        tank.angle = math.atan2(self.player.y - tank.y, self.player.x - tank.x)
        tank.turret = tank.angle
        tank.stuck = 0.0
        tank.last_x, tank.last_y = tank.x, tank.y

    def update_enemy(self, tank, dt, blocks):
        if not self.player:
            tank.stuck = 0.0
            tank.left_pow = tank.right_pow = 0.3
            return
        if math.hypot(tank.x - tank.last_x, tank.y - tank.last_y) < 10 * dt or self.tank_blocked(tank, blocks):
            tank.stuck += dt
        else:
            tank.stuck = 0.0
        tank.last_x, tank.last_y = tank.x, tank.y
        if tank.stuck >= 30:
            self.relocate_enemy(tank)
            return
        foes = self.allies()
        target = min(foes, key=lambda f: math.hypot(f.x - tank.x, f.y - tank.y)) if foes else None
        if target:
            desired = math.atan2(target.y - tank.y, target.x - tank.x)
            tank.turret += clamp(ang_diff(desired, tank.turret), -2.1 * dt, 2.1 * dt)
            if math.hypot(target.x - tank.x, target.y - tank.y) > 200:
                self.drive_toward(tank, target.x, target.y)
            if abs(ang_diff(desired, tank.turret)) < 0.2:
                self.fire(tank, quiet=True)
        else:
            tank.left_pow = tank.right_pow = 0.5

    def pull_stuck(self):
        if not self.player or not (0 < self.between <= 3):
            self.notice = "7 only works in the last 3 seconds before a raid."
            self.notice_t = 1.6
            return
        n = 0
        for t in self.followers():
            home = self.formation_point(t)
            if t.stuck > 0.3 or t.detour or math.hypot(home[0] - t.x, home[1] - t.y) > 90:
                t.x, t.y = home
                t.stuck = 0.0
                self.clear_detour(t)
                n += 1
        self.notice = f"Pulled {n} stuck tanks into formation."
        self.notice_t = 1.6

    def grant_building(self, n, kind):
        if not self.player:
            return
        for _ in range(n):
            mate = Tank(self.player.x + random.uniform(-30, 30), self.player.y + 50, True)
            mate.angle = self.player.angle
            self.tanks.append(mate)
        self.assign_formation()
        self.sounds["wave"].play()
        self.notice = f"{kind} down. +{n} tanks ({self.blue_count()})."
        self.notice_t = 2.2

    def destroy_building(self, b):
        b.alive = False
        self.waves_fx.append(Shockwave(b.rect.centerx, b.rect.centery))
        self.sounds["explode"].play()
        self.shake = max(self.shake, 10)
        for _ in range(random.randint(2, 5)):
            self.robots.append(Robot(b.rect.centerx + random.uniform(-20, 20), b.rect.centery + random.uniform(-10, 10)))
        self.grant_building(BUILDING_PAY[b.kind], b.kind)

    def claim_territory(self):
        if not self.player or not self.player.alive:
            return
        key = self.chunk_key(self.player.x, self.player.y)
        if key in self.cleared or any(self.chunk_key(e.x, e.y) == key for e in self.enemies()):
            return
        self.cleared.add(key)

    def lose_territory(self):
        if self.cleared and self.player:
            key = min(self.cleared, key=lambda k: math.hypot(k[0] * CHUNK - self.player.x, k[1] * CHUNK - self.player.y))
            self.cleared.discard(key)
        self.red_pressure = min(32.0, self.red_pressure + 2.0)

    def add_blue(self, n, reason):
        if not self.player:
            return 0
        room = MAX_BLUE - self.blue_count()
        if room <= 0:
            return 0
        gained = min(n, room)
        for _ in range(gained):
            self.tanks.append(Tank(self.player.x, self.player.y + 40, True))
        self.assign_formation()
        self.notice = f"{reason} +{gained} ({self.blue_count()})."
        self.notice_t = 1.8
        self.sounds["wave"].play()
        return gained

    def spawn_wave(self):
        if not self.player or not self.player.alive:
            return
        n = self.wave_count()
        self.wave_serial += 1
        base = self.player.angle + math.pi
        for i in range(n):
            ang = base + (i - (n - 1) / 2) * 0.18
            dist = random.uniform(620, 860)
            e = Tank(self.player.x + math.cos(ang) * dist, self.player.y + math.sin(ang) * dist, False)
            e.wave_id = self.wave_serial
            e.angle = math.atan2(self.player.y - e.y, self.player.x - e.x)
            e.turret = e.angle
            self.tanks.append(e)
        self.wave_index += 1
        self.between = random.uniform(30, 60)
        self.notice = f"Wave {self.wave_index}: {n} red tanks."
        self.notice_t = 2.2

    def switch_player(self):
        nxt = next((t for t in self.tanks if t.friendly and t.alive and not t.exploding and t is not self.player), None)
        if self.player:
            self.player.player = False
        if not nxt:
            self.player = None
            self.notice = "All tanks lost. Press R."
            self.notice_t = 99
            return
        nxt.player = True
        nxt.follow_slot = 0
        self.player = nxt
        self.assign_formation()
        self.sounds["switch"].play()

    def update(self, dt, keys):
        p = self.player
        blocks = self.solid_blocks()
        attack = self.under_attack()
        if p and p.alive:
            if keys[pygame.K_z]:
                p.left_pow = 1
            if keys[pygame.K_x]:
                p.right_pow = 1
            if keys[pygame.K_a]:
                p.left_pow = -1
            if keys[pygame.K_s]:
                p.right_pow = -1
            if keys[pygame.K_b]:
                p.turret -= 2.2 * dt
            if keys[pygame.K_m]:
                p.turret += 2.2 * dt
            robot = self.nearest_robot(p)
            if robot and self.auto_fire:
                desired = math.atan2(robot.y - p.y, robot.x - p.x)
                if not keys[pygame.K_b] and not keys[pygame.K_m]:
                    p.turret += clamp(ang_diff(desired, p.turret), -2.6 * dt, 2.6 * dt)
                if abs(ang_diff(desired, p.turret)) < 0.3:
                    self.zap(p, robot)
            elif attack and self.siege and self.auto_fire:
                b = self.nearest_building(p)
                if b and not keys[pygame.K_b] and not keys[pygame.K_m]:
                    self.aim_fire(p, dt, b.rect.centerx, b.rect.centery)
            elif self.auto_fire:
                e = self.nearest_enemy(p, 700)
                if e and not keys[pygame.K_b] and not keys[pygame.K_m]:
                    self.aim_fire(p, dt, e.x, e.y)
            if self.blue_count() < MAX_BLUE:
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
                t.update(dt, self.particles, ENEMY_SPEED)
            if t.alive and self.tank_blocked(t, blocks):
                t.x, t.y = ox, oy
                t.stuck += dt

        lost = False
        can_siege = attack and self.siege
        for b in self.bullets:
            b.update(dt)
            if not b.alive:
                continue
            for block in blocks:
                if block.blocks_fire() and block.rect.collidepoint(b.x, b.y):
                    b.alive = False
                    break
            if not b.alive:
                continue
            if b.friendly and can_siege:
                for building in self.buildings:
                    if building.alive and building.rect.collidepoint(b.x, b.y):
                        building.hp -= 1
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
                    t.hit(30, self.particles, self.waves_fx)
                    b.alive = False
                    self.sounds["hit"].play()
                    if t.exploding:
                        self.sounds["explode"].play()
                        if not t.friendly:
                            self.kills += 1
                            self.cleared.add(self.chunk_key(t.x, t.y))
                        if t.player:
                            lost = True
                    break
        if lost:
            self.switch_player()

        for robot in self.robots:
            if not robot.alive:
                continue
            victim = robot.update(dt, self.tanks)
            if victim:
                victim.kill(self.particles, self.waves_fx)
                robot.alive = False
                robot.remove = True
                self.sounds["explode"].play()
                self.shake = 14
                if victim.player:
                    self.switch_player()
        self.robots = [r for r in self.robots if not r.remove]
        self.robot_timer -= dt
        if self.robot_timer <= 0:
            self.robot_timer = random.uniform(22, 48)
            if self.player and random.random() < 0.35:
                ang = random.random() * math.tau
                self.robots.append(Robot(self.player.x + math.cos(ang) * 700, self.player.y + math.sin(ang) * 700))

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
                self.loss_timer = 1.5 if self.leftover_waves() else 3.0
                self.lose_territory()
        else:
            self.red_pressure = max(0.0, self.red_pressure - dt * 1.2)
            self.loss_timer = 3.0
            self.siege = False
        if self.player and self.player.alive:
            self.between = max(0.0, self.between - dt)
            if self.between <= 0:
                self.spawn_wave()
            self.cam[0] = self.player.x - self.w / 2
            self.cam[1] = self.player.y - self.h / 2
        if self.shake:
            self.cam[0] += random.uniform(-self.shake, self.shake)
            self.cam[1] += random.uniform(-self.shake, self.shake)
        self.ensure_chunks()
        self.notice_t = max(0.0, self.notice_t - dt)

    def draw(self):
        self.screen.fill((52, 74, 46))
        cam = self.cam
        for key in self.cleared:
            pygame.draw.rect(self.screen, (42, 78, 62), (key[0] * CHUNK - cam[0], key[1] * CHUNK - cam[1], CHUNK, CHUNK))
        for block in self.solid_blocks():
            if block.kind != "block":
                block.draw(self.screen, cam)
        for b in self.buildings:
            b.draw(self.screen, cam, self.small)
        for block in self.solid_blocks():
            if block.kind == "block":
                block.draw(self.screen, cam)
        for r in self.robots:
            r.draw(self.screen, cam)
        for t in self.tanks:
            if not t.player:
                t.draw(self.screen, cam)
        if self.player:
            self.player.draw(self.screen, cam)
        for b in self.bullets:
            b.draw(self.screen, cam)
        for bolt in self.bolts:
            bolt.draw(self.screen, cam)
        for p in self.particles:
            p.draw(self.screen, cam)
        for w in self.waves_fx:
            w.draw(self.screen, cam)
        hp = max(0, int(self.player.hp)) if self.player and self.player.alive else 0
        mode = "BUILDINGS" if self.siege and self.under_attack() else "RED TANKS"
        lines = [
            "Z/X A/S treads  B/M turret  SPACE auto  P pause  T target  1-6 form  7 unstick",
            f"HP {hp}  blue {self.blue_count()}  red {len(self.enemies())}  bots {len(self.robots)}  target {mode}  next {int(self.between)}s  form {FORM_NAMES[self.formation]}",
        ]
        for i, line in enumerate(lines):
            self.screen.blit(self.font.render(line, True, (235, 235, 220)), (12, 8 + i * 20))
        if self.notice_t > 0:
            self.screen.blit(self.font.render(self.notice, True, (255, 220, 120)), (12, 52))
        if self.paused:
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
                    elif event.key == pygame.K_p:
                        self.paused = not self.paused
                    elif self.paused:
                        continue
                    elif event.key == pygame.K_SPACE:
                        self.auto_fire = not self.auto_fire
                    elif event.key == pygame.K_t:
                        if self.under_attack():
                            self.siege = not self.siege
                            self.notice = "Targeting buildings." if self.siege else "Targeting the red wave."
                        else:
                            self.notice = "Buildings can only be attacked during a wave."
                        self.notice_t = 1.6
                    elif event.key == pygame.K_r and not self.allies():
                        self.reset()
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
            if not self.paused:
                self.update(dt, pygame.key.get_pressed())
            self.draw()
            pygame.display.flip()
        x, y = get_window_pos()
        save_config(self.w, self.h, x, y)
        pygame.quit()

if __name__ == "__main__":
    Game().run()