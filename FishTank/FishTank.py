#!/usr/bin/env python3
"""
3D aquarium simulation (2.5D with z-sorting and anaglyph modes).

Usage:
    python3 fishtank.py
    python3 fishtank.py --song path/to/music.mp3

Controls:
    T   cycle view (normal gray -> red/green anaglyph -> red/blue anaglyph)
    Y   swap anaglyph filter sides (left/right)
    X   randomize tank
    ESC quit
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys

import pygame

W, H = 1280, 720
FPS = 60
Z_NEAR, Z_FAR = 0.15, 1.0
MODES = ("normal", "anaglyph_rg", "anaglyph_rb")

FISH_KINDS = ("angelfish", "tang", "grouper", "goldfish", "guppy", "seahorse")
SMALL_PREY = {"guppy", "goldfish"}
ANGEL_FLOCK_SIZE = (4, 7)

LUMA_MIN = 36
LUMA_MAX = 195

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fishtank_window.json")
MIN_W, MIN_H = 640, 360

SPRITE_CACHE = {}


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return a + (b - a) * t


def ang_diff(a, b):
    return (b - a + math.pi) % math.tau - math.pi


def luma(rgb):
    r, g, b = rgb[:3]
    y = int(0.299 * r + 0.587 * g + 0.114 * b)
    return int(clamp(y, LUMA_MIN, LUMA_MAX))


def tone_color(rgb):
    y = luma(rgb)
    return (y, y, y)


def z_scale(z):
    return lerp(1.55, 0.45, (z - Z_NEAR) / (Z_FAR - Z_NEAR))


def parallax_px(z, strength=14.0):
    closeness = clamp((Z_FAR - z) / (Z_FAR - Z_NEAR), 0.0, 1.0)
    if closeness < 0.12:
        return 0
    return int(round(closeness * closeness * strength))


def load_window_cfg():
    cfg = {"w": 1280, "h": 720, "x": None, "y": None}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg["w"] = max(MIN_W, int(data.get("w", cfg["w"])))
        cfg["h"] = max(MIN_H, int(data.get("h", cfg["h"])))
        if data.get("x") is not None and data.get("y") is not None:
            cfg["x"] = int(data["x"])
            cfg["y"] = int(data["y"])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return cfg


def save_window_cfg(size=None, pos=None):
    surf = pygame.display.get_surface()
    if surf is None:
        return
    w, h = size or surf.get_size()
    data = load_window_cfg()
    data["w"], data["h"] = int(w), int(h)
    if pos is not None and pos[0] is not None:
        data["x"], data["y"] = int(pos[0]), int(pos[1])
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def compose_anaglyph(left, right, mode):
    try:
        la = pygame.surfarray.array3d(left)
        ra = pygame.surfarray.array3d(right)
        out = pygame.surfarray.array3d(left)
        out[:, :, :] = 0
        out[:, :, 0] = la[:, :, 0]
        if mode == "anaglyph_rg":
            out[:, :, 1] = ra[:, :, 1]
        else:
            out[:, :, 2] = ra[:, :, 2]
        return pygame.surfarray.make_surface(out)
    except Exception:
        return left


def fish_palette(kind):
    # Same mid-olive family as the grouper; only luminance varies by species.
    base = [
        (72, 108, 78),
        (48, 64, 50),
        (168, 150, 78),
    ]
    shift = {
        "angelfish": 18,
        "tang": 10,
        "grouper": 0,
        "goldfish": 14,
        "guppy": 8,
        "seahorse": 6,
    }[kind]
    return [tone_color((c[0] + shift, c[1] + shift // 2, c[2])) for c in base]


def build_fish_sprite(kind, palette):
    c1, c2, c3 = palette
    eye = tone_color((48, 52, 46))
    if kind == "angelfish":
        w, h = 70, 90
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(im, c1, [(int(w*0.25), h//2), (int(w*0.85), int(h*0.08)), (int(w*0.85), int(h*0.92))])
        pygame.draw.polygon(im, c2, [(int(w*0.4), h//2), (int(w*0.82), int(h*0.18)), (int(w*0.82), int(h*0.82))])
        pygame.draw.ellipse(im, c1, (int(w*0.15), int(h*0.32), int(w*0.55), int(h*0.36)))
        pygame.draw.circle(im, eye, (int(w*0.28), int(h*0.48)), 3)
    elif kind == "tang":
        w, h = 80, 42
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(im, c1, (int(w*0.1), int(h*0.15), int(w*0.7), int(h*0.7)))
        pygame.draw.polygon(im, c2, [(int(w*0.72), h//2), (w, int(h*0.15)), (w, int(h*0.85))])
        pygame.draw.polygon(im, c3, [(int(w*0.4), int(h*0.2)), (int(w*0.55), 0), (int(w*0.5), int(h*0.3))])
        pygame.draw.circle(im, eye, (int(w*0.22), int(h*0.45)), 3)
    elif kind == "grouper":
        w, h = 110, 55
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(im, c1, (int(w*0.05), int(h*0.15), int(w*0.75), int(h*0.7)))
        pygame.draw.polygon(im, c2, [(int(w*0.7), h//2), (w-2, int(h*0.2)), (w-2, int(h*0.8))])
        for i in range(4):
            pygame.draw.circle(im, c3, (int(w*(0.25+0.12*i)), int(h*0.5)), 3)
        pygame.draw.circle(im, eye, (int(w*0.18), int(h*0.42)), 4)
    elif kind == "goldfish":
        w, h = 64, 36
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(im, c1, (int(w*0.08), int(h*0.2), int(w*0.6), int(h*0.6)))
        pygame.draw.polygon(im, c2, [(int(w*0.6), h//2), (w, 2), (int(w*0.72), h//2), (w, h-2)])
        pygame.draw.circle(im, eye, (int(w*0.2), int(h*0.45)), 2)
    elif kind == "guppy":
        w, h = 46, 28
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(im, c1, (2, int(h*0.3), int(w*0.45), int(h*0.45)))
        pygame.draw.polygon(im, c2, [(int(w*0.4), h//2), (w, 1), (int(w*0.55), h//2), (w-2, h-1)])
        pygame.draw.circle(im, eye, (int(w*0.12), int(h*0.48)), 2)
    else:
        w, h = 28, 70
        im = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.circle(im, c1, (int(w*0.55), int(h*0.18)), 8)
        pygame.draw.lines(
            im, c1, False,
            [(int(w*0.55), int(h*0.25)), (int(w*0.4), int(h*0.45)),
             (int(w*0.55), int(h*0.65)), (int(w*0.35), int(h*0.9))],
            6,
        )
        pygame.draw.circle(im, eye, (int(w*0.42), int(h*0.16)), 2)
    return im


def get_sprite(kind):
    if kind not in SPRITE_CACHE:
        SPRITE_CACHE[kind] = build_fish_sprite(kind, fish_palette(kind))
    return SPRITE_CACHE[kind]


class Fish:
    def __init__(self, kind=None, small_angel=False, flock=None, leader=False, slot=0):
        self.kind = kind or random.choice(FISH_KINDS)
        self.small_angel = small_angel and self.kind == "angelfish"
        self.flock = flock
        self.is_leader = leader
        self.slot = slot
        self.alive = True
        self.reset(full=True)

    def size_factor(self):
        if self.kind == "grouper":
            return 1.35
        if self.kind == "guppy" or self.small_angel:
            return 0.55
        if self.kind == "seahorse":
            return 0.7
        return 1.0

    def edible(self):
        if self.kind in ("grouper", "seahorse"):
            return False
        return self.kind in SMALL_PREY or self.small_angel

    def reset(self, full=False, edge=None):
        self.z = random.uniform(Z_NEAR + 0.08, Z_FAR - 0.08)
        self.y = random.uniform(90, max(91, H - 150))
        self.heading = random.uniform(-0.4, 0.4)
        if random.random() < 0.5:
            self.heading += math.pi
        self.desired_heading = self.heading
        self.pitch = random.uniform(-0.25, 0.25)
        self.desired_pitch = self.pitch
        self.speed = random.uniform(20, 50)
        base = {
            "angelfish": 95, "tang": 140, "grouper": 70,
            "goldfish": 85, "guppy": 120, "seahorse": 36,
        }[self.kind]
        if self.small_angel:
            base = 110
        self.max_speed = base * random.uniform(0.85, 1.15)
        self.drag = 0.55 if self.kind != "grouper" else 0.4
        self.phase = random.uniform(0, math.tau)
        self.wag_timer = random.uniform(0.0, 0.6)
        self.wagging = False
        self.wag_amp = 0.0
        self.arc_timer = random.uniform(0.8, 2.5)
        self.hunt_cooldown = 0.0
        if full and edge is None:
            self.x = random.uniform(80, max(90, W - 80))
        else:
            edge = edge or random.choice(("left", "right", "top", "bottom"))
            if edge == "left":
                self.x, self.heading = -70, 0.0
            elif edge == "right":
                self.x, self.heading = W + 70, math.pi
            elif edge == "top":
                self.x, self.y = random.uniform(80, max(90, W - 80)), -50
                self.heading = random.uniform(0.4, math.pi - 0.4)
            else:
                self.x, self.y = random.uniform(80, max(90, W - 80)), H + 50
                self.heading = random.uniform(-math.pi + 0.4, -0.4)
            self.desired_heading = self.heading
        self.vx = math.cos(self.heading) * self.speed
        self.vy = math.sin(self.heading) * self.speed * 0.35
        self.vz = random.uniform(-0.06, 0.06)
        self.desired_vz = self.vz

    def _pick_arc(self):
        self.desired_heading += random.uniform(-0.9, 0.9)
        self.desired_pitch = clamp(self.desired_pitch + random.uniform(-0.35, 0.35), -0.55, 0.55)
        self.desired_vz = random.uniform(-0.14, 0.14)
        self.arc_timer = random.uniform(1.4, 3.8)

    def _flock_follow(self):
        lead = self.flock.leader if self.flock else None
        if not lead or not lead.alive or lead is self:
            return
        row = (self.slot + 2) // 2
        side = -1 if self.slot % 2 else 1
        back = 28 + row * 26
        spread = 16 + row * 14
        hx, hy = math.cos(lead.heading), math.sin(lead.heading)
        px, py = -hy, hx
        tx = lead.x - hx * back + px * side * spread
        ty = lead.y - hy * back * 0.45 + py * side * spread * 0.25
        dx, dy = tx - self.x, ty - self.y
        self.desired_heading = math.atan2(dy, dx)
        self.desired_pitch = lead.pitch
        self.z = lerp(self.z, lead.z + 0.012 * side, 0.08)
        if math.hypot(dx, dy) > 18:
            self.wagging = True

    def update(self, dt, others):
        if not self.alive:
            return
        self.phase += dt * (7 + self.wag_amp * 10)
        self.hunt_cooldown = max(0.0, self.hunt_cooldown - dt)
        self.arc_timer -= dt

        if self.small_angel and not self.is_leader and self.flock:
            self._flock_follow()
        elif self.arc_timer <= 0:
            self._pick_arc()

        if self.kind == "grouper" and self.hunt_cooldown <= 0:
            prey, best = None, 180
            for o in others:
                if o is self or not o.alive or not o.edible():
                    continue
                d = math.hypot(o.x - self.x, o.y - self.y) + abs(o.z - self.z) * 120
                if d < best:
                    best, prey = d, o
            if prey and best < 170:
                self.desired_heading = math.atan2(prey.y - self.y, prey.x - self.x)
                if best < 28 and abs(prey.z - self.z) < 0.18:
                    prey.alive = False
                    self.hunt_cooldown = random.uniform(3.0, 6.5)
                    self.speed = min(self.max_speed, self.speed + 18)

        turn = 2.4 if (self.small_angel and not self.is_leader) else (0.7 if self.kind == "grouper" else 1.1)
        self.heading += clamp(ang_diff(self.heading, self.desired_heading), -turn * dt, turn * dt)
        self.pitch += clamp(self.desired_pitch - self.pitch, -0.8 * dt, 0.8 * dt)

        self.speed *= math.exp(-self.drag * dt)
        self.wag_timer -= dt
        cruise = self.max_speed * (0.28 if self.kind != "seahorse" else 0.2)
        if self.speed < cruise and self.wag_timer <= 0:
            self.wagging = True
            self.wag_timer = random.uniform(0.18, 0.38)
        if self.wagging:
            self.wag_amp = lerp(self.wag_amp, 1.0, 0.35)
            impulse = self.max_speed * (0.55 if self.kind != "seahorse" else 0.35)
            self.speed = min(self.max_speed, self.speed + impulse * dt * 3.2)
            if self.wag_timer <= 0:
                self.wagging = False
        else:
            self.wag_amp = lerp(self.wag_amp, 0.12, 0.2)

        self.vz = lerp(self.vz, self.desired_vz, 0.04)
        self.vx = math.cos(self.heading) * self.speed
        self.vy = math.sin(self.heading) * self.speed * 0.42 + self.pitch * self.speed * 0.55
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z = clamp(self.z + self.vz * dt, Z_NEAR, Z_FAR)
        if self.z in (Z_NEAR, Z_FAR):
            self.vz *= -1
            self.desired_vz = -self.desired_vz
        if self.y < 40:
            self.desired_pitch = abs(self.desired_pitch)
            self.y = 40
        elif self.y > H - 70:
            self.desired_pitch = -abs(self.desired_pitch)
            self.y = H - 70

    def offscreen(self):
        return self.x < -140 or self.x > W + 140 or self.y < -100 or self.y > H + 100

    def draw(self, surf, ox=0):
        if not self.alive:
            return
        src = get_sprite(self.kind)
        s = max(0.25, z_scale(self.z) * self.size_factor())
        w = max(4, int(src.get_width() * s))
        h = max(4, int(src.get_height() * s))
        sprite = pygame.transform.scale(src, (w, h))
        if math.cos(self.heading) >= 0:
            sprite = pygame.transform.flip(sprite, True, False)
        ang = -math.degrees(self.pitch)
        if self.kind == "seahorse":
            ang *= 0.28
        if abs(ang) > 1:
            sprite = pygame.transform.rotate(sprite, ang)
        rect = sprite.get_rect(center=(int(self.x + ox), int(self.y)))
        surf.blit(sprite, rect)


class Flock:
    def __init__(self):
        n = random.randint(*ANGEL_FLOCK_SIZE)
        self.members = []
        leader = Fish("angelfish", small_angel=True, flock=self, leader=True, slot=0)
        self.leader = leader
        self.members.append(leader)
        for i in range(1, n):
            f = Fish("angelfish", small_angel=True, flock=self, leader=False, slot=i)
            f.x = leader.x - 20 * i
            f.y = leader.y + (i % 2 - 0.5) * 16
            f.z = leader.z
            self.members.append(f)

    def living(self):
        return [m for m in self.members if m.alive]


class Bubble:
    def __init__(self):
        self.reset(random.uniform(0, H))

    def reset(self, y=None):
        self.x = random.uniform(20, max(21, W - 20))
        self.y = H + 10 if y is None else y
        self.z = random.uniform(Z_NEAR, Z_FAR)
        self.r = random.uniform(2, 7)
        self.spd = random.uniform(20, 70)

    def update(self, dt):
        self.y -= self.spd * dt
        self.x += math.sin(self.y * 0.05) * 20 * dt
        if self.y < -10:
            self.reset()

    def draw(self, surf, ox=0):
        r = max(1, int(self.r * z_scale(self.z)))
        pygame.draw.circle(surf, tone_color((120, 130, 125)), (int(self.x + ox), int(self.y)), r, 1)


class Kelp:
    def __init__(self):
        self.x = random.uniform(10, max(11, W - 10))
        self.z = random.uniform(0.28, Z_FAR)
        self.h = random.uniform(80, 280)
        self.phase = random.uniform(0, math.tau)
        self.color = tone_color(random.choice([(48, 78, 52), (40, 70, 48), (56, 82, 58)]))
        self.segs = 10

    def point_z(self, p, t):
        wave = math.sin(t * 1.15 + self.phase + p * 4.2) * 0.16 * p
        wave += math.sin(t * 0.55 + self.phase * 0.7 + p * 2.0) * 0.07 * p
        return clamp(self.z + wave, Z_NEAR, Z_FAR)

    def draw(self, surf, t, eye_sign=0):
        prev = None
        for i in range(self.segs + 1):
            p = i / self.segs
            z = self.point_z(p, t)
            sway = math.sin(t * 1.3 + self.phase + p * 3) * (8 + 18 * p)
            ox = eye_sign * parallax_px(z)
            sc = z_scale(z)
            pt = (self.x + ox + sway * sc, H - 30 - self.h * sc * p)
            if prev is not None:
                pygame.draw.line(surf, self.color, prev, pt, max(2, int(6 * sc * (1.0 - 0.45 * p))))
            prev = pt


class Rock:
    def __init__(self):
        self.x = random.uniform(30, max(31, W - 30))
        self.z = random.uniform(0.22, Z_FAR)
        sc = z_scale(self.z)
        self.w = random.choice([28, 40, 55, 80, 110, 150]) * sc * random.uniform(0.8, 1.2)
        self.h = self.w * random.uniform(0.28, 0.55)
        self.col = tone_color(random.choice([
            (78, 82, 70), (64, 70, 60), (88, 86, 74), (56, 60, 52)
        ]))

    def draw(self, surf, ox=0):
        rect = pygame.Rect(0, 0, int(self.w), int(self.h))
        rect.midbottom = (int(self.x + ox), H - 24)
        pygame.draw.ellipse(surf, self.col, rect)


class Gem:
    def __init__(self):
        self.x = random.uniform(40, max(41, W - 40))
        self.y = random.uniform(max(40, H - 90), max(41, H - 40))
        self.z = random.uniform(Z_NEAR + 0.05, Z_FAR)
        self.col = tone_color(random.choice([
            (90, 110, 80), (70, 90, 70), (120, 115, 70), (80, 95, 88)
        ]))
        self.r = random.uniform(5, 14)
        self.phase = random.uniform(0, math.tau)

    def draw(self, surf, t, ox=0):
        r = max(2, int(self.r * z_scale(self.z)))
        spark = 0.72 + 0.18 * abs(math.sin(t * 3 + self.phase))
        y = int(clamp(self.col[0] * spark, LUMA_MIN, LUMA_MAX))
        col = (y, y, y)
        cx, cy = int(self.x + ox), int(self.y)
        pygame.draw.polygon(surf, col, [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])


class Sculpture:
    def __init__(self):
        self.x = random.uniform(80, max(81, W - 80))
        self.z = random.uniform(0.2, 0.95)
        self.h = random.uniform(70, 180) * z_scale(self.z)
        self.w = random.uniform(30, 70) * z_scale(self.z)
        self.kind = random.choice(("spiral", "arch", "obelisk"))
        self.col = tone_color((120, 128, 118))

    def draw(self, surf, t, ox=0):
        x = self.x + ox
        if self.kind == "obelisk":
            pygame.draw.polygon(surf, self.col, [
                (x, H - 30 - self.h), (x + self.w * 0.35, H - 30), (x - self.w * 0.35, H - 30)
            ])
        elif self.kind == "arch":
            rect = pygame.Rect(0, 0, int(self.w), int(self.h))
            rect.midbottom = (int(x), H - 28)
            pygame.draw.ellipse(surf, self.col, rect, max(3, int(6 * z_scale(self.z))))
        else:
            pts = [(x + math.sin(p * 6 + t * 0.4) * self.w * 0.45, H - 30 - self.h * p) for p in (i / 11 for i in range(12))]
            pygame.draw.lines(surf, self.col, False, pts, max(3, int(5 * z_scale(self.z))))


class PirateShip:
    def __init__(self):
        self.z = 0.62
        self.x = 80

    def draw(self, surf, t, ox=0):
        x = self.x + ox
        hull = tone_color((86, 64, 48))
        mast = tone_color((54, 46, 40))
        sail = tone_color((150, 148, 132))
        chest = tone_color((120, 96, 52))
        lid = tone_color((148, 128, 70))
        bone = tone_color((168, 164, 148))
        pygame.draw.polygon(surf, hull, [
            (x + 20, H - 70), (x + 280, H - 70), (x + 250, H - 150), (x + 50, H - 150)
        ])
        pygame.draw.polygon(surf, mast, [
            (x + 120, H - 150), (x + 132, H - 150), (x + 128, H - 268), (x + 122, H - 268)
        ])
        sway = math.sin(t * 0.7) * 6
        pygame.draw.polygon(surf, sail, [
            (x + 128, H - 255), (x + 210 + sway, H - 210), (x + 128, H - 198)
        ])
        pygame.draw.rect(surf, chest, (x + 150, H - 102, 56, 30))
        pygame.draw.rect(surf, lid, (x + 150, H - 102, 56, 9))
        for sx in (x + 70, x + 230):
            pygame.draw.circle(surf, bone, (sx, H - 118), 8)
            pygame.draw.line(surf, bone, (sx, H - 110), (sx, H - 78), 2)
            pygame.draw.line(surf, bone, (sx - 12, H - 98), (sx + 12, H - 98), 2)
            pygame.draw.line(surf, bone, (sx, H - 78), (sx - 8, H - 62), 2)
            pygame.draw.line(surf, bone, (sx, H - 78), (sx + 8, H - 62), 2)


class Castle:
    def __init__(self):
        self.z = 0.70

    def draw(self, surf, t, ox=0):
        base_x = W - 380 + ox
        stone = tone_color((118, 118, 112))
        dark = tone_color((78, 80, 74))
        roof = tone_color((92, 70, 62))
        pygame.draw.rect(surf, stone, (base_x, H - 210, 240, 170))
        for tw in (0, 95, 190):
            pygame.draw.rect(surf, dark, (base_x + tw, H - 268, 52, 70))
            pygame.draw.polygon(surf, roof, [
                (base_x + tw, H - 268),
                (base_x + tw + 26, H - 312),
                (base_x + tw + 52, H - 268),
            ])
            for merlon in range(3):
                pygame.draw.rect(surf, stone, (base_x + tw + 4 + merlon * 16, H - 278, 10, 12))
        pygame.draw.rect(surf, tone_color((52, 54, 50)), (base_x + 95, H - 118, 48, 78))
        pygame.draw.circle(surf, tone_color((52, 54, 50)), (base_x + 119, H - 118), 24)


class LavaBit:
    __slots__ = ("x", "y", "z", "vx", "vy", "vz", "life", "r")

    def __init__(self, cx, cy, cz):
        self.x = cx + random.uniform(-8, 8)
        self.y = cy
        self.z = cz
        spread = random.uniform(-70, 70)
        up = random.uniform(-420, -220)
        self.vx = spread
        self.vy = up
        self.vz = random.uniform(-0.55, -0.18)
        self.life = random.uniform(1.2, 2.4)
        self.r = random.uniform(3, 8)

    def update(self, dt):
        self.vy += 280 * dt
        self.vz += 0.12 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.z = clamp(self.z + self.vz * dt, Z_NEAR, Z_FAR)
        self.life -= dt
        return self.life > 0 and self.y < H + 20

    def draw(self, surf, ox=0):
        age = clamp(self.life / 2.4, 0.0, 1.0)
        y = int(lerp(70, 175, age))
        col = tone_color((y + 20, y - 10, y - 30))
        r = max(1, int(self.r * z_scale(self.z) * (0.45 + 0.55 * age)))
        pygame.draw.circle(surf, col, (int(self.x + ox), int(self.y)), r)


class Volcano:
    def __init__(self):
        self.z = 0.78
        self.particles = []
        self.burst_t = 0.0
        self.gushing = False
        self.gush_left = 0.0

    def update(self, dt):
        self.burst_t -= dt
        self.gush_left -= dt
        if self.gush_left <= 0:
            self.gushing = False
        if self.burst_t <= 0:
            if random.random() < 0.45:
                self.gushing = True
                self.gush_left = random.uniform(1.6, 3.2)
                self.burst_t = random.uniform(4.0, 8.0)
            else:
                self.burst_t = random.uniform(0.8, 2.2)
        cx, cy, cz = W * 0.5, H - 258, self.z - 0.04
        n = 18 if self.gushing else (4 if random.random() < 0.5 else 0)
        for _ in range(n):
            self.particles.append(LavaBit(cx, cy, cz))
        self.particles = [p for p in self.particles if p.update(dt)]

    def draw(self, surf, t, ox=0, eye_sign=0):
        cx = W * 0.5 + ox
        cone = tone_color((74, 58, 48))
        crater = tone_color((52, 44, 40))
        pygame.draw.polygon(surf, cone, [
            (cx - 170, H - 30), (cx + 170, H - 30), (cx, H - 268)
        ])
        pygame.draw.polygon(surf, crater, [
            (cx - 46, H - 236), (cx + 46, H - 236), (cx, H - 268)
        ])
        for p in self.particles:
            pox = eye_sign * parallax_px(p.z)
            p.draw(surf, pox - ox + ox)


class Tank:
    def __init__(self):
        self.mode_i = 0
        self.swap_filters = False
        self.target_count = 20
        self.randomize()

    def randomize(self):
        self.fish = []
        self.flocks = []
        self.target_count = random.randint(16, 24)
        for _ in range(random.randint(1, 2)):
            fl = Flock()
            self.flocks.append(fl)
            self.fish.extend(fl.members)
        kinds_loose = [k for k in FISH_KINDS if k != "angelfish"]
        while len(self.fish) < self.target_count:
            k = random.choice(kinds_loose + ["angelfish", "grouper"])
            self.fish.append(Fish(k, small_angel=False))
        self.kelp = [Kelp() for _ in range(random.randint(10, 18))]
        self.rocks = [Rock() for _ in range(random.randint(8, 16))]
        self.gems = [Gem() for _ in range(random.randint(8, 16))]
        self.sculptures = [Sculpture() for _ in range(random.randint(3, 7))]
        self.bubbles = [Bubble() for _ in range(28)]
        self.pirate = PirateShip()
        self.castle = Castle()
        self.volcano = Volcano()
        self.t = 0.0

    def _spawn_replacement(self):
        edge = random.choice(("left", "right", "top", "bottom"))
        if random.random() < 0.2:
            fl = Flock()
            for i, m in enumerate(fl.members):
                m.reset(full=False, edge=edge)
                m.x += i * 12
            self.flocks.append(fl)
            self.fish.extend(fl.members)
            return
        f = Fish(random.choice(FISH_KINDS))
        f.reset(full=False, edge=edge)
        self.fish.append(f)

    @property
    def mode(self):
        return MODES[self.mode_i]

    def toggle_mode(self):
        self.mode_i = (self.mode_i + 1) % len(MODES)

    def toggle_filter_sides(self):
        self.swap_filters = not self.swap_filters

    def update(self, dt):
        self.t += dt
        living = [f for f in self.fish if f.alive]
        for f in living:
            f.update(dt, living)
        for fl in self.flocks:
            if fl.leader is None or not fl.leader.alive:
                live = fl.living()
                if live:
                    fl.leader = live[0]
                    fl.leader.is_leader = True
                    for i, m in enumerate(live):
                        m.slot = i
                        m.flock = fl
                else:
                    fl.leader = None
        stayed = []
        for f in self.fish:
            if not f.alive or f.offscreen():
                continue
            stayed.append(f)
        self.fish = stayed
        while len(self.fish) < self.target_count:
            self._spawn_replacement()
        for b in self.bubbles:
            b.update(dt)
        self.volcano.update(dt)

    def _draw_scene(self, surf, eye_sign=0):
        step = 8
        for y in range(0, H, step):
            c = int(lerp(42, 78, y / max(1, H)))
            pygame.draw.rect(surf, (c, c, c), (0, y, W, step))
        pygame.draw.rect(surf, tone_color((120, 112, 88)), (0, H - 36, W, 36))

        items = []
        for r in self.rocks:
            items.append((r.z, "rock", r))
        for k in self.kelp:
            items.append((k.z, "kelp", k))
        for g in self.gems:
            items.append((g.z, "gem", g))
        for s in self.sculptures:
            items.append((s.z, "sculpt", s))
        items.append((self.pirate.z, "pirate", self.pirate))
        items.append((self.castle.z, "castle", self.castle))
        items.append((self.volcano.z, "volcano", self.volcano))
        for f in self.fish:
            items.append((f.z, "fish", f))
        for b in self.bubbles:
            items.append((b.z, "bubble", b))
        items.sort(key=lambda it: -it[0])

        for z, typ, obj in items:
            ox = eye_sign * parallax_px(z)
            if typ == "rock":
                obj.draw(surf, ox)
            elif typ == "kelp":
                obj.draw(surf, self.t, eye_sign)
            elif typ == "gem":
                obj.draw(surf, self.t, ox)
            elif typ == "sculpt":
                obj.draw(surf, self.t, ox)
            elif typ == "pirate":
                obj.draw(surf, self.t, ox)
            elif typ == "castle":
                obj.draw(surf, self.t, ox)
            elif typ == "volcano":
                obj.draw(surf, self.t, ox, eye_sign)
            elif typ == "fish":
                obj.draw(surf, ox)
            else:
                obj.draw(surf, ox)
        pygame.draw.rect(surf, tone_color((140, 148, 142)), (0, 0, W, H), 3)

    def draw(self, screen):
        if self.mode == "normal":
            self._draw_scene(screen, 0)
        else:
            left = pygame.Surface((W, H))
            right = pygame.Surface((W, H))
            left.fill((48, 48, 48))
            right.fill((48, 48, 48))
            self._draw_scene(left, -1)
            self._draw_scene(right, +1)
            if self.swap_filters:
                left, right = right, left
            screen.blit(compose_anaglyph(left, right, self.mode), (0, 0))


def parse_args():
    p = argparse.ArgumentParser(description="3D fish tank")
    p.add_argument("--song", default=None, help="Background music file (mp3/ogg/wav)")
    return p.parse_args()


def main():
    global W, H
    args = parse_args()

    pygame.init()
    pygame.display.init()

    cfg = load_window_cfg()
    W, H = cfg["w"], cfg["h"]
    if cfg["x"] is not None and cfg["y"] is not None:
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{cfg['x']},{cfg['y']}"

    pygame.display.set_caption("Fish Tank 3D")
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    if args.song:
        try:
            pygame.mixer.init()
            pygame.mixer.music.load(args.song)
            pygame.mixer.music.set_volume(0.45)
            pygame.mixer.music.play(-1)
        except pygame.error as e:
            print(f"Could not play song: {e}", file=sys.stderr)

    tank = Tank()
    running = True
    while running:
        dt = min(0.05, clock.tick(FPS) / 1000.0)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE:
                W = max(MIN_W, e.w)
                H = max(MIN_H, e.h)
                screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
                save_window_cfg((W, H))
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_t:
                    tank.toggle_mode()
                elif e.key == pygame.K_y:
                    tank.toggle_filter_sides()
                elif e.key == pygame.K_x:
                    tank.randomize()

        tank.update(dt)
        tank.draw(screen)
        pygame.display.flip()

    save_window_cfg()
    pygame.quit()


if __name__ == "__main__":
    main()