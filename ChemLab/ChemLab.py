#!/usr/bin/env python3
"""
ChemLab — simulated student chemistry workbench
Requires: pygame, numpy
  pip install pygame numpy
  python chemlab.py
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pygame

pygame.init()
pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
pygame.display.set_caption("ChemLab")

W, H = 1280, 720
FPS = 60


# ---------------------------------------------------------------------------
# Procedural sounds
# ---------------------------------------------------------------------------

def _tone(freq, ms, vol=0.25, decay=True, wave="sine"):
    n = int(22050 * ms / 1000)
    t = np.arange(n) / 22050.0
    if wave == "sine":
        sig = np.sin(2 * np.pi * freq * t)
    elif wave == "square":
        sig = np.sign(np.sin(2 * np.pi * freq * t))
    elif wave == "noise":
        sig = np.random.uniform(-1, 1, n)
    else:
        sig = np.sin(2 * np.pi * freq * t) * 0.7 + np.random.uniform(-0.3, 0.3, n)
    if decay:
        sig *= np.linspace(1.0, 0.0, n)
    sig = (sig * vol * 32767).astype(np.int16)
    stereo = np.column_stack((sig, sig))
    return pygame.sndarray.make_sound(stereo)


def _loop_hum(freq=90, vol=0.12):
    n = int(22050 * 0.4)
    t = np.arange(n) / 22050.0
    sig = 0.6 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
    sig += 0.15 * np.random.uniform(-1, 1, n)
    sig = (sig * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((sig, sig)))


def _bubble_loop(vol=0.16):
    n = int(22050 * 0.5)
    sig = np.zeros(n)
    for _ in range(8):
        start = random.randint(0, n - 800)
        length = random.randint(400, 900)
        tt = np.arange(length) / 22050.0
        f = random.uniform(400, 1100)
        burst = np.sin(2 * np.pi * f * tt) * np.linspace(1, 0, length)
        end = min(n, start + length)
        sig[start:end] += burst[: end - start]
    sig = (np.clip(sig, -1, 1) * vol * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(np.column_stack((sig, sig)))


SOUNDS = {
    "click": _tone(880, 80, 0.22, True, "sine"),
    "drop": _tone(220, 140, 0.28, True, "sine"),
    "beep": _tone(660, 90, 0.2, True, "sine"),
    "spark": _tone(1400, 60, 0.18, True, "square"),
    "heat": _tone(140, 200, 0.15, True, "noise"),
    "cool": _tone(320, 180, 0.15, True, "sine"),
    "boom": _tone(70, 400, 0.4, True, "noise"),
    "hiss": _tone(1800, 250, 0.12, True, "noise"),
    "win": _tone(523, 180, 0.2, True, "sine"),
    "stir": _loop_hum(75, 0.14),
    "bubble": _bubble_loop(0.18),
    "current": _loop_hum(110, 0.10),
}


def play(name, loops=0):
    snd = SOUNDS.get(name)
    if snd:
        snd.play(loops=loops)


# ---------------------------------------------------------------------------
# Chemistry data
# ---------------------------------------------------------------------------

CHEMICALS = {
    "water": dict(color=(80, 140, 220), bp=100, mp=0, toxic=0, explode=0, gas="steam"),
    "HCl": dict(color=(180, 220, 120), bp=85, mp=-30, toxic=2, explode=0, gas="HCl vapor"),
    "H2SO4": dict(color=(220, 220, 80), bp=337, mp=10, toxic=3, explode=1, gas="SO3"),
    "HNO3": dict(color=(220, 200, 60), bp=83, mp=-42, toxic=3, explode=2, gas="NOx"),
    "NaOH": dict(color=(240, 240, 240), bp=1388, mp=318, toxic=2, explode=0, gas=None),
    "KOH": dict(color=(230, 230, 245), bp=1327, mp=360, toxic=2, explode=0, gas=None),
    "NaCl": dict(color=(250, 250, 250), bp=1465, mp=801, toxic=0, explode=0, gas=None),
    "CuSO4": dict(color=(40, 90, 210), bp=650, mp=110, toxic=2, explode=0, gas=None),
    "Fe2O3": dict(color=(160, 60, 40), bp=None, mp=1565, toxic=1, explode=0, gas=None),
    "Al powder": dict(color=(190, 195, 200), bp=None, mp=660, toxic=1, explode=3, gas=None),
    "Mg ribbon": dict(color=(200, 205, 210), bp=1090, mp=650, toxic=1, explode=3, gas=None),
    "KMnO4": dict(color=(120, 20, 90), bp=None, mp=240, toxic=2, explode=2, gas="O2"),
    "H2O2": dict(color=(200, 230, 255), bp=150, mp=-0.4, toxic=2, explode=2, gas="O2"),
    "ethanol": dict(color=(200, 230, 200), bp=78, mp=-114, toxic=1, explode=3, gas="ethanol vapor"),
    "methanol": dict(color=(190, 220, 190), bp=65, mp=-98, toxic=3, explode=3, gas="methanol vapor"),
    "acetic acid": dict(color=(230, 230, 180), bp=118, mp=17, toxic=1, explode=1, gas="acetic vapor"),
    "ammonia": dict(color=(200, 220, 255), bp=-33, mp=-78, toxic=2, explode=1, gas="NH3"),
    "AgNO3": dict(color=(245, 245, 250), bp=444, mp=212, toxic=2, explode=1, gas=None),
    "KI": dict(color=(240, 240, 210), bp=1330, mp=681, toxic=1, explode=0, gas=None),
    "Pb(NO3)2": dict(color=(240, 240, 220), bp=None, mp=470, toxic=3, explode=2, gas="NOx"),
    "BaCl2": dict(color=(230, 230, 230), bp=1560, mp=962, toxic=3, explode=0, gas=None),
    "Na2CO3": dict(color=(245, 245, 245), bp=None, mp=851, toxic=1, explode=0, gas="CO2"),
    "CaCO3": dict(color=(240, 240, 235), bp=None, mp=825, toxic=0, explode=0, gas="CO2"),
    "zinc": dict(color=(170, 180, 190), bp=907, mp=420, toxic=1, explode=1, gas=None),
    "copper": dict(color=(184, 115, 51), bp=2562, mp=1085, toxic=1, explode=0, gas=None),
    "iron filings": dict(color=(120, 120, 125), bp=2862, mp=1538, toxic=1, explode=1, gas=None),
    "sulfur": dict(color=(230, 210, 40), bp=445, mp=115, toxic=1, explode=2, gas="SO2"),
    "carbon": dict(color=(40, 40, 40), bp=None, mp=3550, toxic=0, explode=1, gas="CO2"),
    "I2": dict(color=(90, 40, 140), bp=184, mp=114, toxic=2, explode=0, gas="I2 vapor"),
    "phenol": dict(color=(240, 230, 180), bp=182, mp=41, toxic=3, explode=1, gas=None),
    "benzene": dict(color=(210, 200, 160), bp=80, mp=5.5, toxic=3, explode=3, gas="benzene vapor"),
    "glycerol": dict(color=(220, 220, 200), bp=290, mp=18, toxic=0, explode=0, gas=None),
    "KClO3": dict(color=(250, 250, 250), bp=None, mp=356, toxic=2, explode=4, gas="O2"),
    "NH4NO3": dict(color=(250, 250, 245), bp=None, mp=170, toxic=2, explode=5, gas="NOx"),
    "phenolphthalein": dict(color=(255, 200, 220), bp=None, mp=260, toxic=1, explode=0, gas=None),
    "universal indicator": dict(color=(80, 180, 80), bp=100, mp=0, toxic=1, explode=0, gas=None),
    "starch": dict(color=(250, 245, 230), bp=None, mp=None, toxic=0, explode=0, gas=None),
    "glucose": dict(color=(250, 250, 240), bp=None, mp=146, toxic=0, explode=0, gas=None),
    "CuO": dict(color=(20, 40, 80), bp=None, mp=1326, toxic=2, explode=0, gas=None),
    "MnO2": dict(color=(50, 50, 55), bp=None, mp=535, toxic=2, explode=1, gas=None),
    "H2": dict(color=(220, 240, 255), bp=-253, mp=-259, toxic=0, explode=5, gas="H2"),
    "O2": dict(color=(180, 220, 255), bp=-183, mp=-218, toxic=0, explode=2, gas="O2"),
    "Cl2": dict(color=(180, 220, 80), bp=-34, mp=-102, toxic=4, explode=1, gas="Cl2"),
    "Na metal": dict(color=(200, 200, 210), bp=883, mp=98, toxic=3, explode=5, gas="H2"),
    "K metal": dict(color=(200, 200, 200), bp=759, mp=64, toxic=3, explode=5, gas="H2"),
    "mercury": dict(color=(180, 180, 185), bp=357, mp=-39, toxic=5, explode=0, gas="Hg vapor"),
    "cyanide salt": dict(color=(240, 240, 240), bp=None, mp=563, toxic=5, explode=1, gas="HCN"),
}

GAS_COLORS = {
    "steam": (220, 230, 240),
    "HCl vapor": (180, 230, 120),
    "SO3": (230, 230, 80),
    "NOx": (180, 80, 40),
    "O2": (180, 220, 255),
    "ethanol vapor": (200, 240, 200),
    "methanol vapor": (190, 230, 190),
    "acetic vapor": (230, 230, 160),
    "NH3": (210, 230, 255),
    "CO2": (200, 200, 200),
    "H2": (230, 245, 255),
    "Cl2": (170, 220, 70),
    "SO2": (230, 220, 80),
    "I2 vapor": (140, 60, 180),
    "benzene vapor": (210, 200, 140),
    "Hg vapor": (190, 190, 200),
    "HCN": (210, 230, 180),
}

REACTIONS = {
    frozenset(["HCl", "NaOH"]): ("NaCl solution", -8, 0, 0, "neutralization"),
    frozenset(["H2SO4", "NaOH"]): ("Na2SO4 solution", -15, 0, 1, "strong neutralization"),
    frozenset(["HCl", "Na2CO3"]): ("NaCl + CO2", 2, 0, 1, "CO2 evolution"),
    frozenset(["HCl", "CaCO3"]): ("CaCl2 + CO2", 2, 0, 1, "marble + acid"),
    frozenset(["HCl", "zinc"]): ("ZnCl2 + H2", 5, 3, 1, "hydrogen generation"),
    frozenset(["H2SO4", "zinc"]): ("ZnSO4 + H2", 8, 3, 1, "hydrogen generation"),
    frozenset(["AgNO3", "KI"]): ("AgI precipitate", 0, 0, 1, "yellow ppt"),
    frozenset(["AgNO3", "NaCl"]): ("AgCl precipitate", 0, 0, 1, "white ppt"),
    frozenset(["Pb(NO3)2", "KI"]): ("PbI2 gold rain", 0, 0, 2, "golden precipitate"),
    frozenset(["BaCl2", "H2SO4"]): ("BaSO4 precipitate", 0, 0, 2, "white ppt"),
    frozenset(["CuSO4", "NaOH"]): ("Cu(OH)2 blue ppt", 0, 0, 1, "gelatinous blue"),
    frozenset(["Fe2O3", "Al powder"]): ("thermite mix", 0, 5, 1, "DO NOT IGNITE casually"),
    frozenset(["H2O2", "MnO2"]): ("O2 + water", 20, 2, 1, "catalytic decomposition"),
    frozenset(["KMnO4", "HCl"]): ("Cl2 gas", 10, 2, 4, "chlorine evolution"),
    frozenset(["ethanol", "acetic acid"]): ("ethyl acetate mix", 0, 1, 1, "esterification start"),
    frozenset(["Na metal", "water"]): ("NaOH + H2 FIRE", 80, 5, 3, "violent"),
    frozenset(["K metal", "water"]): ("KOH + H2 FIRE", 100, 5, 3, "violent"),
    frozenset(["cyanide salt", "HCl"]): ("HCN gas", 0, 1, 5, "lethal vapor"),
    frozenset(["NH4NO3", "Al powder"]): ("unstable mix", 0, 5, 2, "detonable"),
    frozenset(["KClO3", "sulfur"]): ("chlorate-sulfur", 0, 5, 2, "friction sensitive"),
    frozenset(["CuSO4", "iron filings"]): ("iron + copper displacement", 2, 0, 1, "red copper"),
    frozenset(["CuO", "carbon"]): ("Cu + CO2 mix", 0, 1, 1, "needs heat"),
    frozenset(["I2", "starch"]): ("blue-black complex", 0, 0, 1, "iodine test"),
    frozenset(["HCl", "ammonia"]): ("NH4Cl smoke", 5, 0, 1, "white fumes"),
    frozenset(["H2SO4", "glucose"]): ("carbon foam", 40, 1, 2, "dehydration"),
    frozenset(["glycerol", "KMnO4"]): ("ignition mix", 50, 4, 2, "spontaneous heat"),
    frozenset(["HNO3", "copper"]): ("Cu nitrate + NOx", 15, 1, 3, "brown gas"),
    frozenset(["phenolphthalein", "NaOH"]): ("pink indicator", 0, 0, 0, "basic"),
    frozenset(["universal indicator", "HCl"]): ("red indicator", 0, 0, 0, "acidic"),
    frozenset(["universal indicator", "NaOH"]): ("purple indicator", 0, 0, 0, "basic"),
}

DANGEROUS = {
    "Na metal", "K metal", "cyanide salt", "NH4NO3", "KClO3",
    "mercury", "benzene", "Cl2", "H2",
}


def build_experiments():
    templates = [
        ("Neutralize {a} with {b}", ["HCl", "NaOH"], 2, ["beaker", "grad_cyl", "stirrer", "thermo"], "Mix acid and base until inert salt solution."),
        ("Precipitate from {a} + {b}", ["AgNO3", "NaCl"], 2, ["beaker", "tube", "stirrer"], "Form a solid precipitate and leave it inert."),
        ("Generate gas from {a} + {b}", ["HCl", "zinc"], 3, ["beaker", "gas_trap", "thermo"], "Capture evolved gas safely."),
        ("Electrolyze aqueous {a}", ["NaCl"], 4, ["beaker", "electrodes", "ammeter", "stirrer"], "Pass current; observe products."),
        ("Distill {a}", ["ethanol"], 3, ["beaker", "thermo", "gas_trap", "grad_cyl"], "Heat and capture vapor."),
        ("Decompose {a} with catalyst {b}", ["H2O2", "MnO2"], 3, ["beaker", "stirrer", "gas_trap", "thermo"], "Catalytic O2 release."),
        ("Flame-adjacent oxidation of {a}", ["Mg ribbon"], 4, ["crucible", "thermo", "scale"], "Controlled high-temp oxidation — do not overheat wildly."),
        ("Crystal demo with {a}", ["CuSO4"], 2, ["beaker", "stirrer", "thermo", "scale"], "Dissolve and cool."),
        ("Titration of {a} vs {b}", ["HCl", "NaOH"], 3, ["grad_cyl", "beaker", "stirrer", "thermo"], "Measure volumes then mix."),
        ("Displacement {a} + {b}", ["CuSO4", "iron filings"], 2, ["beaker", "stirrer", "scale"], "Metal displacement."),
        ("Iodine-starch with {a} + {b}", ["I2", "starch"], 1, ["beaker", "stirrer"], "Blue-black complex."),
        ("Ester start {a} + {b}", ["ethanol", "acetic acid"], 3, ["beaker", "thermo", "stirrer"], "Gentle heat only."),
        ("Carbonate acid {a} + {b}", ["CaCO3", "HCl"], 2, ["beaker", "gas_trap"], "CO2 capture."),
        ("Chlorine caution {a} + {b}", ["KMnO4", "HCl"], 5, ["beaker", "gas_trap", "thermo"], "Toxic gas — trap it or you fail."),
        ("Thermite prep {a} + {b}", ["Fe2O3", "Al powder"], 5, ["crucible", "scale", "thermo"], "Prepare mix; do not runaway heat."),
        ("Sugar char {a} + {b}", ["glucose", "H2SO4"], 4, ["beaker", "thermo", "stirrer"], "Dehydration — hot and hazardous."),
        ("NOx from {a} + {b}", ["HNO3", "copper"], 4, ["beaker", "gas_trap", "thermo"], "Brown gas must be trapped."),
        ("Gold rain {a} + {b}", ["Pb(NO3)2", "KI"], 2, ["tube", "stirrer"], "PbI2 crystals."),
        ("BaSO4 ppt {a} + {b}", ["BaCl2", "H2SO4"], 3, ["beaker", "stirrer"], "Insoluble sulfate."),
        ("Indicator {a} + {b}", ["phenolphthalein", "NaOH"], 1, ["tube", "beaker"], "Color change."),
    ]
    extras_a = list(CHEMICALS.keys())
    exps = []
    for i in range(100):
        tmpl = templates[i % len(templates)]
        title, pair, diff, equip, goal = tmpl
        a, b = pair[0], (pair[1] if len(pair) > 1 else None)
        if i >= 40:
            a = extras_a[i % len(extras_a)]
            b = extras_a[(i * 3) % len(extras_a)]
            if a == b:
                b = extras_a[(i * 7) % len(extras_a)]
        needed = [a] + ([b] if b else [])
        name = f"{i+1:03d}. " + title.format(a=a, b=b or "")
        exps.append(
            {
                "id": i + 1,
                "name": name,
                "difficulty": max(1, min(5, diff + (i // 40))),
                "equipment": equip,
                "chemicals": needed,
                "goal": goal,
                "manual": (
                    f"CONTRACT {i+1}\n{name}\n\nGoal: {goal}\n"
                    f"Use: {', '.join(equip)}\nReagents: {', '.join(needed)}\n\n"
                    "AUTO mode moves a pink helper-mouse, highlights clicks,\n"
                    "and waits 5s per step. Replay repeats. Exit bench for score.\n"
                    "Manual may be opened ONLY ONCE this job."
                ),
            }
        )
    return exps


EXPERIMENTS = build_experiments()


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@dataclass
class ChemAmount:
    name: str
    grams: float = 10.0


@dataclass
class Container:
    kind: str
    x: float
    y: float
    w: float = 70
    h: float = 90
    contents: list = field(default_factory=list)
    temp: float = 22.0
    heating: bool = False
    stirring: bool = False
    powered: bool = False
    current: float = 0.0
    label: str = ""
    highlight: float = 0.0

    def mass(self):
        return sum(c.grams for c in self.contents)

    def names(self):
        return [c.name for c in self.contents]

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), int(self.w), int(self.h))

    def center(self):
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass
class ShelfItem:
    name: str
    x: int
    y: int
    w: int = 56
    h: int = 28
    highlight: float = 0.0

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def center(self):
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: tuple
    kind: str  # bubble or vapor
    r: float


@dataclass
class FakeMouse:
    x: float = 640
    y: float = 360
    tx: float = 640
    ty: float = 360
    visible: bool = False
    carrying: Optional[str] = None
    speed: float = 140.0

    def go(self, pos, carry=None):
        self.tx, self.ty = pos
        self.visible = True
        if carry is not None:
            self.carrying = carry

    def arrived(self, dist=8):
        return math.hypot(self.tx - self.x, self.ty - self.y) < dist

    def tick(self, dt):
        if not self.visible:
            return
        dx, dy = self.tx - self.x, self.ty - self.y
        d = math.hypot(dx, dy)
        if d < 1:
            self.x, self.y = self.tx, self.ty
            return
        step = self.speed * dt
        if step >= d:
            self.x, self.y = self.tx, self.ty
        else:
            self.x += dx / d * step
            self.y += dy / d * step


def draw_pink_mouse(surf, x, y, carrying=None):
    px, py = int(x), int(y)
    body = (255, 150, 190)
    ear = (255, 120, 170)
    dark = (90, 40, 60)
    pygame.draw.circle(surf, ear, (px - 7, py - 8), 5)
    pygame.draw.circle(surf, ear, (px + 7, py - 8), 5)
    pygame.draw.circle(surf, (255, 200, 220), (px - 7, py - 8), 2)
    pygame.draw.circle(surf, (255, 200, 220), (px + 7, py - 8), 2)
    pygame.draw.ellipse(surf, body, (px - 10, py - 6, 20, 16))
    pygame.draw.circle(surf, (20, 20, 20), (px - 3, py - 1), 2)
    pygame.draw.circle(surf, (20, 20, 20), (px + 3, py - 1), 2)
    pygame.draw.circle(surf, (255, 80, 120), (px, py + 3), 2)
    for ang in (-0.4, 0, 0.4):
        pygame.draw.line(
            surf, dark,
            (px + 8, py + 2),
            (px + 18, py + 2 + int(6 * math.sin(ang))),
            1,
        )
        pygame.draw.line(
            surf, dark,
            (px - 8, py + 2),
            (px - 18, py + 2 + int(6 * math.sin(ang))),
            1,
        )
    pygame.draw.circle(surf, (255, 180, 210), (px + 12, py + 8), 3)
    if carrying:
        col = CHEMICALS.get(carrying, {}).get("color", (255, 255, 255))
        pygame.draw.circle(surf, col, (px + 6, py + 14), 6)
        pygame.draw.circle(surf, (0, 0, 0), (px + 6, py + 14), 6, 1)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class ChemLab:
    STEP_PAUSE = 5.0

    def __init__(self):
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 16)
        self.small = pygame.font.SysFont("consolas", 13)
        self.big = pygame.font.SysFont("consolas", 28)
        self.state = "menu"
        self.score = 0
        self.jobs_done = 0
        self.thermal = False
        self.manual_used = False
        self.show_manual = False
        self.log = []
        self.t0 = time.time()
        self.job: Optional[dict] = None
        self.containers: list[Container] = []
        self.shelf: list[ShelfItem] = []
        self.drag = None
        self.message = "Accept a contractor job."
        self.alive = True
        self.fail_reason = ""
        self.pending_jobs = EXPERIMENTS.copy()
        random.shuffle(self.pending_jobs)
        self.current_offer = None
        self.replay = []
        self.auto = False
        self.auto_queue: list[tuple] = []
        self.auto_plan: list[tuple] = []
        self.auto_wait = 0.0
        self.auto_done = False
        self.selected = None
        self.catalog_scroll = 0
        self.particles: list[Particle] = []
        self.mouse = FakeMouse()
        self.pending_step = None
        self.stir_playing = False
        self.bubble_playing = False
        self.current_playing = False
        self._layout_shelf()
        self._offer_job()

    def log_action(self, text):
        t = time.time() - self.t0
        line = f"[{t:8.2f}s] {text}"
        self.log.append(line)
        self.replay.append({"t": t, "text": text})
        if len(self.log) > 400:
            self.log = self.log[-400:]

    def _layout_shelf(self):
        self.shelf = []
        for i, n in enumerate(CHEMICALS.keys()):
            col, row = i % 6, i // 6
            self.shelf.append(ShelfItem(n, 12 + col * 60, 80 + row * 32))

    def _offer_job(self):
        if not self.pending_jobs:
            self.pending_jobs = EXPERIMENTS.copy()
            random.shuffle(self.pending_jobs)
        self.current_offer = self.pending_jobs.pop(0)

    def find(self, kind):
        for c in self.containers:
            if c.kind == kind:
                return c
        return None

    def shelf_item(self, name):
        for it in self.shelf:
            if it.name == name:
                return it
        return None

    def primary_vessel(self):
        for k in ("beaker", "crucible", "tube", "grad_cyl"):
            v = self.find(k)
            if v:
                return v
        ves = [c for c in self.containers if c.kind in ("beaker", "tube", "grad_cyl", "crucible")]
        return ves[0] if ves else None

    def last_vessel(self):
        ves = [c for c in self.containers if c.kind in ("beaker", "tube", "grad_cyl", "crucible")]
        return ves[-1] if ves else None

    def highlight(self, obj, seconds=0.5):
        if obj is not None:
            obj.highlight = seconds
            play("click")

    def spawn_bubbles(self, cont, n=3):
        cx, cy = cont.center()
        col = (220, 230, 255)
        if cont.contents:
            col = CHEMICALS.get(cont.contents[-1].name, {}).get("color", col)
        for _ in range(n):
            self.particles.append(
                Particle(
                    cx + random.uniform(-cont.w * 0.25, cont.w * 0.25),
                    cy + random.uniform(0, cont.h * 0.2),
                    random.uniform(-8, 8),
                    random.uniform(-40, -18),
                    random.uniform(0.6, 1.4),
                    col,
                    "bubble",
                    random.uniform(2, 5),
                )
            )

    def spawn_vapor(self, cont, gas_name, n=8):
        cx, cy = cont.center()
        col = GAS_COLORS.get(gas_name, (210, 210, 220))
        for _ in range(n):
            self.particles.append(
                Particle(
                    cx + random.uniform(-16, 16),
                    cont.y - 4,
                    random.uniform(-12, 12),
                    random.uniform(-28, -10),
                    random.uniform(0.8, 2.0),
                    col,
                    "vapor",
                    random.uniform(6, 14),
                )
            )

    def accept_job(self):
        self.job = self.current_offer
        self.manual_used = False
        self.show_manual = False
        self.containers = []
        self.thermal = False
        self.auto = False
        self.auto_queue = []
        self.auto_plan = []
        self.auto_wait = 0.0
        self.auto_done = False
        self.pending_step = None
        self.particles = []
        self.mouse.visible = False
        self.message = f"Accepted: {self.job['name']}"
        self.log_action(f"ACCEPTED {self.job['name']}")
        play("beep")
        layout = {
            "beaker": (420, 420), "tube": (520, 430), "grad_cyl": (600, 400),
            "crucible": (700, 440), "thermo": (800, 400), "stirrer": (880, 440),
            "electrodes": (960, 400), "ammeter": (1040, 440), "scale": (420, 560),
            "gas_trap": (780, 540),
        }
        sizes = {
            "beaker": (80, 100), "tube": (28, 110), "grad_cyl": (36, 130),
            "crucible": (70, 50), "thermo": (18, 120), "stirrer": (70, 40),
            "electrodes": (50, 80), "ammeter": (70, 40), "scale": (110, 50),
            "gas_trap": (80, 70),
        }
        for eq in self.job["equipment"]:
            x, y = layout.get(eq, (500, 400))
            w, h = sizes.get(eq, (60, 60))
            self.containers.append(Container(eq, x, y, w, h, label=eq))
        self.state = "play"

    def add_chem_to(self, cont: Container, name: str, grams=10.0, actor="USER"):
        if cont.kind in ("thermo", "stirrer", "electrodes", "ammeter", "scale"):
            if cont.kind == "thermo":
                self.message = f"Thermometer reading: {cont.temp:.1f} C"
                self.log_action(f"{actor} read thermometer {cont.temp:.1f}C")
                self.highlight(cont)
                return
            self.message = f"{cont.kind} is a tool, not a reagent vessel."
            return
        cont.contents.append(ChemAmount(name, grams))
        self.log_action(f"{actor} added {grams}g {name} to {cont.kind}")
        play("drop")
        self.spawn_bubbles(cont, 6)
        self.highlight(cont)
        self._react(cont, actor)

    def _react(self, cont: Container, actor="USER"):
        names = cont.names()
        if len(names) < 2:
            return
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                key = frozenset([names[i], names[j]])
                if key in REACTIONS:
                    prod, dT, expl, tox, note = REACTIONS[key]
                    cont.temp += dT
                    cont.contents.append(ChemAmount(prod, 5))
                    self.log_action(
                        f"{actor} observed reaction in {cont.kind}: {note} -> {prod} (dT={dT})"
                    )
                    self.message = f"Reaction: {note}"
                    self.spawn_bubbles(cont, 10)
                    if "gas" in note.lower() or "CO2" in note or "H2" in note or "Cl2" in note:
                        self.spawn_vapor(cont, "CO2" if "CO2" in note else "H2", 10)
                        play("hiss")
                    if expl >= 5 or (cont.temp > 200 and expl >= 3):
                        play("boom")
                        self.die("EXPLOSION — mixture detonated")
                        return
                    if tox >= 4:
                        trapped = any(c.kind == "gas_trap" for c in self.containers)
                        if not trapped:
                            self.die("POISON — toxic gas not captured")
                            return

    def die(self, reason):
        self.alive = False
        self.auto = False
        self.stop_loops()
        self.fail_reason = reason
        self.state = "fail"
        self.log_action("FAIL " + reason)
        play("boom")

    def start_auto(self, replay=False):
        if self.state != "play" or not self.job:
            return
        if self.auto and not replay:
            self.auto = False
            self.auto_queue = []
            self.pending_step = None
            self.mouse.visible = False
            self.log_action("COMPUTER halted auto-run")
            self.message = "Auto-run stopped. Review the bench or press Replay."
            return
        self.auto_plan = self._plan_auto()
        self.auto_queue = list(self.auto_plan)
        self.auto = True
        self.auto_done = False
        self.pending_step = None
        self.auto_wait = 0.4
        self.mouse.visible = True
        tag = "REPLAY" if replay else "started auto-run"
        self.log_action(f"COMPUTER {tag} ({len(self.auto_queue)} steps, {self.STEP_PAUSE:.0f}s each)")
        self.message = "Watch the pink mouse. Each action is shown and logged."

    def replay_auto(self):
        if self.state != "play" or not self.job:
            return
        for c in self.containers:
            c.contents = []
            c.temp = 22.0
            c.heating = False
            c.stirring = False
            c.powered = False
            c.current = 0.0
        self.particles = []
        self.log_action("USER pressed REPLAY — bench reagents cleared, computer will repeat")
        self.start_auto(replay=True)

    def exit_workbench(self):
        if self.state != "play" or not self.job:
            return
        self.auto = False
        self.mouse.visible = False
        self.log_action("USER exited workbench")
        self.try_complete()

    def _plan_auto(self):
        job = self.job
        pause = self.STEP_PAUSE
        steps = []
        steps.append(("log", "COMPUTER reviewed contract and safety card"))
        steps.append(("wait", pause))

        need_trap = (
            "gas_trap" in job["equipment"]
            or any(CHEMICALS.get(n, {}).get("toxic", 0) >= 3 for n in job["chemicals"])
            or any(n in DANGEROUS for n in job["chemicals"])
        )
        if need_trap and not self.find("gas_trap"):
            steps.append(("spawn", "gas_trap"))
            steps.append(("wait", pause))
            steps.append(("log", "COMPUTER placed emergency gas trap on bench"))
            steps.append(("wait", pause))

        vessel_kind = None
        for k in ("beaker", "crucible", "tube", "grad_cyl"):
            if self.find(k) or k in job["equipment"]:
                vessel_kind = k
                break
        if vessel_kind is None:
            steps.append(("spawn", "beaker"))
            steps.append(("wait", pause))
            vessel_kind = "beaker"

        steps.append(("select", vessel_kind))
        steps.append(("wait", pause))

        for chem in job["chemicals"]:
            steps.append(("weigh", chem))
            steps.append(("wait", pause))
            steps.append(("carry_add", (vessel_kind, chem, 8.0)))
            steps.append(("wait", pause))

        if self.find("stirrer") or "stirrer" in job["equipment"]:
            steps.append(("stir", (vessel_kind, True)))
            steps.append(("wait", pause))

        name_l = job["name"].lower() + " " + job["goal"].lower()
        gentle_heat = any(w in name_l for w in ("distill", "ester", "crystal", "decompos", "electro"))
        hot_heat = any(w in name_l for w in ("oxidation", "thermite", "char", "flame"))
        if hot_heat:
            steps.append(("log", "COMPUTER refused runaway heat — holding below 90 C"))
            steps.append(("wait", pause))
            steps.append(("heat", (vessel_kind, True)))
            steps.append(("wait", pause))
            steps.append(("heat", (vessel_kind, False)))
            steps.append(("wait", pause))
        elif gentle_heat or "thermo" in job["equipment"]:
            steps.append(("heat", (vessel_kind, True)))
            steps.append(("wait", pause))
            steps.append(("heat", (vessel_kind, False)))
            steps.append(("wait", pause))

        if self.find("electrodes") or "electrodes" in job["equipment"] or "electro" in name_l:
            steps.append(("power", (vessel_kind, True)))
            steps.append(("wait", pause))
            steps.append(("read_i", vessel_kind))
            steps.append(("wait", pause))
            steps.append(("power", (vessel_kind, False)))
            steps.append(("wait", pause))

        steps.append(("cool", vessel_kind))
        steps.append(("wait", pause))
        if self.find("stirrer") or "stirrer" in job["equipment"]:
            steps.append(("stir", (vessel_kind, False)))
            steps.append(("wait", pause))
        steps.append(("log", "COMPUTER finished. Review the bench and log, then Replay or Exit."))
        steps.append(("stay", None))
        return steps

    def _begin_visual_step(self, step):
        """Start mouse travel / highlight; return True if step is finished immediately."""
        op, arg = step
        if op == "log":
            self.log_action(arg)
            self.message = arg
            return True
        if op == "wait":
            self.auto_wait = max(self.STEP_PAUSE, float(arg))
            return True
        if op == "stay":
            self.auto = False
            self.auto_done = True
            self.mouse.visible = False
            self.mouse.carrying = None
            self.message = "Computer done. Review steps, Replay, or Exit workbench for score."
            self.log_action("COMPUTER standing by on workbench (no award yet)")
            return True
        if op == "spawn":
            kind = arg
            if not self.find(kind):
                c = Container(kind, 860, 540, 80, 70, label=kind)
                self.containers.append(c)
                self.highlight(c)
            self.log_action(f"COMPUTER deployed extra equipment: {kind}")
            return True
        if op == "select":
            v = self.find(arg) or self.primary_vessel()
            self.selected = v
            if v:
                self.mouse.go(v.center())
                self.pending_step = ("arrive_select", v)
                self.log_action(f"COMPUTER moving to {v.kind}")
                return False
            return True
        if op == "weigh":
            chem = arg
            it = self.shelf_item(chem)
            sc = self.find("scale")
            target = sc.center() if sc else ((it.center() if it else (200, 200)))
            if it:
                self.highlight(it)
            self.mouse.go(target)
            grams = 8.0
            if sc is not None:
                self.log_action(f"COMPUTER moving to scale to weigh {grams}g {chem}")
            else:
                self.log_action(f"COMPUTER estimated {grams}g {chem} (no scale on bench)")
            self.pending_step = ("arrive_weigh", (chem, sc))
            return False
        if op == "carry_add":
            kind, chem, grams = arg
            it = self.shelf_item(chem)
            v = self.find(kind) or self.primary_vessel()
            if it:
                self.highlight(it)
                self.mouse.go(it.center(), carry=None)
                self.pending_step = ("arrive_pick", (it, v, chem, grams))
                self.log_action(f"COMPUTER moving to shelf for {chem}")
                return False
            if v:
                self.add_chem_to(v, chem, grams, actor="COMPUTER")
            return True
        if op in ("stir", "heat", "power", "cool", "read_i"):
            kind = arg[0] if isinstance(arg, tuple) else arg
            v = self.find(kind) or self.primary_vessel()
            tool_map = {"stir": "stirrer", "heat": "thermo", "power": "electrodes", "read_i": "ammeter", "cool": "beaker"}
            tool = self.find(tool_map.get(op, kind)) or v
            if tool:
                self.mouse.go(tool.center())
            elif v:
                self.mouse.go(v.center())
            self.pending_step = ("arrive_tool", (op, arg, v, tool))
            self.log_action(f"COMPUTER moving to use {op} on {getattr(v, 'kind', '?')}")
            return False
        return True

    def _finish_visual_step(self):
        kind, data = self.pending_step
        self.pending_step = None
        if kind == "arrive_select":
            v = data
            self.highlight(v)
            self.log_action(f"COMPUTER focused {v.kind} at ({int(v.x)},{int(v.y)})")
        elif kind == "arrive_weigh":
            chem, sc = data
            if sc:
                self.highlight(sc)
            play("beep")
            self.log_action(f"COMPUTER weighed 8g {chem}")
        elif kind == "arrive_pick":
            it, v, chem, grams = data
            self.highlight(it)
            self.mouse.carrying = chem
            self.log_action(f"COMPUTER picked up {chem} from shelf")
            if v:
                self.mouse.go(v.center(), carry=chem)
                self.pending_step = ("arrive_drop", (v, chem, grams))
                self.log_action(f"COMPUTER carrying {chem} to {v.kind}")
                return  # still travelling
        elif kind == "arrive_drop":
            v, chem, grams = data
            self.mouse.carrying = None
            self.highlight(v)
            names = set(v.names())
            probe = frozenset([chem, next(iter(names))]) if names else None
            if probe in REACTIONS:
                _, _, expl, tox, note = REACTIONS[probe]
                if expl >= 5 or tox >= 5:
                    self.log_action(f"COMPUTER skipped add of {chem}: {note} is unsurvivable")
                    self.message = "Computer skipped a lethal combination."
                    return
            self.add_chem_to(v, chem, grams, actor="COMPUTER")
            self.log_action(f"COMPUTER poured {chem} into {v.kind}")
        elif kind == "arrive_tool":
            op, arg, v, tool = data
            if tool:
                self.highlight(tool)
            if v:
                self.highlight(v)
            if op == "stir":
                _, on = arg
                if v:
                    v.stirring = on
                    self.log_action(f"COMPUTER set stirrer {v.kind}={'ON' if on else 'OFF'}")
            elif op == "heat":
                _, on = arg
                if v:
                    v.heating = on
                    play("heat" if on else "cool")
                    self.log_action(f"COMPUTER set heater {v.kind}={'ON' if on else 'OFF'} (T={v.temp:.1f}C)")
            elif op == "power":
                _, on = arg
                if v:
                    v.powered = on
                    play("spark")
                    self.log_action(f"COMPUTER set electrodes {v.kind}={'ON' if on else 'OFF'}")
            elif op == "read_i":
                if v:
                    v.current = 0.45
                    am = self.find("ammeter")
                    if am:
                        self.highlight(am)
                    self.log_action(f"COMPUTER ammeter reading {v.current:.2f} A on {v.kind}")
            elif op == "cool":
                if v:
                    v.heating = False
                    v.powered = False
                    v.temp = min(v.temp, 35.0)
                    play("cool")
                    self.log_action(f"COMPUTER water-bath cooled {v.kind} to {v.temp:.1f}C")

    def tick_auto(self, dt):
        if not self.auto or self.state != "play":
            return
        self.mouse.tick(dt)
        if self.pending_step:
            if self.mouse.arrived():
                self._finish_visual_step()
                if self.pending_step is None:
                    self.auto_wait = self.STEP_PAUSE
            return
        self.auto_wait -= dt
        if self.auto_wait > 0:
            return
        if not self.auto_queue:
            self.auto = False
            self.auto_done = True
            self.mouse.visible = False
            self.log_action("COMPUTER finished step queue — remaining on workbench")
            return
        step = self.auto_queue.pop(0)
        done = self._begin_visual_step(step)
        if done and step[0] != "wait":
            self.auto_wait = self.STEP_PAUSE

    def stop_loops(self):
        if self.stir_playing:
            SOUNDS["stir"].stop()
            self.stir_playing = False
        if self.bubble_playing:
            SOUNDS["bubble"].stop()
            self.bubble_playing = False
        if self.current_playing:
            SOUNDS["current"].stop()
            self.current_playing = False

    def tick_physics(self, dt):
        if self.state != "play":
            return
        self.tick_auto(dt)

        any_stir = False
        any_bubble = False
        any_power = False

        for obj in list(self.containers) + list(self.shelf):
            if obj.highlight > 0:
                obj.highlight = max(0.0, obj.highlight - dt)

        for c in self.containers:
            c.temp += (22.0 - c.temp) * min(1.0, dt * 0.15)
            if c.heating:
                c.temp += 40 * dt
            if c.stirring:
                c.temp += 1 * dt
                any_stir = True
                self.spawn_bubbles(c, 1)
                any_bubble = True
            if c.powered:
                c.current = 0.4 + 0.2 * math.sin(time.time() * 3)
                c.temp += 8 * dt
                any_power = True
                self.spawn_bubbles(c, 1)
            if c.contents and c.temp > 40 and c.kind in ("beaker", "tube", "grad_cyl", "crucible"):
                self.spawn_bubbles(c, 1 if random.random() < 0.3 else 0)
                if c.temp > 50:
                    any_bubble = True
            remain = []
            for chem in c.contents:
                meta = CHEMICALS.get(chem.name, {})
                bp = meta.get("bp")
                if bp is not None and c.temp >= bp:
                    gas = meta.get("gas") or f"{chem.name} vapor"
                    self.log_action(f"{chem.name} evaporated as {gas} from {c.kind}")
                    self.spawn_vapor(c, gas, 12)
                    play("hiss")
                    tox = meta.get("toxic", 0)
                    expl = meta.get("explode", 0)
                    trapped = any(x.kind == "gas_trap" for x in self.containers)
                    if gas and trapped:
                        trap = next(x for x in self.containers if x.kind == "gas_trap")
                        trap.contents.append(ChemAmount(gas, chem.grams * 0.3))
                        self.log_action(f"gas trap captured {gas}")
                    elif tox >= 3 or expl >= 4:
                        if not trapped:
                            self.die(f"POISON/BLAST from {gas}")
                            return
                else:
                    remain.append(chem)
            c.contents = remain
            if c.temp >= 250 and c.contents:
                expl = max((CHEMICALS.get(x.name, {}).get("explode", 0) for x in c.contents), default=0)
                if expl >= 2:
                    self.die("EXPLOSION — thermal runaway")
                    return

        if any_stir and not self.stir_playing:
            SOUNDS["stir"].play(loops=-1)
            self.stir_playing = True
        if not any_stir and self.stir_playing:
            SOUNDS["stir"].stop()
            self.stir_playing = False
        if any_bubble and not self.bubble_playing:
            SOUNDS["bubble"].play(loops=-1)
            self.bubble_playing = True
        if not any_bubble and self.bubble_playing:
            SOUNDS["bubble"].stop()
            self.bubble_playing = False
        if any_power and not self.current_playing:
            SOUNDS["current"].play(loops=-1)
            self.current_playing = True
        if not any_power and self.current_playing:
            SOUNDS["current"].stop()
            self.current_playing = False

        live = []
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.life -= dt
            if p.kind == "vapor":
                p.r += 8 * dt
            if p.life > 0:
                live.append(p)
        self.particles = live[-400:]

    def try_complete(self):
        if not self.job:
            return
        hot = any(c.temp > 80 and c.kind not in ("thermo",) for c in self.containers)
        has = any(c.contents for c in self.containers)
        if hot:
            self.message = "Cool everything below 80 C before leaving the bench."
            self.log_action("EXIT blocked: vessels still hot")
            return
        if not has:
            self.message = "Nothing on the bench to deliver."
            self.log_action("EXIT blocked: empty bench")
            return
        pts = self.job["difficulty"] * 10
        self.score += pts
        self.jobs_done += 1
        self.log_action(f"COMPLETE +{pts} score={self.score}")
        self.auto = False
        self.stop_loops()
        self.state = "winjob"
        self.message = f"Job complete +{pts}"
        play("win")

    def save_log(self):
        path = "chemlab_log.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"score": self.score, "replay": self.replay, "log": self.log}, f, indent=2)
        self.message = f"Saved {path}"
        self.log_action(f"LOG saved to {path}")

    def open_manual(self):
        if not self.job:
            return
        if self.manual_used and not self.show_manual:
            self.message = "Manual already used for this experiment."
            return
        if not self.manual_used:
            self.manual_used = True
            self.log_action("MANUAL opened (only use)")
        self.show_manual = True
        self.state = "help"

    def _btn(self, rect, text, active=False):
        r = pygame.Rect(rect)
        pygame.draw.rect(self.screen, (70, 90, 50) if active else (40, 60, 80), r, border_radius=6)
        pygame.draw.rect(self.screen, (180, 220, 120) if active else (120, 160, 200), r, 1, border_radius=6)
        self.screen.blit(self.font.render(text, True, (230, 240, 255)), (r.x + 8, r.y + 8))
        return r

    def heat_color(self, t):
        if t < 40:
            return (80, 140, 220)
        if t < 100:
            return (220, 70, 60)
        if t < 200:
            return (230, 210, 40)
        return (255, 255, 255)

    def draw_menu(self):
        self.screen.fill((18, 22, 28))
        self.screen.blit(self.big.render("ChemLab", True, (220, 230, 255)), (40, 40))
        if self.current_offer:
            o = self.current_offer
            self.screen.blit(self.font.render(f"Incoming job: {o['name']}", True, (255, 220, 140)), (40, 140))
            self.screen.blit(self.small.render(f"Difficulty {o['difficulty']}  Equip: {', '.join(o['equipment'])}", True, (180, 180, 180)), (40, 168))
            self.screen.blit(self.small.render(o["goal"], True, (160, 200, 160)), (40, 190))
        self._btn((40, 240, 220, 40), "ACCEPT JOB  [Enter]")
        self._btn((40, 300, 220, 40), "CATALOG  [C]")
        self._btn((40, 360, 220, 40), "QUIT  [Esc]")
        self.screen.blit(self.small.render(f"Score {self.score}   Jobs {self.jobs_done}", True, (200, 200, 200)), (40, 430))
        y = 480
        for line in [
            "AUTO [A]: pink helper-mouse performs each step (5s pause).",
            "Clicks flash gold for 0.5s. Carried reagents follow the mouse.",
            "REPLAY [P] repeats. EXIT BENCH [X] opens the award screen.",
            "Stirrer hums, vessels bubble, vapors are colored, current crackles.",
        ]:
            self.screen.blit(self.small.render(line, True, (140, 150, 160)), (40, y))
            y += 20

    def draw_play(self):
        self.screen.fill((30, 34, 40))
        pygame.draw.rect(self.screen, (22, 24, 28), (0, 0, 380, H))
        self.screen.blit(self.font.render("REAGENT SHELF", True, (200, 210, 220)), (12, 50))
        self.screen.blit(self.small.render(f"Score {self.score}", True, (180, 200, 140)), (12, 12))
        if self.job:
            self.screen.blit(self.small.render(self.job["name"][:48], True, (255, 210, 120)), (400, 12))

        for it in self.shelf:
            col = CHEMICALS[it.name]["color"]
            pygame.draw.rect(self.screen, col, it.rect(), border_radius=3)
            border = (255, 220, 40) if it.highlight > 0 else (0, 0, 0)
            width = 3 if it.highlight > 0 else 1
            pygame.draw.rect(self.screen, border, it.rect(), width, border_radius=3)
            self.screen.blit(self.small.render(it.name[:10], True, (10, 10, 10)), (it.x + 2, it.y + 6))

        pygame.draw.rect(self.screen, (50, 48, 44), (400, 360, 860, 340))
        self.screen.blit(self.small.render("WORKBENCH", True, (180, 170, 150)), (410, 368))

        for c in self.containers:
            col = (160, 190, 210) if not self.thermal else self.heat_color(c.temp)
            pygame.draw.rect(self.screen, col, c.rect(), border_radius=4)
            border = (255, 220, 40) if c.highlight > 0 else (20, 20, 20)
            width = 4 if c.highlight > 0 else 2
            pygame.draw.rect(self.screen, border, c.rect(), width, border_radius=4)
            self.screen.blit(self.small.render(c.kind, True, (10, 10, 10)), (c.x + 2, c.y + 2))
            if c.contents:
                names = ",".join(x.name[:6] for x in c.contents[-2:])
                self.screen.blit(self.small.render(names[:12], True, (20, 20, 40)), (c.x + 2, c.y + 18))
            self.screen.blit(self.small.render(f"{c.temp:.0f}C {c.mass():.0f}g", True, (20, 20, 20)), (c.x + 2, c.y + c.h - 16))
            if c.powered:
                pygame.draw.circle(self.screen, (255, 220, 40), (int(c.x + c.w - 8), int(c.y + 8)), 5)
            if c.stirring:
                pygame.draw.line(self.screen, (40, 40, 80), c.center(), (c.center()[0] + 10, c.center()[1] + 8), 2)

        for p in self.particles:
            a = max(20, min(255, int(255 * (p.life / 2))))
            s = pygame.Surface((int(p.r * 2 + 2), int(p.r * 2 + 2)), pygame.SRCALPHA)
            col = (*p.color[:3], a if p.kind == "vapor" else min(255, a + 40))
            pygame.draw.circle(s, col, (int(p.r + 1), int(p.r + 1)), max(1, int(p.r)))
            if p.kind == "bubble":
                pygame.draw.circle(s, (255, 255, 255, a), (int(p.r + 1), int(p.r + 1)), max(1, int(p.r)), 1)
            self.screen.blit(s, (p.x - p.r, p.y - p.r))

        self._btn((400, 48, 110, 30), "THERMAL [T]")
        self._btn((518, 48, 110, 30), "MANUAL [M]")
        self._btn((636, 48, 90, 30), "SAVE [S]")
        self._btn((734, 48, 80, 30), "HEAT [H]")
        self._btn((822, 48, 150, 30), "AUTO [A]", active=self.auto)
        self._btn((980, 48, 120, 30), "REPLAY [P]")
        self._btn((1108, 48, 150, 30), "EXIT BENCH [X]")

        remain = f"{self.auto_wait:.1f}s" if self.auto and not self.pending_step else ("move" if self.pending_step else "--")
        if self.auto:
            msg = f"AUTO {remain} | {len(self.auto_queue)} queued | {self.message}"
        elif self.auto_done:
            msg = "Review the log, Replay [P], or Exit bench [X] for the award."
        else:
            msg = self.message
        self.screen.blit(self.small.render(msg[:96], True, (220, 230, 200)), (400, 86))
        if self.thermal:
            self.screen.blit(self.small.render("THERMAL VIEW  blue<40  red 40-100  yellow 100-200  white>200", True, (200, 180, 180)), (400, 106))

        pygame.draw.rect(self.screen, (16, 16, 20), (400, 128, 860, 222))
        self.screen.blit(self.small.render("ACTION LOG", True, (160, 160, 180)), (410, 134))
        for i, line in enumerate(self.log[-11:]):
            color = (160, 220, 140) if "COMPUTER" in line else (170, 180, 190)
            self.screen.blit(self.small.render(line[:92], True, color), (410, 154 + i * 17))

        if self.drag and self.drag[0] == "shelf":
            mx, my = pygame.mouse.get_pos()
            pygame.draw.circle(self.screen, CHEMICALS[self.drag[1].name]["color"], (mx, my), 10)

        if self.mouse.visible:
            draw_pink_mouse(self.screen, self.mouse.x, self.mouse.y, self.mouse.carrying)

    def draw_help(self):
        self.screen.fill((24, 26, 22))
        lines = self.job["manual"].split("\n") if self.job else ["No job."]
        self.screen.blit(self.font.render("LAB MANUAL (Esc to return)", True, (220, 220, 180)), (20, 20))
        y = 50
        for ln in lines:
            self.screen.blit(self.small.render(ln[:110], True, (200, 205, 190)), (20, y))
            y += 18

    def draw_catalog(self):
        self.screen.fill((20, 22, 26))
        self.screen.blit(self.font.render("EXPERIMENT CATALOG — 100 jobs  (Esc back, arrows scroll)", True, (220, 220, 240)), (20, 12))
        y = 40
        for exp in EXPERIMENTS[self.catalog_scroll : self.catalog_scroll + 32]:
            self.screen.blit(self.small.render(f"{exp['name'][:70]}  d{exp['difficulty']}", True, (190, 200, 210)), (20, y))
            y += 20

    def draw_fail(self):
        self.screen.fill((40, 10, 10))
        self.screen.blit(self.big.render("LAB LOST", True, (255, 80, 80)), (40, 80))
        self.screen.blit(self.font.render(self.fail_reason, True, (255, 200, 200)), (40, 140))
        self.screen.blit(self.font.render("Enter: menu", True, (220, 180, 180)), (40, 200))

    def draw_winjob(self):
        self.screen.fill((10, 30, 20))
        self.screen.blit(self.big.render("JOB SIGNED OFF", True, (140, 255, 180)), (40, 80))
        self.screen.blit(self.font.render(self.message, True, (200, 255, 210)), (40, 140))
        self.screen.blit(self.font.render(f"Total score {self.score}", True, (200, 220, 200)), (40, 180))
        self.screen.blit(self.font.render("Enter: next contractor offer", True, (180, 200, 180)), (40, 230))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    running = False
                elif e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        if self.state == "help":
                            self.show_manual = False
                            self.state = "play"
                        elif self.state == "catalog":
                            self.state = "menu"
                        elif self.state == "play":
                            self.auto = False
                            self.stop_loops()
                            self.state = "menu"
                        else:
                            running = False
                    elif e.key == pygame.K_RETURN:
                        if self.state == "menu":
                            self.accept_job()
                        elif self.state == "winjob":
                            self._offer_job()
                            self.state = "menu"
                        elif self.state == "fail":
                            self.score = 0
                            self.alive = True
                            self._offer_job()
                            self.state = "menu"
                    elif e.key == pygame.K_c and self.state == "menu":
                        self.catalog_scroll = 0
                        self.state = "catalog"
                    elif e.key == pygame.K_DOWN and self.state == "catalog":
                        self.catalog_scroll = min(68, self.catalog_scroll + 1)
                    elif e.key == pygame.K_UP and self.state == "catalog":
                        self.catalog_scroll = max(0, self.catalog_scroll - 1)
                    elif self.state == "play":
                        if e.key == pygame.K_t:
                            self.thermal = not self.thermal
                            self.log_action("thermal " + str(self.thermal))
                        elif e.key == pygame.K_m:
                            self.open_manual()
                        elif e.key in (pygame.K_SPACE, pygame.K_x):
                            self.exit_workbench()
                        elif e.key == pygame.K_s:
                            self.save_log()
                        elif e.key == pygame.K_a:
                            self.start_auto()
                        elif e.key == pygame.K_p:
                            self.replay_auto()
                        elif e.key == pygame.K_h:
                            v = self.selected or self.last_vessel()
                            if v:
                                v.heating = not v.heating
                                self.highlight(v)
                                play("heat" if v.heating else "cool")
                                self.log_action(f"USER heat {v.kind}={v.heating}")
                        elif e.key == pygame.K_r:
                            v = self.selected or self.last_vessel()
                            if v:
                                v.stirring = not v.stirring
                                self.highlight(v)
                                self.log_action(f"USER stir {v.kind}={v.stirring}")
                        elif e.key == pygame.K_e:
                            v = self.selected or self.last_vessel()
                            if v:
                                v.powered = not v.powered
                                self.highlight(v)
                                play("spark")
                                self.log_action(f"USER electrodes {v.kind}={v.powered}")
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    mx, my = e.pos
                    if self.state == "menu":
                        if pygame.Rect(40, 240, 220, 40).collidepoint(mx, my):
                            self.accept_job()
                        elif pygame.Rect(40, 300, 220, 40).collidepoint(mx, my):
                            self.catalog_scroll = 0
                            self.state = "catalog"
                        elif pygame.Rect(40, 360, 220, 40).collidepoint(mx, my):
                            running = False
                    elif self.state == "play":
                        if pygame.Rect(400, 48, 110, 30).collidepoint(mx, my):
                            self.thermal = not self.thermal
                        elif pygame.Rect(518, 48, 110, 30).collidepoint(mx, my):
                            self.open_manual()
                        elif pygame.Rect(636, 48, 90, 30).collidepoint(mx, my):
                            self.save_log()
                        elif pygame.Rect(734, 48, 80, 30).collidepoint(mx, my):
                            v = self.selected or self.last_vessel()
                            if v:
                                v.heating = not v.heating
                                self.highlight(v)
                        elif pygame.Rect(822, 48, 150, 30).collidepoint(mx, my):
                            self.start_auto()
                        elif pygame.Rect(980, 48, 120, 30).collidepoint(mx, my):
                            self.replay_auto()
                        elif pygame.Rect(1108, 48, 150, 30).collidepoint(mx, my):
                            self.exit_workbench()
                        else:
                            grabbed = False
                            for it in self.shelf:
                                if it.rect().collidepoint(mx, my):
                                    self.drag = ("shelf", it)
                                    self.highlight(it)
                                    grabbed = True
                                    break
                            if not grabbed:
                                for c in reversed(self.containers):
                                    if c.rect().collidepoint(mx, my):
                                        self.drag = ("cont", c, mx - c.x, my - c.y)
                                        self.selected = c
                                        self.highlight(c)
                                        grabbed = True
                                        break
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    if self.state == "play" and self.drag:
                        mx, my = e.pos
                        if self.drag[0] == "shelf":
                            for c in self.containers:
                                if c.rect().collidepoint(mx, my):
                                    self.add_chem_to(c, self.drag[1].name, actor="USER")
                                    break
                        self.drag = None
                elif e.type == pygame.MOUSEMOTION:
                    if self.state == "play" and self.drag and self.drag[0] == "cont":
                        _, c, ox, oy = self.drag
                        c.x = e.pos[0] - ox
                        c.y = e.pos[1] - oy

            self.tick_physics(dt)

            if self.state == "menu":
                self.draw_menu()
            elif self.state == "play":
                self.draw_play()
            elif self.state == "help":
                self.draw_help()
            elif self.state == "catalog":
                self.draw_catalog()
            elif self.state == "fail":
                self.draw_fail()
            elif self.state == "winjob":
                self.draw_winjob()
            pygame.display.flip()
        self.stop_loops()
        pygame.quit()


if __name__ == "__main__":
    ChemLab().run()