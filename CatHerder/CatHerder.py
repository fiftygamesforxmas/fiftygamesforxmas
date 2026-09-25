#!/usr/bin/env python3
"""
Cat Herder — Pygame herding game (2.5D orthogonal-ish arena).
Requires: pygame
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import wave
from dataclasses import dataclass, field
from typing import List, Optional

import pygame

ROOT = os.path.dirname(os.path.abspath(__file__))
SOUND_DIR = os.path.join(ROOT, "herd_sounds")
CONFIG_PATH = os.path.join(ROOT, "cat_herder_window.json")
FPS = 60
ROUND_SECONDS = 300
SPLASH_SECONDS = 10
ARENA_W, ARENA_H = 1400, 900
PEN_SIZE = 220


def load_window_geom():
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            return int(d.get("x", 80)), int(d.get("y", 60)), int(d.get("w", 1100)), int(d.get("h", 750))
        except Exception:
            pass
    return 80, 60, 1100, 750


def save_window_geom(x, y, w, h):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"x": x, "y": y, "w": w, "h": h}, f)
    except Exception:
        pass


def _ensure_dir():
    os.makedirs(SOUND_DIR, exist_ok=True)


def _write_wav(path, samples, rate=22050):
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples
        )
        w.writeframes(frames)


def _tone(freq, dur, rate=22050, vol=0.35, wave_kind="sine", decay=True):
    n = int(rate * dur)
    out = []
    for i in range(n):
        t = i / rate
        env = (1.0 - t / dur) if decay else 1.0
        if wave_kind == "sine":
            v = math.sin(2 * math.pi * freq * t)
        elif wave_kind == "square":
            v = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        elif wave_kind == "noise":
            v = random.uniform(-1, 1)
        else:
            v = math.sin(2 * math.pi * freq * t) * 0.7 + random.uniform(-0.3, 0.3)
        out.append(v * vol * max(0.0, env))
    return out


def _chirp(f0, f1, dur, rate=22050, vol=0.3):
    n = int(rate * dur)
    out = []
    for i in range(n):
        t = i / rate
        f = f0 + (f1 - f0) * (t / dur)
        env = 1.0 - t / dur
        out.append(math.sin(2 * math.pi * f * t) * vol * env)
    return out


def generate_sounds():
    _ensure_dir()
    specs = {
        "rat": {"f": 780, "kind": "chirp"},
        "frog": {"f": 140, "kind": "square"},
        "lizard": {"f": 420, "kind": "noise"},
        "duck": {"f": 310, "kind": "square"},
        "ostrich": {"f": 180, "kind": "sine"},
        "squirrel": {"f": 900, "kind": "chirp"},
        "tarantula": {"f": 90, "kind": "noise"},
        "dog": {"f": 220, "kind": "square"},
        "goat": {"f": 260, "kind": "sine"},
        "sheep": {"f": 340, "kind": "sine"},
        "cow": {"f": 110, "kind": "sine"},
        "bear": {"f": 70, "kind": "noise"},
        "cat": {"f": 520, "kind": "chirp"},
        "alien": {"f": 640, "kind": "square"},
    }
    for name, sp in specs.items():
        f = sp["f"]
        files = {
            "backoff": os.path.join(SOUND_DIR, f"{name}_backoff.wav"),
            "group": os.path.join(SOUND_DIR, f"{name}_group.wav"),
            "hit": os.path.join(SOUND_DIR, f"{name}_hit.wav"),
            "fight": os.path.join(SOUND_DIR, f"{name}_fight.wav"),
        }
        if not os.path.isfile(files["backoff"]):
            if sp["kind"] == "chirp":
                _write_wav(files["backoff"], _chirp(f, f * 0.5, 0.22))
            else:
                _write_wav(files["backoff"], _tone(f * 1.3, 0.18, wave_kind=sp["kind"]))
        if not os.path.isfile(files["group"]):
            _write_wav(files["group"], _tone(f * 0.85, 0.28, wave_kind="sine", vol=0.22))
        if not os.path.isfile(files["hit"]):
            _write_wav(files["hit"], _tone(f * 1.6, 0.12, wave_kind="noise", vol=0.4))
        if not os.path.isfile(files["fight"]):
            _write_wav(files["fight"], _tone(f * 0.7, 0.25, wave_kind="square", vol=0.3))
    for i, (a, b) in enumerate([(700, 400), (880, 220), (500, 900)]):
        p = os.path.join(SOUND_DIR, f"cat_fight{i + 2}.wav")
        if not os.path.isfile(p):
            _write_wav(p, _chirp(a, b, 0.3, vol=0.32))
    extras = {
        "stick.wav": _tone(180, 0.08, wave_kind="noise", vol=0.45),
        "pen.wav": _chirp(200, 600, 0.35, vol=0.28),
        "bolt.wav": _tone(1100, 0.12, wave_kind="square", vol=0.2),
        "lure.wav": _tone(440, 0.15, wave_kind="sine", vol=0.25),
        "tame.wav": _chirp(120, 480, 0.5, vol=0.3),
        "hurt.wav": _tone(90, 0.3, wave_kind="noise", vol=0.4),
        "teleport.wav": _chirp(200, 1400, 0.2, vol=0.28),
    }
    for fn, samples in extras.items():
        path = os.path.join(SOUND_DIR, fn)
        if not os.path.isfile(path):
            _write_wav(path, samples)


class SFX:
    def __init__(self):
        self.ok = False
        self.bank = {}
        try:
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            self.ok = True
        except Exception:
            self.ok = False
        if self.ok:
            for fn in os.listdir(SOUND_DIR):
                if fn.endswith(".wav"):
                    try:
                        self.bank[fn[:-4]] = pygame.mixer.Sound(os.path.join(SOUND_DIR, fn))
                    except Exception:
                        pass

    def play(self, key, vol=0.45):
        if not self.ok:
            return
        snd = self.bank.get(key)
        if snd:
            snd.set_volume(vol)
            snd.play()


SPECIES = {
    "rat": {"color": (150, 150, 150), "r": 9, "speed": 2.6, "herd": 1.2, "power": 1, "lure": "bugs"},
    "frog": {"color": (40, 160, 70), "r": 11, "speed": 2.2, "herd": 1.4, "power": 2, "lure": "bugs"},
    "lizard": {"color": (70, 140, 50), "r": 12, "speed": 2.4, "herd": 1.6, "power": 3, "lure": "bugs"},
    "duck": {"color": (210, 180, 40), "r": 14, "speed": 2.0, "herd": 1.8, "power": 4, "lure": "grain"},
    "squirrel": {"color": (170, 100, 40), "r": 11, "speed": 3.0, "herd": 2.0, "power": 3, "lure": "grain"},
    "tarantula": {"color": (80, 40, 20), "r": 13, "speed": 1.8, "herd": 2.3, "power": 5, "lure": "bugs"},
    "dog": {"color": (160, 110, 60), "r": 17, "speed": 2.5, "herd": 2.5, "power": 7, "lure": "bone"},
    "goat": {"color": (200, 200, 190), "r": 18, "speed": 2.1, "herd": 2.8, "power": 8, "lure": "grain"},
    "sheep": {"color": (230, 230, 230), "r": 18, "speed": 1.7, "herd": 3.1, "power": 8, "lure": "grain"},
    "ostrich": {"color": (180, 140, 80), "r": 23, "speed": 3.2, "herd": 3.4, "power": 9, "lure": "grain"},
    "cow": {"color": (90, 70, 50), "r": 27, "speed": 1.4, "herd": 3.8, "power": 10, "lure": "grain"},
    "bear": {"color": (90, 55, 25), "r": 32, "speed": 1.9, "herd": 99, "power": 14, "lure": None},
    "cat": {"color": (240, 140, 40), "r": 15, "speed": 2.8, "herd": 4.2, "power": 12, "lure": "catnip"},
    "alien": {"color": (80, 255, 120), "r": 19, "speed": 2.2, "herd": 4.5, "power": 15, "lure": "tech"},
}

BEHAVIOR = {
    "frog": {"hop": "high", "hop_cd": (0.35, 0.7)},
    "squirrel": {"hop": "high", "hop_cd": (0.25, 0.55)},
    "goat": {"hop": "low", "hop_cd": (0.45, 0.9)},
    "sheep": {"hop": "low", "hop_cd": (0.55, 1.1)},
    "dog": {"run_around": True},
    "ostrich": {"run_around": True},
    "rat": {"run_around": True},
    "cat": {"run_around": True},
}

CAT_VARIANTS = [
    {"name": "ginger", "color": (230, 130, 30), "stripes": True},
    {"name": "siamese", "color": (240, 230, 210), "points": (60, 40, 30)},
    {"name": "russian_blue", "color": (90, 110, 130), "stripes": False},
    {"name": "black", "color": (30, 30, 32), "stripes": False},
    {"name": "white", "color": (245, 245, 248), "stripes": False},
    {"name": "calico", "color": (220, 160, 80), "patches": True},
]

WAVES = [
    ["rat"] * 10,
    ["dog"] * 6,
    ["goat"] * 6,
    ["sheep"] * 6,
    ["squirrel"] * 8,
    ["tarantula"] * 7,
    ["cow"] * 4,
    ["bear"] * 1,
    ["cat"] * 8,
    ["alien"] * 5,
    ["rat", "frog", "lizard", "duck", "ostrich", "dog", "goat", "sheep",
     "squirrel", "tarantula", "cow", "cat", "alien", "cat", "dog", "sheep"],
]


def shade(color, k):
    return tuple(max(0, min(255, int(c * k))) for c in color)


def facing_from_vel(vx, vy, fallback=1):
    if abs(vx) < 0.05 and abs(vy) < 0.05:
        return fallback
    return 1 if vx >= 0 else -1


_SPRITE_CACHE = {}


def _base_surf(w, h):
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _eye(s, x, y, r=2, col=(20, 20, 20), gleam=True):
    pygame.draw.circle(s, col, (int(x), int(y)), max(1, r))
    if gleam and r >= 2:
        pygame.draw.circle(s, (255, 255, 255), (int(x - r * 0.3), int(y - r * 0.3)), max(1, r // 3))


def draw_rat_sprite(col, face):
    s = _base_surf(48, 32)
    body, dark = shade(col, 0.95), shade(col, 0.7)
    pygame.draw.ellipse(s, body, (8, 12, 26, 14))
    pygame.draw.circle(s, body, (34, 16), 7)
    pygame.draw.circle(s, (230, 180, 180), (36, 12), 3)
    pygame.draw.circle(s, (230, 180, 180), (30, 11), 3)
    pygame.draw.circle(s, (40, 30, 30), (40, 17), 2)
    _eye(s, 36, 15, 2)
    pygame.draw.lines(s, (180, 120, 130), False, [(10, 18), (3, 10), (1, 20), (8, 22)], 2)
    pygame.draw.ellipse(s, dark, (14, 22, 7, 5))
    pygame.draw.ellipse(s, dark, (22, 23, 7, 5))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_frog_sprite(col, face):
    s = _base_surf(44, 32)
    pygame.draw.ellipse(s, col, (8, 12, 28, 16))
    pygame.draw.circle(s, shade(col, 0.85), (16, 12), 6)
    pygame.draw.circle(s, shade(col, 0.85), (28, 12), 6)
    pygame.draw.circle(s, (250, 250, 210), (16, 11), 3)
    pygame.draw.circle(s, (250, 250, 210), (28, 11), 3)
    _eye(s, 16, 11, 2)
    _eye(s, 28, 11, 2)
    pygame.draw.ellipse(s, shade(col, 0.7), (4, 20, 12, 8))
    pygame.draw.ellipse(s, shade(col, 0.7), (28, 20, 12, 8))
    pygame.draw.arc(s, (20, 60, 30), (16, 18, 12, 8), 3.4, 6.0, 2)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_lizard_sprite(col, face):
    s = _base_surf(56, 28)
    pygame.draw.ellipse(s, col, (12, 10, 26, 10))
    pygame.draw.circle(s, col, (38, 14), 6)
    pygame.draw.polygon(s, col, [(12, 14), (1, 8), (4, 16)])
    pygame.draw.polygon(s, shade(col, 0.75), [(22, 10), (18, 4), (26, 10)])
    pygame.draw.polygon(s, shade(col, 0.75), [(22, 20), (18, 26), (26, 20)])
    _eye(s, 40, 12, 2, (40, 220, 80))
    pygame.draw.circle(s, (30, 40, 20), (44, 15), 2)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_duck_sprite(col, face, flying=False):
    s = _base_surf(52, 40)
    pygame.draw.ellipse(s, col, (8, 16, 26, 14))
    pygame.draw.circle(s, col, (32, 14), 8)
    pygame.draw.polygon(s, (230, 120, 30), [(38, 14), (48, 16), (38, 19)])
    _eye(s, 34, 12, 2)
    if flying:
        pygame.draw.ellipse(s, shade(col, 0.85), (4, 8, 22, 8))
        pygame.draw.ellipse(s, shade(col, 0.85), (18, 6, 22, 8))
    else:
        pygame.draw.ellipse(s, shade(col, 0.8), (6, 18, 12, 8))
        pygame.draw.line(s, (40, 30, 20), (18, 28), (16, 34), 2)
        pygame.draw.line(s, (40, 30, 20), (24, 28), (26, 34), 2)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_ostrich_sprite(col, face):
    s = _base_surf(44, 64)
    pygame.draw.ellipse(s, col, (10, 28, 22, 16))
    pygame.draw.line(s, col, (22, 30), (24, 10), 4)
    pygame.draw.circle(s, (240, 220, 180), (26, 8), 6)
    pygame.draw.polygon(s, (40, 30, 20), [(30, 8), (40, 10), (30, 12)])
    _eye(s, 28, 7, 2)
    pygame.draw.line(s, (40, 30, 20), (16, 42), (12, 60), 3)
    pygame.draw.line(s, (40, 30, 20), (26, 42), (30, 60), 3)
    pygame.draw.polygon(s, shade(col, 0.7), [(8, 30), (2, 18), (14, 28)])
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_squirrel_sprite(col, face):
    s = _base_surf(44, 40)
    pygame.draw.ellipse(s, col, (12, 16, 18, 12))
    pygame.draw.circle(s, col, (30, 14), 7)
    pygame.draw.circle(s, shade(col, 0.8), (28, 8), 4)
    pygame.draw.circle(s, shade(col, 0.8), (34, 8), 4)
    _eye(s, 32, 13, 2)
    pygame.draw.circle(s, (30, 20, 15), (36, 16), 2)
    pygame.draw.ellipse(s, shade(col, 1.05), (2, 6, 16, 22))
    pygame.draw.ellipse(s, shade(col, 0.7), (16, 24, 7, 8))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_tarantula_sprite(col, face):
    s = _base_surf(52, 36)
    dark = shade(col, 0.75)
    cx, cy = 26, 18
    pygame.draw.circle(s, col, (cx - 6, cy), 7)
    pygame.draw.circle(s, dark, (cx + 6, cy), 8)
    legs = [(-18, -10), (-20, -2), (-18, 8), (-14, 14), (18, -10), (20, -2), (18, 8), (14, 14)]
    for lx, ly in legs:
        pygame.draw.line(s, dark, (cx, cy), (cx + lx, cy + ly), 2)
        pygame.draw.circle(s, dark, (cx + lx, cy + ly), 2)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_dog_sprite(col, face, patch=None):
    s = _base_surf(56, 40)
    dark = shade(col, 0.7)
    pygame.draw.ellipse(s, col, (8, 16, 28, 16))
    pygame.draw.circle(s, col, (36, 16), 9)
    pygame.draw.ellipse(s, dark, (28, 8, 8, 12))
    pygame.draw.ellipse(s, dark, (40, 8, 8, 12))
    pygame.draw.circle(s, (30, 20, 15), (44, 18), 3)
    pygame.draw.ellipse(s, (250, 230, 230), (38, 18, 10, 6))
    _eye(s, 34, 14, 2)
    _eye(s, 40, 14, 2)
    if patch == "L":
        pygame.draw.circle(s, (25, 20, 18), (34, 14), 5)
        _eye(s, 34, 14, 2, (240, 240, 240))
    elif patch == "R":
        pygame.draw.circle(s, (25, 20, 18), (40, 14), 5)
        _eye(s, 40, 14, 2, (240, 240, 240))
    pygame.draw.ellipse(s, dark, (10, 28, 8, 8))
    pygame.draw.ellipse(s, dark, (22, 28, 8, 8))
    pygame.draw.lines(s, dark, False, [(10, 20), (2, 12), (6, 22)], 3)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_goat_sprite(col, face):
    s = _base_surf(56, 44)
    pygame.draw.ellipse(s, col, (10, 18, 28, 16))
    pygame.draw.circle(s, col, (38, 18), 8)
    pygame.draw.line(s, (220, 220, 210), (34, 12), (28, 2), 2)
    pygame.draw.line(s, (220, 220, 210), (42, 12), (48, 2), 2)
    _eye(s, 36, 17, 2)
    _eye(s, 42, 17, 2)
    pygame.draw.circle(s, (40, 30, 25), (46, 20), 2)
    pygame.draw.line(s, shade(col, 0.6), (16, 32), (14, 42), 3)
    pygame.draw.line(s, shade(col, 0.6), (28, 32), (30, 42), 3)
    pygame.draw.rect(s, (80, 60, 40), (42, 20, 2, 8))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_sheep_sprite(col, face):
    s = _base_surf(56, 40)
    pygame.draw.circle(s, col, (18, 20), 10)
    pygame.draw.circle(s, col, (28, 16), 11)
    pygame.draw.circle(s, col, (36, 22), 10)
    pygame.draw.circle(s, col, (24, 26), 9)
    pygame.draw.circle(s, (40, 30, 28), (42, 20), 7)
    _eye(s, 40, 18, 2, (240, 240, 200))
    pygame.draw.rect(s, (40, 30, 25), (16, 30, 4, 8))
    pygame.draw.rect(s, (40, 30, 25), (30, 30, 4, 8))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_cow_sprite(col, face):
    s = _base_surf(72, 48)
    pygame.draw.ellipse(s, col, (8, 16, 42, 22))
    pygame.draw.circle(s, (240, 235, 220), (22, 22), 7)
    pygame.draw.circle(s, (30, 25, 20), (36, 28), 6)
    pygame.draw.circle(s, col, (50, 16), 10)
    pygame.draw.polygon(s, (250, 250, 240), [(44, 10), (42, 2), (50, 10)])
    pygame.draw.polygon(s, (250, 250, 240), [(54, 10), (60, 2), (58, 12)])
    pygame.draw.ellipse(s, (230, 160, 160), (52, 18, 14, 10))
    _eye(s, 48, 14, 2)
    pygame.draw.rect(s, shade(col, 0.6), (16, 34, 6, 12))
    pygame.draw.rect(s, shade(col, 0.6), (30, 34, 6, 12))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_bear_sprite(col, face, tame=False):
    s = _base_surf(72, 56)
    dark = shade(col, 0.75)
    pygame.draw.ellipse(s, col, (10, 18, 40, 26))
    pygame.draw.circle(s, col, (48, 20), 14)
    pygame.draw.circle(s, dark, (40, 10), 6)
    pygame.draw.circle(s, dark, (56, 10), 6)
    pygame.draw.ellipse(s, (50, 30, 20), (50, 22, 16, 10))
    pygame.draw.circle(s, (20, 12, 8), (64, 26), 3)
    _eye(s, 46, 18, 3, (10, 10, 10) if not tame else (80, 140, 40))
    _eye(s, 54, 18, 3, (10, 10, 10) if not tame else (80, 140, 40))
    pygame.draw.ellipse(s, dark, (12, 36, 12, 10))
    pygame.draw.ellipse(s, dark, (28, 38, 12, 10))
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_cat_sprite(variant, face):
    col = variant["color"]
    s = _base_surf(52, 40)
    dark = shade(col, 0.7)
    pygame.draw.ellipse(s, col, (8, 16, 26, 14))
    pygame.draw.circle(s, col, (34, 14), 9)
    pygame.draw.polygon(s, col, [(28, 10), (26, 2), (34, 10)])
    pygame.draw.polygon(s, col, [(36, 10), (42, 1), (44, 12)])
    inner = variant.get("points", (80, 40, 50))
    pygame.draw.polygon(s, inner, [(29, 10), (28, 5), (33, 10)])
    pygame.draw.polygon(s, inner, [(37, 10), (41, 4), (42, 11)])
    if variant.get("points"):
        pygame.draw.circle(s, variant["points"], (34, 16), 5)
    if variant.get("stripes"):
        for ox in (12, 18, 24):
            pygame.draw.line(s, dark, (ox, 18), (ox + 2, 26), 2)
    if variant.get("patches"):
        pygame.draw.circle(s, (30, 30, 30), (16, 20), 4)
        pygame.draw.circle(s, (200, 60, 40), (24, 24), 4)
    pygame.draw.ellipse(s, (240, 200, 200), (34, 16, 10, 6))
    _eye(s, 32, 13, 2, (40, 90, 255))
    _eye(s, 38, 13, 2, (40, 230, 50))
    pygame.draw.lines(s, col, False, [(10, 18), (2, 8), (8, 4)], 3)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def draw_alien_sprite(col, face):
    s = _base_surf(48, 52)
    pygame.draw.ellipse(s, col, (14, 4, 20, 26))
    pygame.draw.ellipse(s, shade(col, 0.6), (18, 28, 12, 16))
    pygame.draw.ellipse(s, (10, 10, 20), (16, 12, 8, 12))
    pygame.draw.ellipse(s, (10, 10, 20), (24, 12, 8, 12))
    pygame.draw.ellipse(s, (180, 255, 80), (18, 14, 4, 8))
    pygame.draw.ellipse(s, (180, 255, 80), (26, 14, 4, 8))
    pygame.draw.line(s, col, (16, 30), (6, 40), 3)
    pygame.draw.line(s, col, (32, 30), (42, 40), 3)
    pygame.draw.circle(s, (40, 255, 180), (24, 2), 3)
    return pygame.transform.flip(s, True, False) if face < 0 else s


def get_animal_sprite(a, sc):
    face = facing_from_vel(a.vx, a.vy, a.face)
    a.face = face
    key = (a.kind, a.variant.get("name"), a.patch_eye, a.tame, face, a.flying, round(sc, 2), a.color)
    if key in _SPRITE_CACHE:
        return _SPRITE_CACHE[key]
    drawers = {
        "rat": lambda: draw_rat_sprite(a.color, face),
        "frog": lambda: draw_frog_sprite(a.color, face),
        "lizard": lambda: draw_lizard_sprite(a.color, face),
        "duck": lambda: draw_duck_sprite(a.color, face, a.flying),
        "ostrich": lambda: draw_ostrich_sprite(a.color, face),
        "squirrel": lambda: draw_squirrel_sprite(a.color, face),
        "tarantula": lambda: draw_tarantula_sprite(a.color, face),
        "dog": lambda: draw_dog_sprite(a.color, face, a.patch_eye),
        "goat": lambda: draw_goat_sprite(a.color, face),
        "sheep": lambda: draw_sheep_sprite(a.color, face),
        "cow": lambda: draw_cow_sprite(a.color, face),
        "bear": lambda: draw_bear_sprite(a.color, face, a.tame),
        "cat": lambda: draw_cat_sprite(a.variant or CAT_VARIANTS[0], face),
        "alien": lambda: draw_alien_sprite(a.color, face),
    }
    raw = drawers.get(a.kind, drawers["rat"])()
    w = max(8, int(raw.get_width() * sc * (a.r / 14)))
    h = max(8, int(raw.get_height() * sc * (a.r / 14)))
    spr = pygame.transform.smoothscale(raw, (w, h))
    _SPRITE_CACHE[key] = spr
    return spr


@dataclass
class Lure:
    kind: str
    x: float
    y: float
    life: float = 18.0


@dataclass
class Bolt:
    x: float
    y: float
    vx: float
    vy: float
    life: float = 3.5


@dataclass
class Animal:
    kind: str
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    in_pen: bool = False
    hp: int = 3
    tame: bool = False
    hits: int = 0
    variant: dict = field(default_factory=dict)
    patch_eye: Optional[str] = None
    fight_cd: float = 0.0
    sound_cd: float = 0.0
    grouped: bool = False
    shoot_cd: float = 0.0
    alive: bool = True
    face: int = 1
    asleep: bool = False
    wake_hits: int = 0
    hop_phase: float = 0.0
    hop_cd: float = 0.0
    hop_z: float = 0.0
    flying: bool = False
    fly_time: float = 0.0
    fly_cd: float = 0.0
    snake_t: float = 0.0
    snake_heading: float = 0.0
    run_t: float = 0.0
    run_heading: float = 0.0
    running: bool = False
    tame_left: float = 0.0
    teleport_cd: float = 0.0

    @property
    def spec(self):
        return SPECIES[self.kind]

    @property
    def r(self):
        return self.spec["r"]

    @property
    def color(self):
        if self.kind == "cat" and self.variant:
            return self.variant["color"]
        return self.spec["color"]


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.speed = 3.4
        self.dir = 0.0
        self.swing = 0.0
        self.hp = 8
        self.lure_counts = {"bone": 6, "grain": 8, "catnip": 5, "tech": 4, "bugs": 8}


def make_leaping_cat(w=520, h=280) -> pygame.Surface:
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (28, 28, 30), pygame.Rect(90, 110, 220, 90))
    pygame.draw.ellipse(s, (50, 50, 54), (120, 140, 160, 50))
    pygame.draw.ellipse(s, (22, 22, 24), (70, 160, 70, 28))
    pygame.draw.ellipse(s, (22, 22, 24), (50, 145, 55, 22))
    pygame.draw.ellipse(s, (22, 22, 24), (280, 150, 80, 22))
    pygame.draw.ellipse(s, (22, 22, 24), (300, 125, 70, 18))
    pygame.draw.lines(s, (20, 20, 22), False, [(95, 150), (40, 90), (20, 40), (55, 20)], 8)
    pygame.draw.circle(s, (30, 30, 32), (340, 95), 42)
    pygame.draw.polygon(s, (25, 25, 28), [(318, 70), (325, 28), (348, 68)])
    pygame.draw.polygon(s, (25, 25, 28), [(348, 65), (380, 22), (372, 78)])
    pygame.draw.ellipse(s, (40, 90, 255), (331, 84, 16, 12))
    pygame.draw.ellipse(s, (40, 230, 50), (355, 82, 16, 12))
    pygame.draw.circle(s, (10, 10, 12), (340, 90), 3)
    pygame.draw.circle(s, (10, 10, 12), (364, 88), 3)
    return s


def streak_title(surface, text, font, y=36):
    w = surface.get_width()
    base = font.render(text, True, (255, 40, 40))
    for i, alpha in enumerate((40, 70, 110, 160)):
        ghost = font.render(text, True, (255, 30, 30))
        ghost.set_alpha(alpha)
        surface.blit(ghost, (w // 2 - base.get_width() // 2 - 18 + i * 7, y - 4 + i))
    surface.blit(base, (w // 2 - base.get_width() // 2 + 16, y))


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.font = pygame.font.SysFont("georgia", 22)
        self.big = pygame.font.SysFont("impact", 72)
        self.sfx = SFX()
        self.infinite_time = False
        self.reset()

    def reset(self):
        self.player = Player(ARENA_W * 0.5, ARENA_H * 0.75)
        self.animals: List[Animal] = []
        self.lures: List[Lure] = []
        self.bolts: List[Bolt] = []
        self.wave_i = 0
        self.time_left = float(ROUND_SECONDS)
        self.score = 0
        self.over = False
        self.walls = self._make_walls()
        self.pen = pygame.Rect(
            ARENA_W // 2 - PEN_SIZE // 2, ARENA_H // 2 - PEN_SIZE // 2, PEN_SIZE, PEN_SIZE
        )
        self.spawn_wave()

    def cycle_level(self):
        """Infinite-time debug: advance to the next wave, wrapping around."""
        if not self.infinite_time or self.over:
            return
        self.wave_i = (self.wave_i + 1) % len(WAVES)
        self.bolts.clear()
        self.lures.clear()
        self.spawn_wave(clear_pen=True)
        self.sfx.play("pen", 0.25)

    def _make_walls(self):
        return [
            pygame.Rect(180, 140, 220, 28),
            pygame.Rect(980, 160, 240, 28),
            pygame.Rect(160, 620, 28, 180),
            pygame.Rect(1180, 500, 28, 220),
            pygame.Rect(420, 720, 260, 24),
            pygame.Rect(740, 80, 24, 160),
        ]

    def spawn_wave(self, clear_pen=False):
        kinds = WAVES[min(self.wave_i, len(WAVES) - 1)]
        if clear_pen:
            self.animals = []
        else:
            self.animals = [a for a in self.animals if a.in_pen and a.alive]
        sleepers = {"cow", "sheep", "cat", "dog", "goat", "tarantula"}
        for k in kinds:
            for _try in range(40):
                x = random.uniform(80, ARENA_W - 80)
                y = random.uniform(80, ARENA_H - 80)
                if self.pen.inflate(80, 80).collidepoint(x, y):
                    continue
                if any(w.inflate(20, 20).collidepoint(x, y) for w in self.walls):
                    continue
                a = Animal(k, x, y)
                if k == "cat":
                    a.variant = random.choice(CAT_VARIANTS)
                if k == "dog" and random.random() < 0.55:
                    a.patch_eye = random.choice(["L", "R"])
                if k == "bear":
                    a.hp = 6
                    a.tame = False
                    a.tame_left = 0
                if k in sleepers and random.random() < 0.28:
                    a.asleep = True
                    a.wake_hits = 0
                a.snake_heading = random.uniform(0, math.tau)
                a.run_heading = random.uniform(0, math.tau)
                a.fly_cd = random.uniform(2.0, 8.0)
                a.teleport_cd = random.uniform(3.0, 8.0)
                self.animals.append(a)
                break

    def blocked(self, x, y, r=10):
        if x < r or y < r or x > ARENA_W - r or y > ARENA_H - r:
            return True
        dummy = pygame.Rect(int(x - r), int(y - r), int(r * 2), int(r * 2))
        return any(dummy.colliderect(w) for w in self.walls)

    def move_entity(self, x, y, vx, vy, r):
        nx, ny = x + vx, y + vy
        if not self.blocked(nx, y, r):
            x = nx
        else:
            vx = 0
        if not self.blocked(x, ny, r):
            y = ny
        else:
            vy = 0
        return x, y, vx, vy

    def random_open(self, r=16):
        for _ in range(30):
            x = random.uniform(80, ARENA_W - 80)
            y = random.uniform(80, ARENA_H - 80)
            if not self.blocked(x, y, r) and not self.pen.inflate(40, 40).collidepoint(x, y):
                return x, y
        return ARENA_W * 0.2, ARENA_H * 0.2

    def in_pen_pos(self, x, y):
        return self.pen.inflate(-16, -16).collidepoint(x, y)

    def play_animal(self, a: Animal, kind: str):
        if a.sound_cd > 0:
            return
        key = f"{a.kind}_{kind}"
        if a.kind == "cat" and kind == "fight":
            key = random.choice(["cat_fight", "cat_fight2", "cat_fight3", "cat_fight4"])
        self.sfx.play(key, 0.35)
        a.sound_cd = 0.35

    def drop_lure(self, kind):
        if self.player.lure_counts.get(kind, 0) <= 0:
            return
        self.player.lure_counts[kind] -= 1
        fx = self.player.x + math.cos(self.player.dir) * 36
        fy = self.player.y + math.sin(self.player.dir) * 36
        self.lures.append(Lure(kind, fx, fy))
        self.sfx.play("lure")

    def update(self, dt):
        if self.over:
            return
        if not self.infinite_time:
            self.time_left -= dt
            if self.time_left <= 0:
                self.time_left = 0
                self.over = True
                return

        keys = pygame.key.get_pressed()
        dx = dy = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            dx -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            dx += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            dy -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            dy += 1
        if dx or dy:
            ang = math.atan2(dy, dx)
            self.player.dir = ang
            self.player.x, self.player.y, _, _ = self.move_entity(
                self.player.x, self.player.y,
                math.cos(ang) * self.player.speed,
                math.sin(ang) * self.player.speed, 14,
            )

        ctrl = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        if ctrl and self.player.swing <= 0:
            self.player.swing = 0.28
            self.sfx.play("stick", 0.5)
        if self.player.swing > 0:
            self.player.swing -= dt

        if self.player.swing > 0.12:
            sx = self.player.x + math.cos(self.player.dir) * 38
            sy = self.player.y + math.sin(self.player.dir) * 38
            for a in self.animals:
                if not a.alive or a.in_pen:
                    continue
                if math.hypot(a.x - sx, a.y - sy) < a.r + 22:
                    self._stick_hit(a)

        for a in self.animals:
            if a.sound_cd > 0:
                a.sound_cd -= dt
            if a.fight_cd > 0:
                a.fight_cd -= dt
            if a.shoot_cd > 0:
                a.shoot_cd -= dt
            if a.teleport_cd > 0:
                a.teleport_cd -= dt
            if a.fly_cd > 0:
                a.fly_cd -= dt
            if a.tame and a.kind == "bear":
                a.tame_left -= dt
                if a.tame_left <= 0:
                    a.tame = False

        self._update_animals(dt)
        self._update_combat(dt)
        self._update_lures(dt)
        self._update_bolts(dt)

        active = [a for a in self.animals if a.alive and not a.in_pen]
        if not active and self.wave_i < len(WAVES) - 1:
            self.wave_i += 1
            self.spawn_wave()
        elif not active and self.wave_i >= len(WAVES) - 1 and not self.infinite_time:
            self.over = True
        elif not active and self.wave_i >= len(WAVES) - 1 and self.infinite_time:
            self.wave_i = 0
            self.spawn_wave()
        if self.player.hp <= 0:
            self.over = True
        self.score = sum(1 for a in self.animals if a.alive and a.in_pen)

    def _stick_hit(self, a: Animal):
        self.play_animal(a, "hit")
        if a.asleep:
            a.wake_hits += 1
            if a.wake_hits >= 2:
                a.asleep = False
            return
        ang = math.atan2(a.y - self.player.y, a.x - self.player.x)
        push = 7.5 / max(0.6, a.spec["herd"] * 0.35)
        a.vx += math.cos(ang) * push
        a.vy += math.sin(ang) * push
        if a.kind == "bear":
            a.tame = True
            a.tame_left = random.uniform(3.0, 10.0)
            self.sfx.play("tame")
        if a.kind == "duck":
            a.flying = True
            a.fly_time = random.uniform(2.0, 4.5)
        if a.kind == "alien" and a.teleport_cd <= 0 and random.random() < 0.65:
            self._teleport(a)

    def _teleport(self, a: Animal):
        nx, ny = self.random_open(a.r)
        a.x, a.y = nx, ny
        a.vx = a.vy = 0
        a.teleport_cd = random.uniform(2.5, 6.0)
        self.sfx.play("teleport")

    def _best_lure(self, a: Animal) -> Optional[Lure]:
        want = a.spec["lure"]
        if not want:
            return None
        best, bd = None, 1e9
        for L in self.lures:
            if L.kind != want:
                continue
            d = math.hypot(L.x - a.x, L.y - a.y)
            if d < bd:
                bd, best = d, L
        return best if best and bd < 280 else None

    def _update_animals(self, dt):
        herder = self.player
        stick_on = herder.swing > 0
        for a in self.animals:
            if not a.alive:
                continue
            if a.in_pen:
                a.flying = False
                a.hop_z *= 0.8
                a.asleep = False
                cx, cy = self.pen.center
                a.vx += (cx - a.x) * 0.002
                a.vy += (cy - a.y) * 0.002
                a.vx *= 0.9
                a.vy *= 0.9
                a.x = max(self.pen.left + a.r, min(self.pen.right - a.r, a.x + a.vx))
                a.y = max(self.pen.top + a.r, min(self.pen.bottom - a.r, a.y + a.vy))
                continue

            if a.asleep:
                a.vx = a.vy = 0
                a.hop_z = 0
                continue

            if self.in_pen_pos(a.x, a.y) and (a.kind != "bear" or a.tame):
                a.in_pen = True
                a.vx = a.vy = 0
                a.flying = False
                self.sfx.play("pen")
                continue

            fx = fy = 0.0
            dx, dy = a.x - herder.x, a.y - herder.y
            dist = math.hypot(dx, dy) + 1e-5
            threat_r = 95 if stick_on else 55
            threatened = dist < threat_r

            if threatened:
                w = (threat_r - dist) / threat_r
                strength = (2.8 if stick_on else 1.4) / (0.5 + a.spec["herd"] * 0.25)
                fx += dx / dist * strength * w
                fy += dy / dist * strength * w
                if stick_on and a.sound_cd <= 0:
                    self.play_animal(a, "backoff")
                if a.kind == "duck":
                    a.flying = True
                    a.fly_time = max(a.fly_time, 2.2)
                if a.kind == "alien" and stick_on and a.teleport_cd <= 0 and random.random() < 0.08:
                    self._teleport(a)

            same = [o for o in self.animals if o.alive and not o.in_pen and o.kind == a.kind and o is not a]
            if same and not a.flying:
                gx = sum(o.x for o in same) / len(same)
                gy = sum(o.y for o in same) / len(same)
                if math.hypot(gx - a.x, gy - a.y) < 160:
                    pull = 0.55 / a.spec["herd"]
                    fx += (gx - a.x) * 0.01 * pull
                    fy += (gy - a.y) * 0.01 * pull
                    if a.sound_cd <= 0 and random.random() < 0.01:
                        self.play_animal(a, "group")

            lure = self._best_lure(a)
            if lure and not a.flying:
                fx += (lure.x - a.x) * 0.012
                fy += (lure.y - a.y) * 0.012

            if a.kind == "bear" and not a.tame:
                fx += (herder.x - a.x) * 0.01
                fy += (herder.y - a.y) * 0.01
                if dist < 36:
                    self.player.hp -= 3 * dt
                    if random.random() < 0.05:
                        self.sfx.play("hurt")
            elif a.kind == "bear" and a.tame:
                fx += (self.pen.centerx - a.x) * 0.01
                fy += (self.pen.centery - a.y) * 0.01

            if a.kind == "duck":
                if not a.flying and a.fly_cd <= 0:
                    a.flying = True
                    a.fly_time = random.uniform(1.8, 4.0)
                    a.fly_cd = random.uniform(5.0, 12.0)
                if a.flying:
                    a.fly_time -= dt
                    ang = math.atan2(a.vy, a.vx) if abs(a.vx) + abs(a.vy) > 0.1 else random.random() * math.tau
                    ang += random.uniform(-0.15, 0.15)
                    fx += math.cos(ang) * 0.35
                    fy += math.sin(ang) * 0.35
                    a.hop_z = 22 + 6 * math.sin(pygame.time.get_ticks() * 0.012)
                    if a.fly_time <= 0 and not threatened:
                        a.flying = False
                        a.hop_z = 0

            if a.kind == "alien" and a.teleport_cd <= 0 and random.random() < 0.004:
                self._teleport(a)

            if a.kind == "lizard":
                a.snake_t += dt
                a.snake_heading += math.sin(a.snake_t * 3.2) * 0.12
                fx += math.cos(a.snake_heading) * 0.45
                fy += math.sin(a.snake_heading) * 0.45
                side = math.sin(a.snake_t * 6.0) * 1.15
                fx += math.cos(a.snake_heading + math.pi / 2) * side * 0.25
                fy += math.sin(a.snake_heading + math.pi / 2) * side * 0.25

            beh = BEHAVIOR.get(a.kind, {})
            if beh.get("run_around"):
                a.run_t -= dt
                if a.run_t <= 0:
                    a.running = random.random() < 0.55
                    a.run_t = random.uniform(1.2, 3.5)
                    a.run_heading = random.uniform(0, math.tau)
                if a.running:
                    a.run_heading += random.uniform(-0.08, 0.08)
                    fx += math.cos(a.run_heading) * 0.7
                    fy += math.sin(a.run_heading) * 0.7

            hop_kind = beh.get("hop")
            if hop_kind and not a.flying:
                a.hop_cd -= dt
                if a.hop_cd <= 0:
                    a.hop_phase = 0.001
                    lo, hi = beh.get("hop_cd", (0.4, 0.8))
                    a.hop_cd = random.uniform(lo, hi)
                    angh = math.atan2(fy + a.vy, fx + a.vx) if abs(fx) + abs(fy) > 0.05 else random.random() * math.tau
                    impulse = 4.2 if hop_kind == "high" else 2.2
                    a.vx += math.cos(angh) * impulse * 0.35
                    a.vy += math.sin(angh) * impulse * 0.35
                if a.hop_phase > 0:
                    a.hop_phase += dt * (5.5 if hop_kind == "high" else 4.0)
                    peak = 16 if hop_kind == "high" else 7
                    a.hop_z = max(0.0, math.sin(min(math.pi, a.hop_phase)) * peak)
                    if a.hop_phase >= math.pi:
                        a.hop_phase = 0
                        a.hop_z = 0
            elif not a.flying:
                a.hop_z *= 0.7

            fx += random.uniform(-0.12, 0.12)
            fy += random.uniform(-0.12, 0.12)
            a.vx = (a.vx + fx) * 0.86
            a.vy = (a.vy + fy) * 0.86
            cap = a.spec["speed"] * (1.55 if a.running else 1.0) * (1.4 if a.flying else 1.0)
            sp = math.hypot(a.vx, a.vy)
            if sp > cap:
                a.vx *= cap / sp
                a.vy *= cap / sp
            a.x, a.y, a.vx, a.vy = self.move_entity(a.x, a.y, a.vx, a.vy, a.r)

            if a.kind == "alien" and a.shoot_cd <= 0 and dist < 320:
                ang = math.atan2(herder.y - a.y, herder.x - a.x)
                self.bolts.append(Bolt(a.x, a.y, math.cos(ang) * 2.1, math.sin(ang) * 2.1))
                self.sfx.play("bolt", 0.25)
                a.shoot_cd = random.uniform(1.4, 2.4)

    def _update_combat(self, dt):
        alive = [a for a in self.animals if a.alive and not a.in_pen and not a.asleep]
        for i, a in enumerate(alive):
            for b in alive[i + 1:]:
                if a.kind == b.kind:
                    continue
                if math.hypot(a.x - b.x, a.y - b.y) < a.r + b.r + 6:
                    if a.spec["power"] == b.spec["power"]:
                        if a.fight_cd <= 0:
                            self.play_animal(a, "fight")
                            a.fight_cd = 0.4
                        continue
                    winner, loser = (a, b) if a.spec["power"] > b.spec["power"] else (b, a)
                    if winner.fight_cd <= 0:
                        self.play_animal(winner, "fight")
                        winner.fight_cd = 0.35
                        loser.hp -= 1
                        if loser.hp <= 0:
                            loser.alive = False

    def _update_lures(self, dt):
        for L in self.lures:
            L.life -= dt
        self.lures = [L for L in self.lures if L.life > 0]

    def _update_bolts(self, dt):
        p = self.player
        remain = []
        for b in self.bolts:
            b.x += b.vx
            b.y += b.vy
            b.life -= dt
            if self.blocked(b.x, b.y, 4):
                continue
            if math.hypot(b.x - p.x, b.y - p.y) < 16:
                p.hp -= 1
                self.sfx.play("hurt")
                continue
            if b.life > 0:
                remain.append(b)
        self.bolts = remain

    def world_to_screen(self, x, y):
        sw, sh = self.screen.get_size()
        scale = min(sw / ARENA_W, sh / ARENA_H)
        ox = (sw - ARENA_W * scale) / 2
        oy = (sh - ARENA_H * scale) / 2
        sx = ox + x * scale
        sy = oy + y * scale * 0.82 + (sh * 0.06)
        return sx, sy, scale

    def _hidden_by_wall(self, a: Animal) -> bool:
        for w in self.walls:
            if w.left - 8 <= a.x <= w.right + 8 and w.top - 4 <= a.y <= w.top + 18:
                return True
            if w.width < 40 and w.left - 6 <= a.x <= w.right + 6 and w.top <= a.y <= w.bottom:
                return True
        return False

    def draw(self):
        self.screen.fill((28, 46, 28))
        sw, sh = self.screen.get_size()
        pts = [self.world_to_screen(x, y)[:2] for x, y in [(0, 0), (ARENA_W, 0), (ARENA_W, ARENA_H), (0, ARENA_H)]]
        pygame.draw.polygon(self.screen, (62, 92, 48), pts)

        sx, sy, sc = self.world_to_screen(self.pen.x, self.pen.y)
        pw, ph = self.pen.w * sc, self.pen.h * sc * 0.82
        pygame.draw.rect(self.screen, (90, 70, 40), (sx, sy, pw, ph), border_radius=8)
        pygame.draw.rect(self.screen, (200, 170, 80), (sx, sy, pw, ph), 4, border_radius=8)
        label = self.font.render("PEN", True, (255, 230, 140))
        self.screen.blit(label, (sx + pw / 2 - label.get_width() / 2, sy + 8))

        for w in self.walls:
            x, y, sc = self.world_to_screen(w.x, w.y)
            ww, hh = w.w * sc, w.h * sc * 0.82
            pygame.draw.rect(self.screen, (70, 70, 78), (x, y - 16 * sc, ww, hh + 16 * sc))
            pygame.draw.rect(self.screen, (110, 110, 120), (x, y - 16 * sc, ww, 16 * sc))

        for L in self.lures:
            x, y, sc = self.world_to_screen(L.x, L.y)
            cols = {"bone": (240, 240, 230), "grain": (210, 180, 50), "catnip": (80, 200, 90),
                    "tech": (80, 180, 255), "bugs": (40, 40, 20)}
            pygame.draw.circle(self.screen, cols.get(L.kind, (255, 255, 255)), (int(x), int(y)), int(6 * sc))

        for b in self.bolts:
            x, y, sc = self.world_to_screen(b.x, b.y)
            pygame.draw.circle(self.screen, (120, 255, 160), (int(x), int(y)), int(5 * sc))

        draw_list = [a for a in self.animals if a.alive]
        draw_list.sort(key=lambda a: a.y)
        for a in draw_list:
            hidden = self._hidden_by_wall(a) and not a.in_pen
            x, y, sc = self.world_to_screen(a.x, a.y)
            lift = a.hop_z * sc
            spr = get_animal_sprite(a, sc)
            rw, rh = spr.get_width(), spr.get_height()
            pygame.draw.ellipse(self.screen, (20, 30, 18), (x - rw * 0.35, y + rh * 0.15, rw * 0.7, rh * 0.22))
            draw_y = y - rh * 0.82 - lift
            if a.asleep:
                spr2 = spr.copy()
                spr2.fill((40, 40, 80, 60), special_flags=pygame.BLEND_RGBA_ADD)
                self.screen.blit(spr2, (x - rw / 2, draw_y))
                zzz = self.font.render("z", True, (200, 200, 255))
                self.screen.blit(zzz, (x + 6, draw_y - 8))
            else:
                self.screen.blit(spr, (x - rw / 2, draw_y))
            if a.kind == "bear" and not a.tame:
                pygame.draw.circle(self.screen, (180, 30, 30), (int(x), int(y - rh * 0.95 - lift)), 4)
            if hidden:
                pygame.draw.polygon(
                    self.screen, (255, 50, 50),
                    [(x, y - rh * 1.05 - lift), (x - 6, y - rh * 0.85 - lift), (x + 6, y - rh * 0.85 - lift)],
                )

        x, y, sc = self.world_to_screen(self.player.x, self.player.y)
        pygame.draw.circle(self.screen, (40, 70, 140), (int(x), int(y)), int(14 * sc))
        pygame.draw.circle(self.screen, (220, 190, 150), (int(x), int(y - 16 * sc)), int(8 * sc))
        extra = 18 if self.player.swing > 0 else 0
        swing_off = math.sin(self.player.swing * 12) * 0.8 if self.player.swing > 0 else 0
        ang2 = self.player.dir + swing_off
        x2 = x + math.cos(ang2) * (28 + extra) * sc
        y2 = y + math.sin(ang2) * (28 + extra) * sc * 0.82
        pygame.draw.line(self.screen, (140, 90, 40), (x, y), (x2, y2), max(2, int(4 * sc)))

        if self.infinite_time:
            tlabel = "Time INF"
        else:
            m, s = divmod(int(self.time_left), 60)
            tlabel = f"Time {m:02d}:{s:02d}"
        hud = f"Score {self.score}   {tlabel}   Wave {self.wave_i + 1}/{len(WAVES)}   HP {max(0, int(self.player.hp))}"
        self.screen.blit(self.font.render(hud, True, (255, 255, 230)), (16, 10))
        lures = "  ".join(f"{k}:{v}" for k, v in self.player.lure_counts.items())
        extra = "  |  T next wave" if self.infinite_time else ""
        self.screen.blit(self.font.render("Lures 1-5  |  " + lures + "  |  U infinite time" + extra, True, (220, 220, 180)), (16, 36))
        self.screen.blit(self.font.render("Arrows/WASD move  |  Ctrl swing stick", True, (200, 200, 170)), (16, 62))

        if self.over:
            msg = f"TIME UP  —  Penned: {self.score}"
            t = self.big.render(msg, True, (255, 220, 80))
            self.screen.blit(t, (sw // 2 - t.get_width() // 2, sh // 2 - 40))
            t2 = self.font.render("Press R to restart", True, (255, 255, 255))
            self.screen.blit(t2, (sw // 2 - t2.get_width() // 2, sh // 2 + 40))


def splash(screen, clock):
    cat = make_leaping_cat()
    t0 = pygame.time.get_ticks()
    title_font = pygame.font.SysFont("impact", 96)
    sub = pygame.font.SysFont("georgia", 22)
    while True:
        clock.tick(FPS)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                return False
            if e.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(e.size, pygame.RESIZABLE)
        elapsed = (pygame.time.get_ticks() - t0) / 1000.0
        if elapsed >= SPLASH_SECONDS:
            return True
        sw, sh = screen.get_size()
        screen.fill((8, 8, 12))
        streak_title(screen, "Cat Herder", title_font, y=int(sh * 0.08))
        cx = sw // 2 - cat.get_width() // 2
        cy = int(sh * 0.32)
        screen.blit(cat, (cx, cy))
        hint = sub.render("Herd them in. Don't get eaten.", True, (180, 180, 190))
        screen.blit(hint, (sw // 2 - hint.get_width() // 2, cy + cat.get_height() + 16))
        bar_w = int(sw * 0.4)
        pygame.draw.rect(screen, (60, 60, 70), (sw // 2 - bar_w // 2, sh - 40, bar_w, 8), border_radius=4)
        pygame.draw.rect(
            screen, (220, 40, 40),
            (sw // 2 - bar_w // 2, sh - 40, int(bar_w * min(1, elapsed / SPLASH_SECONDS)), 8),
            border_radius=4,
        )
        pygame.display.flip()


def main():
    generate_sounds()
    x, y, w, h = load_window_geom()
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
    pygame.init()
    pygame.display.set_caption("Cat Herder")
    screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    if not splash(screen, clock):
        pygame.quit()
        return
    game = Game(screen)
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode(e.size, pygame.RESIZABLE)
                game.screen = screen
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_u:
                    game.infinite_time = not game.infinite_time
                elif e.key == pygame.K_t:
                    game.cycle_level()
                elif e.key == pygame.K_r and game.over:
                    game.reset()
                elif e.key == pygame.K_1:
                    game.drop_lure("bone")
                elif e.key == pygame.K_2:
                    game.drop_lure("grain")
                elif e.key == pygame.K_3:
                    game.drop_lure("catnip")
                elif e.key == pygame.K_4:
                    game.drop_lure("tech")
                elif e.key == pygame.K_5:
                    game.drop_lure("bugs")
        game.update(dt)
        game.draw()
        pygame.display.flip()
    w, h = screen.get_size()
    info = pygame.display.get_wm_info()
    wx = info.get("x", x) if isinstance(info, dict) else x
    wy = info.get("y", y) if isinstance(info, dict) else y
    try:
        wx = int(wx) if wx is not None else x
        wy = int(wy) if wy is not None else y
    except Exception:
        wx, wy = x, y
    save_window_geom(wx, wy, w, h)
    pygame.quit()


if __name__ == "__main__":
    main()