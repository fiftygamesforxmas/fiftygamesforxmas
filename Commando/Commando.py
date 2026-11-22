#!/usr/bin/env python3
"""Commando-like vertical run-and-gun. pip install pygame"""
import array
import math
import random
import sys
import pygame

W, H = 480, 640
WORLD_H = 4200
SCROLL_LOCK = H * 0.45
TILE = 32
HIT_DAMAGE = 0.01
START_LIVES = 3.0
SPR = 32

GRASS, GRASS2 = (46, 92, 38), (58, 110, 48)
SAND, WATER, WATER2 = (140, 122, 70), (40, 80, 130), (55, 100, 150)
HUD = (230, 230, 210)

# 8 facings: N NE E SE S SW W NW
FACE_VECS = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def clamp(v, a, b):
    return max(a, min(b, v))


def facing_from_vec(dx, dy):
    if dx == 0 and dy == 0:
        return 0
    ang = math.atan2(dx, -dy)  # 0 = north
    idx = int((ang + math.pi / 8) // (math.pi / 4)) % 8
    return idx


def make_rock_music():
    """Procedural 4-bar garage-rock loop (drums + power chords)."""
    sr = 22050
    bars = 4
    bpm = 148
    beat = 60.0 / bpm
    n = int(sr * beat * 4 * bars)
    samples = [0] * n

    def add(i, v):
        if 0 <= i < n:
            samples[i] = max(-32000, min(32000, samples[i] + int(v)))

    def tone(t0, dur, freq, amp, kind="sq"):
        length = int(dur * sr)
        for i in range(length):
            t = i / sr
            env = max(0.0, 1.0 - t / dur)
            ph = 2 * math.pi * freq * t
            if kind == "sq":
                w = 1.0 if math.sin(ph) >= 0 else -1.0
            elif kind == "noise":
                w = random.uniform(-1, 1)
            else:
                w = math.sin(ph)
            add(int(t0 * sr) + i, w * amp * env)

    # power-chord roots per beat (E5 / G5 / A5 / E5)
    roots = [82.4, 82.4, 98.0, 98.0, 110.0, 110.0, 82.4, 98.0]
    for bar in range(bars):
        for b, root in enumerate(roots):
            t0 = (bar * 8 + b) * beat * 0.5
            tone(t0, 0.28, root, 4200, "sq")
            tone(t0, 0.28, root * 1.5, 2800, "sq")
            tone(t0, 0.28, root * 2, 1800, "sin")

    # drums
    for bar in range(bars):
        for beat_i in range(8):
            t0 = (bar * 8 + beat_i) * beat * 0.5
            if beat_i % 2 == 0:
                tone(t0, 0.12, 55, 9000, "sin")  # kick
            if beat_i in (2, 6):
                tone(t0, 0.08, 180, 5000, "noise")  # snare
            if beat_i % 2 == 1:
                tone(t0, 0.04, 6000, 2500, "noise")  # hat

    stereo = array.array("h")
    for s in samples:
        stereo.append(s)
        stereo.append(int(s * 0.85))
    snd = pygame.mixer.Sound(buffer=stereo)
    snd.set_volume(0.35)
    return snd


def blit_px(surf, x, y, col, s=1):
    if 0 <= x < SPR and 0 <= y < SPR:
        surf.set_at((x, y), col)


def draw_soldier(kind, face, frame, pose):
    """Tiny cartoon commando / enemy. pose: idle, walk0, walk1, shoot, die0, die1."""
    s = pygame.Surface((SPR, SPR), pygame.SRCALPHA)
    # palette
    if kind == "player":
        suit, pack, gun = (206, 186, 70), (90, 70, 30), (40, 40, 35)
        helm = (70, 90, 45)
    elif kind == "officer":
        suit, pack, gun = (40, 42, 90), (30, 30, 50), (40, 40, 35)
        helm = (30, 30, 40)
    else:
        suit, pack, gun = (150, 52, 44), (70, 30, 28), (40, 40, 35)
        helm = (55, 70, 40)
    skin, boot = (232, 196, 154), (40, 28, 20)

    cx, cy = 16, 16
    fx, fy = FACE_VECS[face]
    # death flop
    if pose.startswith("die"):
        tilt = 1 if pose == "die0" else 2
        body = pygame.Rect(6, 14 + tilt * 3, 20, 10)
        pygame.draw.ellipse(s, suit, body)
        pygame.draw.circle(s, skin, (10 + tilt * 6, 16 + tilt * 2), 4)
        pygame.draw.circle(s, helm, (10 + tilt * 6, 14 + tilt * 2), 4)
        if pose == "die1":
            pygame.draw.circle(s, (180, 40, 30), (cx, cy + 4), 5)
        return s

    walk = 0
    if pose == "walk0":
        walk = -2
    elif pose == "walk1":
        walk = 2
    shoot = pose == "shoot"

    # shadow
    pygame.draw.ellipse(s, (0, 0, 0, 70), (8, 26, 16, 5))

    # legs
    lx = cx - 3 + fy * 1
    rx = cx + 3 + fy * 1
    ly = 24 + (walk if abs(fy) + abs(fx) else 0)
    ry = 24 - (walk if abs(fy) + abs(fx) else 0)
    pygame.draw.line(s, boot, (lx, 20), (lx + fx, ly), 3)
    pygame.draw.line(s, boot, (rx, 20), (rx - fx, ry), 3)

    # torso
    pygame.draw.rect(s, suit, (cx - 5, 12, 10, 10))
    pygame.draw.rect(s, pack, (cx - 4 - fx * 2, 13, 5, 7))

    # head / helmet
    hx, hy = cx + fx, 9 + fy
    pygame.draw.circle(s, skin, (hx, hy + 1), 5)
    pygame.draw.ellipse(s, helm, (hx - 6, hy - 5, 12, 8))
    pygame.draw.rect(s, helm, (hx - 6, hy - 1, 12, 3))

    # gun
    gx, gy = cx + fx * 7, 16 + fy * 5
    if shoot:
        gx += fx * 2
        gy += fy * 2
        pygame.draw.circle(s, (255, 220, 80), (gx + fx * 5, gy + fy * 5), 3)
    pygame.draw.line(s, gun, (cx + fx * 2, 16), (gx + fx * 4, gy + fy * 3), 3)
    return s


class SpriteBank:
    def __init__(self):
        self.cache = {}
        for kind in ("player", "soldier", "officer"):
            for face in range(8):
                for pose in ("idle", "walk0", "walk1", "shoot", "die0", "die1"):
                    self.cache[(kind, face, pose)] = draw_soldier(kind, face, 0, pose)

    def get(self, kind, face, pose):
        return self.cache[(kind, face, pose)]


class Particle:
    def __init__(self, x, y, col, life=20):
        self.x, self.y = x, y
        self.vx, self.vy = random.uniform(-2, 2), random.uniform(-3, 1)
        self.col = col
        self.life = life
        self.max = life

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.12
        self.life -= 1
        return self.life > 0

    def draw(self, surf, cam):
        a = self.life / self.max
        r = max(1, int(4 * a))
        pygame.draw.circle(surf, self.col, (int(self.x), int(self.y - cam)), r)


class Bullet:
    def __init__(self, x, y, dx, dy, friendly=True, speed=9):
        self.x, self.y = x, y
        self.dx, self.dy = dx * speed, dy * speed
        self.friendly = friendly
        self.alive = True

    def update(self, world):
        self.x += self.dx
        self.y += self.dy
        if self.x < 8 or self.x > W - 8 or self.y < -40 or self.y > WORLD_H + 40:
            self.alive = False
        for obst in world.solid:
            if obst.collidepoint(self.x, self.y):
                self.alive = False
                break

    def draw(self, surf, cam):
        col = (255, 230, 80) if self.friendly else (255, 80, 60)
        pygame.draw.circle(surf, col, (int(self.x), int(self.y - cam)), 3)


class Grenade:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.vy = -7.2
        self.life = 28
        self.alive = True
        self.exploded = False

    def update(self):
        self.y += self.vy
        self.vy += 0.28
        self.life -= 1
        if self.life <= 0 or self.vy > 3.5:
            self.exploded = True
            self.alive = False

    def draw(self, surf, cam):
        pygame.draw.circle(surf, (40, 90, 50), (int(self.x), int(self.y - cam)), 5)
        pygame.draw.circle(surf, (20, 40, 20), (int(self.x), int(self.y - cam)), 5, 1)


class Pickup:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x - 10, y - 8, 20, 16)
        self.alive = True

    def draw(self, surf, cam):
        r = pygame.Rect(self.rect.x, self.rect.y - cam, self.rect.w, self.rect.h)
        pygame.draw.rect(surf, (90, 70, 30), r)
        pygame.draw.rect(surf, (200, 180, 60), r, 1)
        pygame.draw.circle(surf, (40, 90, 50), (r.centerx, r.centery), 4)


class Actor:
    def __init__(self, x, y, kind="soldier"):
        self.x, self.y = x, y
        self.kind = kind
        self.face = 4
        self.pose = "idle"
        self.anim = 0
        self.shoot_t = 0
        self.dead_t = 0
        self.alive = True
        self.gone = False
        self.hp = 1 if kind != "jeep" else 4
        self.w = self.h = 16 if kind != "jeep" else 28
        self.speed = 1.15 if kind == "soldier" else (1.4 if kind == "officer" else 2.0)
        self.cd = random.randint(15, 70)
        self.touch_cd = 0
        self.moving = False

    def rect(self):
        return pygame.Rect(self.x - self.w // 2, self.y - self.h // 2, self.w, self.h)

    def kill(self):
        if self.alive:
            self.alive = False
            self.dead_t = 28
            self.pose = "die0"

    def animate(self):
        self.anim += 1
        if not self.alive:
            self.pose = "die0" if self.dead_t > 14 else "die1"
            self.dead_t -= 1
            if self.dead_t <= 0:
                self.gone = True
            return
        if self.shoot_t > 0:
            self.pose = "shoot"
            self.shoot_t -= 1
        elif self.moving:
            self.pose = "walk0" if (self.anim // 6) % 2 == 0 else "walk1"
        else:
            self.pose = "idle"

    def update_ai(self, player, bullets):
        if not self.alive:
            self.animate()
            return
        self.touch_cd = max(0, self.touch_cd - 1)
        dx, dy = player.x - self.x, player.y - self.y
        dist = math.hypot(dx, dy) or 1
        nx, ny = dx / dist, dy / dist
        self.moving = False

        if self.kind == "officer":
            self.x -= nx * self.speed * 1.4
            self.y -= ny * self.speed * 0.6
            self.moving = True
            self.face = facing_from_vec(-nx, -ny)
        elif self.kind == "jeep":
            self.y += self.speed
            self.x += math.sin(self.y * 0.02) * 0.8
            self.moving = True
            self.face = 4
        else:
            if dist > 90:
                self.x += nx * self.speed
                self.y += ny * self.speed * 0.35
            else:
                self.x += -ny * self.speed * 0.7
                self.y += nx * self.speed * 0.2
            self.moving = True
            self.face = facing_from_vec(nx, ny)

        self.x = clamp(self.x, 16, W - 16)
        self.y = clamp(self.y, 20, WORLD_H - 20)
        self.cd -= 1
        if self.cd <= 0 and dist < 300 and self.kind != "officer":
            fx, fy = FACE_VECS[self.face]
            mag = math.hypot(fx, fy) or 1
            bullets.append(Bullet(self.x, self.y, fx / mag, fy / mag, False, 5.2))
            self.shoot_t = 8
            self.cd = random.randint(40, 80)
        self.animate()

    def draw(self, surf, cam, bank, tick):
        if self.gone:
            return
        if self.kind == "jeep":
            r = self.rect()
            sy = r.y - cam
            pygame.draw.rect(surf, (70, 80, 50), (r.x, sy, r.w, r.h))
            pygame.draw.rect(surf, (30, 30, 25), (r.x + 4, sy + 6, r.w - 8, 10))
            wob = math.sin(tick * 0.3 + self.x) * 1
            pygame.draw.circle(surf, (20, 20, 20), (r.x + 6, int(sy + r.h - 2 + wob)), 4)
            pygame.draw.circle(surf, (20, 20, 20), (r.right - 6, int(sy + r.h - 2 - wob)), 4)
            return
        spr = bank.get(self.kind if self.kind != "player" else "player", self.face, self.pose)
        surf.blit(spr, (int(self.x - SPR // 2), int(self.y - SPR // 2 - cam)))


class Player(Actor):
    def __init__(self):
        super().__init__(W // 2, WORLD_H - 80, "player")
        self.score = 0
        self.lives = START_LIVES
        self.grenades = 5
        self.speed = 2.6
        self.invuln = 0
        self.fire_cd = 0
        self.face = 0

    def reset_position(self):
        self.x, self.y = W // 2, WORLD_H - 80
        self.face = 0
        self.invuln = 60
        self.alive = True
        self.gone = False
        self.pose = "idle"

    def update_player(self, keys, world, bullets):
        if not self.alive:
            self.animate()
            return
        dx = (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
        dy = (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
        self.moving = bool(dx or dy)
        if self.moving:
            mag = math.hypot(dx, dy)
            self.x += self.speed * dx / mag
            self.y += self.speed * dy / mag
            self.face = facing_from_vec(dx, dy)

        self.x = clamp(self.x, 14, W - 14)
        self.y = clamp(self.y, 20, WORLD_H - 16)
        pr = self.rect()
        for s in world.solid:
            if pr.colliderect(s):
                ox = min(pr.right - s.left, s.right - pr.left)
                oy = min(pr.bottom - s.top, s.bottom - pr.top)
                if ox < oy:
                    self.x += -ox if pr.centerx < s.centerx else ox
                else:
                    self.y += -oy if pr.centery < s.centery else oy
                pr = self.rect()
        for wrect in world.water:
            if pr.colliderect(wrect):
                self.hurt(0.25)

        self.fire_cd = max(0, self.fire_cd - 1)
        self.invuln = max(0, self.invuln - 1)
        if keys[pygame.K_SPACE] and self.fire_cd == 0:
            fx, fy = FACE_VECS[self.face]
            mag = math.hypot(fx, fy)
            bullets.append(Bullet(self.x, self.y - 4, fx / mag, fy / mag, True, 10))
            self.fire_cd = 7
            self.shoot_t = 6
        self.animate()

    def throw(self, grenades):
        if self.grenades > 0 and self.alive:
            self.grenades -= 1
            grenades.append(Grenade(self.x, self.y - 8))

    def hurt(self, amount=HIT_DAMAGE):
        if self.invuln > 0 and amount <= HIT_DAMAGE:
            return
        self.lives -= amount
        self.invuln = 8 if amount <= HIT_DAMAGE else 40
        if self.lives <= 0:
            self.lives = 0
            self.kill()

    def draw(self, surf, cam, bank, tick):
        if self.invuln and (self.invuln // 2) % 2 == 0 and self.invuln > 4:
            return
        super().draw(surf, cam, bank, tick)


class World:
    def __init__(self):
        self.rng = random.Random()
        self.solid, self.water, self.decor, self.pickups = [], [], [], []
        self.spawn_points = []
        self.generate()

    def generate(self):
        rng = self.rng
        for _ in range(rng.randint(2, 4)):
            y = rng.randint(400, WORLD_H - 400)
            h = rng.choice([28, 36, 44])
            gap = rng.randint(70, 140)
            gx = rng.randint(40, W - 40 - gap)
            left = pygame.Rect(0, y, gx, h)
            right = pygame.Rect(gx + gap, y, W - (gx + gap), h)
            self.water += [left, right]
            self.decor += [("water", left), ("water", right), ("sand", pygame.Rect(gx, y, gap, h))]

        for _ in range(90):
            x, y = rng.randint(20, W - 40), rng.randint(260, WORLD_H - 140)
            if any(r.inflate(20, 20).collidepoint(x, y) for r in self.water):
                continue
            if rng.random() < 0.7:
                rec = pygame.Rect(x, y, rng.randint(18, 28), rng.randint(22, 34))
                self.solid.append(rec)
                self.decor.append(("tree", rec))
            else:
                rec = pygame.Rect(x, y, rng.randint(16, 26), rng.randint(14, 22))
                self.solid.append(rec)
                self.decor.append(("rock", rec))

        for _ in range(rng.randint(6, 10)):
            rec = pygame.Rect(rng.randint(30, W - 80), rng.randint(320, WORLD_H - 300), 56, 28)
            if any(rec.colliderect(s) for s in self.solid + self.water):
                continue
            self.solid.append(rec)
            self.decor.append(("bunker", rec))
            self.spawn_points.append((rec.centerx, rec.bottom + 12))

        for _ in range(rng.randint(7, 12)):
            x, y = rng.randint(30, W - 30), rng.randint(300, WORLD_H - 160)
            if any(s.collidepoint(x, y) for s in self.solid + self.water):
                continue
            self.pickups.append(Pickup(x, y))

        self.solid += [pygame.Rect(0, 100, W // 2 - 40, 40), pygame.Rect(W // 2 + 40, 100, W // 2 - 40, 40)]
        self.decor.append(("wall", pygame.Rect(0, 100, W, 40)))

        self.initial_enemies = []
        for _ in range(24):
            x, y = rng.randint(30, W - 30), rng.randint(260, WORLD_H - 180)
            if any(s.inflate(8, 8).collidepoint(x, y) for s in self.solid + self.water):
                continue
            self.initial_enemies.append(Actor(x, y, "soldier"))
        self.initial_enemies.append(Actor(rng.randint(40, W - 40), rng.randint(500, 1800), "jeep"))
        for bx, by in self.spawn_points:
            self.initial_enemies.append(Actor(bx, by, "soldier"))

    def draw_ground(self, surf, cam, tick):
        y0 = int(cam) // TILE * TILE
        for y in range(y0 - TILE, int(cam) + H + TILE, TILE):
            for x in range(0, W, TILE):
                c = GRASS if ((x // TILE) + (y // TILE)) % 2 == 0 else GRASS2
                pygame.draw.rect(surf, c, (x, y - cam, TILE, TILE))
        wind = math.sin(tick * 0.04)
        for kind, rec in self.decor:
            r = pygame.Rect(rec.x, rec.y - cam, rec.w, rec.h)
            if r.bottom < -30 or r.top > H + 30:
                continue
            if kind == "water":
                pygame.draw.rect(surf, WATER, r)
                pygame.draw.line(surf, WATER2, (r.x, r.y + 6 + wind), (r.right, r.y + 6 - wind), 2)
            elif kind == "sand":
                pygame.draw.rect(surf, SAND, r)
            elif kind == "tree":
                sway = int(wind * 3 + math.sin(tick * 0.05 + rec.x) * 2)
                pygame.draw.rect(surf, (80, 50, 30), (r.centerx - 3, r.bottom - 8, 6, 8))
                canopy = r.move(sway, 0)
                pygame.draw.ellipse(surf, (22, 62, 28), canopy)
                pygame.draw.ellipse(surf, (34, 90, 36), canopy.inflate(-6, -8))
            elif kind == "rock":
                wob = int(math.sin(tick * 0.03 + rec.y) * 1)
                pygame.draw.ellipse(surf, (90, 90, 85), r.move(wob, 0))
                pygame.draw.ellipse(surf, (120, 118, 110), r.move(wob, 0).inflate(-8, -6))
            elif kind == "bunker":
                pygame.draw.rect(surf, (70, 68, 55), r)
                pygame.draw.rect(surf, (20, 20, 18), (r.x + 8, r.y + 8, 16, 8))
                pygame.draw.rect(surf, (20, 20, 18), (r.right - 24, r.y + 8, 16, 8))
            elif kind == "wall":
                pygame.draw.rect(surf, (55, 52, 45), r)
                pygame.draw.rect(surf, (90, 80, 50), (W // 2 - 40, 140 - cam, 80, 28))


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption("COMMANDO  —  random sector")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big = pygame.font.SysFont("consolas", 28, bold=True)
        self.bank = SpriteBank()
        self.tick = 0
        self.sector = 1
        try:
            self.music = make_rock_music()
            self.music.play(-1)
        except Exception:
            self.music = None
        self.player = Player()
        self.new_level(False)

    def new_level(self, keep_player=True):
        self.world = World()
        if keep_player:
            self.player.reset_position()
            self.player.grenades += 2
        else:
            self.player = Player()
        self.bullets, self.grenades, self.particles = [], [], []
        self.enemies = list(self.world.initial_enemies)
        self.cam = self.player.y - H + 120
        self.state = "play"
        self.wave_timer = 0
        self.officer_spawned = False
        self.rush_done = False
        self.advance_timer = 0

    def explode(self, x, y, radius=46):
        for _ in range(18):
            self.particles.append(Particle(x, y, random.choice([(220, 160, 40), (200, 60, 20), (80, 80, 80)])))
        for e in self.enemies:
            if e.alive and math.hypot(e.x - x, e.y - y) < radius:
                e.hp -= 3
                if e.hp <= 0:
                    self.player.score += 200 if e.kind == "officer" else (150 if e.kind == "jeep" else 100)
                    e.kill()
                    self.burst(e.x, e.y)
        if math.hypot(self.player.x - x, self.player.y - y) < radius * 0.7:
            self.player.hurt(HIT_DAMAGE)

    def burst(self, x, y):
        for _ in range(10):
            self.particles.append(Particle(x, y, (160, 50, 45)))

    def update_cam(self):
        target = self.player.y - SCROLL_LOCK
        if self.state in ("fortress", "clearing"):
            self.cam += (40 - self.cam) * 0.08
        elif target < self.cam:
            self.cam = target
        self.cam = clamp(self.cam, 0, WORLD_H - H)
        if self.player.y > self.cam + H - 24:
            self.player.y = self.cam + H - 24

    def handle_combat(self):
        for b in self.bullets:
            if not b.alive:
                continue
            if b.friendly:
                for e in self.enemies:
                    if e.alive and e.rect().collidepoint(b.x, b.y):
                        e.hp -= 1
                        b.alive = False
                        if e.hp <= 0:
                            self.player.score += 300 if e.kind == "officer" else (150 if e.kind == "jeep" else 50)
                            e.kill()
                            self.burst(e.x, e.y)
                        break
            elif self.player.alive and self.player.rect().inflate(-4, -4).collidepoint(b.x, b.y):
                b.alive = False
                self.player.hurt(HIT_DAMAGE)

        pr = self.player.rect()
        for p in self.world.pickups:
            if p.alive and pr.colliderect(p.rect):
                p.alive = False
                self.player.grenades += 3
                self.player.score += 50
        for e in self.enemies:
            if e.alive and pr.colliderect(e.rect()) and e.touch_cd == 0:
                self.player.hurt(HIT_DAMAGE)
                e.touch_cd = 12

    def fortress_logic(self):
        if self.state == "play" and self.player.y < 280:
            self.state = "fortress"
            if not self.officer_spawned:
                self.enemies.append(Actor(W // 2, 160, "officer"))
                self.officer_spawned = True
                for i in range(4):
                    self.enemies.append(Actor(W // 2 + random.randint(-30, 30), 150 + i, "soldier"))
        if self.state == "fortress":
            self.wave_timer += 1
            if self.wave_timer < 900:
                interval = max(18, 36 - self.sector)
                if self.wave_timer % interval == 0:
                    self.enemies.append(Actor(W // 2 + random.randint(-36, 36), 152, "soldier"))
            else:
                self.rush_done = True
            living = sum(1 for e in self.enemies if e.alive or not e.gone)
            # wait until corpses finish too? only living combatants:
            living = sum(1 for e in self.enemies if e.alive)
            if self.rush_done and living == 0:
                self.state = "clearing"
                self.advance_timer = 90
                self.player.score += 1000 + self.sector * 250
        if self.state == "clearing":
            self.advance_timer -= 1
            if self.advance_timer <= 0:
                self.sector += 1
                self.new_level(True)

    def update(self):
        self.tick += 1
        keys = pygame.key.get_pressed()
        if self.state in ("play", "fortress", "clearing") and (self.player.alive or not self.player.gone):
            if self.player.alive:
                self.player.update_player(keys, self.world, self.bullets)
            else:
                self.player.animate()
            for e in self.enemies:
                e.update_ai(self.player, self.bullets)
            for b in self.bullets:
                b.update(self.world)
            for g in self.grenades:
                g.update()
                if g.exploded:
                    self.explode(g.x, g.y)
            self.bullets = [b for b in self.bullets if b.alive]
            self.grenades = [g for g in self.grenades if g.alive]
            self.particles = [p for p in self.particles if p.update()]
            self.enemies = [e for e in self.enemies if not e.gone]
            self.handle_combat()
            self.fortress_logic()
            self.update_cam()
            if self.player.gone:
                self.state = "dead"
        else:
            self.particles = [p for p in self.particles if p.update()]

    def draw_hud(self):
        bar = pygame.Surface((W, 28), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 140))
        self.screen.blit(bar, (0, 0))
        txt = self.font.render(
            f"SEC {self.sector}  SCORE {self.player.score:06d}  LIVES {self.player.lives:.2f}  G {self.player.grenades}",
            True, HUD)
        self.screen.blit(txt, (8, 5))
        pygame.draw.rect(self.screen, (80, 20, 20), (8, 30, 120, 6))
        pygame.draw.rect(self.screen, (80, 200, 70), (8, 30, int(120 * (self.player.lives / START_LIVES)), 6))
        if self.state == "clearing":
            t = self.big.render("SECTOR CLEARED", True, (255, 220, 80))
            self.screen.blit(t, t.get_rect(center=(W // 2, 80)))
        elif self.state == "dead":
            t = self.big.render("YOU ARE DOWN", True, (220, 60, 50))
            self.screen.blit(t, t.get_rect(center=(W // 2, H // 2)))
            s = self.font.render("R  retry   ESC  quit", True, HUD)
            self.screen.blit(s, s.get_rect(center=(W // 2, H // 2 + 36)))

    def draw(self):
        cam = self.cam
        self.world.draw_ground(self.screen, cam, self.tick)
        for p in self.world.pickups:
            if p.alive:
                p.draw(self.screen, cam)
        for e in self.enemies:
            e.draw(self.screen, cam, self.bank, self.tick)
        self.player.draw(self.screen, cam, self.bank, self.tick)
        for b in self.bullets:
            b.draw(self.screen, cam)
        for g in self.grenades:
            g.draw(self.screen, cam)
        for p in self.particles:
            p.draw(self.screen, cam)
        self.draw_hud()
        pygame.display.flip()

    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit(); sys.exit()
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit(); sys.exit()
                    if ev.key in (pygame.K_g, pygame.K_LCTRL, pygame.K_RCTRL):
                        self.player.throw(self.grenades)
                    if ev.key == pygame.K_r:
                        self.sector = 1
                        self.new_level(False)
            self.update()
            self.draw()
            self.clock.tick(60)


if __name__ == "__main__":
    Game().run()