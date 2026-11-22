#!/usr/bin/env python3
"""DX7-style FM synth with authentic 32 algorithms and ROM voice loading.

Place ROM1A.syx (or rom1a.syx) next to this script for the real factory bank.
Command-line:
  python dx7.py --generate-all
  python dx7.py --generate-all --no-loop
"""

import json, math, os, re, time, zipfile, wave, random, subprocess, shutil, fnmatch, argparse
from copy import deepcopy
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import pygame

HAS_MIDI = False
try:
    import pygame.midi
    HAS_MIDI = True
except Exception:
    pass

SAMPLE_RATE, NOTE_SECONDS, XFADE_SEC = 44100, 5.0, 0.02
PREVIEW_SECONDS = 1.0
PREVIEW_NOTES = (48, 60, 72, 84)
TWO_PI, MAX_POLY, MAX_OPS = 2.0 * math.pi, 16, 12
HERE = os.path.dirname(os.path.abspath(__file__))
LAUNCH_DIR = os.getcwd()
GEOM_FILE = os.path.join(HERE, "fm_window.json")
BANK_FILE = os.path.join(HERE, "fm_bank.json")
PATHS_FILE = os.path.join(HERE, "fm_paths.json")
SITE_KEY = os.path.join(HERE, "site.key")
TONES_DIR = os.path.join(HERE, "tones")
EXPORT_DIR = os.path.join(LAUNCH_DIR, "dx7_export")
EFFECTS_DIR = os.path.join(LAUNCH_DIR, "effects")
DEFAULT_KEYMAP_TOKENS = (
    "z48 s49 x50 d51 c52 v53 g54 b55 h56 n57 j58 m59 ,60 l61 .62 /64 "
    "q60 261 w62 363 e64 r65 566 t67 668 y69 770 u71 i72 o73 p74 [76 ]77"
)
DEFAULT_ADSR = {"a": 0.02, "d": 0.12, "s": 0.85, "r": 0.25}
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
DEFAULT_POST = {"delay_on": False, "delay_kind": "digital", "delay_time": 0.35, "delay_fb": 0.25, "delay_mix": 0.22,
                "verb_on": False, "verb_kind": "hall", "verb_mix": 0.28, "verb_decay": 0.45}

def midi_note_label(n):
    n = int(n)
    return f"{NOTE_NAMES[n % 12]}{n // 12}_{n:02d}"

def parse_keymap(text):
    mapping = {}
    for tok in text.replace(",", " ,").split():
        tok = tok.strip()
        if len(tok) < 2:
            continue
        i = 1
        while i < len(tok) and not tok[i].isdigit() and tok[i] not in "+-":
            i += 1
        key, num = tok[:i], tok[i:]
        if not num:
            continue
        try:
            mapping[key.lower()] = int(num)
        except ValueError:
            continue
    return mapping

def load_keymap():
    if os.path.isfile(SITE_KEY):
        with open(SITE_KEY, "r", encoding="utf-8") as f:
            m = parse_keymap(f.read())
        if m:
            return m, "site.key"
    return parse_keymap(DEFAULT_KEYMAP_TOKENS), "default"

KEY_NAME_ALIASES = {"comma": ",", "period": ".", "slash": "/", "semicolon": ";",
                    "leftbracket": "[", "rightbracket": "]"}

def event_key_token(event):
    name = pygame.key.name(event.key)
    if event.unicode and event.unicode.strip():
        ch = event.unicode.lower()
        if len(ch) == 1:
            return ch
    return KEY_NAME_ALIASES.get(name.lower(), name.lower())

def load_json(path, default):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def load_geom():
    d = {"w": 1280, "h": 820, "x": 80, "y": 80}
    d.update({k: int(v) for k, v in load_json(GEOM_FILE, {}).items() if k in d})
    d["w"] = max(1100, min(d["w"], 2400))
    d["h"] = max(640, min(d["h"], 1600))
    return d

def save_geom(w, h, x, y):
    save_json(GEOM_FILE, {"w": int(w), "h": int(h), "x": int(x), "y": int(y)})

def load_paths():
    d = {"last_dir": EXPORT_DIR, "last_fx_dir": EFFECTS_DIR}
    raw = load_json(PATHS_FILE, {})
    for k in ("last_dir", "last_fx_dir"):
        if isinstance(raw.get(k), str) and os.path.isdir(raw[k]):
            d[k] = raw[k]
    return d

def save_paths(paths):
    save_json(PATHS_FILE, paths)

def coarse_ratio(c):
    c = int(c) & 31
    return 0.5 if c == 0 else float(c)

def op_ratio(op):
    """DX7-style ratio: coarse (0 → 0.5) * (1 + fine/100) + small detune."""
    coarse = coarse_ratio(op.get("coarse", 1))
    fine = max(0, min(99, int(op.get("fine", 0))))
    det = int(op.get("detune", 0))
    ratio = coarse * (1.0 + fine / 100.0)
    cents = det * 2.0
    return ratio * (2.0 ** (cents / 1200.0))

def midi_to_hz(n):
    return 440.0 * (2.0 ** ((n - 69) / 12.0))

def safe_tone_name(name):
    return re.sub(r"[^\w\-]+", "_", (name or "INIT").strip() or "INIT")[:48]

def unique_patch_name(name, existing):
    base = (name or "Imported").strip() or "Imported"
    names = {str(n) for n in existing}
    if base not in names:
        return base
    i = 2
    while f"{base}_{i}" in names:
        i += 1
    return f"{base}_{i}"

def ensure_export_dir():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(EFFECTS_DIR, exist_ok=True)
    return EXPORT_DIR

def tone_candidates(n):
    os.makedirs(TONES_DIR, exist_ok=True)
    b = os.path.join(TONES_DIR, safe_tone_name(n))
    return [b + ".dat.npz", b + ".npz", b + ".dat"]

def tone_save_path(n):
    os.makedirs(TONES_DIR, exist_ok=True)
    return os.path.join(TONES_DIR, safe_tone_name(n) + ".dat.npz")

def tone_json_path(n):
    os.makedirs(TONES_DIR, exist_ok=True)
    return os.path.join(TONES_DIR, safe_tone_name(n) + ".json")

def sample_src_dir(n):
    p = os.path.join(TONES_DIR, "captured", safe_tone_name(n))
    os.makedirs(p, exist_ok=True)
    return p

def ensure_adsr(p):
    if "adsr" not in p or not isinstance(p["adsr"], dict):
        p["adsr"] = dict(DEFAULT_ADSR)
    a = p["adsr"]
    a["a"] = float(max(0.001, min(2.0, a.get("a", 0.02))))
    a["d"] = float(max(0.001, min(2.0, a.get("d", 0.12))))
    a["s"] = float(max(0.0, min(1.0, a.get("s", 0.85))))
    a["r"] = float(max(0.001, min(3.0, a.get("r", 0.25))))
    p.setdefault("kind", "fm")
    p.setdefault("captured", {})
    return p

# ---------------------------------------------------------------------------
# Authentic DX7 algorithms (1–32)
# Operators 0-based (0 = DX7 OP1 ... 5 = DX7 OP6)
# ---------------------------------------------------------------------------
_RAW_ALGOS = [
    # 1: (2→1) + (6→5→4→3)   fb:6
    {"carriers": {0, 2}, "mod": [(1,0),(5,4),(4,3),(3,2)], "fb": 5},
    # 2: (2→1) + (6→5→4→3)   fb:2
    {"carriers": {0, 2}, "mod": [(1,0),(5,4),(4,3),(3,2)], "fb": 1},
    # 3: (3→2→1) + (6→5→4)   fb:6
    {"carriers": {0, 3}, "mod": [(2,1),(1,0),(5,4),(4,3)], "fb": 5},
    # 4: (3→2→1) + (6→5→4)   fb on 4 (approx)
    {"carriers": {0, 3}, "mod": [(2,1),(1,0),(5,4),(4,3)], "fb": 3},
    # 5: (2→1) + (4→3) + (6→5)   fb:6
    {"carriers": {0, 2, 4}, "mod": [(1,0),(3,2),(5,4)], "fb": 5},
    # 6: (2→1) + (4→3) + (6→5)   fb on 5
    {"carriers": {0, 2, 4}, "mod": [(1,0),(3,2),(5,4)], "fb": 4},
    # 7: (2→1) + (4 + (6→5) → 3)   fb:6
    {"carriers": {0, 2}, "mod": [(1,0),(3,2),(5,4),(4,2)], "fb": 5},
    # 8: (2→1) + ((4 + (6→5)) → 3)   fb:4
    {"carriers": {0, 2}, "mod": [(1,0),(3,2),(5,4),(4,2)], "fb": 3},
    # 9: (2→1) + (4 + (6→5) → 3)   fb:2
    {"carriers": {0, 2}, "mod": [(1,0),(3,2),(5,4),(4,2)], "fb": 1},
    # 10: (5+6→4) + (3→2→1)   fb:3
    {"carriers": {0, 3}, "mod": [(4,3),(5,3),(2,1),(1,0)], "fb": 2},
    # 11: (5+(6)→4) + (3→2→1)   fb:6
    {"carriers": {0, 3}, "mod": [(4,3),(5,3),(2,1),(1,0)], "fb": 5},
    # 12: (4+5+6→3) + (2→1)   fb:2
    {"carriers": {0, 2}, "mod": [(3,2),(4,2),(5,2),(1,0)], "fb": 1},
    # 13: (4+5+(6)→3) + (2→1)   fb:6
    {"carriers": {0, 2}, "mod": [(3,2),(4,2),(5,2),(1,0)], "fb": 5},
    # 14: (2→1) + (5+6→4→3)   fb:6
    {"carriers": {0, 2}, "mod": [(1,0),(4,3),(5,3),(3,2)], "fb": 5},
    # 15: (2→1) + (5+6→4→3)   fb:2
    {"carriers": {0, 2}, "mod": [(1,0),(4,3),(5,3),(3,2)], "fb": 1},
    # 16: 2 + (4→3) + (6→5) → 1   fb:6
    {"carriers": {0}, "mod": [(1,0),(3,2),(2,0),(5,4),(4,0)], "fb": 5},
    # 17: 2 + (4→3) + (6→5) → 1   fb:2
    {"carriers": {0}, "mod": [(1,0),(3,2),(2,0),(5,4),(4,0)], "fb": 1},
    # 18: 2 + 3 + (6→5→4) → 1   fb:3
    {"carriers": {0}, "mod": [(1,0),(2,0),(5,4),(4,3),(3,0)], "fb": 2},
    # 19: (3→2→1) + (6 → 4 and 5)   fb:6
    {"carriers": {0, 3, 4}, "mod": [(2,1),(1,0),(5,3),(5,4)], "fb": 5},
    # 20: (3 → 1 and 2) + (5+6→4)   fb:3
    {"carriers": {0, 1, 3}, "mod": [(2,0),(2,1),(4,3),(5,3)], "fb": 2},
    # 21: (3 → 1 and 2) + (6 → 4 and 5)   fb:3
    {"carriers": {0, 1, 3, 4}, "mod": [(2,0),(2,1),(5,3),(5,4)], "fb": 2},
    # 22: (2→1) + (6 → 3,4,5)   fb:6
    {"carriers": {0, 2, 3, 4}, "mod": [(1,0),(5,2),(5,3),(5,4)], "fb": 5},
    # 23: 1 + (3→2) + (6 → 4 and 5)   fb:6
    {"carriers": {0, 1, 3, 4}, "mod": [(2,1),(5,3),(5,4)], "fb": 5},
    # 24: 1 + 2 + (6 → 3,4,5)   fb:6
    {"carriers": {0, 1, 2, 3, 4}, "mod": [(5,2),(5,3),(5,4)], "fb": 5},
    # 25: 1 + 2 + 3 + (6 → 4 and 5)   fb:6
    {"carriers": {0, 1, 2, 3, 4}, "mod": [(5,3),(5,4)], "fb": 5},
    # 26: 1 + (3→2) + (5+6→4)   fb:6
    {"carriers": {0, 1, 3}, "mod": [(2,1),(4,3),(5,3)], "fb": 5},
    # 27: 1 + (3→2) + (5+6→4)   fb:3
    {"carriers": {0, 1, 3}, "mod": [(2,1),(4,3),(5,3)], "fb": 2},
    # 28: (2→1) + (5→4→3) + 6   fb:5
    {"carriers": {0, 2, 5}, "mod": [(1,0),(4,3),(3,2)], "fb": 4},
    # 29: 1 + 2 + (4→3) + (6→5)   fb:6
    {"carriers": {0, 1, 2, 4}, "mod": [(3,2),(5,4)], "fb": 5},
    # 30: 1 + 2 + (5→4→3) + 6   fb:5
    {"carriers": {0, 1, 2, 5}, "mod": [(4,3),(3,2)], "fb": 4},
    # 31: 1 + 2 + 3 + 4 + (6→5)   fb:6
    {"carriers": {0, 1, 2, 3, 4}, "mod": [(5,4)], "fb": 5},
    # 32: all six carriers   fb:6
    {"carriers": {0, 1, 2, 3, 4, 5}, "mod": [], "fb": 5},
]

def _algo_mod_dict(algo):
    d = {i: [] for i in range(6)}
    for src, dst in algo["mod"]:
        d[dst].append(src)
    return d

ALGORITHMS = {}
for i, a in enumerate(_RAW_ALGOS, 1):
    ALGORITHMS[i] = {
        "mod": _algo_mod_dict(a),
        "carriers": list(a["carriers"]),
        "fb": a["fb"],
    }
ALGO_KEYS = sorted(ALGORITHMS.keys())

def default_op(level=99, coarse=1, detune=0, rates=None, levels=None, on=True):
    return {"on": on, "level": level, "coarse": coarse, "fine": 0, "detune": detune,
            "rates": rates or [99, 99, 99, 70], "levels": levels or [99, 99, 99, 0]}

def make_patch(name, algo, feedback, ops, adsr=None, kind="fm"):
    p = {"name": name, "algo": int(algo), "feedback": int(feedback), "ops": ops,
         "adsr": dict(adsr or DEFAULT_ADSR), "kind": kind, "captured": {}}
    while len(p["ops"]) < 6:
        p["ops"].append(default_op(0, 1, 0, [99, 99, 99, 99], [0, 0, 0, 0], False))
    return ensure_adsr(p)

def off_ops(n=3):
    return [default_op(0, 1, 0, [99, 99, 99, 99], [0, 0, 0, 0], False) for _ in range(n)]

# ---------------------------------------------------------------------------
# DX7 SysEx bulk dump loader
# ---------------------------------------------------------------------------
def unpack_dx7_voice(packed):
    if len(packed) < 128:
        return None
    name = "".join(chr(b & 0x7F) for b in packed[118:128]).strip() or "UNNAMED"
    algo = (packed[110] & 0x1F) + 1
    fb = packed[111] & 0x07
    ops = []
    for op in range(6):
        base = op * 17
        rates = list(packed[base:base+4])
        levels = list(packed[base+4:base+8])
        detune = ((packed[base+12] >> 3) & 0x0F) - 7
        level = packed[base+14] & 0x7F
        coarse = (packed[base+15] >> 1) & 0x1F
        fine = packed[base+16] & 0x7F
        ops.append({
            "on": True,
            "level": level,
            "coarse": coarse,
            "fine": fine,
            "detune": detune,
            "rates": rates,
            "levels": levels,
        })
    ops = ops[::-1]  # packed data is OP6..OP1
    return make_patch(name, algo, fb, ops)

def load_sysex_bank(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    i = 0
    while i < len(data) - 128:
        if data[i] == 0xF0 and i + 6 < len(data) and data[i+1] == 0x43:
            start = i + 6
            if start + 4096 <= len(data):
                patches = []
                for v in range(32):
                    voice = data[start + v*128 : start + (v+1)*128]
                    p = unpack_dx7_voice(voice)
                    if p:
                        patches.append(p)
                if patches:
                    return patches
        i += 1
    return None

def load_rom_or_factory():
    for candidate in ("ROM1A.syx", "rom1a.syx", "ROM1A.SYX"):
        path = os.path.join(HERE, candidate)
        loaded = load_sysex_bank(path)
        if loaded:
            print(f"Loaded {len(loaded)} authentic DX7 voices from {candidate}")
            return loaded
    print("No ROM1A.syx found — using built-in fallback bank")
    return [make_patch("INIT", 1, 0, [default_op() for _ in range(6)])]

FACTORY = load_rom_or_factory()

def load_bank():
    data = load_json(BANK_FILE, None)
    if isinstance(data, list) and len(data) >= 1:
        return [ensure_adsr(p) for p in data]
    return [ensure_adsr(deepcopy(p)) for p in FACTORY]

def one_pole(x, hz):
    x = np.asarray(x, np.float32)
    c = math.exp(-2.0 * math.pi * max(20.0, hz) / SAMPLE_RATE)
    y = np.empty_like(x)
    acc = 0.0
    omc = 1.0 - c
    for i, s in enumerate(x):
        acc = acc * c + s * omc
        y[i] = acc
    return y

def highpass(x, hz):
    return x - one_pole(x, hz)

def soft_clip(x, drive):
    return np.tanh(x * (1.0 + drive * 8.0)).astype(np.float32)

def hard_clip(x, drive):
    return np.clip(x * (2.0 + drive * 16.0), -1, 1).astype(np.float32)

def tube_clip(x, drive):
    y = x * (1.0 + drive * 6.0)
    return (np.tanh(y) + 0.15 * np.tanh(y * 3.0)).astype(np.float32)

def output_clip(x, mode):
    x = np.asarray(x, np.float32)
    if mode == "hard":
        return np.clip(x, -1, 1)
    if mode == "soft":
        return np.tanh(x).astype(np.float32)
    if mode == "tube":
        return tube_clip(x, 0.35)
    return x

def envelope_follow(x, hz=40.0):
    return one_pole(np.abs(x).astype(np.float32), hz)

def instrument_dist(x, drive, tone=0.45, rat=False):
    x = np.asarray(x, np.float32)
    env = envelope_follow(x, 30.0)
    pre = highpass(x, 90.0)
    pre = pre + 0.35 * highpass(x, 1800.0)
    dyn = 0.45 + 1.8 * np.clip(env * 3.0, 0, 1)
    amt = drive * (5.0 if rat else 3.2)
    y = np.tanh(pre * amt * dyn)
    y = y + 0.12 * np.sign(pre) * np.clip(np.abs(pre) * amt, 0, 1)
    y = one_pole(y, 500 + tone * 4500)
    pk = float(np.max(np.abs(y))) + 1e-9
    return (y * (0.85 / max(0.35, min(pk, 2.5)))).astype(np.float32)

def pitch_shift_buf(x, semi):
    if abs(semi) < 0.01:
        return np.asarray(x, np.float32)
    ratio = 2.0 ** (semi / 12.0)
    n = len(x)
    idx = np.mod(np.arange(n) * ratio, max(1, n - 1))
    i0 = np.floor(idx).astype(np.int32)
    frac = idx - i0
    i1 = np.minimum(i0 + 1, n - 1)
    return (x[i0] * (1 - frac) + x[i1] * frac).astype(np.float32)

def comb_delay(x, delay_s, fb, mix):
    d = max(1, int(delay_s * SAMPLE_RATE))
    y = np.asarray(x, np.float32).copy()
    for i in range(d, len(y)):
        y[i] += y[i - d] * fb
    return (x * (1 - mix) + y * mix).astype(np.float32)

def analog_delay(x, delay_s, fb, mix, tape=False):
    d = max(1, int(delay_s * SAMPLE_RATE))
    y = np.asarray(x, np.float32).copy()
    acc = np.zeros(d, np.float32)
    wi = 0
    out = np.empty_like(y)
    for i, s in enumerate(y):
        delayed = acc[wi]
        if tape:
            delayed = 0.92 * delayed + 0.08 * math.tanh(delayed * 2.0)
        out[i] = s + delayed * mix
        acc[wi] = s + delayed * fb
        wi = (wi + 1) % d
    return out.astype(np.float32)

def lfo(n, hz, ph=0.0):
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    return np.sin(TWO_PI * hz * t + ph)

def attack_boost(x, enable, extra=0.20, ms=300.0):
    if not enable:
        return x
    n = min(len(x), int(SAMPLE_RATE * max(20.0, ms) / 1000.0))
    env = np.ones(len(x), np.float32)
    if n > 1:
        env[:n] = 1.0 + extra * np.linspace(1.0, 0.0, n)
    return (x * env).astype(np.float32)

def mistress_flange(x, rate, depth, color, matrix):
    x = np.asarray(x, np.float32)
    n = len(x)
    base_d = 0.0008 + depth * 0.0045
    dmax = max(2, int(base_d * SAMPLE_RATE))
    y = np.zeros(n, np.float32)
    if matrix:
        d = max(2, int((0.0012 + depth * 0.003) * SAMPLE_RATE))
        fb = 0.35 + color * 0.45
        for i in range(n):
            y[i] = x[i] + (y[i - d] if i >= d else 0.0) * fb
        return one_pole(y, 800 + color * 3500)
    mod = 0.5 + 0.5 * lfo(n, max(0.05, rate * 2.8))
    delays = (2 + mod * dmax).astype(np.int32)
    fb = 0.22 + color * 0.4
    for i in range(n):
        di = int(delays[i])
        y[i] = x[i] + (y[i - di] if i >= di else 0.0) * fb
    return one_pole(0.55 * x + 0.55 * y, 900 + color * 2800)

def holy_grail(x, mix, mode):
    x = np.asarray(x, np.float32)
    if mode == "spring":
        y = comb_delay(x, 0.029, 0.58, 1.0)
        y = y + 0.08 * comb_delay(highpass(x, 900), 0.017, 0.35, 1.0)
    elif mode == "flerb":
        y = comb_delay(x, 0.038, 0.5, 1.0)
        y = mistress_flange(y, 0.18, 0.45, 0.4, False)
    else:
        y = comb_delay(x, 0.045, 0.62, 1.0)
        y = one_pole(y, 2200) + 0.25 * comb_delay(x, 0.071, 0.4, 1.0)
    return (x * (1 - mix) + y * mix).astype(np.float32)

def apply_post_fx(x, post):
    y = np.asarray(x, np.float32).copy()
    if post.get("delay_on"):
        t = float(post.get("delay_time", 0.35))
        fb = float(post.get("delay_fb", 0.25))
        mix = float(post.get("delay_mix", 0.22))
        if post.get("delay_kind") == "tape":
            y = analog_delay(y, t, fb, mix, tape=True)
        else:
            y = analog_delay(y, t, fb, mix, tape=False)
    if post.get("verb_on"):
        mix = float(post.get("verb_mix", 0.28))
        kind = post.get("verb_kind", "hall")
        if kind == "spring":
            y = holy_grail(y, mix, "spring")
        else:
            y = holy_grail(y, max(mix, 0.35), "hall")
    return y

def P(name, default, lo, hi):
    return (name, float(default), float(lo), float(hi))

def S(name, default=False):
    return (name, bool(default))

def E(eid, name, color, kind, params, switches=None):
    return {"id": eid, "name": name, "color": color, "kind": kind,
            "params": params, "switches": switches or []}

def luminance(color):
    r, g, b = color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b

def pedal_ink(color):
    if luminance(color) >= 150:
        return (12, 16, 28), (20, 30, 90), (70, 20, 110)
    return (255, 255, 255), (255, 230, 70), (255, 140, 200)

def knob_style(pedal_color):
    if luminance(pedal_color) < 150:
        return (236, 230, 214), (10, 22, 70), (40, 42, 50)
    return (28, 28, 32), (255, 255, 255), (210, 210, 210)

def short_knob(name):
    s = re.sub(r"[^A-Za-z0-9]+", "", str(name))
    return (s or str(name))[:6].upper()

DIST_KINDS = {"dist", "fuzz", "od"}
DIST_PARAMS = [P("dist", 0.55, 0, 1), P("tone", 0.45, 0, 1), P("level", 0.7, 0, 1), P("boost_ms", 300, 50, 800)]
DIST_SW = [S("attack_boost", False)]

EFFECT_DEFS = [
    E("nuxroct", "NUX Roctary", (150, 72, 48), "nuxroct",
      [P("speed", 3.2, 0.2, 10), P("balance", 0.5, 0, 1), P("horn", 0.55, 0, 1), P("drive", 0.35, 0, 1),
       P("oct_mix", 0.4, 0, 1), P("dry", 0.65, 0, 1), P("tone", 0.5, 0, 1), P("level", 0.75, 0, 1)]),
    E("twdist", "Mosky Audio TW Distortion", (22, 22, 24), "dist",
      [P("gain", 0.55, 0, 1), P("bass", 0.5, 0, 1), P("mid", 0.48, 0, 1), P("treble", 0.52, 0, 1),
       P("presence", 0.4, 0, 1), P("level", 0.7, 0, 1), P("boost_ms", 300, 50, 800)], [S("modern"), S("attack_boost", False)]),
    E("ph9", "Behringer PH9", (190, 20, 25), "phase", [P("rate", 0.45, 0.05, 6)], [S("color")]),
    E("rat", "ProCo RAT", (18, 18, 18), "dist",
      [P("dist", 0.55, 0, 1), P("filter", 0.45, 0.05, 1), P("level", 1.4, 0.2, 4.0), P("boost_ms", 300, 50, 800)],
      [S("turbo"), S("attack_boost", False)]),
    E("overdrive", "Classic Overdrive", (30, 150, 50), "od",
      [P("drive", 0.4, 0, 1), P("tone", 0.55, 0, 1), P("level", 0.8, 0, 1), P("boost_ms", 300, 50, 800)], [S("attack_boost", False)]),
    E("bd2", "BOSS Blues Driver", (40, 80, 180), "od",
      [P("drive", 0.65, 0, 1), P("tone", 0.5, 0, 1), P("level", 1.3, 0.2, 4.0), P("boost_ms", 300, 50, 800)], [S("attack_boost", False)]),
    E("volume", "Volume Boost", (200, 200, 60), "vol", [P("gain", 2.0, 1.0, 20.0)]),
    E("lpb1", "EHX LPB-1 Linear Power Booster", (20, 20, 20), "boost", [P("gain", 4.0, 1.0, 10.0), P("level", 1.0, 0.2, 2.0)]),
    E("bedford", "Bedford Delay", (40, 70, 120), "bedford", [P("time", 4.0, 1.0, 20.0), P("fb", 0.25, 0, 0.7), P("mix", 0.35, 0, 1)]),
    E("dusty", "The Dusty", (90, 40, 120), "dusty", [P("position_ms", 120, 0, 2000)]),
    E("chorus", "Fab Chorus", (40, 90, 210), "chorus", [P("rate", 0.35, 0.05, 2), P("depth", 0.35, 0, 1), P("mix", 0.4, 0, 1)]),
    E("reverb", "Hall Reverb", (120, 40, 180), "verb", [P("mix", 0.28, 0, 1), P("decay", 0.45, 0.05, 0.95), P("size", 0.35, 0.05, 1)]),
    E("springverb", "Spring Reverb Tank", (160, 130, 70), "spring", [P("mix", 0.35, 0, 1), P("drip", 0.45, 0, 1), P("decay", 0.4, 0, 1)]),
    E("delay", "Delay / Echo", (70, 40, 160), "delay", [P("time", 0.28, 0.05, 0.8), P("fb", 0.35, 0, 0.9), P("mix", 0.3, 0, 1)]),
    E("tremolo", "Tremolo", (230, 120, 30), "trem", [P("rate", 4.5, 0.2, 12), P("depth", 0.55, 0, 1)]),
    E("harmonizer", "Harmonizer", (255, 90, 170), "harm", [P("semi", 7, -12, 12), P("mix", 0.4, 0, 1)]),
    E("merge", "Patch Merge", (80, 120, 160), "merge", [P("current", 0.5, 0, 1), P("external", 0.5, 0, 1)]),
    E("colourbox", "JHS Colour Box V2", (180, 90, 40), "amp",
      [P("gain", 0.55, 0, 1), P("bass", 0.5, 0, 1), P("mid", 0.5, 0, 1), P("treble", 0.55, 0, 1), P("level", 0.75, 0, 1), P("boost_ms", 300, 50, 800)],
      [S("attack_boost", False)]),
    E("echoverb", "Flamma Echoverb", (90, 40, 140), "combo", [P("time", 0.28, 0.05, 0.7), P("decay", 0.45, 0, 1), P("mix", 0.4, 0, 1)]),
    E("fc05", "Flamma FC05 Multi", (50, 90, 140), "combo", [P("a", 0.4, 0, 1), P("b", 0.4, 0, 1), P("mix", 0.45, 0, 1)]),
    E("princeton", "Fender Princeton Amp", (200, 40, 40), "amp",
      [P("gain", 0.35, 0, 1), P("bass", 0.5, 0, 1), P("treble", 0.55, 0, 1), P("level", 0.8, 0, 1)]),
    E("deluxe65", "65 Fender Deluxe Reverb", (180, 30, 30), "amp",
      [P("gain", 0.4, 0, 1), P("vibrato", 0.25, 0, 1), P("reverb", 0.35, 0, 1), P("level", 0.8, 0, 1)]),
    E("deathmetal", "DOD FX86 Death Metal", (20, 20, 20), "dist",
      [P("gag", 0.7, 0, 1), P("mid", 0.4, 0, 1), P("low", 0.5, 0, 1), P("level", 0.65, 0, 1), P("boost_ms", 300, 50, 800)], [S("attack_boost", False)]),
    E("grunge", "DOD FX69B Grunge", (40, 40, 20), "dist",
      [P("grunge", 0.65, 0, 1), P("face", 0.5, 0, 1), P("loud", 0.7, 0, 1), P("butt", 0.45, 0, 1), P("boost_ms", 300, 50, 800)], [S("attack_boost", False)]),
    E("bustedamp", "Busted Amp Crackle", (90, 70, 40), "busted",
      [P("bottom", 20, 1, 100), P("cutoff", 90, 1, 100), P("crackle", 0.55, 0, 1)]),
    E("notefeedback", "Note Feedback Howl", (160, 40, 40), "feedback", [P("amount", 0.35, 0, 1), P("time", 0.22, 0.05, 0.6), P("mix", 0.4, 0, 1)]),
    E("springkick", "Kicked Spring Tank", (150, 120, 50), "kickspring", [P("thump", 0.6, 0, 1), P("rattle", 0.45, 0, 1), P("mix", 0.4, 0, 1)]),
    E("lightning", "Lightning Then Thunder", (40, 60, 160), "lightning", [P("mix", 0.45, 0, 1), P("level", 0.7, 0, 1)]),
    E("turbojet", "Turbo Jet Sky", (60, 80, 100), "jet", [P("mix", 0.4, 0, 1), P("whoosh", 0.5, 0, 1), P("level", 0.7, 0, 1)]),
    E("bug", "Bug Line Noise", (180, 180, 40), "bug",
      [P("volume", 100, 0, 500), P("mix", 0.3, 0, 1), P("bass", 0.5, 0, 1), P("mid", 0.5, 0, 1), P("treble", 0.5, 0, 1)],
      [S("computer"), S("transformer"), S("lights", True), S("radio"), S("phonograph"), S("random_click")]),
    E("electricmistress", "EHX Electric Mistress", (40, 80, 160), "mistress",
      [P("rate", 0.35, 0.05, 4), P("range", 0.55, 0, 1), P("color", 0.45, 0, 1)], [S("filter_matrix")]),
    E("holy", "EHX Holy Grail", (180, 160, 40), "holygrail", [P("reverb", 0.45, 0, 1)], [S("spring", True), S("hall"), S("flerb")]),
]
MORE = [
    ("ts9", "Ibanez TS9 Tube Screamer", (40, 170, 70), "od"),
    ("bigmuff", "EHX Big Muff Pi", (200, 40, 40), "fuzz"),
    ("soulfood", "EHX Soul Food", (210, 180, 80), "od"),
    ("canyon", "EHX Canyon Delay", (40, 40, 40), "delay"),
    ("pog2", "EHX POG2", (30, 30, 30), "oct"),
    ("mel9", "EHX MEL9", (200, 160, 40), "form"),
    ("platform", "EHX Platform Compressor", (20, 20, 20), "comp"),
    ("pitchfork", "EHX Pitch Fork", (200, 20, 20), "pitch"),
    ("memoryboy", "EHX Memory Boy", (180, 80, 20), "delay"),
    ("ce1", "BOSS CE-1 Chorus", (40, 80, 160), "chorus"),
    ("dd3", "BOSS DD-3 Digital Delay", (200, 80, 20), "delay"),
    ("rv6", "BOSS RV-6 Reverb", (40, 120, 160), "verb"),
    ("mt2", "BOSS Metal Zone", (180, 40, 20), "dist"),
    ("sd1", "BOSS SD-1 Super OverDrive", (220, 120, 20), "od"),
    ("ph3", "BOSS PH-3 Phase Shifter", (180, 20, 20), "phase"),
    ("kloncentaur", "Klon Centaur", (200, 180, 90), "od"),
    ("carboncopy", "MXR Carbon Copy", (20, 80, 40), "delay"),
    ("dynacomp", "MXR Dyna Comp", (220, 80, 20), "comp"),
    ("strymonbigsky", "Strymon BigSky", (200, 200, 210), "verb"),
    ("strymontimeline", "Strymon TimeLine", (40, 40, 40), "delay"),
    ("smallclone", "EHX Small Clone", (40, 160, 80), "chorus"),
    ("smallstone", "EHX Small Stone", (40, 160, 80), "phase"),
    ("oceans11", "EHX Oceans 11", (40, 80, 180), "verb"),
    ("freezehold", "EHX Freeze", (200, 200, 200), "verb"),
]
kinds_guess = {
    "od": DIST_PARAMS, "dist": DIST_PARAMS, "fuzz": DIST_PARAMS,
    "delay": [P("time", 0.28, 0.05, 0.8), P("fb", 0.35, 0, 0.9), P("mix", 0.3, 0, 1)],
    "verb": [P("mix", 0.3, 0, 1), P("decay", 0.45, 0, 1), P("size", 0.4, 0, 1)],
    "chorus": [P("rate", 0.35, 0.05, 2), P("depth", 0.35, 0, 1), P("mix", 0.4, 0, 1)],
    "phase": [P("rate", 0.4, 0.05, 4), P("depth", 0.6, 0, 1), P("fb", 0.3, 0, 0.8)],
    "flange": [P("rate", 0.25, 0.05, 2), P("depth", 0.4, 0, 1), P("fb", 0.35, 0, 0.8)],
    "trem": [P("rate", 4.5, 0.2, 12), P("depth", 0.55, 0, 1)],
    "oct": [P("down1", 0.4, 0, 1), P("up1", 0.2, 0, 1), P("dry", 0.7, 0, 1)],
    "pitch": [P("semi", 0, -12, 12), P("mix", 1, 0, 1)],
    "harm": [P("semi", 7, -12, 12), P("mix", 0.4, 0, 1)],
    "comp": [P("sustain", 0.5, 0, 1), P("attack", 0.3, 0, 1), P("level", 0.8, 0, 1)],
    "boost": [P("gain", 4.0, 1, 10), P("level", 1.0, 0.2, 2)],
    "form": [P("form", 0.4, 0, 1), P("mix", 0.4, 0, 1)],
    "combo": [P("a", 0.4, 0, 1), P("b", 0.4, 0, 1), P("mix", 0.4, 0, 1)],
    "amp": [P("gain", 0.45, 0, 1), P("treble", 0.55, 0, 1), P("level", 0.75, 0, 1)],
}
seen = {e["id"] for e in EFFECT_DEFS}
for eid, name, col, kind in MORE:
    if eid in seen:
        continue
    sw = DIST_SW if kind in DIST_KINDS else []
    EFFECT_DEFS.append(E(eid, name, col, kind, kinds_guess.get(kind, [P("mix", 0.5, 0, 1), P("level", 0.8, 0, 1)]), sw))
    seen.add(eid)
FX_INDEX = {e["id"]: e for e in EFFECT_DEFS}

def default_instance(eid):
    e = FX_INDEX.get(eid)
    if not e:
        return {"base": str(eid), "on": True, "params": {}, "switches": {}, "merge_patch": ""}
    return {"base": eid, "on": True,
            "params": {p[0]: p[1] for p in e["params"]},
            "switches": {s[0]: s[1] for s in e["switches"]},
            "merge_patch": ""}

def normalize_chain(chain):
    out = []
    if not chain:
        return out
    for item in chain:
        if isinstance(item, str):
            if item in FX_INDEX:
                out.append(default_instance(item))
        elif isinstance(item, dict):
            base = item.get("base") or item.get("id")
            if not base:
                continue
            inst = default_instance(base)
            if isinstance(item.get("params"), dict):
                inst["params"].update(item["params"])
            if isinstance(item.get("switches"), dict):
                inst["switches"].update(item["switches"])
            inst["on"] = bool(item.get("on", True))
            inst["merge_patch"] = item.get("merge_patch", "")
            out.append(inst)
    return out

def instance_label(inst, count_map):
    e = FX_INDEX.get(inst.get("base"))
    name = e["name"] if e else inst.get("base", "?")
    n = count_map.get(inst.get("base"), 1)
    return name if n <= 1 else f"{name}{n}"

def apply_effect(x, e, st, ctx=None):
    x = np.asarray(x, np.float32)
    p, sw, kind = st.get("params", {}), st.get("switches", {}), e["kind"]
    g = lambda k, d=0.5: float(p.get(k, d))
    if e["id"] == "rat" or (kind in ("dist", "fuzz") and e["id"] != "bd2"):
        y = instrument_dist(x, g("dist", g("gain", g("grunge", g("gag", 0.55)))), g("filter", g("tone", 0.45)), rat=True)
        y = attack_boost(y, bool(sw.get("attack_boost", False)), extra=0.20, ms=g("boost_ms", 300))
        return (y * g("level", g("loud", 1.2))).astype(np.float32)
    if e["id"] == "bd2" or kind in ("od",):
        y = instrument_dist(x, g("drive", g("gain", 0.65)), g("tone", 0.5), rat=True)
        y = attack_boost(y, bool(sw.get("attack_boost", False)), extra=0.20, ms=g("boost_ms", 300))
        return (y * g("level", 1.2)).astype(np.float32)
    if kind == "vol" or e["id"] == "volume":
        return (x * g("gain", 2.0)).astype(np.float32)
    if e["id"] == "lpb1" or kind == "boost":
        return (x * g("gain", 4.0) * g("level", 1.0)).astype(np.float32)
    if kind == "amp":
        y = instrument_dist(x, g("gain", 0.45), g("treble", 0.55), rat=False)
        y = attack_boost(y, bool(sw.get("attack_boost", False)), extra=0.20, ms=g("boost_ms", 300))
        y = y * g("level", 0.75)
        if e["id"] == "deluxe65":
            y = y * (1.0 - g("vibrato", 0.25) * 0.3 * (0.5 + 0.5 * lfo(len(y), 5)))
            y = comb_delay(y, 0.03, 0.4, g("reverb", 0.35) * 0.5)
        return y
    if kind == "nuxroct":
        rate = g("speed") * (1.85 if sw.get("fast") else 1.0)
        y = soft_clip(x, g("drive"))
        horn = y * (1.0 - g("horn") * 0.35 * (0.5 + 0.5 * lfo(len(y), rate)))
        drum = one_pole(y, 280) * (0.5 + 0.5 * lfo(len(y), rate * 0.5, 1.2))
        rot = horn * g("balance") + drum * (1.0 - g("balance"))
        if not sw.get("rotary"):
            rot = y
        octv = pitch_shift_buf(x, -12.0)
        if sw.get("poly"):
            octv = octv + pitch_shift_buf(x, 12.0) * 0.35
        return one_pole(rot * g("dry") + octv * g("oct_mix"), 400 + g("tone") * 5000) * g("level")
    if kind == "mistress":
        return mistress_flange(x, g("rate", 0.35), g("range", 0.55), g("color", 0.45), sw.get("filter_matrix", False))
    if kind == "holygrail":
        mode = "flerb" if sw.get("flerb") else ("hall" if sw.get("hall") else "spring")
        return holy_grail(x, g("reverb", 0.45), mode)
    if kind == "bedford":
        y = analog_delay(x, g("time", 4.0), g("fb", 0.25), g("mix", 0.35), tape=False)
        return make_loopable(y)
    if kind == "dusty":
        pos = int(g("position_ms", 120) * SAMPLE_RATE / 1000.0)
        pos = max(0, min(len(x) - 1, pos))
        y = x.copy()
        head = y[:pos][::-1]
        y[:] = 0
        y[:len(head)] = head
        return make_loopable(y)
    if kind == "phase":
        y = x + highpass(x, 250 + g("depth", 0.6) * 800) * 0.35
        return (x * 0.5 + y * (0.5 + 0.5 * lfo(len(x), g("rate", 0.4))) * 0.5).astype(np.float32)
    if kind in ("chorus", "vibe"):
        d = int((0.003 + g("depth", 0.35) * 0.012) * SAMPLE_RATE)
        idx = np.clip(np.arange(len(x)) - (lfo(len(x), g("rate", g("speed", 0.35))) * 0.5 + 0.5) * d, 0, len(x) - 1).astype(np.int32)
        return x * (1 - g("mix", 0.4)) + x[idx] * g("mix", 0.4)
    if kind == "flange":
        return mistress_flange(x, g("rate", 0.25), g("depth", 0.4), g("fb", 0.35), False)
    if kind == "trem":
        return (x * (1.0 - g("depth", 0.5) * 0.5 * (1 + lfo(len(x), g("rate", 4))))).astype(np.float32)
    if kind == "delay":
        return analog_delay(x, g("time", 0.28), g("fb", 0.35), g("mix", 0.3), tape=False)
    if kind == "verb":
        return holy_grail(x, g("mix", 0.28), "hall")
    if kind == "spring":
        return holy_grail(x, g("mix", 0.35), "spring")
    if kind in ("oct", "pitch", "harm"):
        return x * (1 - g("mix", 0.4)) + pitch_shift_buf(x, g("semi", -12 if kind == "oct" else 7)) * g("mix", 0.4)
    if kind == "comp":
        env = envelope_follow(x, 40)
        gain = np.where(env > 0.3, 0.3 / (env + 1e-6), 1.0)
        return x * (1.0 - (1.0 - gain) * g("sustain", 0.5)) * g("level", 0.85)
    if kind == "combo":
        y = analog_delay(soft_clip(x, g("a", 0.4)), 0.22, 0.3, g("mix", 0.4))
        return holy_grail(y, g("b", 0.4) * 0.5, "hall")
    if kind == "busted":
        env = envelope_follow(x, 25)
        bottom = g("bottom", 20) / 100.0
        cutoff = bottom * (g("cutoff", 90) / 100.0)
        crackle_amt = g("crackle", 0.55)
        noise = highpass(np.random.randn(len(x)).astype(np.float32), 1200)
        y = x.copy()
        silent = env < cutoff * 0.89
        mid = (env <= bottom) & (~silent)
        at_cut = np.abs(env - cutoff) < 0.02
        y[mid] = y[mid] * 0.55 + noise[mid] * crackle_amt * 0.25
        y[at_cut] = y[at_cut] * 0.25 + noise[at_cut] * crackle_amt * 0.35
        y[silent] = 0
        return y.astype(np.float32)
    if kind == "feedback":
        return comb_delay(x, g("time", 0.22), 0.55 + g("amount", 0.35) * 0.35, g("mix", 0.4))
    if kind == "kickspring":
        t = np.arange(len(x), dtype=np.float32) / SAMPLE_RATE
        thump = np.sin(TWO_PI * 55 * t) * np.exp(-t * 18) * g("thump", 0.6)
        rattle = highpass(np.random.randn(len(x)).astype(np.float32), 1200) * np.exp(-t * 8) * g("rattle", 0.45)
        return x * (1 - g("mix")) + (x * 0.5 + thump + rattle) * g("mix")
    if kind == "lightning":
        t = np.arange(len(x), dtype=np.float32) / SAMPLE_RATE
        bolt = highpass(x * (np.random.rand(len(x)) > 0.97).astype(np.float32) * 8, 2000) * np.exp(-t * 12)
        thunder = one_pole(x * lfo(len(x), 18) * np.exp(-t * 1.2), 180)
        return (x * (1 - g("mix")) + (bolt * 0.7 + thunder) * g("mix") * g("level", 0.7)).astype(np.float32)
    if kind == "jet":
        t = np.arange(len(x), dtype=np.float32) / SAMPLE_RATE
        whoosh = lfo(len(x), 0.4 + g("whoosh", 0.5)) * (1 - np.exp(-t * 0.8))
        jet = one_pole(x * (0.4 + 0.6 * whoosh) + highpass(x, 2000) * whoosh * 0.3, 900)
        return x * (1 - g("mix")) + jet * g("mix") * g("level", 0.7)
    if kind == "bug":
        t = np.arange(len(x), dtype=np.float32) / SAMPLE_RATE
        noise = np.zeros(len(x), np.float32)
        if sw.get("lights", True):
            noise += 0.04 * np.sin(TWO_PI * 120 * t)
        if sw.get("transformer"):
            noise += 0.05 * np.sin(TWO_PI * 60 * t)
        if sw.get("computer"):
            noise += 0.03 * np.sin(TWO_PI * 15750 * t)
        if sw.get("radio"):
            noise += 0.02 * np.random.randn(len(x)).astype(np.float32)
        if sw.get("phonograph"):
            noise += highpass(np.random.randn(len(x)).astype(np.float32), 400) * 0.03
        if sw.get("random_click"):
            step = int(SAMPLE_RATE * (1.0 + 0.8 * np.random.rand()))
            noise[::max(1, step)] += 0.4
        y = one_pole(noise, 80 + g("bass") * 200)
        y = y + (noise - one_pole(noise, 800)) * g("mid")
        y = y + highpass(noise, 2500) * g("treble")
        vol = g("volume", 100) / 100.0
        return x * (1 - g("mix")) + y * vol * g("mix")
    if kind == "merge" and ctx and ctx.get("merge_wave") is not None:
        ext = ctx["merge_wave"]
        if len(ext) < len(x):
            ext = np.pad(ext, (0, len(x) - len(ext)))
        ext = ext[:len(x)]
        return (x * g("current", 0.5) + ext * g("external", 0.5)).astype(np.float32)
    return x

def apply_fx_chain(x, instances, extra=None, clip_mode="none"):
    y = np.asarray(x, np.float32).copy()
    extra = extra or {}
    for inst in normalize_chain(instances):
        if not inst.get("on", True):
            continue
        e = FX_INDEX.get(inst["base"])
        if not e:
            continue
        ctx = dict(extra)
        if e["kind"] == "merge":
            ctx["merge_wave"] = extra.get("merge_map", {}).get(inst.get("merge_patch"))
        y = apply_effect(y, e, inst, ctx)
    y = output_clip(y, clip_mode)
    return y.astype(np.float32)

class Envelope:
    def __init__(self, rates, levels, out_level):
        self.rates = [max(0, min(99, r)) for r in rates]
        self.levels = [max(0, min(99, lv)) / 99.0 for lv in levels]
        self.out = max(0, min(99, out_level)) / 99.0
        self.stage = 0
        self.level = 0.0
        self.released = False
        self.done = False
        self._set_target(0)
    def _set_target(self, st):
        self.stage = st
        self.target = self.levels[min(st, len(self.levels) - 1)]
        r = self.rates[min(st, len(self.rates) - 1)] / 99.0
        self.coeff = 1.0 - math.exp(-1.0 / ((0.003 + (1 - r) ** 2 * 3.5) * SAMPLE_RATE))
    def step(self):
        if self.done:
            return 0.0
        self.level += (self.target - self.level) * self.coeff
        if abs(self.target - self.level) < 0.002:
            self.level = self.target
            if not self.released and self.stage < 2:
                self._set_target(self.stage + 1)
        return self.level * self.out

def make_loopable(buf, force=False):
    if not force and len(buf) < SAMPLE_RATE * 1.5:
        return buf.astype(np.float32)
    xfade = max(32, min(int(SAMPLE_RATE * XFADE_SEC), len(buf) // 8))
    skip = min(int(SAMPLE_RATE * 0.5), len(buf) // 4)
    body = buf[skip:].astype(np.float32, copy=True)
    if len(body) <= xfade * 2:
        return buf.astype(np.float32)
    fo = np.cos(np.linspace(0, math.pi * 0.5, xfade, dtype=np.float32))
    fi = np.sin(np.linspace(0, math.pi * 0.5, xfade, dtype=np.float32))
    looped = np.concatenate([body[xfade:-xfade], body[-xfade:] * fo + body[:xfade] * fi])
    looped -= float(np.mean(looped))
    pk = float(np.max(np.abs(looped))) + 1e-9
    if pk > 1.2:
        looped *= 1.0 / pk
    return looped.astype(np.float32)

def render_note_first_iteration(patch, midi_note, seconds=NOTE_SECONDS, velocity=110, no_loop=False):
    nops = max(6, min(MAX_OPS, len(patch.get("ops", []))))
    ops = list(patch["ops"]) + [default_op(0, 1, 0, [99, 99, 99, 99], [0, 0, 0, 0], False)] * (nops - len(patch["ops"]))
    n = int(SAMPLE_RATE * seconds)
    vel = velocity / 127.0
    algo = ALGORITHMS.get(int(patch.get("algo", 2)), ALGORITHMS[2])
    fb_level = float(patch.get("feedback", 0))
    # Feedback scaling closer to Dexed/DX7
    fb_amt = 0.0 if fb_level <= 0 else (2.0 ** (fb_level - 7.0)) * 6.0
    base = midi_to_hz(midi_note)
    phase = [0.0] * nops
    inc = [0.0] * nops
    envs = []
    last = [0.0] * nops
    for i in range(nops):
        op = ops[i]
        ratio = op_ratio(op)
        inc[i] = TWO_PI * base * ratio / SAMPLE_RATE
        envs.append(Envelope(op.get("rates", [99, 99, 99, 70]), op.get("levels", [99, 99, 99, 0]),
                             op.get("level", 99) if op.get("on", True) else 0))
    mods, carriers, fb_op = algo["mod"], list(algo["carriers"]), algo["fb"]
    extra = [i for i in range(6, nops) if ops[i].get("on", True)]
    carriers = carriers + extra
    out = np.zeros(n, np.float32)
    order = list(range(nops - 1, -1, -1))
    # Stronger modulation index for authentic DX7 character
    MOD_SCALE = 12.0
    for i in range(n):
        env = [e.step() for e in envs]
        vals = [0.0] * nops
        for opi in order:
            mod = sum(vals[s] for s in mods.get(opi, [])) * MOD_SCALE
            if opi == fb_op and fb_amt > 0:
                mod += last[opi] * fb_amt * MOD_SCALE
            vals[opi] = math.sin(phase[opi] + mod) * env[opi]
            phase[opi] += inc[opi]
            if phase[opi] >= TWO_PI:
                phase[opi] -= TWO_PI
        last = vals
        out[i] = sum(vals[c] for c in carriers if c < nops)
    pk = float(np.max(np.abs(out))) + 1e-9
    if pk > 1.5:
        out *= 1.5 / pk
    out *= 0.22 * (0.3 + 0.7 * vel)
    adsr = patch.get("adsr", DEFAULT_ADSR)
    do_loop = (not no_loop) and adsr.get("s", 0.5) > 0.35
    return make_loopable(out, force=do_loop) if do_loop else out.astype(np.float32)

def pcm_sound(samples):
    pcm = np.clip(samples * 32767, -32767, 32767).astype(np.int16)
    return pygame.mixer.Sound(buffer=memoryview(pcm).tobytes()), samples

def save_tone_file(path, waves):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {"notes": np.array(sorted(int(n) for n in waves.keys()), np.int16)}
    for n, w in waves.items():
        payload[f"n{int(n)}"] = np.asarray(w, np.float32)
    np.savez_compressed(path, **payload)

def load_tone_file(path, needed):
    try:
        data = np.load(path, allow_pickle=False)
    except Exception:
        return None
    keys = set(data.files)
    waves = {}
    for n in needed:
        key = f"n{int(n)}"
        if key not in keys:
            data.close()
            return None
        waves[int(n)] = np.array(data[key], dtype=np.float32)
    data.close()
    return waves

def write_wav(path, samples):
    pcm = np.clip(np.asarray(samples) * 32767, -32767, 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())

def try_mp3(wav_path, mp3_path):
    for cmd in (
        ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "4", mp3_path],
        ["lame", "-V4", wav_path, mp3_path],
    ):
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.isfile(mp3_path):
                return True
        except Exception:
            continue
    return False

def format_gen_time(seconds):
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    total = int(math.floor(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def patch_fingerprint(p):
    q = deepcopy(p)
    q.pop("adsr", None)
    return json.dumps(q, sort_keys=True)

def estimate_period(wave):
    w = np.asarray(wave, np.float32)
    n = min(len(w), 4096)
    w = w[:n] - float(np.mean(w[:n]))
    if n < 64:
        return 64
    spec = np.abs(np.fft.rfft(w * np.hanning(n)))
    spec[0] = 0
    k = int(np.argmax(spec[2:n // 8]) + 2)
    if k <= 0:
        return 128
    period = max(16, int(n / k))
    return period

COL_BG, COL_PANEL, COL_ACCENT, COL_ORANGE = (18, 20, 28), (32, 36, 48), (90, 200, 255), (255, 160, 60)
COL_TEXT, COL_DIM, COL_KEY, COL_KEY_BLK = (230, 232, 240), (140, 146, 160), (245, 245, 248), (20, 20, 24)
COL_KEY_ON, COL_KEY_UNMAPPED = (255, 190, 70), (90, 92, 100)
GRAPH_Y, GRAPH_H = 188, 128
NEON = (80, 255, 90)

class PlayingNote:
    def __init__(self, note, sound, channel, adsr, wave):
        self.note, self.sound, self.channel, self.wave = note, sound, channel, wave
        self.a = max(0.001, float(adsr["a"]))
        self.d = max(0.001, float(adsr["d"]))
        self.s = max(0.0, min(1.0, float(adsr["s"])))
        self.r = max(0.001, float(adsr["r"]))
        self.t = self.release_t = self.level = self.release_from = self.pos = 0.0
        self.released = self.done = False
        self._apply(0.0)
    def owns_channel(self):
        try:
            return self.channel is not None and self.channel.get_sound() is self.sound
        except Exception:
            return False
    def current_level(self):
        if not self.released:
            if self.t < self.a:
                return self.t / self.a
            if self.t < self.a + self.d:
                return 1.0 + (self.s - 1.0) * ((self.t - self.a) / self.d)
            return self.s
        u = self.release_t / self.r
        return 0.0 if u >= 1 else self.release_from * (1 - u)
    def _apply(self, vol):
        self.level = max(0.0, min(1.0, vol))
        if self.owns_channel():
            try:
                self.channel.set_volume(self.level)
            except Exception:
                pass
    def stop_now(self):
        self.done = True
        if self.owns_channel():
            try:
                self.channel.stop()
            except Exception:
                pass
        self.channel = None
    def update(self, dt):
        if self.done:
            return
        if not self.owns_channel():
            self.done = True
            self.channel = None
            return
        if not self.released:
            self.t += dt
        else:
            self.release_t += dt
        if self.wave is not None and len(self.wave):
            self.pos = (self.pos + dt * SAMPLE_RATE) % len(self.wave)
        vol = self.current_level()
        self._apply(vol)
        if self.released and vol <= 0.0005:
            self.stop_now()
    def note_off(self):
        if self.released or self.done:
            return
        self.release_from = max(0.0001, self.current_level())
        self.released = True
        self.release_t = 0.0

class Slider:
    def __init__(self, rect, vmin, vmax, value, label):
        self.rect = pygame.Rect(rect)
        self.vmin, self.vmax, self.value, self.label = vmin, vmax, value, label
        self.dragging = False
    def _set(self, x):
        t = max(0.0, min(1.0, (x - self.rect.x) / max(1, self.rect.w)))
        self.value = self.vmin + t * (self.vmax - self.vmin)
    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.inflate(0, 10).collidepoint(ev.pos):
            self.dragging = True
            self._set(ev.pos[0])
            return True
        if ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.dragging = False
        if ev.type == pygame.MOUSEMOTION and self.dragging:
            self._set(ev.pos[0])
            return True
        return False
    def draw(self, surf, font):
        pygame.draw.rect(surf, (20, 22, 30), self.rect, border_radius=3)
        t = (self.value - self.vmin) / max(1e-6, self.vmax - self.vmin)
        pygame.draw.rect(surf, (70, 120, 150), pygame.Rect(self.rect.x, self.rect.y, int(self.rect.w * t), self.rect.h), border_radius=3)
        pygame.draw.rect(surf, COL_ACCENT, self.rect, 1, border_radius=3)
        pygame.draw.circle(surf, COL_ORANGE, (self.rect.x + int(self.rect.w * t), self.rect.centery), 5)
        surf.blit(font.render(f"{self.label} {self.value:.3g}", True, COL_TEXT), (self.rect.x, self.rect.y - 14))

class Button:
    def __init__(self, rect, label, action=None):
        self.rect = pygame.Rect(rect)
        self.label, self.action, self.on, self.hot = label, action, False, False
    def draw(self, surf, font):
        col = (220, 120, 30) if self.hot else ((40, 130, 160) if self.on else (60, 90, 120))
        pygame.draw.rect(surf, col, self.rect, border_radius=6)
        pygame.draw.rect(surf, (255, 220, 80) if self.hot else COL_ACCENT, self.rect, 2 if self.hot else 1, border_radius=6)
        t = font.render(self.label, True, COL_TEXT)
        surf.blit(t, t.get_rect(center=self.rect.center))
    def click(self, pos):
        if self.rect.collidepoint(pos) and self.action:
            self.action()
            return True
        return False

class Dropdown:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.open = False
        self.scroll = 0
        self.row_h = 22
        self.max_rows = 18
        self._open_fp = None
        self.hi = 0

    def list_rect(self, n):
        h = min(self.max_rows, n) * self.row_h
        return pygame.Rect(self.rect.x, self.rect.bottom, self.rect.w, h)

    def handle(self, event, app):
        n = len(app.patches)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.open = not self.open
                if self.open:
                    self._open_fp = patch_fingerprint(app.patch)
                    self.hi = app.patch_index
                    self.scroll = max(0, min(self.hi - 4, max(0, n - self.max_rows)))
                else:
                    self.close(app)
                return True
            if self.open:
                lr = self.list_rect(n)
                if lr.collidepoint(event.pos):
                    idx = self.scroll + (event.pos[1] - lr.y) // self.row_h
                    if 0 <= idx < n:
                        app.select_loaded_patch(idx)
                    self.close(app)
                    return True
                self.close(app)
                return True
        if event.type == pygame.MOUSEWHEEL and self.open:
            self.scroll = max(0, min(max(0, n - self.max_rows), self.scroll - event.y * 2))
            return True
        if event.type == pygame.KEYDOWN and self.open:
            if event.key == pygame.K_UP:
                self.hi = max(0, self.hi - 1)
                if self.hi < self.scroll:
                    self.scroll = self.hi
                return True
            if event.key == pygame.K_DOWN:
                self.hi = min(n - 1, self.hi + 1)
                if self.hi >= self.scroll + self.max_rows:
                    self.scroll = self.hi - self.max_rows + 1
                return True
            if event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                if 0 <= self.hi < n:
                    app.select_loaded_patch(self.hi)
                self.close(app)
                return True
            if event.key == pygame.K_ESCAPE:
                self.close(app)
                return True
        return False

    def close(self, app):
        was = self.open
        self.open = False
        if was and patch_fingerprint(app.patch) != self._open_fp:
            app.mark_dirty()
        self._open_fp = None

    def draw(self, surf, font, small, app):
        pygame.draw.rect(surf, (40, 48, 64), self.rect, border_radius=6)
        pygame.draw.rect(surf, COL_ACCENT, self.rect, 1, border_radius=6)
        surf.blit(small.render(f"{app.patch_index+1:02d}  {app.patch['name']}"[:28], True, COL_TEXT),
                  (self.rect.x + 8, self.rect.y + 5))
        if not self.open:
            return
        n = len(app.patches)
        lr = self.list_rect(n)
        pygame.draw.rect(surf, (16, 18, 26), lr)
        pygame.draw.rect(surf, COL_ACCENT, lr, 1)
        if n > self.max_rows:
            bar_h = max(20, int(lr.h * self.max_rows / n))
            bar_y = lr.y + int((lr.h - bar_h) * self.scroll / max(1, n - self.max_rows))
            pygame.draw.rect(surf, COL_ORANGE, (lr.right - 6, bar_y, 4, bar_h), border_radius=2)
        for i in range(min(self.max_rows, n)):
            idx = self.scroll + i
            if idx >= n:
                break
            row = pygame.Rect(lr.x, lr.y + i * self.row_h, lr.w - 8, self.row_h)
            if idx == self.hi:
                pygame.draw.rect(surf, (70, 100, 140), row)
            elif idx == app.patch_index:
                pygame.draw.rect(surf, (50, 70, 90), row)
            surf.blit(small.render(f"{idx+1:02d}  {app.patches[idx]['name']}"[:32], True, COL_TEXT),
                      (row.x + 8, row.y + 3))

class FileBrowser:
    ROW = 22
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.mode = "export"
        self.dir = load_paths()["last_dir"]
        self.entries = []
        self.sel = 0
        self.scroll = 0
        self.name = ""
        self.cb = None
        self.filter = "*"
    def _refresh(self):
        self.dir = os.path.abspath(self.dir or EXPORT_DIR)
        if not os.path.isdir(self.dir):
            os.makedirs(self.dir, exist_ok=True)
        ents = [("..", True)]
        pat = self.filter or "*"
        try:
            for fn in sorted(os.listdir(self.dir), key=str.lower):
                if fn.startswith("."):
                    continue
                full = os.path.join(self.dir, fn)
                isdir = os.path.isdir(full)
                if isdir or fnmatch.fnmatch(fn.lower(), pat.lower()) or fn.lower().endswith((".json", ".zip", ".wav", ".mp3")):
                    if isdir or fnmatch.fnmatch(fn, pat) or "*" in pat or "?" in pat or fn.lower().endswith(".json"):
                        ents.append((fn, isdir))
        except Exception:
            pass
        self.entries = ents
        self.sel = 0
        self.scroll = 0
        paths = load_paths()
        key = "last_fx_dir" if "effect" in self.mode else "last_dir"
        paths[key] = self.dir
        save_paths(paths)
    def open(self, mode, default_name, cb, directory=None, filt="*"):
        self.mode = mode
        self.visible = True
        self.name = default_name
        self.cb = cb
        self.filter = filt or "*"
        paths = load_paths()
        self.dir = directory or (paths.get("last_fx_dir") if "effect" in mode else paths.get("last_dir")) or EXPORT_DIR
        os.makedirs(self.dir, exist_ok=True)
        self._refresh()
    def rect(self):
        w, h = self.app.screen.get_size()
        return pygame.Rect((w - 700) // 2, (h - 460) // 2, 700, 460)
    def list_rect(self):
        r = self.rect()
        return pygame.Rect(r.x + 16, r.y + 92, 668, 250)
    def handle(self, event):
        if not self.visible:
            return False
        n = len(self.entries)
        lr = self.list_rect()
        vis = max(1, lr.h // self.ROW)
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, min(max(0, n - vis), self.scroll - event.y))
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                return True
            if event.key == pygame.K_UP:
                self.sel = max(0, self.sel - 1)
            elif event.key == pygame.K_DOWN:
                self.sel = min(max(0, n - 1), self.sel + 1)
            elif event.key == pygame.K_RETURN:
                self._activate()
            elif event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
                if "import" in self.mode:
                    self.filter = self.name or "*"
                    self._refresh()
            elif event.unicode and event.unicode.isprintable() and len(self.name) < 64:
                self.name += event.unicode
                if "import" in self.mode:
                    self.filter = self.name or "*"
                    self._refresh()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            r = self.rect()
            if not r.collidepoint(event.pos):
                self.visible = False
                return True
            if pygame.Rect(r.x + 16, r.y + 56, 80, 24).collidepoint(event.pos):
                self.dir = os.path.dirname(self.dir)
                self._refresh()
                return True
            if lr.collidepoint(event.pos) and n:
                idx = self.scroll + (event.pos[1] - lr.y) // self.ROW
                if 0 <= idx < n:
                    self.sel = idx
                    fn, isdir = self.entries[idx]
                    if not isdir:
                        self.name = fn
            if pygame.Rect(r.x + 16, r.bottom - 48, 120, 30).collidepoint(event.pos):
                self._ok()
            elif pygame.Rect(r.x + 150, r.bottom - 48, 120, 30).collidepoint(event.pos):
                self.visible = False
            return True
        return True
    def _activate(self):
        if not self.entries:
            self._ok()
            return
        fn, isdir = self.entries[self.sel]
        if isdir:
            self.dir = os.path.abspath(os.path.join(self.dir, fn))
            self._refresh()
        else:
            self.name = fn
            self._ok()
    def _ok(self):
        if "import" in self.mode and self.entries:
            fn, isdir = self.entries[self.sel]
            if isdir:
                self._activate()
                return
            path = os.path.join(self.dir, fn)
        else:
            path = os.path.join(self.dir, self.name.strip() or "file")
        self.visible = False
        if self.cb:
            self.cb(path)
    def draw(self, surf, font, small):
        if not self.visible:
            return
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surf.blit(ov, (0, 0))
        r = self.rect()
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ORANGE, r, 2, border_radius=10)
        surf.blit(font.render(self.mode.upper(), True, COL_ORANGE), (r.x + 16, r.y + 12))
        surf.blit(small.render(self.dir, True, COL_DIM), (r.x + 16, r.y + 36))
        pygame.draw.rect(surf, (60, 90, 120), pygame.Rect(r.x + 16, r.y + 56, 80, 24), border_radius=4)
        surf.blit(small.render("Parent", True, COL_TEXT), (r.x + 28, r.y + 60))
        lr = self.list_rect()
        pygame.draw.rect(surf, (16, 18, 24), lr)
        vis = max(1, lr.h // self.ROW)
        for i in range(min(vis, max(0, len(self.entries) - self.scroll))):
            idx = self.scroll + i
            fn, isdir = self.entries[idx]
            row = pygame.Rect(lr.x, lr.y + i * self.ROW, lr.w, self.ROW)
            if idx == self.sel:
                pygame.draw.rect(surf, (50, 70, 90), row)
            surf.blit(small.render(("[DIR] " if isdir else "      ") + fn, True, COL_TEXT), (row.x + 8, row.y + 3))
        pygame.draw.rect(surf, (20, 22, 30), pygame.Rect(r.x + 16, r.bottom - 92, 668, 28), border_radius=4)
        surf.blit(small.render(self.name + "_", True, COL_TEXT), (r.x + 22, r.bottom - 86))
        pygame.draw.rect(surf, (40, 130, 80), pygame.Rect(r.x + 16, r.bottom - 48, 120, 30), border_radius=6)
        pygame.draw.rect(surf, (70, 70, 80), pygame.Rect(r.x + 150, r.bottom - 48, 120, 30), border_radius=6)
        surf.blit(small.render("OK", True, COL_TEXT), (r.x + 60, r.bottom - 40))
        surf.blit(small.render("Cancel", True, COL_TEXT), (r.x + 180, r.bottom - 40))

class ConfirmDialog:
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.title = ""
        self.hint = ""
        self.checked = True
        self.show_check = True
        self.ok_cb = None
    def open(self, title, cb, checked=True, hint="", show_check=True):
        self.visible = True
        self.title, self.ok_cb, self.checked, self.hint, self.show_check = title, cb, checked, hint, show_check
    def handle(self, event):
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.visible = False
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            w, h = self.app.screen.get_size()
            r = pygame.Rect((w - 520) // 2, (h - 220) // 2, 520, 220)
            if self.show_check and pygame.Rect(r.x + 24, r.y + 90, 18, 18).collidepoint(event.pos):
                self.checked = not self.checked
                return True
            if pygame.Rect(r.x + 24, r.bottom - 50, 140, 30).collidepoint(event.pos):
                cb, ch = self.ok_cb, self.checked
                self.visible = False
                if cb:
                    cb(ch)
            elif pygame.Rect(r.x + 180, r.bottom - 50, 140, 30).collidepoint(event.pos):
                self.visible = False
            return True
        return True
    def draw(self, surf, font, small):
        if not self.visible:
            return
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surf.blit(ov, (0, 0))
        w, h = surf.get_size()
        r = pygame.Rect((w - 520) // 2, (h - 220) // 2, 520, 220)
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ORANGE, r, 2, border_radius=10)
        surf.blit(font.render(self.title[:42], True, COL_ORANGE), (r.x + 20, r.y + 16))
        if self.hint:
            surf.blit(small.render(self.hint[:60], True, COL_TEXT), (r.x + 24, r.y + 56))
        if self.show_check:
            pygame.draw.rect(surf, (80, 200, 90) if self.checked else (50, 50, 60), pygame.Rect(r.x + 24, r.y + 90, 18, 18))
            surf.blit(small.render("Delete sample files for this patch", True, COL_TEXT), (r.x + 52, r.y + 90))
        pygame.draw.rect(surf, (160, 50, 40), pygame.Rect(r.x + 24, r.bottom - 50, 140, 30), border_radius=6)
        pygame.draw.rect(surf, (70, 70, 80), pygame.Rect(r.x + 180, r.bottom - 50, 140, 30), border_radius=6)
        surf.blit(small.render("OK", True, COL_TEXT), (r.x + 76, r.bottom - 42))
        surf.blit(small.render("Cancel", True, COL_TEXT), (r.x + 222, r.bottom - 42))

class ImportChoiceDialog:
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.name = ""
        self.source = ""
        self.pending = None
    def open(self, pending, suggested, source_name):
        self.visible = True
        self.pending = pending
        self.source = source_name or suggested
        existing = [p["name"] for p in self.app.patches]
        self.name = unique_patch_name(suggested, existing)
    def rect(self):
        w, h = self.app.screen.get_size()
        return pygame.Rect((w - 620) // 2, (h - 280) // 2, 620, 280)
    def handle(self, event):
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                return True
            if event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
                return True
            if event.unicode and event.unicode.isprintable() and len(self.name) < 24:
                self.name += event.unicode
                return True
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            r = self.rect()
            if pygame.Rect(r.x + 20, r.bottom - 56, 180, 32).collidepoint(event.pos):
                self.app.finish_import(self.pending, mode="replace", name=self.name or self.source)
                self.visible = False
            elif pygame.Rect(r.x + 220, r.bottom - 56, 200, 32).collidepoint(event.pos):
                existing = [p["name"] for p in self.app.patches]
                nm = (self.name or self.source).strip()
                if nm in existing:
                    nm = unique_patch_name(nm, existing)
                self.app.finish_import(self.pending, mode="new", name=nm)
                self.visible = False
            elif pygame.Rect(r.x + 440, r.bottom - 56, 140, 32).collidepoint(event.pos) or not r.collidepoint(event.pos):
                self.visible = False
            return True
        return True
    def draw(self, surf, font, small):
        if not self.visible:
            return
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surf.blit(ov, (0, 0))
        r = self.rect()
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ORANGE, r, 2, border_radius=10)
        surf.blit(font.render("IMPORT PATCH", True, COL_ORANGE), (r.x + 18, r.y + 14))
        pygame.draw.rect(surf, (20, 22, 30), pygame.Rect(r.x + 18, r.y + 100, 580, 30), border_radius=4)
        surf.blit(font.render((self.name or "") + "_", True, COL_TEXT), (r.x + 26, r.y + 104))
        for rect, lab, col in (
            (pygame.Rect(r.x + 20, r.bottom - 56, 180, 32), "Replace current", (140, 70, 40)),
            (pygame.Rect(r.x + 220, r.bottom - 56, 200, 32), "Save as new patch", (40, 130, 80)),
            (pygame.Rect(r.x + 440, r.bottom - 56, 140, 32), "Cancel", (60, 70, 80)),
        ):
            pygame.draw.rect(surf, col, rect, border_radius=6)
            surf.blit(small.render(lab, True, COL_TEXT), (rect.x + 18, rect.y + 8))

class PatchDialog:
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.mode = "edit"
        self.name = ""
    def open(self, mode="edit"):
        self.app.capture_patch_state()
        self.visible = True
        self.mode = mode
        self.name = self.app.patch["name"]
    def handle(self, event):
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                return True
            if event.key == pygame.K_RETURN:
                self.app.patch["name"] = self.name or self.app.patch["name"]
                self.app.capture_patch_state()
                if self.mode == "create":
                    self.app.patches.insert(0, deepcopy(self.app.patch))
                    self.app.patch_index = 0
                    self.app.save_bank()
                    self.app.mark_dirty()
                else:
                    self.app.patches[self.app.patch_index] = deepcopy(self.app.patch)
                    self.app.save_bank()
                self.visible = False
                return True
            if event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.name) < 16:
                self.name += event.unicode
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.visible = False
            return True
        return True
    def draw(self, surf, font, small):
        if not self.visible:
            return
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surf.blit(ov, (0, 0))
        w, h = surf.get_size()
        r = pygame.Rect((w - 520) // 2, (h - 220) // 2, 520, 220)
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ACCENT, r, 2, border_radius=10)
        surf.blit(font.render(self.mode.upper(), True, COL_ORANGE), (r.x + 20, r.y + 16))
        pygame.draw.rect(surf, (20, 22, 30), pygame.Rect(r.x + 20, r.y + 70, 360, 28), border_radius=4)
        surf.blit(font.render(self.name + "_", True, COL_TEXT), (r.x + 28, r.y + 74))

class CaptureWizard:
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.last = None
    def open(self):
        self.visible = True
        self.last = None
    def handle(self, event):
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible = False
                return True
            tok = event_key_token(event)
            note = self.app.keymap.get(tok)
            if note is not None:
                self.last = note
                self.app.note_on(note)
            return True
        if event.type == pygame.KEYUP:
            tok = event_key_token(event)
            note = self.app.keymap.get(tok)
            if note is not None:
                self.app.note_off(note)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            w, h = self.app.screen.get_size()
            r = pygame.Rect((w - 560) // 2, (h - 260) // 2, 560, 260)
            if pygame.Rect(r.x + 20, r.bottom - 50, 160, 30).collidepoint(event.pos) and self.last is not None:
                self.app.capture_current_note(self.last)
            elif pygame.Rect(r.x + 200, r.bottom - 50, 160, 30).collidepoint(event.pos):
                self.app.rebuild_interpolated()
            elif pygame.Rect(r.x + 380, r.bottom - 50, 140, 30).collidepoint(event.pos) or not r.collidepoint(event.pos):
                self.visible = False
            return True
        return True
    def draw(self, surf, font, small):
        if not self.visible:
            return
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surf.blit(ov, (0, 0))
        w, h = surf.get_size()
        r = pygame.Rect((w - 560) // 2, (h - 260) // 2, 560, 260)
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ORANGE, r, 2, border_radius=10)
        surf.blit(font.render("SAMPLE CAPTURE WIZARD", True, COL_ORANGE), (r.x + 16, r.y + 14))
        for rect, lab in (
            (pygame.Rect(r.x + 20, r.bottom - 50, 160, 30), "Capture note"),
            (pygame.Rect(r.x + 200, r.bottom - 50, 160, 30), "Rebuild others"),
            (pygame.Rect(r.x + 380, r.bottom - 50, 140, 30), "Close"),
        ):
            pygame.draw.rect(surf, (60, 90, 120), rect, border_radius=6)
            surf.blit(small.render(lab, True, COL_TEXT), (rect.x + 16, rect.y + 8))

class EffectsDialog:
    ROW = 22
    KNOBS_VIS = 6
    def __init__(self, app):
        self.app = app
        self.visible = False
        self.sel = 0
        self.scroll = 0
        self.pscr = 0
        self.search = ""
        self.search_focus = False
        self.sliders = []
        self.focus = "catalog"
        self.merge_open = False
        self.last_click = {"where": None, "idx": None, "t": 0.0}
        self.drafts = {}
        self.snap = None
        self.dirty = False
    def snapshot(self):
        return json.dumps({"chain": self.app.fx_chain, "clip": self.app.clip_mode, "post": self.app.post_fx}, sort_keys=True)
    def open(self):
        self.visible = True
        self.search = ""
        self.scroll = 0
        self.pscr = 0
        self.focus = "catalog"
        self.merge_open = False
        self.app.fx_chain = normalize_chain(self.app.fx_chain)
        self.drafts = {}
        self.snap = self.snapshot()
        self.dirty = False
        if self.sel >= len(EFFECT_DEFS):
            self.sel = 0
        self.ensure_draft(EFFECT_DEFS[self.sel]["id"])
        self._rebuild()
    def close(self):
        self.visible = False
        self.app.clear_preview_notes()
    def ensure_draft(self, eid):
        if eid not in self.drafts:
            self.drafts[eid] = default_instance(eid)
        return self.drafts[eid]
    def ordered_ids(self):
        q = self.search.strip().lower()
        ids = list(range(len(EFFECT_DEFS)))
        ids.sort(key=lambda i: EFFECT_DEFS[i]["name"].lower())
        if q:
            ids = [i for i in ids if q in EFFECT_DEFS[i]["name"].lower() or q in EFFECT_DEFS[i]["id"].lower()]
        return ids
    def display_effect(self):
        if self.focus == "chain":
            inst = self.current_instance()
            if inst:
                return FX_INDEX.get(inst.get("base"), EFFECT_DEFS[self.sel])
        return EFFECT_DEFS[self.sel]
    def display_state(self):
        if self.focus == "chain":
            inst = self.current_instance()
            if inst:
                return inst
        return self.ensure_draft(EFFECT_DEFS[self.sel]["id"])
    def current_instance(self):
        self.app.fx_chain = normalize_chain(self.app.fx_chain)
        if self.app.fx_sel_inst is None or not (0 <= self.app.fx_sel_inst < len(self.app.fx_chain)):
            return None
        inst = self.app.fx_chain[self.app.fx_sel_inst]
        return inst if isinstance(inst, dict) else None
    def pedal_h(self):
        e = self.display_effect()
        rows = max(2, (min(self.KNOBS_VIS, len(e["params"])) + 2) // 3)
        sw_rows = max(1, (len(e["switches"]) + 2) // 3)
        return 70 + rows * 52 + sw_rows * 36
    def slider_origin(self):
        box = self.pedal_rect()
        return box.x, box.bottom + 36
    def pedal_rect(self):
        r = self.rect()
        return pygame.Rect(r.x + 510, r.y + 44, 460, self.pedal_h())
    def rect(self):
        w, h = self.app.screen.get_size()
        return pygame.Rect(16, 16, min(1180, w - 32), min(700, h - 32))
    def list_rect(self):
        r = self.rect()
        return pygame.Rect(r.x + 8, r.y + 100, 250, r.h - 160)
    def chain_rect(self):
        r = self.rect()
        return pygame.Rect(r.x + 268, r.y + 44, 220, r.h - 160)
    def search_rect(self):
        r = self.rect()
        return pygame.Rect(r.x + 8, r.y + 44, 250, 24)
    def merge_drop_rect(self):
        x, y = self.slider_origin()
        return pygame.Rect(x, y + 220, 280, 24)
    def chain_btns(self):
        r = self.rect()
        y = r.bottom - 44
        return {
            "rm": pygame.Rect(r.x + 268, y, 70, 24),
            "rmall": pygame.Rect(r.x + 342, y, 70, 24),
            "up": pygame.Rect(r.x + 416, y, 36, 24),
            "dn": pygame.Rect(r.x + 456, y, 36, 24),
        }
    def _rebuild(self):
        e = self.display_effect()
        st = self.display_state()
        self.pscr = max(0, min(self.pscr, max(0, len(e["params"]) - self.KNOBS_VIS)))
        sx, sy = self.slider_origin()
        self.sliders = []
        for i, (nm, d, lo, hi) in enumerate(e["params"]):
            if self.pscr <= i < self.pscr + self.KNOBS_VIS:
                val = float(st.get("params", {}).get(nm, d))
                self.sliders.append(Slider((sx, sy + (i - self.pscr) * 34, 360, 11), lo, hi, val, nm))
    def _write(self):
        st = self.display_state()
        for sl in self.sliders:
            st.setdefault("params", {})[sl.label] = sl.value
        self.dirty = True
    def move_sel(self, delta):
        ids = self.ordered_ids()
        if not ids:
            return
        if self.sel not in ids:
            self.sel = ids[0]
        else:
            self.sel = ids[max(0, min(len(ids) - 1, ids.index(self.sel) + delta))]
        self.ensure_draft(EFFECT_DEFS[self.sel]["id"])
        self._rebuild()
    def move_chain_sel(self, delta):
        n = len(self.app.fx_chain)
        if n <= 0:
            return
        cur = self.app.fx_sel_inst if self.app.fx_sel_inst is not None else 0
        self.app.fx_sel_inst = max(0, min(n - 1, cur + delta))
        inst = self.app.fx_chain[self.app.fx_sel_inst]
        for i, e in enumerate(EFFECT_DEFS):
            if e["id"] == inst.get("base"):
                self.sel = i
                break
        self._rebuild()
    def _double(self, where, idx):
        now = time.perf_counter()
        hit = self.last_click["where"] == where and self.last_click["idx"] == idx and (now - self.last_click["t"]) < 0.35
        self.last_click = {"where": where, "idx": idx, "t": now}
        return hit
    def try_close_cancel(self):
        if self.dirty or self.snapshot() != self.snap:
            self.app.confirmdlg.open("Discard effect changes?", lambda *_: self._cancel(),
                                     show_check=False, hint="Unsaved chain edits will be lost.")
        else:
            self._cancel()
    def _cancel(self, *_):
        if self.snap:
            data = json.loads(self.snap)
            self.app.fx_chain = normalize_chain(data.get("chain"))
            self.app.clip_mode = data.get("clip", "none")
            self.app.post_fx = data.get("post", dict(DEFAULT_POST))
        self.close()
    def save_and_close(self):
        self.app.save_tone_json()
        self.app.save_bank()
        self.dirty = False
        self.snap = self.snapshot()
        self.close()
        self.app.status = "Effects saved"
    def handle(self, event):
        if not self.visible:
            return False
        self.app.fx_chain = normalize_chain(self.app.fx_chain)
        ids = self.ordered_ids()
        lr = self.list_rect()
        vis = max(1, lr.h // self.ROW)
        if event.type == pygame.KEYDOWN:
            if self.search_focus:
                if event.key == pygame.K_ESCAPE:
                    self.search_focus = False
                    return True
                if event.key == pygame.K_BACKSPACE:
                    self.search = self.search[:-1]
                    return True
                if event.unicode and event.unicode.isprintable() and len(self.search) < 24:
                    self.search += event.unicode
                    return True
                return True
            if event.key == pygame.K_ESCAPE:
                self.try_close_cancel()
                return True
            if event.key in (pygame.K_UP, pygame.K_DOWN):
                step = -1 if event.key == pygame.K_UP else 1
                if self.focus == "chain":
                    self.move_chain_sel(step)
                else:
                    self.move_sel(step)
                return True
            return False
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if lr.collidepoint((mx, my)):
                self.scroll = max(0, min(max(0, len(ids) - vis), self.scroll - event.y))
                return True
            if self.pedal_rect().collidepoint((mx, my)):
                self.pscr = max(0, min(max(0, len(self.display_effect()["params"]) - self.KNOBS_VIS), self.pscr - event.y))
                self._rebuild()
                return True
            return True
        if any(sl.handle(event) for sl in self.sliders):
            self._write()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            r = self.rect()
            if not r.collidepoint(event.pos):
                return True
            if self.search_rect().collidepoint(event.pos):
                self.search_focus = True
                return True
            self.search_focus = False
            boxes = {
                "all": pygame.Rect(r.x + 8, r.y + 72, 16, 16),
                "rand": pygame.Rect(r.x + 130, r.y + 72, 16, 16),
                "p48": pygame.Rect(r.right - 430, r.y + 10, 70, 22),
                "test": pygame.Rect(r.right - 350, r.y + 10, 80, 22),
                "rev": pygame.Rect(r.right - 260, r.y + 10, 70, 22),
                "exp": pygame.Rect(r.right - 180, r.y + 10, 70, 22),
                "imp": pygame.Rect(r.right - 100, r.y + 10, 70, 22),
                "save": pygame.Rect(r.right - 250, r.bottom - 40, 90, 26),
                "cancel": pygame.Rect(r.right - 150, r.bottom - 40, 90, 26),
                "gen": pygame.Rect(r.right - 360, r.bottom - 40, 100, 26),
            }
            if boxes["all"].collidepoint(event.pos):
                self.app.select_all_effects(); self.dirty = True; return True
            if boxes["rand"].collidepoint(event.pos):
                self.app.randomize_effects(); self.dirty = True; return True
            if boxes["p48"].collidepoint(event.pos):
                self.app.quick_preview(48); return True
            if boxes["test"].collidepoint(event.pos):
                self.app.test_gen_previews(); return True
            if boxes["rev"].collidepoint(event.pos):
                self.app.revert_previews(); return True
            if boxes["exp"].collidepoint(event.pos):
                self.app.export_fx_chain(); return True
            if boxes["imp"].collidepoint(event.pos):
                self.app.import_fx_chain(); return True
            if boxes["save"].collidepoint(event.pos):
                self.save_and_close(); return True
            if boxes["cancel"].collidepoint(event.pos):
                self.try_close_cancel(); return True
            if boxes["gen"].collidepoint(event.pos):
                self._write(); self.app.generate_samples(apply_fx=True); return True
            bt = self.chain_btns()
            if bt["rm"].collidepoint(event.pos):
                self.app.remove_selected_effect(); self.dirty = True; return True
            if bt["rmall"].collidepoint(event.pos):
                self.app.ask_clear_effects(); return True
            if bt["up"].collidepoint(event.pos):
                self.app.move_effect(-1); self.dirty = True; self._rebuild(); return True
            if bt["dn"].collidepoint(event.pos):
                self.app.move_effect(1); self.dirty = True; self._rebuild(); return True
            for i, mode in enumerate(("none", "hard", "tube", "soft")):
                b = pygame.Rect(r.x + 8 + i * 62, r.bottom - 44, 58, 20)
                if b.collidepoint(event.pos):
                    self.app.clip_mode = mode
                    self.dirty = True
                    return True
            if lr.collidepoint(event.pos):
                self.focus = "catalog"
                visn = min(vis, max(0, len(ids) - self.scroll))
                for i in range(visn):
                    gi = ids[self.scroll + i]
                    row = pygame.Rect(lr.x, lr.y + i * self.ROW, lr.w, self.ROW)
                    if row.collidepoint(event.pos):
                        self.sel = gi
                        self.ensure_draft(EFFECT_DEFS[gi]["id"])
                        if self._double("catalog", gi):
                            self.app.add_effect_instance(EFFECT_DEFS[gi]["id"], draft=self.drafts.get(EFFECT_DEFS[gi]["id"]))
                            self.dirty = True
                        self._rebuild()
                        return True
                return True
            cr = self.chain_rect()
            if cr.collidepoint(event.pos):
                self.focus = "chain"
                idx = (event.pos[1] - cr.y - 22) // self.ROW
                if 0 <= idx < len(self.app.fx_chain):
                    box = pygame.Rect(cr.x + 4, cr.y + 24 + idx * self.ROW, 14, 14)
                    if box.collidepoint(event.pos):
                        self.app.fx_chain[idx]["on"] = not self.app.fx_chain[idx].get("on", True)
                        self.dirty = True
                        return True
                    self.app.fx_sel_inst = idx
                    base = self.app.fx_chain[idx].get("base")
                    for i, e in enumerate(EFFECT_DEFS):
                        if e["id"] == base:
                            self.sel = i
                            break
                    if self._double("chain", idx):
                        self.app.remove_selected_effect()
                        self.dirty = True
                    self._rebuild()
                return True
            e = self.display_effect()
            st = self.display_state()
            box = self.pedal_rect()
            knobs = e["params"][self.pscr:self.pscr + self.KNOBS_VIS]
            sw_y = box.y + 62 + ((len(knobs) + 2) // 3) * 52
            for i, sw in enumerate(e["switches"]):
                b = pygame.Rect(box.x + 10 + (i % 3) * 148, sw_y + (i // 3) * 32, 130, 22)
                if b.collidepoint(event.pos):
                    st.setdefault("switches", {})[sw[0]] = not st["switches"].get(sw[0], sw[1])
                    self.dirty = True
                    return True
            if any(s[0] == "attack_boost" for s in e["switches"]):
                cb = pygame.Rect(self.slider_origin()[0], self.slider_origin()[1] - 22, 16, 16)
                if cb.collidepoint(event.pos):
                    st.setdefault("switches", {})["attack_boost"] = not st["switches"].get("attack_boost", False)
                    self.dirty = True
                    return True
            if e["id"] == "merge":
                md = self.merge_drop_rect()
                if md.collidepoint(event.pos):
                    self.merge_open = not self.merge_open
                    return True
                if self.merge_open:
                    for i, p in enumerate(self.app.patches):
                        row = pygame.Rect(md.x, md.bottom + i * 18, md.w, 18)
                        if row.collidepoint(event.pos):
                            st["merge_patch"] = p["name"]
                            self.merge_open = False
                            self.dirty = True
                            return True
        return True
    def draw(self, surf, font, small):
        if not self.visible:
            return
        self.app.fx_chain = normalize_chain(self.app.fx_chain)
        ov = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 175))
        surf.blit(ov, (0, 0))
        r = self.rect()
        pygame.draw.rect(surf, COL_PANEL, r, border_radius=10)
        pygame.draw.rect(surf, COL_ACCENT, r, 2, border_radius=10)
        surf.blit(font.render("EFFECTS", True, COL_ORANGE), (r.x + 12, r.y + 8))
        pygame.draw.rect(surf, (80, 200, 90), pygame.Rect(r.x + 8, r.y + 72, 16, 16))
        surf.blit(small.render("Select All", True, COL_TEXT), (r.x + 28, r.y + 72))
        pygame.draw.rect(surf, (200, 160, 40), pygame.Rect(r.x + 130, r.y + 72, 16, 16))
        surf.blit(small.render("Randomize", True, COL_TEXT), (r.x + 150, r.y + 72))
        for lab, x in (("Q48", r.right - 430), ("TestGen", r.right - 350), ("Revert", r.right - 260),
                       ("ExpFX", r.right - 180), ("ImpFX", r.right - 100)):
            pygame.draw.rect(surf, (60, 90, 120), pygame.Rect(x, r.y + 10, 70 if lab != "TestGen" else 80, 22), border_radius=4)
            surf.blit(small.render(lab, True, COL_TEXT), (x + 8, r.y + 14))
        sr = self.search_rect()
        pygame.draw.rect(surf, (16, 18, 24), sr, border_radius=4)
        surf.blit(small.render((self.search or "search")[:28], True, COL_TEXT if self.search else COL_DIM), (sr.x + 6, sr.y + 4))
        lr = self.list_rect()
        pygame.draw.rect(surf, (16, 18, 24), lr)
        if self.focus == "catalog":
            pygame.draw.rect(surf, COL_ORANGE, lr, 2)
        ids = self.ordered_ids()
        vis = max(1, lr.h // self.ROW)
        self.scroll = min(self.scroll, max(0, len(ids) - vis))
        for i in range(min(vis, max(0, len(ids) - self.scroll))):
            gi = ids[self.scroll + i]
            row = pygame.Rect(lr.x, lr.y + i * self.ROW, lr.w, self.ROW)
            if gi == self.sel:
                pygame.draw.rect(surf, (50, 70, 90), row)
            surf.blit(small.render(EFFECT_DEFS[gi]["name"][:26], True, COL_TEXT), (row.x + 6, row.y + 3))
        cr = self.chain_rect()
        pygame.draw.rect(surf, (16, 18, 24), cr)
        if self.focus == "chain":
            pygame.draw.rect(surf, COL_ORANGE, cr, 2)
        surf.blit(small.render("DX7 output", True, COL_ORANGE), (cr.x + 6, cr.y + 4))
        counts = {}
        for i, inst in enumerate(self.app.fx_chain):
            if not isinstance(inst, dict):
                continue
            base = inst.get("base", "?")
            counts[base] = counts.get(base, 0) + 1
            row = pygame.Rect(cr.x, cr.y + 22 + i * self.ROW, cr.w, self.ROW)
            if i == self.app.fx_sel_inst:
                pygame.draw.rect(surf, (50, 70, 90), row)
            on = inst.get("on", True)
            pygame.draw.rect(surf, (80, 200, 90) if on else (60, 60, 70), pygame.Rect(row.x + 4, row.y + 4, 14, 14))
            surf.blit(small.render(instance_label(inst, counts)[:20], True, COL_TEXT), (row.x + 22, row.y + 3))
        bt = self.chain_btns()
        for key, lab in (("rm", "Remove"), ("rmall", "Clr all"), ("up", "Up"), ("dn", "Dn")):
            pygame.draw.rect(surf, (70, 80, 100), bt[key], border_radius=4)
            surf.blit(small.render(lab, True, COL_TEXT), (bt[key].x + 4, bt[key].y + 4))
        e = self.display_effect()
        st = self.display_state()
        box = self.pedal_rect()
        pygame.draw.rect(surf, e["color"], box, border_radius=12)
        ink, _, _ = pedal_ink(e["color"])
        fill, needle, ring = knob_style(e["color"])
        surf.blit(self.app.tiny.render(e["name"][:32], True, ink), (box.x + 8, box.y + 4))
        if e["id"] == "merge" and st.get("merge_patch"):
            ital = pygame.font.SysFont("consolas", 16, italic=True) or self.app.small
            surf.blit(ital.render(st["merge_patch"], True, NEON), (box.x + 10, box.y + 20))
        visp = e["params"][self.pscr:self.pscr + self.KNOBS_VIS]
        for i, (nm, d, lo, hi) in enumerate(visp):
            cx = box.x + 56 + (i % 3) * 148
            cy = box.y + 58 + (i // 3) * 52
            val = float(st.get("params", {}).get(nm, d))
            t = 0.0 if hi == lo else max(0.0, min(1.0, (val - lo) / (hi - lo)))
            ang = math.pi * 0.75 + t * math.pi * 1.5
            pygame.draw.circle(surf, fill, (cx, cy), 14)
            pygame.draw.circle(surf, ring, (cx, cy), 14, 2)
            pygame.draw.line(surf, needle, (cx, cy), (cx + int(math.cos(ang) * 9), cy + int(math.sin(ang) * 9)), 2)
            surf.blit(self.app.tiny.render(short_knob(nm), True, ink), (cx - 16, cy + 16))
        sw_y = box.y + 62 + ((len(visp) + 2) // 3) * 52
        for i, sw in enumerate(e["switches"]):
            on = bool(st.get("switches", {}).get(sw[0], sw[1]))
            b = pygame.Rect(box.x + 10 + (i % 3) * 148, sw_y + (i // 3) * 32, 130, 22)
            pygame.draw.rect(surf, (40, 40, 48), b, border_radius=8)
            knob = pygame.Rect(b.x + (70 if on else 6), b.y + 3, 50, 16)
            pygame.draw.rect(surf, (80, 220, 90) if on else (160, 160, 170), knob, border_radius=8)
            surf.blit(self.app.tiny.render(short_knob(sw[0]), True, ink), (b.x + 4, b.y - 12))
        sx, sy = self.slider_origin()
        if any(s[0] == "attack_boost" for s in e["switches"]):
            pygame.draw.rect(surf, (80, 200, 90) if st.get("switches", {}).get("attack_boost") else (50, 50, 60),
                             pygame.Rect(sx, sy - 22, 16, 16))
            surf.blit(small.render("Attack boost", True, COL_TEXT), (sx + 22, sy - 22))
        for sl in self.sliders:
            sl.draw(surf, small)
        if e["id"] == "merge":
            md = self.merge_drop_rect()
            pygame.draw.rect(surf, (20, 22, 30), md, border_radius=4)
            pygame.draw.rect(surf, COL_ACCENT, md, 1, border_radius=4)
            lab = st.get("merge_patch") or "Select merge patch"
            surf.blit(small.render(lab[:28], True, NEON if st.get("merge_patch") else COL_DIM), (md.x + 6, md.y + 4))
            if self.merge_open:
                panel = pygame.Rect(md.x, md.bottom, md.w, min(180, 18 * len(self.app.patches)))
                pygame.draw.rect(surf, (16, 18, 24), panel)
                for i, p in enumerate(self.app.patches[:10]):
                    surf.blit(small.render(p["name"], True, COL_TEXT), (panel.x + 6, panel.y + i * 18 + 2))
        for i, mode in enumerate(("none", "hard", "tube", "soft")):
            b = pygame.Rect(r.x + 8 + i * 62, r.bottom - 44, 58, 20)
            pygame.draw.rect(surf, (40, 130, 80) if self.app.clip_mode == mode else (50, 60, 70), b, border_radius=4)
            surf.blit(small.render(mode, True, COL_TEXT), (b.x + 6, b.y + 3))
        pygame.draw.rect(surf, (40, 130, 80), pygame.Rect(r.right - 360, r.bottom - 40, 100, 26), border_radius=6)
        pygame.draw.rect(surf, (40, 130, 80), pygame.Rect(r.right - 250, r.bottom - 40, 90, 26), border_radius=6)
        pygame.draw.rect(surf, (120, 60, 50), pygame.Rect(r.right - 150, r.bottom - 40, 90, 26), border_radius=6)
        surf.blit(small.render("GENERATE", True, COL_TEXT), (r.right - 342, r.bottom - 34))
        surf.blit(small.render("SAVE", True, COL_TEXT), (r.right - 222, r.bottom - 34))
        surf.blit(small.render("CANCEL", True, COL_TEXT), (r.right - 132, r.bottom - 34))

class App:
    def __init__(self):
        ensure_export_dir()
        self.geom = load_geom()
        pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{self.geom.get('x', 80)},{self.geom.get('y', 80)}"
        pygame.init()
        if not pygame.mixer.get_init():
            pygame.mixer.init(SAMPLE_RATE, -16, 1, 512)
        pygame.mixer.set_num_channels(MAX_POLY)
        pygame.display.set_caption("DX7-style FM")
        self.screen = pygame.display.set_mode((self.geom["w"], self.geom["h"]), pygame.RESIZABLE)
        self.font = pygame.font.SysFont("consolas", 18) or pygame.font.Font(None, 22)
        self.small = pygame.font.SysFont("consolas", 14) or pygame.font.Font(None, 18)
        self.tiny = pygame.font.SysFont("consolas", 12) or pygame.font.Font(None, 16)
        self.clock = pygame.time.Clock()
        self.keymap, self.keymap_src = load_keymap()
        self.midi_notes = sorted(set(self.keymap.values()))
        self.mapped = set(self.midi_notes)
        self.key_by_note = {}
        for k, n in self.keymap.items():
            self.key_by_note.setdefault(n, k)
        self.held_keys, self.held_midi = {}, set()
        self.playing, self.voice_order = {}, []
        self.patches = load_bank()
        self.patch_index = 0
        self.patch = deepcopy(self.patches[0])
        self.fx_chain = []
        self.fx_sel_inst = None
        self.clip_mode = "none"
        self.post_fx = dict(DEFAULT_POST)
        self.sel_op = 0
        self.sounds, self.waves, self.base_waves = {}, {}, {}
        self.preview_sounds, self.preview_waves = {}, {}
        self.full_backup = {}
        self.status = "Ready"
        self.dirty = False
        self.use_threads = True
        self.max_threads = 2
        self.thread_text = "2"
        self.thread_edit = False
        self.last_gen_time = "00:00:00.000"
        self.exp_mp3 = True
        self.no_loop = False
        self.scope = np.zeros(512, np.float32)
        self.scope_freeze = False
        self.scope_lock = False
        a = self.patch["adsr"]
        self.sliders = [
            Slider((40, 348, 150, 11), 0.001, 2.0, a["a"], "A"),
            Slider((200, 348, 150, 11), 0.001, 2.0, a["d"], "D"),
            Slider((360, 348, 150, 11), 0.0, 1.0, a["s"], "S"),
            Slider((520, 348, 150, 11), 0.001, 3.0, a["r"], "R"),
        ]
        self.op_sliders = []
        self.rebuild_op_sliders()
        self.midi_in = None
        self.midi_id = -1
        self.midi_name = "Off"
        self.midi_devs = []
        self.dialog = PatchDialog(self)
        self.fxdlg = EffectsDialog(self)
        self.importdlg = ImportChoiceDialog(self)
        self.filedlg = FileBrowser(self)
        self.confirmdlg = ConfirmDialog(self)
        self.wizard = CaptureWizard(self)
        self.dropdown = Dropdown((20, 50, 220, 26))
        self.gen_btn = None
        self.op_buttons = []
        self.thread_box = pygame.Rect(890, 48, 16, 16)
        self.thread_edit_rect = pygame.Rect(980, 44, 50, 22)
        self.mp3_box = pygame.Rect(890, 72, 16, 16)
        self.noloop_box = pygame.Rect(890, 96, 16, 16)
        self._layout_buttons()
        os.makedirs(TONES_DIR, exist_ok=True)
        self.load_tone_json()
        self.load_or_build_tones(force=False, apply_fx=bool(self.fx_chain))

    def generate_all(self, no_loop=False):
        print(f"Generating all {len(self.patches)} patches (overwrite) no_loop={no_loop}...")
        t_start = time.perf_counter()
        old = self.no_loop
        self.no_loop = no_loop
        for i, p in enumerate(self.patches):
            print(f"[{i+1}/{len(self.patches)}] {p.get('name', '?')}")
            self.patch_index = i
            self.patch = ensure_adsr(deepcopy(p))
            self.fx_chain = []
            self.load_or_build_tones(force=True, apply_fx=False)
        self.no_loop = old
        print(f"Done. Total time: {format_gen_time(time.perf_counter() - t_start)}")
        pygame.quit()

    def apply_thread_text(self):
        try:
            self.max_threads = max(1, min(88, int(self.thread_text or "2")))
        except ValueError:
            self.max_threads = 2
        self.thread_text = str(self.max_threads)
        self.thread_edit = False
    def rebuild_op_sliders(self):
        op = self.patch["ops"][self.sel_op]
        x0, y, w, gap = 40, 376, 150, 16
        self.op_sliders = [
            Slider((x0 + 0 * (w + gap), y, w, 11), 0, 99, op["level"], "LVL"),
            Slider((x0 + 1 * (w + gap), y, w, 11), 0, 31, op["coarse"], "CRS"),
            Slider((x0 + 2 * (w + gap), y, w, 11), 0, 99, op.get("fine", 0), "FINE"),
            Slider((x0 + 3 * (w + gap), y, w, 11), -7, 7, op.get("detune", 0), "DET"),
        ]
        for i in range(4):
            self.op_sliders.append(Slider((x0 + i * (w + gap), y + 32, w, 11), 0, 99, op["rates"][i], f"R{i+1}"))
        for i in range(4):
            self.op_sliders.append(Slider((x0 + i * (w + gap), y + 64, w, 11), 0, 99, op["levels"][i], f"L{i+1}"))
    def apply_op_sliders(self):
        op = self.patch["ops"][self.sel_op]
        op["level"] = int(round(self.op_sliders[0].value))
        op["coarse"] = int(round(self.op_sliders[1].value))
        op["fine"] = int(round(self.op_sliders[2].value))
        op["detune"] = int(round(self.op_sliders[3].value))
        op["rates"] = [int(round(self.op_sliders[4 + i].value)) for i in range(4)]
        op["levels"] = [int(round(self.op_sliders[8 + i].value)) for i in range(4)]
        self.mark_dirty()
    def graph_rects(self):
        w, _ = self.screen.get_size()
        gap, x0 = 16, 20
        usable = max(600, w - 40)
        gw = (usable - 2 * gap) // 3
        return (pygame.Rect(x0, GRAPH_Y, gw, GRAPH_H), pygame.Rect(x0 + gw + gap, GRAPH_Y, gw, GRAPH_H),
                pygame.Rect(x0 + 2 * (gw + gap), GRAPH_Y, gw, GRAPH_H))
    def _layout_buttons(self):
        self.gen_btn = Button((770, 16, 110, 28), "GENERATE", lambda: self.generate_samples(apply_fx=bool(self.fx_chain)))
        self.buttons = [
            Button((20, 16, 70, 28), "CREATE", lambda: self.dialog.open("create")),
            Button((94, 16, 60, 28), "EDIT", self.open_edit),
            Button((158, 16, 70, 28), "DELETE", self.ask_delete_patch),
            Button((232, 16, 118, 28), "MIDI CONNECT", self.cycle_midi),
            Button((354, 16, 80, 28), "EFFECTS", self.fxdlg.open),
            Button((438, 16, 70, 28), "EXPORT", self.export_patch),
            Button((512, 16, 70, 28), "IMPORT", self.import_patch_ask),
            Button((586, 16, 80, 28), "ExpWav", self.export_wav_zip),
            Button((670, 16, 90, 28), "SAMPATCH", self.make_sample_patch),
            self.gen_btn,
            Button((250, 50, 50, 26), "ALG-", lambda: self.chg_algo(-1)),
            Button((304, 50, 50, 26), "ALG+", lambda: self.chg_algo(1)),
            Button((360, 50, 50, 26), "FB-", lambda: self.chg_fb(-1)),
            Button((414, 50, 50, 26), "FB+", lambda: self.chg_fb(1)),
            Button((470, 50, 70, 26), "ADD OP", self.add_op),
            Button((544, 50, 70, 26), "OP ON", self.toggle_op),
            Button((618, 50, 80, 26), "CAPTURE", self.wizard.open),
        ]
        self.refresh_op_buttons()
    def refresh_op_buttons(self):
        n = max(6, min(MAX_OPS, len(self.patch.get("ops", []))))
        self.op_buttons = []
        x, y = 20, 84
        for i in range(n):
            if i == 6:
                x, y = 20, 108
            self.op_buttons.append(Button((x, y, 50, 22), f"OP{i+1}", action=lambda i=i: self.select_op(i)))
            x += 54
    def select_op(self, i):
        if i < len(self.patch["ops"]):
            self.sel_op = i
            self.rebuild_op_sliders()
    def add_op(self):
        if len(self.patch["ops"]) >= MAX_OPS:
            return
        self.patch["ops"].append(default_op(80, 1, 0))
        self.sel_op = len(self.patch["ops"]) - 1
        self.refresh_op_buttons()
        self.rebuild_op_sliders()
        self.mark_dirty()
    def toggle_op(self):
        op = self.patch["ops"][self.sel_op]
        op["on"] = not op.get("on", True)
        self.mark_dirty()
    def mark_dirty(self):
        self.dirty = True
        if self.gen_btn:
            self.gen_btn.hot = True
    def add_effect_instance(self, eid, draft=None):
        self.fx_chain = normalize_chain(self.fx_chain)
        inst = deepcopy(draft) if draft else default_instance(eid)
        inst["base"] = eid
        inst["on"] = True
        self.fx_chain.append(inst)
        self.fx_sel_inst = len(self.fx_chain) - 1
        self.fxdlg.focus = "chain"
        self.mark_dirty()
    def move_effect(self, delta):
        self.fx_chain = normalize_chain(self.fx_chain)
        i = self.fx_sel_inst
        if i is None or not (0 <= i < len(self.fx_chain)):
            return
        j = i + delta
        if j < 0 or j >= len(self.fx_chain):
            return
        self.fx_chain[i], self.fx_chain[j] = self.fx_chain[j], self.fx_chain[i]
        self.fx_sel_inst = j
        self.mark_dirty()
    def remove_selected_effect(self, *_):
        if self.fx_sel_inst is None or not (0 <= self.fx_sel_inst < len(self.fx_chain)):
            return
        del self.fx_chain[self.fx_sel_inst]
        self.fx_sel_inst = min(self.fx_sel_inst, len(self.fx_chain) - 1) if self.fx_chain else None
        self.mark_dirty()
        self.fxdlg._rebuild()
    def ask_clear_effects(self):
        self.confirmdlg.open("Clear all effects from the chain?", lambda *_: self.clear_effects(),
                             show_check=False, hint="DX7 patch input remains.")
    def clear_effects(self, *_):
        self.fx_chain = []
        self.fx_sel_inst = None
        self.mark_dirty()
        self.fxdlg._rebuild()
    def select_all_effects(self):
        self.fx_chain = normalize_chain(self.fx_chain)
        have = {i["base"] for i in self.fx_chain}
        for e in EFFECT_DEFS:
            if e["id"] not in have:
                self.fx_chain.append(deepcopy(self.fxdlg.drafts.get(e["id"]) or default_instance(e["id"])))
        self.mark_dirty()
    def randomize_effects(self):
        self.fx_chain = normalize_chain(self.fx_chain)
        for inst in self.fx_chain:
            e = FX_INDEX.get(inst["base"])
            if not e:
                continue
            for nm, d, lo, hi in e["params"]:
                inst["params"][nm] = random.uniform(lo, hi)
            for nm, d in e["switches"]:
                inst["switches"][nm] = bool(random.getrandbits(1))
        self.mark_dirty()
        self.fxdlg._rebuild()
    def export_fx_chain(self):
        self.filedlg.open("export effects", "chain.json", self._write_fx, directory=EFFECTS_DIR, filt="*.json")
    def _write_fx(self, path):
        if not path.lower().endswith(".json"):
            path += ".json"
        save_json(path, {"format": "dx7-fx-chain-v1", "chain": normalize_chain(self.fx_chain),
                         "clip_mode": self.clip_mode, "post_fx": self.post_fx})
        self.status = f"Exported effects {path}"
    def import_fx_chain(self):
        self.filedlg.open("import effects", "*", self._read_fx, directory=EFFECTS_DIR, filt="*")
    def _read_fx(self, path):
        data = load_json(path, None)
        if not data:
            self.status = "FX import failed"
            return
        self.fx_chain = normalize_chain(data.get("chain") or [])
        self.clip_mode = data.get("clip_mode", "none")
        if isinstance(data.get("post_fx"), dict):
            self.post_fx.update(data["post_fx"])
        self.fxdlg.dirty = True
        self.status = f"Imported effects {os.path.basename(path)}"
    def capture_patch_state(self):
        self.read_adsr_from_sliders()
        ensure_adsr(self.patch)
        self.patch["algo"] = int(self.patch.get("algo", 2))
        self.patch["feedback"] = int(self.patch.get("feedback", 0))
        self.fx_chain = normalize_chain(self.fx_chain)
        self.patches[self.patch_index] = deepcopy(self.patch)
    def open_edit(self):
        self.capture_patch_state()
        self.save_bank()
        self.dialog.open("edit")
    def ask_delete_patch(self):
        self.confirmdlg.open(f"Delete patch {self.patch['name']}?", self.delete_patch, show_check=True)
    def delete_patch(self, delete_files):
        name = self.patch["name"]
        if delete_files:
            for p in tone_candidates(name):
                if os.path.isfile(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
        if len(self.patches) <= 1:
            self.patches = [ensure_adsr(deepcopy(FACTORY[0] if FACTORY else make_patch("INIT", 1, 0, [default_op() for _ in range(6)])))]
        else:
            del self.patches[self.patch_index]
        self.patch_index = min(self.patch_index, len(self.patches) - 1)
        self.patch = deepcopy(self.patches[self.patch_index])
        self.save_bank()
        self.select_loaded_patch(self.patch_index)
    def select_loaded_patch(self, idx):
        self.patch_index = idx
        self.patch = ensure_adsr(deepcopy(self.patches[idx]))
        self.sel_op = 0
        self.sync_adsr_sliders()
        self.rebuild_op_sliders()
        self.refresh_op_buttons()
        self.load_tone_json()
        self.load_or_build_tones(force=False, apply_fx=bool(self.fx_chain))
    def sync_adsr_sliders(self):
        a = ensure_adsr(self.patch)["adsr"]
        self.sliders[0].value, self.sliders[1].value = a["a"], a["d"]
        self.sliders[2].value, self.sliders[3].value = a["s"], a["r"]
    def read_adsr_from_sliders(self):
        self.patch["adsr"] = {"a": self.sliders[0].value, "d": self.sliders[1].value, "s": self.sliders[2].value, "r": self.sliders[3].value}
        ensure_adsr(self.patch)
    def export_payload(self):
        self.capture_patch_state()
        return {
            "format": "dx7-pygame-patch-v2",
            "exported": datetime.utcnow().isoformat() + "Z",
            "source_name": self.patch["name"],
            "original_name": self.patch["name"],
            "patch": deepcopy(self.patch),
            "chain": normalize_chain(self.fx_chain),
            "clip_mode": self.clip_mode,
            "post_fx": dict(self.post_fx),
        }
    def export_patch(self):
        self.filedlg.open("export json", safe_tone_name(self.patch["name"]) + ".json", self._write_export)
    def _write_export(self, path):
        if not path.lower().endswith(".json"):
            path += ".json"
        save_json(path, self.export_payload())
        self.status = f"Exported {path}"
    def import_patch_ask(self):
        self.filedlg.open("import json", "", self.begin_import)
    def begin_import(self, path):
        data = load_json(path, None)
        if not data:
            self.status = "Import failed"
            return
        p = data.get("patch", data)
        suggested = data.get("source_name") or data.get("original_name") or p.get("name") or "Imported"
        self.importdlg.open(data, suggested, suggested)
    def finish_import(self, data, mode, name):
        p = data.get("patch", data)
        ops = p.get("ops") or []
        while len(ops) < 6:
            ops.append(default_op(0, 1, 0, [99, 99, 99, 99], [0, 0, 0, 0], False))
        newp = ensure_adsr(make_patch(name, int(p.get("algo", 2)), int(p.get("feedback", 0)), deepcopy(ops[:MAX_OPS]), p.get("adsr"), p.get("kind", "fm")))
        newp["captured"] = p.get("captured", {})
        self.fx_chain = normalize_chain(data.get("chain") or [])
        self.clip_mode = data.get("clip_mode", "none")
        if isinstance(data.get("post_fx"), dict):
            self.post_fx.update(data["post_fx"])
        if mode == "replace":
            self.patch = newp
            self.patches[self.patch_index] = deepcopy(self.patch)
        else:
            existing = [q["name"] for q in self.patches]
            newp["name"] = unique_patch_name(name, existing)
            self.patches.insert(0, deepcopy(newp))
            self.patch_index = 0
            self.patch = deepcopy(newp)
        self.save_bank()
        self.save_tone_json()
        self.load_or_build_tones(force=False, apply_fx=bool(self.fx_chain))
    def save_tone_json(self):
        self.capture_patch_state()
        save_json(tone_json_path(self.patch["name"]), self.export_payload())
    def load_tone_json(self):
        self.fx_chain = []
        path = tone_json_path(self.patch["name"])
        data = load_json(path, None)
        if not data:
            return
        if isinstance(data.get("patch"), dict):
            p = data["patch"]
            self.patch.update({k: p[k] for k in p if k in ("ops", "algo", "feedback", "adsr", "kind", "captured", "name")})
            self.patch = ensure_adsr(self.patch)
            self.patches[self.patch_index] = deepcopy(self.patch)
            self.sync_adsr_sliders()
            self.rebuild_op_sliders()
            self.refresh_op_buttons()
        self.fx_chain = normalize_chain(data.get("chain") or [])
        self.clip_mode = data.get("clip_mode", "none")
        if isinstance(data.get("post_fx"), dict):
            self.post_fx.update(data["post_fx"])
    def install_waves(self, waves):
        self.note_off_all()
        self.sounds.clear()
        self.waves = {int(n): np.asarray(w, np.float32) for n, w in waves.items()}
        for n, w in self.waves.items():
            self.sounds[int(n)], _ = pcm_sound(w)
    def make_sample_patch(self):
        name = unique_patch_name("SamplePatch", [p["name"] for p in self.patches])
        p = make_patch(name, 32, 0, [default_op() for _ in range(6)], kind="sample")
        self.patches.insert(0, p)
        self.patch_index = 0
        self.patch = deepcopy(p)
        self.save_bank()
        self.wizard.open()
    def capture_current_note(self, note):
        src = self.waves.get(note) or self.base_waves.get(note) or render_note_first_iteration(self.patch, note, no_loop=self.no_loop)
        path = os.path.join(sample_src_dir(self.patch["name"]), f"n{int(note)}.npy")
        np.save(path, np.asarray(src, np.float32))
        self.patch.setdefault("captured", {})[str(int(note))] = path
        self.patch["kind"] = "sample"
        self.base_waves[int(note)] = np.asarray(src, np.float32)
        self.save_bank()
    def rebuild_interpolated(self):
        captured = {}
        for k, path in self.patch.get("captured", {}).items():
            if os.path.isfile(path):
                captured[int(k)] = np.load(path).astype(np.float32)
        if not captured:
            return
        self.base_waves = {}
        keys = sorted(captured)
        for note in self.midi_notes:
            if note in captured:
                self.base_waves[note] = captured[note]
            else:
                nearest = min(keys, key=lambda k: abs(k - note))
                self.base_waves[note] = pitch_shift_buf(captured[nearest], note - nearest)
        self.install_waves(self.base_waves)
        save_tone_file(tone_save_path(self.patch["name"]), self.waves)
    def source_wave_for_note(self, note, seconds=NOTE_SECONDS):
        if self.patch.get("kind") == "sample":
            if note in self.base_waves:
                w = self.base_waves[note]
            else:
                cap = {}
                for k, path in self.patch.get("captured", {}).items():
                    if os.path.isfile(path):
                        cap[int(k)] = np.load(path).astype(np.float32)
                if cap:
                    nearest = min(cap, key=lambda k: abs(k - note))
                    w = pitch_shift_buf(cap[nearest], note - nearest)
                else:
                    w = render_note_first_iteration(self.patch, note, seconds, no_loop=self.no_loop)
            if len(w) < int(SAMPLE_RATE * seconds):
                reps = int(math.ceil(SAMPLE_RATE * seconds / max(1, len(w))))
                w = np.tile(w, reps)[:int(SAMPLE_RATE * seconds)]
            return np.asarray(w[:int(SAMPLE_RATE * seconds)], np.float32)
        return render_note_first_iteration(self.patch, note, seconds, no_loop=self.no_loop)
    def merge_map(self):
        out = {}
        for inst in normalize_chain(self.fx_chain):
            if FX_INDEX.get(inst.get("base"), {}).get("kind") == "merge":
                name = inst.get("merge_patch")
                if name and os.path.isfile(tone_save_path(name)):
                    waves = load_tone_file(tone_save_path(name), self.midi_notes)
                    if waves:
                        out[name] = waves
        return out
    def generate_one(self, note, seconds, apply_fx, merge_waves):
        wave = self.source_wave_for_note(note, seconds)
        if apply_fx and self.fx_chain:
            extra = {"merge_map": {k: v.get(note) for k, v in merge_waves.items() if v and note in v}}
            wave = apply_fx_chain(wave, self.fx_chain, extra, self.clip_mode)
            adsr = self.patch.get("adsr", DEFAULT_ADSR)
            if (not self.no_loop) and adsr.get("s", 0.5) > 0.35:
                wave = make_loopable(wave)
        return int(note), wave
    def generate_samples(self, apply_fx=False):
        self.capture_patch_state()
        self.load_or_build_tones(force=True, apply_fx=apply_fx or bool(self.fx_chain))
        self.full_backup = {n: np.array(w) for n, w in self.waves.items()}
        self.dirty = False
        if self.gen_btn:
            self.gen_btn.hot = False
    def test_gen_previews(self):
        self.full_backup = {n: np.array(self.waves[n]) for n in self.waves}
        t0 = time.perf_counter()
        mm = self.merge_map()
        for note in PREVIEW_NOTES:
            _, wave = self.generate_one(note, PREVIEW_SECONDS, True, mm)
            snd, wav = pcm_sound(wave)
            self.preview_sounds[note] = snd
            self.preview_waves[note] = wav
        self.status = f"Test gen {format_gen_time(time.perf_counter()-t0)}"
    def revert_previews(self):
        self.preview_sounds.clear()
        self.preview_waves.clear()
        if self.full_backup:
            for n, w in self.full_backup.items():
                self.waves[n] = w
                self.sounds[n], _ = pcm_sound(w)
        self.status = "Reverted test notes"
    def quick_preview(self, note):
        _, wave = self.generate_one(note, PREVIEW_SECONDS, True, self.merge_map())
        self.preview_sounds[note], self.preview_waves[note] = pcm_sound(wave)
    def clear_preview_notes(self):
        self.preview_sounds.clear()
        self.preview_waves.clear()
    def load_or_build_tones(self, force=False, apply_fx=False):
        self.capture_patch_state()
        os.makedirs(TONES_DIR, exist_ok=True)
        if not force:
            for path in tone_candidates(self.patch["name"]):
                if os.path.isfile(path):
                    waves = load_tone_file(path, self.midi_notes)
                    if waves:
                        self.install_waves(waves)
                        self.full_backup = {n: np.array(w) for n, w in waves.items()}
                        self.status = f"Loaded samples {os.path.basename(path)}"
                        return
        self.note_off_all()
        use_fx = bool(apply_fx or self.fx_chain)
        merge_waves = self.merge_map() if use_fx else {}
        t0 = time.perf_counter()
        results = {}
        nthreads = max(1, min(88, int(self.max_threads))) if self.use_threads else 1
        notes = list(self.midi_notes)
        if nthreads > 1 and len(notes) > 1:
            with ThreadPoolExecutor(max_workers=nthreads) as ex:
                futs = [ex.submit(self.generate_one, n, NOTE_SECONDS, use_fx, merge_waves) for n in notes]
                done = 0
                for fut in as_completed(futs):
                    note, wave = fut.result()
                    results[note] = wave
                    done += 1
                    self.status = f"Rendering {done}/{len(notes)}"
                    self._draw_status_frame()
        else:
            for i, note in enumerate(notes):
                self.status = f"Rendering {i+1}/{len(notes)}"
                self._draw_status_frame()
                n, wave = self.generate_one(note, NOTE_SECONDS, use_fx, merge_waves)
                results[n] = wave
        self.last_gen_time = format_gen_time(time.perf_counter() - t0)
        self.install_waves(results)
        self.full_backup = {n: np.array(w) for n, w in results.items()}
        save_tone_file(tone_save_path(self.patch["name"]), self.waves)
        self.save_tone_json()
        self.save_bank()
        self.status = f"Wrote samples  {self.last_gen_time}"
    def export_wav_zip(self):
        self.filedlg.open("export zip", safe_tone_name(self.patch["name"]) + ".zip", self._write_zip)
    def _write_zip(self, path):
        if not path.lower().endswith(".zip"):
            path += ".zip"
        tmp = os.path.join(os.path.dirname(path) or ".", "_dx7_exp_tmp")
        os.makedirs(tmp, exist_ok=True)
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for note, wave in sorted(self.waves.items()):
                    base = midi_note_label(note)
                    wavp = os.path.join(tmp, base + ".wav")
                    write_wav(wavp, wave)
                    if self.exp_mp3:
                        mp3p = os.path.join(tmp, base + ".mp3")
                        if try_mp3(wavp, mp3p):
                            zf.write(mp3p, os.path.basename(mp3p))
                            continue
                    zf.write(wavp, os.path.basename(wavp))
            self.status = f"Exported zip {path}"
        except Exception as e:
            self.status = f"Zip failed: {e}"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    def _draw_status_frame(self):
        self.screen.fill(COL_BG)
        self.screen.blit(self.font.render(self.status, True, COL_ORANGE), (30, 240))
        pygame.display.flip()
        pygame.event.pump()
    def persist_geom(self):
        w, h = self.screen.get_size()
        save_geom(w, h, self.geom.get("x", 80), self.geom.get("y", 80))
    def save_bank(self):
        self.capture_patch_state()
        self.patches[self.patch_index] = deepcopy(self.patch)
        save_json(BANK_FILE, self.patches)
    def chg_algo(self, d):
        i = ALGO_KEYS.index(self.patch["algo"]) if self.patch.get("algo") in ALGO_KEYS else 0
        self.patch["algo"] = ALGO_KEYS[(i + d) % len(ALGO_KEYS)]
        self.mark_dirty()
    def chg_fb(self, d):
        self.patch["feedback"] = max(0, min(7, int(self.patch.get("feedback", 0)) + d))
        self.mark_dirty()
    def _steal_oldest(self):
        while self.voice_order:
            old = self.voice_order.pop(0)
            v = self.playing.pop(old, None)
            if v:
                v.stop_now()
                return
    def active_sound(self, note):
        if self.fxdlg.visible and note in self.preview_sounds:
            return self.preview_sounds[note], self.preview_waves.get(note)
        src = self.waves.get(note)
        if src is None:
            return None, None
        wave = np.asarray(src, np.float32)
        if self.post_fx.get("delay_on") or self.post_fx.get("verb_on"):
            wave = apply_post_fx(wave, self.post_fx)
            if not self.no_loop:
                wave = make_loopable(wave)
            snd, wav = pcm_sound(wave)
            return snd, wav
        if note in self.sounds:
            return self.sounds[note], src
        return None, None
    def note_on(self, note):
        snd, wave = self.active_sound(note)
        if snd is None:
            return
        if note in self.playing:
            self.playing[note].stop_now()
            self.playing.pop(note, None)
            if note in self.voice_order:
                self.voice_order.remove(note)
        self.voice_order = [n for n in self.voice_order if n in self.playing and not self.playing[n].done]
        if len(self.voice_order) >= MAX_POLY - 1:
            self._steal_oldest()
        self.read_adsr_from_sliders()
        ch = pygame.mixer.find_channel(False)
        if ch is None:
            self._steal_oldest()
            ch = pygame.mixer.find_channel(False)
        if ch is None:
            return
        ch.play(snd, loops=-1)
        ch.set_volume(0.0)
        self.playing[note] = PlayingNote(note, snd, ch, self.patch["adsr"], wave)
        self.voice_order.append(note)
    def mix_scope(self):
        if self.scope_freeze:
            return
        acc = np.zeros(512, np.float32)
        anyv = False
        period = 128
        for v in self.playing.values():
            if v.done or v.wave is None or not len(v.wave):
                continue
            anyv = True
            n = len(v.wave)
            start = int(v.pos) % n
            if self.scope_lock:
                period = estimate_period(v.wave)
                start = start - (start % max(1, period))
            sl = np.take(v.wave, np.arange(start, start + 4096) % n)[::8][:512]
            acc[:len(sl)] += sl * v.level
        if anyv:
            pk = float(np.max(np.abs(acc))) + 1e-9
            if pk > 1:
                acc /= pk
            self.scope = acc
    def note_off(self, note):
        v = self.playing.get(note)
        if v:
            v.note_off()
    def note_off_all(self):
        for v in list(self.playing.values()):
            v.stop_now()
        self.playing.clear()
        self.voice_order.clear()
        try:
            pygame.mixer.stop()
        except Exception:
            pass
    def update_voices(self, dt):
        dead = [n for n, v in self.playing.items() if (v.update(dt) or v.done)]
        for n in dead:
            self.playing.pop(n, None)
            if n in self.voice_order:
                self.voice_order.remove(n)
        self.mix_scope()
    def list_midi_inputs(self):
        self.midi_devs = []
        if not HAS_MIDI:
            return
        try:
            if not pygame.midi.get_init():
                pygame.midi.init()
            for i in range(pygame.midi.get_count()):
                info = pygame.midi.get_device_info(i)
                is_input = bool(info[2])
                name = info[1].decode() if isinstance(info[1], bytes) else str(info[1])
                iface = info[0].decode() if isinstance(info[0], bytes) else str(info[0])
                if is_input:
                    self.midi_devs.append((i, f"{iface} / {name}"))
        except Exception as e:
            self.midi_name = f"MIDI list err {e}"
    def cycle_midi(self):
        if not HAS_MIDI:
            self.midi_name = "pygame.midi unavailable"
            return
        self.list_midi_inputs()
        if self.midi_in:
            try:
                self.midi_in.close()
            except Exception:
                pass
            self.midi_in = None
        if not self.midi_devs:
            self.midi_id, self.midi_name = -1, "No MIDI inputs"
            return
        ids = [d[0] for d in self.midi_devs]
        nxt = ids[(ids.index(self.midi_id) + 1) % len(ids)] if self.midi_id in ids else ids[0]
        try:
            self.midi_in = pygame.midi.Input(nxt)
            self.midi_id = nxt
            self.midi_name = dict(self.midi_devs)[nxt]
        except Exception as e:
            self.midi_in, self.midi_name = None, f"Open fail: {e}"
    def poll_midi(self):
        if not self.midi_in:
            return
        try:
            if self.midi_in.poll():
                for ev in self.midi_in.read(64):
                    data = ev[0]
                    status, n, v = data[0] & 0xF0, data[1], data[2]
                    if status == 0x90 and v > 0:
                        self.note_on(n)
                        self.held_midi.add(n)
                    elif status in (0x80, 0x90):
                        self.note_off(n)
                        self.held_midi.discard(n)
        except Exception:
            pass
    def note_from_key_event(self, event):
        tok = event_key_token(event)
        if tok in self.keymap:
            return tok, self.keymap[tok]
        if event.unicode:
            u = event.unicode.lower()
            if u in self.keymap:
                return u, self.keymap[u]
        return None, None
    def handle_keydown(self, event):
        if self.thread_edit:
            if event.key == pygame.K_RETURN:
                self.apply_thread_text()
                return
            if event.key == pygame.K_ESCAPE:
                self.thread_edit = False
                self.thread_text = str(self.max_threads)
                return
            if event.key == pygame.K_BACKSPACE:
                self.thread_text = self.thread_text[:-1]
                return
            if event.unicode and event.unicode.isdigit() and len(self.thread_text) < 3:
                self.thread_text += event.unicode
            return
        if self.dialog.visible or self.dropdown.open or self.importdlg.visible or self.filedlg.visible or self.confirmdlg.visible:
            return
        if event.key == pygame.K_ESCAPE and not self.fxdlg.visible:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        tok, note = self.note_from_key_event(event)
        if note is None or tok in self.held_keys:
            return
        self.held_keys[tok] = note
        self.note_on(note)
    def handle_keyup(self, event):
        tok, note = self.note_from_key_event(event)
        if tok in self.held_keys:
            self.note_off(self.held_keys.pop(tok))
        elif note is not None:
            self.note_off(note)
    def draw_graphs(self):
        eg, ag, sc = self.graph_rects()
        op = self.patch["ops"][self.sel_op]
        pygame.draw.rect(self.screen, (16, 18, 24), eg)
        pygame.draw.rect(self.screen, COL_ACCENT, eg, 1)
        rates = [max(1, r) for r in op["rates"]]
        widths = [max(0.08, 100 - r) for r in rates]
        tot = sum(widths)
        xs, acc = [0.0], 0.0
        for w in widths:
            acc += w / tot
            xs.append(acc)
        ys = [0.0] + [lv / 99.0 for lv in op["levels"]]
        pts = [(eg.x + 8 + x * (eg.w - 16), eg.bottom - 8 - y * (eg.h - 28)) for x, y in zip(xs, ys)]
        if len(pts) > 1:
            pygame.draw.aalines(self.screen, COL_ACCENT, False, pts)
        pygame.draw.rect(self.screen, (16, 18, 24), ag)
        pygame.draw.rect(self.screen, COL_ORANGE, ag, 1)
        a, d, s, rv = self.sliders[0].value, self.sliders[1].value, self.sliders[2].value, self.sliders[3].value
        span = max(0.05, a + d + 0.4 + rv)
        inner = pygame.Rect(ag.x + 8, ag.y + 22, ag.w - 16, ag.h - 30)
        pts2 = [(inner.x, inner.bottom), (inner.x + a / span * inner.w, inner.y),
                (inner.x + (a + d) / span * inner.w, inner.bottom - s * inner.h),
                (inner.x + (a + d + 0.4) / span * inner.w, inner.bottom - s * inner.h), (inner.right, inner.bottom)]
        pygame.draw.aalines(self.screen, COL_ORANGE, False, pts2)
        pygame.draw.rect(self.screen, (8, 10, 14), sc)
        pygame.draw.rect(self.screen, COL_ORANGE, sc, 1)
        pts3 = [(sc.x + 8 + i * (sc.w - 16) / max(1, len(self.scope) - 1), sc.centery + 8 - float(sv) * sc.h * 0.32) for i, sv in enumerate(self.scope)]
        if len(pts3) > 1:
            pygame.draw.aalines(self.screen, COL_ACCENT, False, pts3)
        fz = pygame.Rect(sc.x, sc.bottom + 6, 70, 18)
        lk = pygame.Rect(sc.x + 80, sc.bottom + 6, 70, 18)
        pygame.draw.rect(self.screen, (80, 200, 90) if self.scope_freeze else (50, 60, 70), fz, border_radius=4)
        pygame.draw.rect(self.screen, (80, 200, 90) if self.scope_lock else (50, 60, 70), lk, border_radius=4)
        self.screen.blit(self.tiny.render("Freeze", True, COL_TEXT), (fz.x + 10, fz.y + 3))
        self.screen.blit(self.tiny.render("Lock", True, COL_TEXT), (lk.x + 18, lk.y + 3))
        self.screen.blit(self.tiny.render(
            f"POST delay {'ON' if self.post_fx['delay_on'] else 'off'} {self.post_fx['delay_kind']}  "
            f"verb {'ON' if self.post_fx['verb_on'] else 'off'} {self.post_fx['verb_kind']}",
            True, COL_DIM), (sc.x, sc.bottom + 28))
    def draw_keyboard(self):
        w, h = self.screen.get_size()
        if not self.midi_notes:
            return
        lo, hi = self.midi_notes[0], self.midi_notes[-1]
        white = {0, 2, 4, 5, 7, 9, 11}
        whites = [n for n in range(lo, hi + 1) if n % 12 in white]
        kh = 96
        oy = h - kh - 14
        ww = max(14, min(28, (w - 80) // max(1, len(whites))))
        ox = (w - len(whites) * ww) // 2
        notes_on = set(self.held_keys.values()) | self.held_midi | {n for n, v in self.playing.items() if not v.released}
        wi, wx = 0, {}
        for n in range(lo, hi + 1):
            if n % 12 not in white:
                continue
            r = pygame.Rect(ox + wi * ww, oy, ww - 2, kh)
            wx[n] = r.x
            col = COL_KEY_ON if n in notes_on else (COL_KEY if n in self.mapped else COL_KEY_UNMAPPED)
            pygame.draw.rect(self.screen, col, r, border_radius=3)
            if n in self.mapped:
                self.screen.blit(self.tiny.render(str(self.key_by_note.get(n, "")), True, (40, 40, 40)), (r.x + 3, r.bottom - 16))
            wi += 1
        for n in range(lo, hi + 1):
            if n % 12 in white:
                continue
            lw = n - 1
            while lw not in wx and lw >= lo:
                lw -= 1
            if lw not in wx:
                continue
            r = pygame.Rect(wx[lw] + ww - ww // 3, oy, ww // 2, int(kh * 0.62))
            col = COL_ORANGE if n in notes_on else (COL_KEY_BLK if n in self.mapped else (50, 50, 55))
            pygame.draw.rect(self.screen, col, r, border_radius=2)
    def draw_ops(self):
        w, h = self.screen.get_size()
        pygame.draw.rect(self.screen, COL_PANEL, pygame.Rect(20, 132, max(400, w - 40), max(230, h - 250)), border_radius=8)
        self.screen.blit(self.small.render(
            f"OP{self.sel_op+1}/{len(self.patch['ops'])} ALG {self.patch.get('algo')} FB {self.patch.get('feedback')}",
            True, COL_TEXT), (30, 138))
        self.screen.blit(self.tiny.render(self.status, True, COL_ORANGE), (30, 156))
        self.draw_graphs()
        for sl in self.sliders:
            sl.draw(self.screen, self.tiny)
        for sl in self.op_sliders:
            sl.draw(self.screen, self.tiny)
        pygame.draw.rect(self.screen, (80, 200, 90) if self.use_threads else (50, 50, 60), self.thread_box)
        self.screen.blit(self.tiny.render("threads", True, COL_DIM), (self.thread_box.right + 8, self.thread_box.y + 1))
        pygame.draw.rect(self.screen, (20, 22, 30), self.thread_edit_rect, border_radius=3)
        pygame.draw.rect(self.screen, COL_ORANGE if self.thread_edit else COL_ACCENT, self.thread_edit_rect, 1, border_radius=3)
        self.screen.blit(self.tiny.render(self.thread_text + ("_" if self.thread_edit else ""), True, COL_TEXT),
                         (self.thread_edit_rect.x + 6, self.thread_edit_rect.y + 4))
        pygame.draw.rect(self.screen, (80, 200, 90) if self.exp_mp3 else (50, 50, 60), self.mp3_box)
        self.screen.blit(self.tiny.render("zip mp3 (else wav)", True, COL_DIM), (self.mp3_box.right + 8, self.mp3_box.y + 1))
        pygame.draw.rect(self.screen, (200, 80, 60) if self.no_loop else (50, 50, 60), self.noloop_box)
        self.screen.blit(self.tiny.render("No Loop (GENERATE)", True, COL_DIM), (self.noloop_box.right + 8, self.noloop_box.y + 1))
        self.screen.blit(self.tiny.render(f"MIDI:{self.midi_name}", True, COL_ACCENT), (30, 500))
        self.screen.blit(self.tiny.render(f"Last Generation time: {self.last_gen_time}", True, COL_ORANGE), (30, 516))
    def hit_scope_toggles(self, pos):
        sc = self.graph_rects()[2]
        fz = pygame.Rect(sc.x, sc.bottom + 6, 70, 18)
        lk = pygame.Rect(sc.x + 80, sc.bottom + 6, 70, 18)
        if fz.collidepoint(pos):
            self.scope_freeze = not self.scope_freeze
            return True
        if lk.collidepoint(pos):
            self.scope_lock = not self.scope_lock
            return True
        return False
    def hit_post(self, pos):
        sc = self.graph_rects()[2]
        row = pygame.Rect(sc.x, sc.bottom + 26, 420, 18)
        if row.collidepoint(pos):
            if pos[0] < sc.x + 160:
                self.post_fx["delay_on"] = not self.post_fx["delay_on"]
                self.post_fx["delay_kind"] = "tape" if self.post_fx["delay_kind"] == "digital" else "digital"
            else:
                self.post_fx["verb_on"] = not self.post_fx["verb_on"]
                self.post_fx["verb_kind"] = "spring" if self.post_fx["verb_kind"] == "hall" else "hall"
            return True
        return False
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            self.poll_midi()
            self.update_voices(dt)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.geom["w"] = max(1100, event.w)
                    self.geom["h"] = max(640, event.h)
                    self.persist_geom()
                elif self.filedlg.visible:
                    self.filedlg.handle(event)
                elif self.confirmdlg.visible:
                    self.confirmdlg.handle(event)
                elif self.importdlg.visible:
                    self.importdlg.handle(event)
                elif self.wizard.visible:
                    self.wizard.handle(event)
                elif self.fxdlg.visible:
                    consumed = self.fxdlg.handle(event)
                    if event.type == pygame.KEYDOWN and not consumed and not self.fxdlg.search_focus:
                        self.handle_keydown(event)
                    elif event.type == pygame.KEYUP:
                        self.handle_keyup(event)
                elif self.dialog.visible:
                    self.dialog.handle(event)
                elif self.dropdown.handle(event, self):
                    pass
                elif any(sl.handle(event) for sl in self.sliders):
                    self.read_adsr_from_sliders()
                elif any(sl.handle(event) for sl in self.op_sliders):
                    self.apply_op_sliders()
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.hit_scope_toggles(event.pos) or self.hit_post(event.pos):
                        pass
                    elif self.thread_box.collidepoint(event.pos):
                        self.use_threads = not self.use_threads
                    elif self.thread_edit_rect.collidepoint(event.pos):
                        self.thread_edit = True
                    elif self.mp3_box.collidepoint(event.pos):
                        self.exp_mp3 = not self.exp_mp3
                    elif self.noloop_box.collidepoint(event.pos):
                        self.no_loop = not self.no_loop
                    else:
                        if self.thread_edit:
                            self.apply_thread_text()
                        hit = False
                        for b in self.op_buttons:
                            if b.click(event.pos):
                                hit = True
                                break
                        if not hit:
                            for b in self.buttons:
                                b.click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.handle_keydown(event)
                elif event.type == pygame.KEYUP:
                    self.handle_keyup(event)
            self.screen.fill(COL_BG)
            if self.gen_btn:
                self.gen_btn.hot = self.dirty
            for b in self.buttons:
                b.draw(self.screen, self.small)
            for b in self.op_buttons:
                b.on = (b.label == f"OP{self.sel_op+1}")
                b.draw(self.screen, self.small)
            self.draw_ops()
            self.draw_keyboard()
            self.dropdown.draw(self.screen, self.font, self.small, self)
            self.dialog.draw(self.screen, self.font, self.small)
            self.fxdlg.draw(self.screen, self.font, self.small)
            self.importdlg.draw(self.screen, self.font, self.small)
            self.filedlg.draw(self.screen, self.font, self.small)
            self.confirmdlg.draw(self.screen, self.font, self.small)
            self.wizard.draw(self.screen, self.font, self.small)
            pygame.display.flip()
        self.persist_geom()
        self.save_bank()
        if self.midi_in:
            try:
                self.midi_in.close()
            except Exception:
                pass
        if HAS_MIDI:
            try:
                if pygame.midi.get_init():
                    pygame.midi.quit()
            except Exception:
                pass
        pygame.mixer.quit()
        pygame.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DX7-style FM synth")
    parser.add_argument("--generate-all", action="store_true",
                        help="Generate (overwrite) samples for every patch, then exit")
    parser.add_argument("--no-loop", action="store_true",
                        help="Force no looping when generating (CLI or with --generate-all)")
    args = parser.parse_args()
    app = App()
    if args.generate_all:
        app.generate_all(no_loop=args.no_loop)
    else:
        app.run()