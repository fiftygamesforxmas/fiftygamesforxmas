#!/usr/bin/env python3
"""DX7-style FM synth with ordered FX chain. Requires pygame, numpy."""

import json, math, os, re
from copy import deepcopy
import numpy as np
import pygame

HAS_MIDI = False
try:
    import pygame.midi
    HAS_MIDI = True
except Exception:
    pass

SAMPLE_RATE, NOTE_SECONDS, XFADE_SEC = 44100, 5.0, 0.06
TWO_PI, MAX_POLY = 2.0 * math.pi, 16
HERE = os.path.dirname(os.path.abspath(__file__))
GEOM_FILE = os.path.join(HERE, "fm_window.json")
BANK_FILE = os.path.join(HERE, "fm_bank.json")
SITE_KEY = os.path.join(HERE, "site.key")
TONES_DIR = os.path.join(HERE, "tones")
DEFAULT_KEYMAP_TOKENS = (
    "z48 s49 x50 d51 c52 v53 g54 b55 h56 n57 j58 m59 ,60 l61 .62 /64 "
    "q60 261 w62 363 e64 r65 566 t67 668 y69 770 u71 i72 o73 p74 [76 ]77"
)
DEFAULT_ADSR = {"a": 0.02, "d": 0.12, "s": 0.85, "r": 0.25}

def parse_keymap(text):
    mapping = {}
    for tok in text.replace(",", " ,").split():
        tok = tok.strip()
        if len(tok) < 2: continue
        i = 1
        while i < len(tok) and not tok[i].isdigit() and tok[i] not in "+-":
            i += 1
        key, num = tok[:i], tok[i:]
        if not num: continue
        try: mapping[key.lower()] = int(num)
        except ValueError: continue
    return mapping

def load_keymap():
    if os.path.isfile(SITE_KEY):
        with open(SITE_KEY, "r", encoding="utf-8") as f:
            m = parse_keymap(f.read())
        if m: return m, "site.key"
    return parse_keymap(DEFAULT_KEYMAP_TOKENS), "default"

KEY_NAME_ALIASES = {"comma": ",", "period": ".", "slash": "/", "semicolon": ";",
                    "leftbracket": "[", "rightbracket": "]"}

def event_key_token(event):
    name = pygame.key.name(event.key)
    if event.unicode and event.unicode.strip():
        ch = event.unicode.lower()
        if len(ch) == 1: return ch
    return KEY_NAME_ALIASES.get(name.lower(), name.lower())

def load_geom():
    d = {"w": 1200, "h": 700, "x": 80, "y": 80}
    if os.path.isfile(GEOM_FILE):
        try:
            with open(GEOM_FILE, "r", encoding="utf-8") as f:
                d.update({k: int(v) for k, v in json.load(f).items() if k in d})
        except Exception:
            pass
    d["w"] = max(980, min(d["w"], 2400)); d["h"] = max(600, min(d["h"], 1600))
    return d

def save_geom(w, h, x, y):
    try:
        with open(GEOM_FILE, "w", encoding="utf-8") as f:
            json.dump({"w": int(w), "h": int(h), "x": int(x), "y": int(y)}, f)
    except Exception:
        pass

def coarse_ratio(c): return 0.5 if c <= 0 else float(c)
def midi_to_hz(n): return 440.0 * (2.0 ** ((n - 69) / 12.0))
def safe_tone_name(name):
    return re.sub(r"[^\w\-]+", "_", (name or "INIT").strip() or "INIT")[:48]

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

def ensure_adsr(p):
    if "adsr" not in p or not isinstance(p["adsr"], dict):
        p["adsr"] = dict(DEFAULT_ADSR)
    a = p["adsr"]
    a["a"] = float(max(0.001, min(2.0, a.get("a", 0.02))))
    a["d"] = float(max(0.001, min(2.0, a.get("d", 0.12))))
    a["s"] = float(max(0.0, min(1.0, a.get("s", 0.85))))
    a["r"] = float(max(0.001, min(3.0, a.get("r", 0.25))))
    return p

ALGORITHMS = {
    1: {"mod": {0:[1],1:[],2:[3],3:[4],4:[5],5:[]}, "carriers":[0,2], "fb":5},
    2: {"mod": {0:[1],1:[],2:[3],3:[4],4:[5],5:[]}, "carriers":[0,2], "fb":1},
    5: {"mod": {0:[1],1:[],2:[3],3:[],4:[5],5:[]}, "carriers":[0,2,4], "fb":5},
    16:{"mod": {0:[1,2,3,4,5],1:[],2:[],3:[],4:[],5:[]}, "carriers":[0], "fb":5},
    18:{"mod": {0:[1],1:[],2:[],3:[4],4:[5],5:[]}, "carriers":[0,2,3], "fb":5},
    32:{"mod": {0:[],1:[],2:[],3:[],4:[],5:[]}, "carriers":[0,1,2,3,4,5], "fb":5},
}

def default_op(level=99, coarse=1, detune=0, rates=None, levels=None, on=True):
    return {"on":on,"level":level,"coarse":coarse,"fine":0,"detune":detune,
            "rates":rates or [99,99,99,70],"levels":levels or [99,99,99,0]}

def make_patch(name, algo, feedback, ops, adsr=None):
    p = {"name":name,"algo":algo,"feedback":feedback,"ops":ops,"adsr":dict(adsr or DEFAULT_ADSR)}
    while len(p["ops"]) < 6:
        p["ops"].append(default_op(0,1,0,[99,99,99,99],[0,0,0,0],False))
    return ensure_adsr(p)

def off_ops(n=3):
    return [default_op(0,1,0,[99,99,99,99],[0,0,0,0],False) for _ in range(n)]

def make_jump_patch():
    return make_patch("Jump",2,7,[
        default_op(99,0,0,[80,40,30,55],[99,99,99,0]),
        default_op(80,0,3,[90,0,40,50],[99,0,0,0]),
        default_op(99,0,0,[80,40,30,60],[99,99,99,0]),
    ]+off_ops(3), {"a":0.02,"d":0.15,"s":0.9,"r":0.28})

def _simple(name, algo, fb, adsr=None):
    return make_patch(name, algo, fb, [default_op() for _ in range(6)], adsr)

FACTORY = [
    make_jump_patch(),
    make_patch("E.Piano",5,5,[
        default_op(99,1,0,[95,25,25,50],[99,75,0,0]), default_op(70,14,2,[99,40,30,50],[99,60,0,0]),
        default_op(80,1,-2,[90,30,25,55],[99,70,0,0]), default_op(55,1,3,[99,35,30,50],[99,40,0,0]),
        default_op(40,1,0,[99,20,20,40],[99,30,0,0]), default_op(35,1,0,[99,15,20,40],[99,20,0,0]),
    ], {"a":0.005,"d":0.35,"s":0.25,"r":0.35}),
    _simple("Tight Piano",5,4,{"a":0.003,"d":0.22,"s":0.15,"r":0.22}),
    _simple("Tubular Bell",16,3,{"a":0.005,"d":0.8,"s":0.35,"r":1.2}),
    _simple("Marimba",5,2,{"a":0.004,"d":0.18,"s":0.05,"r":0.18}),
    _simple("Music Box",16,1,{"a":0.005,"d":0.6,"s":0.4,"r":0.9}),
    _simple("Vibraphone",5,3,{"a":0.01,"d":0.45,"s":0.4,"r":0.7}),
    _simple("Jazz Organ",32,2,{"a":0.01,"d":0.05,"s":1.0,"r":0.08}),
    _simple("Church Organ",32,1,{"a":0.04,"d":0.08,"s":1.0,"r":0.35}),
    _simple("FM Bass",18,6,{"a":0.01,"d":0.2,"s":0.7,"r":0.18}),
    _simple("Slap Bass",18,5,{"a":0.004,"d":0.12,"s":0.35,"r":0.12}),
    _simple("Jazz Flute",5,2,{"a":0.06,"d":0.12,"s":0.8,"r":0.2}),
    _simple("Pan Flute",5,1,{"a":0.08,"d":0.15,"s":0.75,"r":0.22}),
    _simple("Syn Brass",2,6,{"a":0.07,"d":0.18,"s":0.85,"r":0.3}),
    _simple("Trumpet",2,5,{"a":0.05,"d":0.14,"s":0.8,"r":0.22}),
    _simple("Alto Sax",18,4,{"a":0.06,"d":0.16,"s":0.82,"r":0.24}),
    _simple("Warm Strings",5,2,{"a":0.22,"d":0.35,"s":0.9,"r":0.6}),
    _simple("Choir Aahs",32,3,{"a":0.18,"d":0.3,"s":0.88,"r":0.55}),
    _simple("Soft Pad",5,2,{"a":0.35,"d":0.4,"s":0.92,"r":0.9}),
    _simple("Clavinet",5,6,{"a":0.003,"d":0.1,"s":0.45,"r":0.08}),
    _simple("Nylon Guitar",5,3,{"a":0.006,"d":0.28,"s":0.3,"r":0.32}),
    _simple("Steel Guitar",5,4,{"a":0.005,"d":0.25,"s":0.28,"r":0.28}),
    _simple("Tuba",18,4,{"a":0.05,"d":0.2,"s":0.85,"r":0.3}),
    _simple("INIT",1,0),
]

def one_pole(x, hz):
    x = np.asarray(x, np.float32)
    c = math.exp(-2.0 * math.pi * max(20.0, hz) / SAMPLE_RATE)
    y = np.empty_like(x); acc = 0.0; omc = 1.0 - c
    for i, s in enumerate(x):
        acc = acc * c + s * omc; y[i] = acc
    return y

def highpass(x, hz): return x - one_pole(x, hz)
def soft_clip(x, drive): return np.tanh(x * (1.0 + drive * 8.0)).astype(np.float32)
def hard_clip(x, drive): return np.clip(x * (2.0 + drive * 16.0), -1, 1).astype(np.float32)

def pitch_shift_buf(x, semi):
    if abs(semi) < 0.01: return x.astype(np.float32)
    ratio = 2.0 ** (semi / 12.0)
    n = len(x); idx = np.mod(np.arange(n) * ratio, max(1, n - 1))
    i0 = np.floor(idx).astype(np.int32); frac = idx - i0
    i1 = np.minimum(i0 + 1, n - 1)
    return (x[i0] * (1 - frac) + x[i1] * frac).astype(np.float32)

def comb_delay(x, delay_s, fb, mix):
    d = max(1, int(delay_s * SAMPLE_RATE))
    y = x.astype(np.float32).copy()
    for i in range(d, len(y)):
        y[i] += y[i - d] * fb
    return (x * (1 - mix) + y * mix).astype(np.float32)

def lfo(n, hz, ph=0.0):
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    return np.sin(TWO_PI * hz * t + ph)

def P(name, default, lo, hi): return (name, float(default), float(lo), float(hi))
def S(name, default=False): return (name, bool(default))
def E(eid, name, color, kind, params, switches=None):
    return {"id":eid,"name":name,"color":color,"kind":kind,"params":params,"switches":switches or []}

def short_label(name, n=5):
    s = re.sub(r"[^A-Za-z0-9]+", "", str(name))
    if not s: s = str(name)[:n]
    return s[:n].upper()

def luminance(color):
    r, g, b = color[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b

def pedal_ink(color):
    if luminance(color) >= 150:
        return (12, 16, 28), (20, 30, 90), (70, 20, 110)
    return (255, 255, 255), (255, 230, 70), (255, 140, 200)

def knob_style(pedal_color):
    """Dark enclosure → light knob + dark needle. Light enclosure → dark knob + white needle."""
    if luminance(pedal_color) < 150:
        # cream/light knob on a dark pedal
        return (236, 230, 214), (10, 22, 70), (40, 42, 50)  # fill, dark-blue needle, ring
    # dark knob on a light pedal
    return (28, 28, 32), (255, 255, 255), (210, 210, 210)

def knob_style14(pedal_color):
    """Dark enclosure → light knob + yellow/white needle. Light enclosure → dark knob + white needle."""
    if luminance(pedal_color) < 150:
        return (236, 230, 214), (255, 230, 80), (255, 255, 255)  # fill, needle, ring
    return (28, 28, 32), (255, 255, 255), (210, 210, 210)

EFFECT_DEFS = [
    E("nuxroct","NUX Roctary",(150,72,48),"nuxroct",[
        P("speed",3.2,0.2,10),P("balance",0.5,0,1),P("horn",0.55,0,1),P("drive",0.35,0,1),
        P("oct_mix",0.4,0,1),P("dry",0.65,0,1),P("tone",0.5,0,1),P("level",0.75,0,1),
    ],[S("fast"),S("poly",True),S("rotary",True)]),
    E("twdist","Mosky Audio TW Distortion",(22,22,24),"twdist",[
        P("gain",0.55,0,1),P("bass",0.5,0,1),P("mid",0.48,0,1),P("treble",0.52,0,1),
        P("presence",0.4,0,1),P("level",0.7,0,1),
    ],[S("modern")]),
    E("ph9","Behringer PH9",(190,20,25),"ph9",[P("rate",0.45,0.05,6)],[S("color")]),
    E("gain","Gain / Saturation",(180,50,20),"sat",[P("gain",0.4,0,1),P("sat",0.35,0,1),P("level",0.8,0,1)],[S("bright")]),
    E("cleanboost","Clean Boost",(220,220,200),"boost",[P("gain",0.25,0,1),P("level",0.85,0,1)],[S("buffer",True)]),
    E("trebleboost","Treble Boost",(240,220,80),"boost",[P("gain",0.4,0,1),P("freq",0.7,0.2,1),P("level",0.8,0,1)]),
    E("midboost","Mid Boost",(200,160,40),"boost",[P("gain",0.45,0,1),P("freq",0.45,0.2,0.8),P("q",0.4,0.1,1),P("level",0.8,0,1)]),
    E("preamp","Preamp Always-On",(140,90,40),"boost",[P("gain",0.3,0,1),P("bass",0.5,0,1),P("treble",0.55,0,1),P("level",0.8,0,1)],[S("bright")]),
    E("klon","Klon Overdrive",(190,170,90),"od",[P("gain",0.35,0,1),P("treble",0.55,0,1),P("level",0.75,0,1)],[S("buffer",True)]),
    E("bluesbreaker","BluesBreaker",(40,90,50),"od",[P("gain",0.4,0,1),P("tone",0.5,0,1),P("volume",0.75,0,1)]),
    E("tubescreamer","Tube Screamer Soft Clip",(40,160,70),"od",[P("drive",0.4,0,1),P("tone",0.5,0,1),P("level",0.75,0,1)],[S("mid_hump",True)]),
    E("rat","ProCo RAT",(18,18,18),"dist",[P("dist",0.55,0,1),P("filter",0.45,0.05,1),P("level",0.7,0,1)],[S("turbo")]),
    E("ds1","DS-1 Distortion",(230,80,20),"dist",[P("dist",0.5,0,1),P("tone",0.5,0,1),P("level",0.7,0,1)]),
    E("metal","High-Gain Metal",(80,20,20),"dist",[P("gain",0.75,0,1),P("scoop",0.4,0,1),P("presence",0.5,0,1),P("level",0.65,0,1)],[S("tight")]),
    E("bigmuff","Big Muff Fuzz",(200,40,40),"fuzz",[P("sustain",0.65,0,1),P("tone",0.45,0,1),P("volume",0.6,0,1)],[S("mids")]),
    E("fuzzface","Fuzz Face",(90,20,20),"fuzz",[P("fuzz",0.7,0,1),P("level",0.55,0,1)],[S("germanium",True)]),
    E("octavefuzz","Octave Fuzz",(120,30,80),"fuzz",[P("fuzz",0.6,0,1),P("oct",0.5,0,1),P("level",0.6,0,1)],[S("up"),S("down",True)]),
    E("superfuzz","Behringer Super Fuzz",(200,160,20),"fuzz",[P("fuzz",0.65,0,1),P("tone",0.4,0,1),P("level",0.6,0,1)],[S("expanse")]),
    E("ultravibe","Behringer Ultra Vibrato",(80,200,140),"vib",[P("speed",4.5,0.2,10),P("depth",0.4,0,1),P("mix",0.7,0,1)],[S("chorus_mode")]),
    E("fl9","Ibanez FL9",(40,200,210),"flange",[P("speed",0.3,0.05,2),P("width",0.45,0,1),P("regen",0.3,0,0.85),P("mix",0.5,0,1)],[S("manual")]),
    E("funkymonkey","Mooer Funky Monkey",(250,170,20),"wah",[P("sens",0.55,0,1),P("range",0.6,0,1),P("q",0.4,0.1,1)],[S("up"),S("auto",True)]),
    E("swollen","Swollen Pickle Fuzz",(90,140,40),"fuzz",[P("sustain",0.7,0,1),P("tone",0.4,0,1),P("crunch",0.5,0,1),P("volume",0.55,0,1)],[S("scoop")]),
    E("plexibox","Gokko Plexibox",(160,90,40),"amp",[P("gain",0.55,0,1),P("bass",0.5,0,1),P("mid",0.5,0,1),P("treble",0.55,0,1),P("presence",0.4,0,1),P("level",0.7,0,1)],[S("bright")]),
    E("ravish","EHX Ravish Sitar",(200,120,40),"sitar",[P("sympathetic",0.45,0,1),P("decay",0.5,0,1),P("level",0.7,0,1),P("mix",0.5,0,1)],[S("drone")]),
    E("csus","Behringer Comp Sustainer",(150,70,70),"comp",[P("sustain",0.5,0,1),P("attack",0.3,0,1),P("level",0.8,0,1)]),
    E("bitcrush","Bitcrusher / SR",(160,230,40),"bit",[P("bits",8,3,12),P("rate",0.55,0.1,1),P("mix",1,0,1)],[S("dither")]),
    E("complim","Compressor / Limiter / Sustainer",(150,80,80),"comp",[P("thresh",0.35,0.05,0.9),P("ratio",0.5,0.1,1),P("attack",0.2,0,1),P("release",0.4,0,1),P("level",0.85,0,1)],[S("limit")]),
    E("expander","Expander",(70,110,70),"dyn",[P("thresh",0.15,0,0.5),P("ratio",0.4,0.1,1)]),
    E("gate","Noise Gate / Suppressor",(50,80,50),"dyn",[P("thresh",0.08,0,0.4),P("decay",0.2,0.02,1)],[S("suppress")]),
    E("volpedal","Volume / Swell / Auto-Swell",(90,90,90),"vol",[P("level",1,0,1),P("swell",0.15,0,1)],[S("auto_swell")]),
    E("tremolo","Tremolo",(230,120,30),"trem",[P("rate",4.5,0.2,12),P("depth",0.55,0,1)],[S("optical",True),S("bias"),S("harmonic")]),
    E("transient","Transient Shaper",(200,90,50),"dyn",[P("attack",0.4,0,1),P("sustain",0.4,0,1)]),
    E("geq","Graphic EQ",(90,110,140),"eq",[P("32",0.5,0,1),P("64",0.5,0,1),P("125",0.5,0,1),P("250",0.5,0,1),P("500",0.5,0,1),P("1k",0.5,0,1),P("2k",0.5,0,1),P("4k",0.5,0,1),P("8k",0.5,0,1),P("16k",0.5,0,1)]),
    E("peq6","6-Param EQ",(80,120,150),"eq",[P("f1",0.2,0,1),P("g1",0.5,0,1),P("f2",0.5,0,1),P("g2",0.5,0,1),P("f3",0.8,0,1),P("g3",0.5,0,1)]),
    E("peq10","10-Param EQ",(70,130,160),"eq",[P(f"p{i}",0.5,0,1) for i in range(1,11)]),
    E("peq20","20-Param EQ",(60,140,170),"eq",[P(f"p{i}",0.5,0,1) for i in range(1,21)]),
    E("exciter","Enhancer / Exciter",(240,200,80),"excite",[P("harm",0.35,0,1),P("mix",0.3,0,1)]),
    E("wah","Cry Baby Wah",(255,140,0),"wah",[P("pos",0.4,0,1),P("q",0.45,0.1,1)],[S("vocal")]),
    E("autowah","Auto-Wah / Env Filter",(250,170,20),"wah",[P("sens",0.55,0,1),P("range",0.6,0,1),P("q",0.4,0.1,1),P("rate",2.2,0.2,8)],[S("up")]),
    E("qfilter","Fixed / Q Resonant Filter",(230,200,40),"tone",[P("cutoff",0.5,0.05,1),P("q",0.4,0.05,1)],[S("hp")]),
    E("talkbox","Talk Box",(220,80,140),"form",[P("vowel",0.4,0,1),P("mix",0.45,0,1)]),
    E("formant","Synth / Formant Filter",(180,60,160),"form",[P("form",0.4,0,1),P("res",0.4,0,1),P("mix",0.4,0,1)]),
    E("chorus","Fab Chorus",(40,90,210),"chorus",[P("rate",0.35,0.05,2),P("depth",0.35,0,1),P("mix",0.4,0,1)],[S("stereo_spread")]),
    E("flanger","Flanger",(40,200,210),"flange",[P("rate",0.25,0.05,2),P("depth",0.4,0,1),P("fb",0.35,0,0.8)]),
    E("phaser","Phaser EVH",(190,20,25),"phase",[P("rate",0.4,0.05,4),P("depth",0.6,0,1),P("fb",0.3,0,0.8)]),
    E("vibrato","Vibrato",(80,200,140),"vib",[P("rate",5,0.5,10),P("depth",0.25,0,1)]),
    E("univibe","Uni-Vibe",(90,50,140),"vibe",[P("speed",3.2,0.2,8),P("depth",0.5,0,1),P("mix",0.6,0,1)],[S("chorus_mode",True)]),
    E("rotary","Rotary / Leslie",(160,90,40),"rot",[P("rate",3.5,0.4,8),P("depth",0.45,0,1),P("horn",0.5,0,1)],[S("brake")]),
    E("ringmod","Ring Modulator",(0,180,90),"ring",[P("freq",220,20,800),P("mix",0.35,0,1)]),
    E("freqshift","Frequency Shifter",(0,160,120),"ring",[P("shift",80,0,400),P("mix",0.3,0,1)]),
    E("autopan","Auto-Panner",(100,140,200),"trem",[P("rate",1.5,0.1,8),P("depth",0.7,0,1)]),
    E("harmtrem","Harmonic Tremolo",(230,100,40),"trem",[P("rate",4,0.2,10),P("depth",0.5,0,1)]),
    E("octave","Octave POG-style",(40,70,40),"oct",[P("down1",0.4,0,1),P("down2",0.2,0,1),P("up1",0.2,0,1),P("dry",0.7,0,1)],[S("tracking",True)]),
    E("pitch","Pitch Shifter",(20,160,160),"pitch",[P("semi",0,-12,12),P("mix",1,0,1)]),
    E("harmonizer","Harmonizer",(255,90,170),"harm",[P("semi",7,-12,12),P("mix",0.4,0,1)],[S("key_aware")]),
    E("whammy","Whammy Bend",(255,50,50),"pitch",[P("start",0,-12,12),P("end",12,-12,12),P("mix",1,0,1)]),
    E("detune","Detune",(60,140,180),"chorus",[P("cents",0.25,0,1),P("mix",0.35,0,1)]),
    E("delay","Delay / Echo",(70,40,160),"delay",[P("time",0.28,0.05,0.8),P("fb",0.35,0,0.9),P("mix",0.3,0,1)],[S("tape"),S("analog"),S("reverse"),S("pingpong"),S("mod"),S("shimmer")]),
    E("reverb","Reverb",(120,40,180),"verb",[P("mix",0.28,0,1),P("decay",0.45,0.05,0.95),P("size",0.35,0.05,1)],[S("spring"),S("plate"),S("hall",True),S("room"),S("cathedral"),S("shimmer"),S("freeze"),S("gated"),S("reverse")]),
    E("looper","Looper",(50,50,70),"util",[P("level",1,0,1)],[S("overdub")]),
    E("freeze","Freeze / Infinite Sustain",(140,80,200),"verb",[P("mix",0.5,0,1),P("hold",0.7,0,1)],[S("pad")]),
    E("granular","Granular / Glitch / Stutter",(180,40,120),"glitch",[P("size",0.25,0.02,0.6),P("spray",0.3,0,1),P("mix",0.4,0,1)],[S("stutter")]),
    E("acoustic","Acoustic Simulator",(200,180,120),"cab",[P("body",0.5,0,1),P("air",0.4,0,1),P("level",0.8,0,1)]),
    E("ampsim","Amp Sim / Preamp Modeler",(120,70,30),"amp",[P("gain",0.5,0,1),P("bass",0.5,0,1),P("mid",0.5,0,1),P("treble",0.55,0,1),P("level",0.75,0,1)],[S("amp_on",True)]),
    E("cabsim","Cabinet / IR Loader",(90,60,30),"cab",[P("body",0.55,0,1),P("edge",0.35,0,1)],[S("ir",True)]),
    E("microom","Speaker / Mic / Room",(100,80,50),"cab",[P("mic",0.4,0,1),P("room",0.25,0,1)]),
    E("multifx","Multi-FX Rack",(80,80,120),"combo",[P("a",0.4,0,1),P("b",0.4,0,1),P("c",0.4,0,1)],[S("series",True)]),
    E("tuner","Tuner",(20,20,20),"util",[P("ref",440,430,450)],[S("mute")]),
    E("buffer","Buffer",(80,80,80),"util",[P("level",1,0,1)],[S("true_bypass")]),
    E("abswitch","A/B Switcher / Loop",(70,70,90),"util",[P("mix",1,0,1)],[S("path_b")]),
    E("expr","Expression Pedal",(50,50,50),"util",[P("sweep",0.5,0,1)]),
    E("psu","Isolated Power",(40,40,40),"util",[P("hum",0,0,0.2)]),
    E("wireless","Wireless / MIDI Ctrl",(40,60,90),"util",[P("latency",0.1,0,1)]),
    E("wahfuzz","Wah-Fuzz",(180,80,20),"fuzz",[P("fuzz",0.55,0,1),P("pos",0.4,0,1),P("level",0.6,0,1)]),
    E("fuzzfilter","Fuzz + Filter",(160,50,40),"fuzz",[P("fuzz",0.55,0,1),P("cutoff",0.45,0.05,1),P("level",0.6,0,1)]),
    E("dlyverb","Delay + Reverb",(100,50,170),"combo",[P("time",0.25,0.05,0.7),P("decay",0.4,0.05,0.95),P("mix",0.35,0,1)]),
    E("tremverb","Tremolo + Reverb",(160,60,140),"combo",[P("rate",4,0.2,10),P("decay",0.4,0.05,0.9),P("mix",0.35,0,1)]),
    E("odboost","Overdrive + Boost",(50,140,60),"combo",[P("drive",0.4,0,1),P("boost",0.3,0,1),P("level",0.8,0,1)]),
    E("compod","Compressor + Overdrive",(80,120,70),"combo",[P("comp",0.4,0,1),P("drive",0.35,0,1),P("level",0.8,0,1)]),
    E("synoct","Synth + Octave",(120,40,140),"combo",[P("oct",0.4,0,1),P("form",0.4,0,1),P("mix",0.4,0,1)]),
    E("grandly","Granular Delay",(160,40,100),"glitch",[P("time",0.22,0.05,0.6),P("size",0.2,0.02,0.5),P("mix",0.35,0,1)]),
    E("specfreeze","Spectral Freeze",(140,70,190),"verb",[P("mix",0.5,0,1),P("blur",0.4,0,1)]),
    E("vocoder","Vocoder-style",(200,70,160),"form",[P("bands",0.5,0.1,1),P("mix",0.45,0,1)]),
    E("overdrive","Classic Overdrive",(30,150,50),"od",[P("drive",0.4,0,1),P("tone",0.55,0,1),P("level",0.8,0,1)]),
    E("tube","Tube Distortion",(200,110,30),"dist",[P("heat",0.5,0,1),P("bias",0.15,0,0.5),P("level",0.75,0,1)]),
    E("eightbit","8-Bit",(160,230,40),"bit",[P("bits",8,3,12),P("rate",0.55,0.1,1)]),
    E("tape","Tape Echo",(140,100,60),"delay",[P("time",0.22,0.08,0.55),P("wow",0.25,0,1),P("mix",0.32,0,1)]),
    E("slapback","Slapback",(180,80,40),"delay",[P("time",0.09,0.03,0.2),P("mix",0.35,0,1)]),
    E("lofi","Lo-Fi",(110,90,70),"bit",[P("crush",0.4,0,1),P("noise",0.08,0,0.4)]),
    E("comb","Comb Filter",(200,60,120),"tone",[P("freq",0.35,0.05,1),P("fb",0.45,0,0.9)]),
    E("sat2","Soft Saturation",(180,50,20),"sat",[P("drive",0.45,0,1),P("mix",0.6,0,1)]),
]
FX_INDEX = {e["id"]: e for e in EFFECT_DEFS}

def default_fx_state():
    return {e["id"]: {"on": False,
                     "params": {p[0]: p[1] for p in e["params"]},
                     "switches": {s[0]: s[1] for s in e["switches"]}} for e in EFFECT_DEFS}

def apply_effect(x, e, st):
    x = np.asarray(x, np.float32)
    p, sw, kind = st.get("params", {}), st.get("switches", {}), e["kind"]
    g = lambda k, d=0.5: float(p.get(k, d))
    if kind == "twdist":
        y = highpass(x, 70 if sw.get("modern") else 90)
        drive = 6.0 + g("gain") * (22.0 if sw.get("modern") else 12.0)
        y = np.tanh(y * drive) if not sw.get("modern") else np.clip(y * drive, -1, 1)
        lo = one_pole(y, 180) * (0.4 + g("bass") * 1.2)
        mid = (y - one_pole(y, 250) - (y - one_pole(y, 1800))) * (0.4 + g("mid") * 1.3)
        hi = highpass(y, 2200) * (0.3 + g("treble") * 1.2)
        y = lo + mid + hi + highpass(y, 4500) * g("presence") * 0.5
        if sw.get("modern"): y = highpass(y, 140)
        return (y * g("level")).astype(np.float32)
    if kind == "nuxroct":
        rate = g("speed") * (1.85 if sw.get("fast") else 1.0)
        y = soft_clip(x, g("drive"))
        horn = y * (1.0 - g("horn") * 0.35 * (0.5 + 0.5 * lfo(len(y), rate)))
        drum = one_pole(y, 280) * (0.5 + 0.5 * lfo(len(y), rate * 0.5, 1.2))
        rot = horn * g("balance") + drum * (1.0 - g("balance"))
        if not sw.get("rotary"): rot = y
        octv = pitch_shift_buf(x, -12.0)
        if sw.get("poly"): octv = octv + pitch_shift_buf(x, 12.0) * 0.35
        mix = rot * g("dry") + octv * g("oct_mix")
        return (one_pole(mix, 400 + g("tone") * 5000) * g("level")).astype(np.float32)
    if kind == "ph9":
        stages = 6 if sw.get("color") else 4
        y = x.copy()
        for _ in range(stages):
            y = x + highpass(y, 280) * 0.35
        wob = 0.5 + 0.5 * lfo(len(x), g("rate"))
        return (x * 0.45 + y * wob * 0.55).astype(np.float32)
    if kind in ("boost","sat","od"):
        y = soft_clip(x, g("gain", g("drive", 0.4)))
        if sw.get("mid_hump") or e["id"]=="tubescreamer": y = y + one_pole(x, 700) * 0.25
        if sw.get("bright"): y = y + highpass(x, 2500) * 0.15
        return one_pole(y, 800 + g("tone", g("treble", 0.5)) * 5000) * g("level", g("volume", 0.8))
    if kind == "dist":
        y = hard_clip(highpass(x, 90), g("dist", g("gain", 0.55)))
        if sw.get("tight"): y = highpass(y, 160)
        return one_pole(y, 400 + g("filter", g("tone", 0.45)) * 4000) * g("level", 0.7)
    if kind == "fuzz":
        y = np.sign(x) * (1 - np.exp(-np.abs(x) * (6 + g("fuzz", g("sustain", 0.6)) * 20)))
        if sw.get("down") or g("oct", 0) > 0.05:
            y = y * (1 - g("oct", 0.3)) + pitch_shift_buf(y, -12) * g("oct", 0.3)
        if sw.get("up"): y = y * 0.7 + pitch_shift_buf(x, 12) * 0.3
        return (one_pole(y, 600 + g("tone", 0.45) * 3500) * g("level", g("volume", 0.6))).astype(np.float32)
    if kind == "comp":
        env = one_pole(np.abs(x), 30 + (1 - g("attack", 0.3)) * 80)
        gain = np.where(env > g("thresh", 0.35), g("thresh", 0.35) / (env + 1e-6), 1.0)
        gain = 1.0 - (1.0 - gain) * g("ratio", g("sustain", 0.5))
        return (x * gain * g("level", 0.85)).astype(np.float32)
    if kind == "dyn":
        env = one_pole(np.abs(x), 80)
        if e["id"] == "expander":
            return (x * np.clip((env / (g("thresh", 0.15) + 1e-6)) ** g("ratio", 0.4), 0, 1)).astype(np.float32)
        return (x * (env > g("thresh", 0.08)).astype(np.float32)).astype(np.float32)
    if kind == "vol":
        env = np.clip(np.linspace(0, 1, len(x)) / max(0.01, g("swell", 0.15)), 0, 1) if sw.get("auto_swell") else 1.0
        return (x * g("level", 1) * env).astype(np.float32)
    if kind == "trem":
        return (x * (1.0 - g("depth", 0.5) * 0.5 * (1 + lfo(len(x), g("rate", 4))))).astype(np.float32)
    if kind == "eq":
        tilt = float(np.mean(list(p.values()) or [0.5]))
        return (one_pole(x, 200 + tilt * 6000) * (0.6 + tilt * 0.8)).astype(np.float32)
    if kind in ("tone","cab"):
        y = one_pole(x, 200 + g("cutoff", g("body", 0.5)) * 7000)
        if sw.get("hp"): y = highpass(x, 200 + g("cutoff", 0.4) * 2000)
        return (y + highpass(x, 1800) * g("edge", g("air", 0.3)) * 0.3).astype(np.float32)
    if kind == "wah":
        return one_pole(x, 300 + g("pos", g("range", 0.5)) * 2200).astype(np.float32)
    if kind == "form":
        y = one_pole(x, 400 + g("vowel", g("form", 0.4)) * 1800)
        return x * (1 - g("mix", 0.4)) + y * g("mix", 0.4)
    if kind in ("chorus","vibe"):
        d = int((0.003 + g("depth", 0.35) * 0.012) * SAMPLE_RATE)
        idx = np.clip(np.arange(len(x)) - (lfo(len(x), g("rate", 0.35)) * 0.5 + 0.5) * d, 0, len(x)-1).astype(np.int32)
        return x * (1 - g("mix", 0.4)) + x[idx] * g("mix", 0.4)
    if kind == "flange":
        return comb_delay(x, 0.002 + g("depth", g("width", 0.4)) * 0.006, g("fb", g("regen", 0.3)), g("mix", 0.5))
    if kind == "phase":
        y = x + highpass(x, 250 + g("depth", 0.6) * 800) * (0.3 + g("fb", 0.3) * 0.4)
        return (x * 0.5 + y * (0.5 + 0.5 * lfo(len(x), g("rate", 0.4))) * 0.5).astype(np.float32)
    if kind == "vib":
        d = int(g("depth", 0.25) * 0.008 * SAMPLE_RATE) + 1
        idx = np.clip(np.arange(len(x)) + lfo(len(x), g("rate", 5)) * d, 0, len(x)-1).astype(np.int32)
        return x[idx]
    if kind == "rot":
        amp = 1.0 - g("depth", 0.45) * 0.4 * (0.5 + 0.5 * lfo(len(x), 0.2 if sw.get("brake") else g("rate", 3.5)))
        y = x * amp
        if g("oct", 0) > 0.05 or sw.get("poly"):
            y = y * (1 - g("oct", 0.3)) + pitch_shift_buf(x, -12) * g("oct", 0.3)
        return y.astype(np.float32)
    if kind == "ring":
        return x * (1 - g("mix", 0.35)) + x * lfo(len(x), g("freq", g("shift", 220))) * g("mix", 0.35)
    if kind in ("oct","pitch","harm"):
        if kind == "oct":
            wet = pitch_shift_buf(x,-12)*g("down1",0.4)+pitch_shift_buf(x,-24)*g("down2",0.2)+pitch_shift_buf(x,12)*g("up1",0.2)
            return x * g("dry", 0.7) + wet
        return x * (1 - g("mix", 0.5)) + pitch_shift_buf(x, g("semi", 7)) * g("mix", 0.5)
    if kind == "delay":
        y = comb_delay(x, g("time", 0.28), g("fb", 0.35), g("mix", 0.3))
        if sw.get("reverse"): y = comb_delay(x[::-1].copy(), g("time", 0.28), 0.2, g("mix", 0.3))[::-1]
        if sw.get("shimmer"): y = y + pitch_shift_buf(y, 12) * 0.2
        return y
    if kind == "verb":
        y = comb_delay(x, 0.03 + g("size", 0.35) * 0.05, 0.4 + g("decay", 0.45) * 0.4, 1)
        y = comb_delay(y, 0.041, 0.35 + g("decay", 0.45) * 0.35, 1)
        if sw.get("shimmer") or sw.get("freeze"): y = y + pitch_shift_buf(y, 12) * 0.15
        return x * (1 - g("mix", 0.28)) + one_pole(y, 2800) * g("mix", 0.28)
    if kind == "bit":
        bits = int(g("bits", 8)); step = 2.0 ** (1 - bits)
        dec = max(1, int((1.1 - g("rate", 0.55)) * 12))
        y = np.repeat(np.round(x[::dec] / step) * step, dec)[:len(x)]
        return y.astype(np.float32)
    if kind == "glitch":
        n = max(32, int(g("size", 0.25) * SAMPLE_RATE * 0.2)); y = x.copy()
        for i in range(0, len(y)-n, n):
            if sw.get("stutter") or np.random.rand() < g("spray", 0.3): y[i:i+n] = x[i]
        return x * (1 - g("mix", 0.4)) + y * g("mix", 0.4)
    if kind == "amp":
        return one_pole(soft_clip(x, g("gain", 0.5)), 300 + g("treble", 0.55) * 4000) * g("level", 0.75)
    if kind == "excite":
        return x + highpass(soft_clip(x, 0.3), 3000) * g("harm", 0.35) * g("mix", 0.3)
    if kind == "sitar":
        return comb_delay(x, 0.012 + g("decay", 0.5) * 0.02, 0.5 + g("sympathetic", 0.45) * 0.3, g("mix", 0.5)) * g("level", 0.7)
    if kind == "combo":
        y = apply_effect(x, FX_INDEX.get("overdrive", e), {"params":{"drive":g("drive",g("a",0.4)),"tone":0.5,"level":1},"switches":{}})
        return apply_effect(y, FX_INDEX.get("reverb", e), {"params":{"mix":g("mix",0.3),"decay":g("decay",0.4),"size":0.4},"switches":{}})
    if kind == "util":
        return x * (0 if sw.get("mute") else g("level", 1.0))
    return x

def apply_fx_chain(x, fx_state, chain):
    y = np.asarray(x, np.float32).copy()
    for fid in chain:
        e, st = FX_INDEX.get(fid), fx_state.get(fid)
        if e and st and st.get("on"):
            y = apply_effect(y, e, st)
    pk = float(np.max(np.abs(y))) + 1e-9
    if pk > 1: y *= 0.97 / pk
    return y.astype(np.float32)

class Envelope:
    def __init__(self, rates, levels, out_level):
        self.rates=[max(0,min(99,r)) for r in rates]
        self.levels=[max(0,min(99,lv))/99.0 for lv in levels]
        self.out=max(0,min(99,out_level))/99.0
        self.stage=0; self.level=0.0; self.released=False; self.done=False
        self._set_target(0)
    def _set_target(self, st):
        self.stage=st; self.target=self.levels[st]
        r=self.rates[st]/99.0; self.coeff=1.0-math.exp(-1.0/((0.003+(1-r)**2*3.5)*SAMPLE_RATE))
    def step(self):
        if self.done: return 0.0
        self.level += (self.target-self.level)*self.coeff
        if abs(self.target-self.level)<0.002:
            self.level=self.target
            if not self.released and self.stage<2: self._set_target(self.stage+1)
        return self.level*self.out

def make_loopable(buf):
    xfade=max(64,min(int(SAMPLE_RATE*XFADE_SEC),(len(buf)//4)*2))
    skip=min(int(SAMPLE_RATE*0.35), len(buf)//5)
    body=buf[skip:].astype(np.float32, copy=True)
    if len(body)<=xfade*2: body=buf.astype(np.float32, copy=True)
    fo=np.cos(np.linspace(0,math.pi*0.5,xfade,dtype=np.float32))
    fi=np.sin(np.linspace(0,math.pi*0.5,xfade,dtype=np.float32))
    looped=np.concatenate([body[xfade:-xfade], body[-xfade:]*fo+body[:xfade]*fi])
    looped-=float(np.mean(looped))
    pk=float(np.max(np.abs(looped)))+1e-9
    if pk>1: looped*=0.97/pk
    return looped.astype(np.float32)

def render_note_first_iteration(patch, midi_note, seconds=NOTE_SECONDS, velocity=110):
    n=int(SAMPLE_RATE*seconds); vel=velocity/127.0
    algo=ALGORITHMS.get(patch["algo"], ALGORITHMS[2])
    fb_amt=(patch.get("feedback",0)/7.0)**2*4.0
    base=midi_to_hz(midi_note)
    phase=[0.0]*6; inc=[0.0]*6; envs=[]; last=[0.0]*6
    for i,op in enumerate(patch["ops"]):
        ratio=coarse_ratio(op["coarse"])*(1.0+op.get("fine",0)/1000.0)
        det=op.get("detune",0)*0.03
        inc[i]=TWO_PI*base*ratio*(2.0**(det/12.0))/SAMPLE_RATE
        envs.append(Envelope(op["rates"], op["levels"], op["level"] if op.get("on",True) else 0))
    mods,carriers,fb_op=algo["mod"],algo["carriers"],algo["fb"]
    out=np.zeros(n,np.float32)
    for i in range(n):
        env=[e.step() for e in envs]; vals=[0.0]*6
        for opi in (5,4,3,2,1,0):
            mod=sum(vals[s] for s in mods[opi])
            if opi==fb_op and fb_amt>0: mod+=last[opi]*fb_amt
            vals[opi]=math.sin(phase[opi]+mod)*env[opi]*(1.2 if opi not in carriers else 1.0)
            phase[opi]+=inc[opi]
            if phase[opi]>TWO_PI*8: phase[opi]-=TWO_PI*8
        last=vals; out[i]=sum(vals[c] for c in carriers)
    pk=float(np.max(np.abs(out)))+1e-9
    if pk>1.5: out*=1.5/pk
    out*=0.22*(0.3+0.7*vel); np.clip(out,-1,1,out=out)
    return make_loopable(out)

def pcm_sound(samples):
    pcm=np.clip(samples*32767,-32767,32767).astype(np.int16)
    return pygame.mixer.Sound(buffer=memoryview(pcm).tobytes()), samples

def save_tone_file(path, waves):
    payload={"notes":np.array(sorted(waves.keys()),np.int16)}
    for n,w in waves.items(): payload[f"n{n}"]=w.astype(np.float32)
    np.savez_compressed(path, **payload)

def load_tone_file(path, needed):
    try: data=np.load(path, allow_pickle=False)
    except Exception: return None
    waves={}
    for n in needed:
        if f"n{n}" not in data: return None
        waves[n]=data[f"n{n}"].astype(np.float32)
    return waves

def patch_fingerprint(p):
    q=deepcopy(p); q.pop("adsr",None); return json.dumps(q, sort_keys=True)

COL_BG,COL_PANEL,COL_ACCENT,COL_ORANGE=(18,20,28),(32,36,48),(90,200,255),(255,160,60)
COL_TEXT,COL_DIM,COL_KEY,COL_KEY_BLK=(230,232,240),(140,146,160),(245,245,248),(20,20,24)
COL_KEY_ON,COL_KEY_UNMAPPED=(255,190,70),(90,92,100)
GRAPH_Y,GRAPH_H=200,150

class PlayingNote:
    def __init__(self, note, sound, channel, adsr, wave):
        self.note,self.sound,self.channel,self.wave=note,sound,channel,wave
        self.a=max(0.001,float(adsr["a"])); self.d=max(0.001,float(adsr["d"]))
        self.s=max(0.0,min(1.0,float(adsr["s"]))); self.r=max(0.001,float(adsr["r"]))
        self.t=self.release_t=self.level=self.release_from=self.pos=0.0
        self.released=self.done=False; self._apply(0.0)
    def owns_channel(self):
        try: return self.channel is not None and self.channel.get_sound() is self.sound
        except Exception: return False
    def current_level(self):
        if not self.released:
            if self.t<self.a: return self.t/self.a
            if self.t<self.a+self.d: return 1.0+(self.s-1.0)*((self.t-self.a)/self.d)
            return self.s
        u=self.release_t/self.r
        return 0.0 if u>=1 else self.release_from*(1-u)
    def _apply(self, vol):
        self.level=max(0.0,min(1.0,vol))
        if self.owns_channel():
            try: self.channel.set_volume(self.level)
            except Exception: pass
    def stop_now(self):
        self.done=True
        if self.owns_channel():
            try: self.channel.stop()
            except Exception: pass
        self.channel=None
    def update(self, dt):
        if self.done: return
        if not self.owns_channel():
            self.done=True; self.channel=None; return
        if not self.released: self.t+=dt
        else: self.release_t+=dt
        if self.wave is not None and len(self.wave):
            self.pos=(self.pos+dt*SAMPLE_RATE)%len(self.wave)
        vol=self.current_level(); self._apply(vol)
        if self.released and vol<=0.0005: self.stop_now()
    def note_off(self):
        if self.released or self.done: return
        self.release_from=max(0.0001,self.current_level()); self.released=True; self.release_t=0.0

class Slider:
    def __init__(self, rect, vmin, vmax, value, label):
        self.rect=pygame.Rect(rect); self.vmin,self.vmax,self.value,self.label=vmin,vmax,value,label
        self.dragging=False
    def _set(self,x):
        t=max(0.0,min(1.0,(x-self.rect.x)/max(1,self.rect.w)))
        self.value=self.vmin+t*(self.vmax-self.vmin)
    def handle(self,ev):
        if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1 and self.rect.inflate(0,8).collidepoint(ev.pos):
            self.dragging=True; self._set(ev.pos[0]); return True
        if ev.type==pygame.MOUSEBUTTONUP and ev.button==1: self.dragging=False
        if ev.type==pygame.MOUSEMOTION and self.dragging:
            self._set(ev.pos[0]); return True
        return False
    def draw(self,surf,font):
        pygame.draw.rect(surf,(20,22,30),self.rect,border_radius=3)
        t=(self.value-self.vmin)/max(1e-6,self.vmax-self.vmin)
        pygame.draw.rect(surf,(70,120,150),pygame.Rect(self.rect.x,self.rect.y,int(self.rect.w*t),self.rect.h),border_radius=3)
        pygame.draw.rect(surf,COL_ACCENT,self.rect,1,border_radius=3)
        pygame.draw.circle(surf,COL_ORANGE,(self.rect.x+int(self.rect.w*t),self.rect.centery),5)
        surf.blit(font.render(f"{self.label} {self.value:.3f}",True,COL_TEXT),(self.rect.x,self.rect.y-14))

class Button:
    def __init__(self, rect, label, action=None):
        self.rect=pygame.Rect(rect); self.label,self.action,self.on=label,action,False
    def draw(self,surf,font):
        pygame.draw.rect(surf,(40,130,160) if self.on else (60,90,120),self.rect,border_radius=6)
        pygame.draw.rect(surf,COL_ACCENT,self.rect,1,border_radius=6)
        t=font.render(self.label,True,COL_TEXT); surf.blit(t,t.get_rect(center=self.rect.center))
    def click(self,pos):
        if self.rect.collidepoint(pos) and self.action:
            self.action(); return True
        return False

class Dropdown:
    def __init__(self, rect):
        self.rect=pygame.Rect(rect); self.open=False; self.scroll=0; self.row_h=24; self.max_rows=12; self._open_fp=None
    def list_rect(self,n): return pygame.Rect(self.rect.x,self.rect.bottom,self.rect.w,min(self.max_rows,n)*self.row_h)
    def handle(self, event, app):
        n=len(app.patches)
        if event.type==pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.open=not self.open
                if self.open: self._open_fp=patch_fingerprint(app.patch)
                else: self.close(app)
                return True
            if self.open:
                lr=self.list_rect(n)
                if lr.collidepoint(event.pos):
                    idx=self.scroll+(event.pos[1]-lr.y)//self.row_h
                    if 0<=idx<n: app.select_loaded_patch(idx)
                    self.close(app); return True
                self.close(app); return True
        if event.type==pygame.MOUSEWHEEL and self.open:
            self.scroll=max(0,min(max(0,n-self.max_rows),self.scroll-event.y)); return True
        return False
    def close(self, app):
        was=self.open; self.open=False
        if was and patch_fingerprint(app.patch)!=self._open_fp: app.load_or_build_tones()
        self._open_fp=None
    def draw(self,surf,font,small,app):
        pygame.draw.rect(surf,(40,48,64),self.rect,border_radius=6)
        pygame.draw.rect(surf,COL_ACCENT,self.rect,1,border_radius=6)
        surf.blit(small.render(f"{app.patch_index+1:02d}  {app.patch['name']}"[:28],True,COL_TEXT),(self.rect.x+8,self.rect.y+5))
        if not self.open: return
        n=len(app.patches); lr=self.list_rect(n)
        pygame.draw.rect(surf,(16,18,26),lr); pygame.draw.rect(surf,COL_ACCENT,lr,1)
        for i in range(min(self.max_rows,n)):
            idx=self.scroll+i
            if idx>=n: break
            row=pygame.Rect(lr.x,lr.y+i*self.row_h,lr.w,self.row_h)
            if idx==app.patch_index: pygame.draw.rect(surf,(50,70,90),row)
            surf.blit(small.render(f"{idx+1:02d}  {app.patches[idx]['name']}"[:30],True,COL_TEXT),(row.x+8,row.y+4))

class PatchDialog:
    def __init__(self, app):
        self.app=app; self.visible=False; self.mode="edit"; self.name=""
    def open(self, mode="edit"):
        self.app.capture_patch_state(); self.visible=True; self.mode=mode; self.name=self.app.patch["name"]
    def handle(self, event):
        if not self.visible: return False
        if event.type==pygame.KEYDOWN:
            if event.key==pygame.K_ESCAPE: self.visible=False; return True
            if event.key==pygame.K_RETURN:
                self.app.patch["name"]=self.name or self.app.patch["name"]
                self.app.capture_patch_state()
                if self.mode=="create":
                    self.app.patches.insert(0,deepcopy(self.app.patch)); self.app.patch_index=0
                    self.app.save_bank(); self.app.load_or_build_tones(force=True)
                else:
                    self.app.patches[self.app.patch_index]=deepcopy(self.app.patch); self.app.save_bank()
                self.visible=False; return True
            if event.key==pygame.K_BACKSPACE: self.name=self.name[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.name)<16: self.name+=event.unicode
            return True
        if event.type==pygame.MOUSEBUTTONDOWN:
            w,h=self.app.screen.get_size(); r=pygame.Rect((w-520)//2,(h-300)//2,520,300)
            if not r.collidepoint(event.pos): self.visible=False
            return True
        return True
    def draw(self,surf,font,small):
        if not self.visible: return
        ov=pygame.Surface(surf.get_size(),pygame.SRCALPHA); ov.fill((0,0,0,160)); surf.blit(ov,(0,0))
        w,h=self.app.screen.get_size(); r=pygame.Rect((w-520)//2,(h-300)//2,520,300)
        pygame.draw.rect(surf,COL_PANEL,r,border_radius=10); pygame.draw.rect(surf,COL_ACCENT,r,2,border_radius=10)
        surf.blit(font.render(self.mode.upper(),True,COL_ORANGE),(r.x+20,r.y+16))
        pygame.draw.rect(surf,(20,22,30),pygame.Rect(r.x+20,r.y+70,360,28),border_radius=4)
        surf.blit(font.render(self.name+"_",True,COL_TEXT),(r.x+28,r.y+74))

class EffectsDialog:
    ROW = 22
    KNOBS_VIS = 6
    def __init__(self, app):
        self.app=app; self.visible=False; self.sel=0; self.scroll=0; self.pscr=0
        self.chain_open=False; self.chain_scroll=0
        self.search=""; self.search_focus=False
        self.sliders=[]
        self._rebuild()

    def open(self):
        self.visible=True; self.search=""; self.scroll=0; self.pscr=0; self._rebuild()

    def filtered(self):
        q = self.search.strip().lower()
        if not q: return list(range(len(EFFECT_DEFS)))
        return [i for i,e in enumerate(EFFECT_DEFS) if q in e["name"].lower() or q in e["id"].lower()]

    def max_pscr(self):
        return max(0, len(EFFECT_DEFS[self.sel]["params"]) - self.KNOBS_VIS)

    def visible_rows(self):
        return max(1, self.list_rect().h // self.ROW)

    def ensure_sel_visible(self):
        ids = self.filtered()
        if self.sel not in ids:
            self.sel = ids[0] if ids else 0
            return
        pos = ids.index(self.sel)
        vis = self.visible_rows()
        if pos < self.scroll: self.scroll = pos
        if pos >= self.scroll + vis: self.scroll = pos - vis + 1

    def move_sel(self, delta):
        ids = self.filtered()
        if not ids: return
        if self.sel not in ids:
            self.sel = ids[0]
        else:
            self.sel = ids[max(0, min(len(ids)-1, ids.index(self.sel)+delta))]
        self.pscr = 0
        self.ensure_sel_visible()
        self._rebuild()

    def _rebuild(self):
        e=EFFECT_DEFS[self.sel]; st=self.app.fx[e["id"]]
        self.pscr = max(0, min(self.pscr, self.max_pscr()))
        self.sliders=[]
        for i,(nm,d,lo,hi) in enumerate(e["params"]):
            if self.pscr <= i < self.pscr + self.KNOBS_VIS:
                row = i - self.pscr
                val=float(st["params"].get(nm,d))
                self.sliders.append(Slider((430, 268+row*34, 360, 11), lo, hi, val, nm))

    def _write(self):
        e=EFFECT_DEFS[self.sel]
        for sl in self.sliders:
            self.app.fx[e["id"]]["params"][sl.label]=sl.value

    def rect(self):
        w,h=self.app.screen.get_size()
        return pygame.Rect(16, 24, min(1040, w-32), min(620, h-48))

    def list_rect(self):
        r=self.rect()
        return pygame.Rect(r.x+8, r.y+76, 250, r.h-90)

    def search_rect(self):
        r=self.rect()
        return pygame.Rect(r.x+8, r.y+44, 250, 24)

    def chain_btn_rect(self):
        r=self.rect()
        return pygame.Rect(r.x+270, r.y+44, r.w-430, 24)

    def chain_panel_rect(self):
        r=self.rect()
        return pygame.Rect(r.x+270, r.y+70, r.w-290, r.h-120)

    def pedal_rect(self):
        r=self.rect()
        return pygame.Rect(r.x+270, r.y+76, 420, 132)

    def handle(self, event):
        if not self.visible: return False
        ids = self.filtered()
        lr = self.list_rect()
        vis = max(1, lr.h // self.ROW)

        if event.type==pygame.KEYDOWN:
            if self.search_focus:
                if event.key==pygame.K_ESCAPE:
                    self.search_focus=False; return True
                if event.key==pygame.K_BACKSPACE:
                    self.search=self.search[:-1]; self.scroll=0; return True
                if event.key==pygame.K_RETURN:
                    self.search_focus=False; return True
                if event.unicode and event.unicode.isprintable() and len(self.search)<24:
                    self.search += event.unicode; self.scroll=0; return True
                return True
            if event.key==pygame.K_ESCAPE:
                if self.chain_open:
                    self.chain_open=False; return True
                self.visible=False; return True
            if event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                if event.key==pygame.K_UP: self.move_sel(-1)
                elif event.key==pygame.K_DOWN: self.move_sel(1)
                elif event.key==pygame.K_PAGEUP: self.move_sel(-vis)
                elif event.key==pygame.K_PAGEDOWN: self.move_sel(vis)
                elif event.key==pygame.K_HOME:
                    if ids: self.sel=ids[0]; self.scroll=0; self.pscr=0; self._rebuild()
                elif event.key==pygame.K_END:
                    if ids: self.sel=ids[-1]; self.ensure_sel_visible(); self.pscr=0; self._rebuild()
                return True
            return False  # let App play mapped keys

        if event.type==pygame.MOUSEWHEEL:
            mx,my=pygame.mouse.get_pos()
            if self.chain_open and self.chain_panel_rect().collidepoint((mx,my)):
                n=len(self.app.fx_chain)
                maxs=max(0, n - max(1, self.chain_panel_rect().h//self.ROW))
                self.chain_scroll=max(0,min(maxs, self.chain_scroll-event.y)); return True
            if lr.collidepoint((mx,my)):
                maxs=max(0, len(ids)-vis)
                self.scroll=max(0,min(maxs, self.scroll-event.y)); return True
            pr=self.pedal_rect()
            slr=pygame.Rect(self.rect().x+270, self.rect().y+210, 430, 300)
            if pr.collidepoint((mx,my)) or slr.collidepoint((mx,my)):
                self.pscr=max(0, min(self.max_pscr(), self.pscr-event.y))
                self._rebuild(); return True
            return True

        if not self.chain_open and any(sl.handle(event) for sl in self.sliders):
            self._write(); return True

        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1:
            r=self.rect()
            if not r.collidepoint(event.pos):
                if self.chain_open:
                    self.chain_open=False; return True
                self.visible=False; return True
            if self.search_rect().collidepoint(event.pos):
                self.search_focus=True; return True
            self.search_focus=False
            if self.chain_btn_rect().collidepoint(event.pos):
                self.chain_open = not self.chain_open
                self.chain_scroll=0
                return True
            if self.chain_open:
                pr=self.chain_panel_rect()
                if pr.collidepoint(event.pos):
                    idx = self.chain_scroll + (event.pos[1]-pr.y)//self.ROW
                    if 0<=idx<len(self.app.fx_chain):
                        fid=self.app.fx_chain[idx]
                        for i,e in enumerate(EFFECT_DEFS):
                            if e["id"]==fid:
                                self.sel=i; self.pscr=0; self._rebuild(); break
                    return True
                self.chain_open=False
            visn=min(vis, max(0, len(ids)-self.scroll))
            for i in range(visn):
                gi=ids[self.scroll+i]
                row=pygame.Rect(lr.x, lr.y+i*self.ROW, lr.w, self.ROW)
                box=pygame.Rect(row.x+4,row.y+4,14,14)
                if box.collidepoint(event.pos):
                    fid=EFFECT_DEFS[gi]["id"]
                    on=not self.app.fx[fid]["on"]
                    self.app.fx[fid]["on"]=on
                    if on and fid not in self.app.fx_chain: self.app.fx_chain.append(fid)
                    if not on and fid in self.app.fx_chain: self.app.fx_chain.remove(fid)
                    return True
                if row.collidepoint(event.pos):
                    self.sel=gi; self.pscr=0; self._rebuild(); return True
            e=EFFECT_DEFS[self.sel]
            for i,sw in enumerate(e["switches"]):
                b=pygame.Rect(r.x+270+i*90, r.y+214, 84, 20)
                if b.collidepoint(event.pos):
                    cur=self.app.fx[e["id"]]["switches"].get(sw[0], sw[1])
                    self.app.fx[e["id"]]["switches"][sw[0]]=not cur
                    return True
            gen=pygame.Rect(r.right-150,r.bottom-40,130,26)
            if gen.collidepoint(event.pos):
                self._write(); self.app.generate_with_effects(); return True
        return True

    def draw_pedal(self,surf,box,e,st,tiny):
        pygame.draw.rect(surf,e["color"],box,border_radius=12)
        pygame.draw.rect(surf,(255,255,255),box,2,border_radius=12)
        if e["id"] in ("phaser","ph9"):
            for i,col in enumerate(((250,250,250),(20,20,20),(250,200,20),(190,20,25))):
                pygame.draw.rect(surf,col,pygame.Rect(box.x+18+i*28,box.y+22,12,box.h-40))
        ink, ink2, ink3 = pedal_ink(e["color"])
        surf.blit(tiny.render(e["name"][:30],True,ink),(box.x+8,box.y+4))
        fill, needle, ring = knob_style(e["color"])
        npar = len(e["params"])
        visp = e["params"][self.pscr:self.pscr+self.KNOBS_VIS]
        for i, (nm, d, lo, hi) in enumerate(visp):
            col = i % 3
            row = i // 3
            cx = box.x + 50 + col * 130
            cy = box.y + 48 + row * 42
            val = float(st["params"].get(nm, d))
            t = 0.0 if hi==lo else (val-lo)/(hi-lo)
            t = max(0.0, min(1.0, t))
            ang = math.pi * 0.75 + t * math.pi * 1.5
            pygame.draw.circle(surf, fill, (cx,cy), 14)
            pygame.draw.circle(surf, ring, (cx,cy), 14, 2)
            px = cx + int(math.cos(ang)*9)
            py = cy + int(math.sin(ang)*9)
            pygame.draw.line(surf, needle, (cx,cy), (px,py), 2)
            lab = tiny.render(short_label(nm, 6), True, ink if luminance(e["color"])>=150 else ink2)
            surf.blit(lab, (cx - lab.get_width()//2, cy + 15))
        if npar > self.KNOBS_VIS:
            hint = tiny.render(f"knobs {self.pscr+1}-{self.pscr+len(visp)}/{npar}", True, ink3)
            surf.blit(hint, (box.right - hint.get_width() - 8, box.y + 4))

    def draw(self,surf,font,small):
        if not self.visible: return
        ov=pygame.Surface(surf.get_size(),pygame.SRCALPHA); ov.fill((0,0,0,175)); surf.blit(ov,(0,0))
        r=self.rect()
        pygame.draw.rect(surf,COL_PANEL,r,border_radius=10); pygame.draw.rect(surf,COL_ACCENT,r,2,border_radius=10)
        surf.blit(font.render(f"EFFECTS  ({len(EFFECT_DEFS)})  arrows scroll list  keys still play",True,COL_ORANGE),(r.x+12,r.y+10))

        sr=self.search_rect()
        pygame.draw.rect(surf,(16,18,24),sr,border_radius=4)
        pygame.draw.rect(surf,COL_ORANGE if self.search_focus else COL_ACCENT,sr,1,border_radius=4)
        hint=self.search if self.search else "search  (nux, rat, ph9…)"
        surf.blit(small.render(hint[:28],True,COL_TEXT if self.search else COL_DIM),(sr.x+6,sr.y+4))

        cb=self.chain_btn_rect()
        pygame.draw.rect(surf,(40,48,64),cb,border_radius=6)
        pygame.draw.rect(surf,COL_ORANGE,cb,1,border_radius=6)
        chain_names=[FX_INDEX[i]["name"] for i in self.app.fx_chain if i in FX_INDEX]
        preview="CHAIN ["+str(len(self.app.fx_chain))+"]  " + (" > ".join(n[:12] for n in chain_names[:3]) if chain_names else "(empty)")
        if len(chain_names)>3: preview += "  … view all"
        surf.blit(small.render(preview[:52],True,COL_TEXT),(cb.x+6,cb.y+4))

        lr=self.list_rect()
        pygame.draw.rect(surf,(16,18,24),lr)
        ids=self.filtered()
        vis=max(1, lr.h//self.ROW)
        self.scroll=min(self.scroll, max(0, len(ids)-vis))
        for i in range(min(vis, max(0,len(ids)-self.scroll))):
            gi=ids[self.scroll+i]; e=EFFECT_DEFS[gi]
            row=pygame.Rect(lr.x, lr.y+i*self.ROW, lr.w, self.ROW)
            if gi==self.sel: pygame.draw.rect(surf,(50,70,90),row)
            on=self.app.fx[e["id"]]["on"]
            pygame.draw.rect(surf,(80,200,90) if on else (40,40,40),pygame.Rect(row.x+4,row.y+4,14,14))
            surf.blit(small.render(e["name"][:24],True,COL_TEXT),(row.x+22,row.y+3))
        if len(ids)>vis:
            surf.blit(small.render(f"{self.scroll+1}-{min(len(ids),self.scroll+vis)} / {len(ids)}  ↑↓",True,COL_DIM),(lr.x+4,lr.bottom-16))

        if not self.chain_open:
            e=EFFECT_DEFS[self.sel]
            st=self.app.fx[e["id"]]
            self.draw_pedal(surf,self.pedal_rect(),e,st,self.app.tiny)
            for i,sw in enumerate(e["switches"]):
                on=st["switches"].get(sw[0], sw[1])
                label=sw[0]
                if e["id"]=="twdist" and sw[0]=="modern":
                    label="MODERN" if on else "VINTAGE"
                b=pygame.Rect(r.x+270+i*90, r.y+214, 84, 20)
                pygame.draw.rect(surf,(70,140,80) if on else (50,50,60),b,border_radius=4)
                surf.blit(small.render(label[:10],True,COL_TEXT),(b.x+4,b.y+3))
            npar=len(e["params"])
            surf.blit(small.render(f"SLIDERS {self.pscr+1}-{min(npar,self.pscr+self.KNOBS_VIS)}/{npar}",True,COL_DIM),(r.x+270,r.y+242))
            for sl in self.sliders: sl.draw(surf,small)

        if self.chain_open:
            pr=self.chain_panel_rect()
            pygame.draw.rect(surf,(12,14,20),pr)
            pygame.draw.rect(surf,COL_ORANGE,pr,2)
            surf.blit(small.render("FULL EFFECT CHAIN  (wheel / click to edit)",True,COL_ORANGE),(pr.x+8,pr.y+4))
            rows=max(1,(pr.h-24)//self.ROW)
            chain=self.app.fx_chain
            self.chain_scroll=min(self.chain_scroll, max(0,len(chain)-rows))
            if not chain:
                surf.blit(small.render("(empty)",True,COL_DIM),(pr.x+10,pr.y+30))
            else:
                for i,fid in enumerate(chain[self.chain_scroll:self.chain_scroll+rows]):
                    nm=FX_INDEX[fid]["name"] if fid in FX_INDEX else fid
                    surf.blit(small.render(f"{i+1+self.chain_scroll:02d}.  {nm}",True,COL_TEXT),(pr.x+10, pr.y+24+i*self.ROW))

        gen=pygame.Rect(r.right-150,r.bottom-40,130,26)
        pygame.draw.rect(surf,(40,130,80),gen,border_radius=6)
        surf.blit(small.render("GENERATE",True,COL_TEXT),gen.move(28,5))

class App:
    def __init__(self):
        self.geom=load_geom()
        pygame.mixer.pre_init(SAMPLE_RATE,-16,1,512)
        os.environ["SDL_VIDEO_WINDOW_POS"]=f"{self.geom.get('x',80)},{self.geom.get('y',80)}"
        pygame.init()
        if not pygame.mixer.get_init(): pygame.mixer.init(SAMPLE_RATE,-16,1,512)
        pygame.mixer.set_num_channels(MAX_POLY)
        pygame.display.set_caption("DX7-style FM — JUMP")
        self.screen=pygame.display.set_mode((self.geom["w"],self.geom["h"]), pygame.RESIZABLE)
        self.font=pygame.font.SysFont("consolas",18) or pygame.font.Font(None,22)
        self.small=pygame.font.SysFont("consolas",14) or pygame.font.Font(None,18)
        self.tiny=pygame.font.SysFont("consolas",12) or pygame.font.Font(None,16)
        self.clock=pygame.time.Clock()
        self.keymap,self.keymap_src=load_keymap()
        self.midi_notes=sorted(set(self.keymap.values())); self.mapped=set(self.midi_notes)
        self.key_by_note={}
        for k,n in self.keymap.items(): self.key_by_note.setdefault(n,k)
        self.held_keys,self.held_midi={},set(); self.playing,self.voice_order={},[]
        self.patches=[ensure_adsr(p) for p in deepcopy(FACTORY)]
        self.patch_index=0; self.patch=deepcopy(self.patches[0])
        self.fx=default_fx_state(); self.fx_chain=[]
        self.sel_op=0; self.sounds,self.waves={},{}; self.status="Ready"; self.dirty=False
        self.scope=np.zeros(512,np.float32)
        a=self.patch["adsr"]
        self.sliders=[
            Slider((40,370,160,12),0.001,2.0,a["a"],"A"),
            Slider((220,370,160,12),0.001,2.0,a["d"],"D"),
            Slider((400,370,160,12),0.0,1.0,a["s"],"S"),
            Slider((580,370,160,12),0.001,3.0,a["r"],"R"),
        ]
        self.midi_in=None; self.midi_id=-1; self.midi_name="Off"
        self.dialog=PatchDialog(self); self.fxdlg=EffectsDialog(self)
        self.dropdown=Dropdown((20,50,220,26))
        self._layout_buttons(); os.makedirs(TONES_DIR, exist_ok=True)
        self.load_tone_json(); self.load_or_build_tones()
    def graph_rects(self):
        w,_=self.screen.get_size(); gap,x0=16,20; usable=max(600,w-40); gw=(usable-2*gap)//3
        return (pygame.Rect(x0,GRAPH_Y,gw,GRAPH_H), pygame.Rect(x0+gw+gap,GRAPH_Y,gw,GRAPH_H),
                pygame.Rect(x0+2*(gw+gap),GRAPH_Y,gw,GRAPH_H))
    def _layout_buttons(self):
        self.buttons=[
            Button((20,16,90,28),"CREATE",lambda:self.dialog.open("create")),
            Button((118,16,90,28),"LOAD",lambda:self.dialog.open("load")),
            Button((216,16,90,28),"EDIT",self.open_edit),
            Button((320,16,130,28),"MIDI CONNECT",self.cycle_midi),
            Button((460,16,80,28),"APPLY",lambda:self.load_or_build_tones(force=True)),
            Button((550,16,110,28),"SAVE ADSR",self.save_adsr),
            Button((670,16,90,28),"EFFECTS",self.fxdlg.open),
            Button((250,50,50,26),"ALG-",lambda:self.chg_algo(-1)),
            Button((304,50,50,26),"ALG+",lambda:self.chg_algo(1)),
            Button((360,50,50,26),"FB-",lambda:self.chg_fb(-1)),
            Button((414,50,50,26),"FB+",lambda:self.chg_fb(1)),
        ]
        for i in range(6):
            self.buttons.append(Button((20+i*70,92,64,24),f"OP{i+1}",action=lambda i=i:setattr(self,"sel_op",i)))
    def capture_patch_state(self):
        self.read_adsr_from_sliders(); ensure_adsr(self.patch)
    def open_edit(self):
        self.capture_patch_state(); self.patches[self.patch_index]=deepcopy(self.patch)
        self.save_bank(); self.dialog.open("edit")
    def select_loaded_patch(self, idx):
        self.patch_index=idx; self.patch=ensure_adsr(deepcopy(self.patches[idx]))
        self.sync_adsr_sliders(); self.load_tone_json()
    def sync_adsr_sliders(self):
        a=ensure_adsr(self.patch)["adsr"]
        self.sliders[0].value,self.sliders[1].value=a["a"],a["d"]
        self.sliders[2].value,self.sliders[3].value=a["s"],a["r"]
    def read_adsr_from_sliders(self):
        self.patch["adsr"]={"a":self.sliders[0].value,"d":self.sliders[1].value,"s":self.sliders[2].value,"r":self.sliders[3].value}
        ensure_adsr(self.patch)
    def save_adsr(self):
        self.capture_patch_state(); self.patches[self.patch_index]=deepcopy(self.patch); self.save_bank()
    def save_tone_json(self):
        self.capture_patch_state()
        path=tone_json_path(self.patch["name"])
        with open(path,"w",encoding="utf-8") as f:
            json.dump({"patch":self.patch,"effects":self.fx,"chain":self.fx_chain}, f, indent=2)
        return path
    def load_tone_json(self):
        self.fx=default_fx_state(); self.fx_chain=[]
        path=tone_json_path(self.patch["name"])
        if not os.path.isfile(path): return
        try:
            with open(path,"r",encoding="utf-8") as f: data=json.load(f)
            if isinstance(data.get("patch"),dict):
                self.patch=ensure_adsr({**self.patch, **data["patch"]}); self.sync_adsr_sliders()
            if isinstance(data.get("effects"),dict):
                for k,v in data["effects"].items():
                    if k in self.fx and isinstance(v,dict):
                        self.fx[k]["on"]=bool(v.get("on"))
                        if isinstance(v.get("params"),dict): self.fx[k]["params"].update(v["params"])
                        if isinstance(v.get("switches"),dict): self.fx[k]["switches"].update(v["switches"])
            if isinstance(data.get("chain"), list):
                self.fx_chain=[i for i in data["chain"] if i in self.fx]
            else:
                self.fx_chain=[e["id"] for e in EFFECT_DEFS if self.fx[e["id"]]["on"]]
        except Exception:
            pass
    def generate_with_effects(self):
        self.save_tone_json()
        self.load_or_build_tones(force=True, apply_fx=True)
        self.status=f"Generated chain ({len(self.fx_chain)})"
    def load_or_build_tones(self, force=False, apply_fx=False):
        ensure_adsr(self.patch); self.sync_adsr_sliders(); os.makedirs(TONES_DIR, exist_ok=True)
        if not force and not apply_fx:
            for path in tone_candidates(self.patch["name"]):
                if os.path.isfile(path):
                    waves=load_tone_file(path,self.midi_notes)
                    if waves is not None:
                        self.note_off_all(); self.sounds.clear(); self.waves=waves
                        for n,w in waves.items(): self.sounds[n],_=pcm_sound(w)
                        self.status=f"Loaded {os.path.basename(path)}"; return
        self.note_off_all(); self.sounds.clear(); self.waves.clear()
        total=max(1,len(self.midi_notes))
        for i,note in enumerate(self.midi_notes):
            self.status=f"Rendering {i+1}/{total} MIDI {note}"; self._draw_status_frame()
            wave=render_note_first_iteration(self.patch,note)
            if apply_fx:
                wave=apply_fx_chain(wave,self.fx,self.fx_chain); wave=make_loopable(wave)
            snd,wav=pcm_sound(wave); self.sounds[note],self.waves[note]=snd,wav
        save_tone_file(tone_save_path(self.patch["name"]), self.waves)
        self.status=f"Saved {os.path.basename(tone_save_path(self.patch['name']))}"
    def _draw_status_frame(self):
        self.screen.fill(COL_BG); self.screen.blit(self.font.render(self.status,True,COL_ORANGE),(30,240))
        pygame.display.flip(); pygame.event.pump()
    def persist_geom(self):
        w,h=self.screen.get_size(); save_geom(w,h,self.geom.get("x",80),self.geom.get("y",80))
    def save_bank(self):
        self.capture_patch_state(); self.patches[self.patch_index]=deepcopy(self.patch)
        with open(BANK_FILE,"w",encoding="utf-8") as f: json.dump(self.patches,f,indent=2)
    def chg_algo(self,d):
        keys=sorted(ALGORITHMS); i=keys.index(self.patch["algo"]) if self.patch["algo"] in keys else 0
        self.patch["algo"]=keys[(i+d)%len(keys)]; self.dirty=True
    def chg_fb(self,d):
        self.patch["feedback"]=max(0,min(7,self.patch["feedback"]+d)); self.dirty=True
    def _steal_oldest(self):
        while self.voice_order:
            old=self.voice_order.pop(0); v=self.playing.pop(old,None)
            if v: v.stop_now(); return
    def note_on(self, note):
        if note not in self.sounds: return
        if note in self.playing:
            self.playing[note].stop_now(); self.playing.pop(note,None)
            if note in self.voice_order: self.voice_order.remove(note)
        self.voice_order=[n for n in self.voice_order if n in self.playing and not self.playing[n].done]
        if len(self.voice_order)>=MAX_POLY-1: self._steal_oldest()
        self.read_adsr_from_sliders()
        ch=pygame.mixer.find_channel(False)
        if ch is None: self._steal_oldest(); ch=pygame.mixer.find_channel(False)
        if ch is None: return
        ch.play(self.sounds[note], loops=-1); ch.set_volume(0.0)
        self.playing[note]=PlayingNote(note,self.sounds[note],ch,self.patch["adsr"],self.waves.get(note))
        self.voice_order.append(note)
    def mix_scope(self):
        acc=np.zeros(512,np.float32); anyv=False
        for v in self.playing.values():
            if v.done or v.wave is None or not len(v.wave): continue
            anyv=True; n=len(v.wave); start=int(v.pos)%n
            sl=np.take(v.wave, np.arange(start,start+4096)%n)[::8][:512]
            acc[:len(sl)] += sl*v.level
        if anyv:
            pk=float(np.max(np.abs(acc)))+1e-9
            if pk>1: acc/=pk
            self.scope=acc
    def note_off(self, note):
        v=self.playing.get(note)
        if v: v.note_off()
    def note_off_all(self):
        for v in list(self.playing.values()): v.stop_now()
        self.playing.clear(); self.voice_order.clear()
        try: pygame.mixer.stop()
        except Exception: pass
    def update_voices(self, dt):
        dead=[n for n,v in self.playing.items() if (v.update(dt) or v.done)]
        for n in dead:
            self.playing.pop(n,None)
            if n in self.voice_order: self.voice_order.remove(n)
        self.mix_scope()
    def cycle_midi(self):
        if not HAS_MIDI: self.midi_name="pygame.midi unavailable"; return
        try:
            if not pygame.midi.get_init(): pygame.midi.init()
        except Exception as e:
            self.midi_name=f"MIDI err {e}"; return
        if self.midi_in:
            try: self.midi_in.close()
            except Exception: pass
            self.midi_in=None
        inputs=[]
        for i in range(pygame.midi.get_count()):
            info=pygame.midi.get_device_info(i)
            if info[2]:
                name=info[1].decode() if isinstance(info[1],bytes) else str(info[1]); inputs.append((i,name))
        if not inputs: self.midi_id,self.midi_name=-1,"No MIDI inputs"; return
        ids=[x[0] for x in inputs]
        nxt=ids[(ids.index(self.midi_id)+1)%len(ids)] if self.midi_id in ids else ids[0]
        try:
            self.midi_in=pygame.midi.Input(nxt); self.midi_id,self.midi_name=nxt,dict(inputs)[nxt]
        except Exception as e:
            self.midi_in,self.midi_name=None,f"Open fail: {e}"
    def poll_midi(self):
        if not self.midi_in: return
        try:
            if self.midi_in.poll():
                for ev in self.midi_in.read(32):
                    data=ev[0]; status,n,v=data[0]&0xF0,data[1],data[2]
                    if status==0x90 and v>0:
                        if n in self.sounds: self.note_on(n); self.held_midi.add(n)
                    elif status in (0x80,0x90):
                        self.note_off(n); self.held_midi.discard(n)
        except Exception: pass
    def note_from_key_event(self, event):
        tok=event_key_token(event)
        if tok in self.keymap: return tok,self.keymap[tok]
        if event.unicode:
            u=event.unicode.lower()
            if u in self.keymap: return u,self.keymap[u]
        return None,None
    def handle_keydown(self, event):
        if self.dialog.visible or self.dropdown.open: return
        if event.key==pygame.K_ESCAPE and not self.fxdlg.visible:
            pygame.event.post(pygame.event.Event(pygame.QUIT)); return
        tok,note=self.note_from_key_event(event)
        if note is None or tok in self.held_keys: return
        self.held_keys[tok]=note; self.note_on(note)
    def handle_keyup(self, event):
        tok,note=self.note_from_key_event(event)
        if tok in self.held_keys: self.note_off(self.held_keys.pop(tok))
        elif note is not None: self.note_off(note)
    def draw_graphs(self):
        eg,ag,sc=self.graph_rects(); op=self.patch["ops"][self.sel_op]
        pygame.draw.rect(self.screen,(16,18,24),eg); pygame.draw.rect(self.screen,COL_ACCENT,eg,1)
        rates=[max(1,r) for r in op["rates"]]; widths=[max(0.08,100-r) for r in rates]; tot=sum(widths)
        xs,acc=[0.0],0.0
        for w in widths:
            acc+=w/tot; xs.append(acc)
        ys=[0.0]+[lv/99.0 for lv in op["levels"]]
        pts=[(eg.x+8+x*(eg.w-16), eg.bottom-8-y*(eg.h-28)) for x,y in zip(xs,ys)]
        if len(pts)>1: pygame.draw.aalines(self.screen,COL_ACCENT,False,pts)
        pygame.draw.rect(self.screen,(16,18,24),ag); pygame.draw.rect(self.screen,COL_ORANGE,ag,1)
        a,d,s,rv=self.sliders[0].value,self.sliders[1].value,self.sliders[2].value,self.sliders[3].value
        span=max(0.05,a+d+0.4+rv); inner=pygame.Rect(ag.x+8,ag.y+22,ag.w-16,ag.h-30)
        pts2=[(inner.x,inner.bottom),(inner.x+a/span*inner.w,inner.y),
              (inner.x+(a+d)/span*inner.w,inner.bottom-s*inner.h),
              (inner.x+(a+d+0.4)/span*inner.w,inner.bottom-s*inner.h),(inner.right,inner.bottom)]
        pygame.draw.aalines(self.screen,COL_ORANGE,False,pts2)
        pygame.draw.rect(self.screen,(8,10,14),sc); pygame.draw.rect(self.screen,COL_ORANGE,sc,1)
        pts3=[(sc.x+8+i*(sc.w-16)/max(1,len(self.scope)-1), sc.centery+8-float(sv)*sc.h*0.32) for i,sv in enumerate(self.scope)]
        if len(pts3)>1: pygame.draw.aalines(self.screen,COL_ACCENT,False,pts3)
    def draw_keyboard(self):
        w,h=self.screen.get_size()
        if not self.midi_notes: return
        lo,hi=self.midi_notes[0],self.midi_notes[-1]
        while lo%12 not in (0,2,4,5,7,9,11) and lo>0: lo-=1
        while hi%12 not in (0,2,4,5,7,9,11) and hi<127: hi+=1
        white={0,2,4,5,7,9,11}
        whites=[n for n in range(lo,hi+1) if n%12 in white]
        kh=108; oy=h-kh-18; ww=max(14,min(28,(w-80)//max(1,len(whites)))); ox=(w-len(whites)*ww)//2
        notes_on=set(self.held_keys.values())|self.held_midi|{n for n,v in self.playing.items() if not v.released}
        wi,wx=0,{}
        for n in range(lo,hi+1):
            if n%12 not in white: continue
            r=pygame.Rect(ox+wi*ww,oy,ww-2,kh); wx[n]=r.x
            col=COL_KEY_ON if n in notes_on else (COL_KEY if n in self.mapped else COL_KEY_UNMAPPED)
            pygame.draw.rect(self.screen,col,r,border_radius=3); pygame.draw.rect(self.screen,(40,40,40),r,1,border_radius=3)
            if n in self.mapped:
                self.screen.blit(self.tiny.render(str(self.key_by_note.get(n,"")),True,(40,40,40)),(r.x+3,r.bottom-16))
            wi+=1
        for n in range(lo,hi+1):
            if n%12 in white: continue
            lw=n-1
            while lw not in wx and lw>=lo: lw-=1
            if lw not in wx: continue
            r=pygame.Rect(wx[lw]+ww-ww//3,oy,ww//2,int(kh*0.62))
            col=COL_ORANGE if n in notes_on else (COL_KEY_BLK if n in self.mapped else (50,50,55))
            pygame.draw.rect(self.screen,col,r,border_radius=2)
    def draw_ops(self):
        w,h=self.screen.get_size(); op=self.patch["ops"][self.sel_op]
        pygame.draw.rect(self.screen,COL_PANEL,pygame.Rect(20,130,max(400,w-40),max(250,h-270)),border_radius=8)
        self.screen.blit(self.small.render(
            f"OP{self.sel_op+1} on={int(op['on'])} lvl={op['level']:02d} coarse={op['coarse']} det={op['detune']:+d}",
            True,COL_TEXT),(30,140))
        self.screen.blit(self.tiny.render(self.status,True,COL_ORANGE),(30,162))
        self.draw_graphs()
        for sl in self.sliders: sl.draw(self.screen,self.tiny)
        self.screen.blit(self.tiny.render(
            f"ALG {self.patch['algo']} FB {self.patch['feedback']} chain:{len(self.fx_chain)} MIDI:{self.midi_name}",
            True,COL_ACCENT),(30,400))
    def tweak_with_mods(self, event):
        if self.dialog.visible or self.dropdown.open or self.fxdlg.visible: return False
        if event.key in (pygame.K_1,pygame.K_2,pygame.K_3,pygame.K_4,pygame.K_5,pygame.K_6,
                         pygame.K_7,pygame.K_8,pygame.K_9,pygame.K_0): return False
        if not (pygame.key.get_mods() & pygame.KMOD_CTRL): return False
        op=self.patch["ops"][self.sel_op]; changed=False
        if event.key==pygame.K_o: op["on"]=not op["on"]; changed=True
        elif event.key==pygame.K_q: op["level"]=min(99,op["level"]+2); changed=True
        elif event.key==pygame.K_a: op["level"]=max(0,op["level"]-2); changed=True
        elif event.key==pygame.K_w: op["coarse"]=min(31,op["coarse"]+1); changed=True
        elif event.key==pygame.K_s: op["coarse"]=max(0,op["coarse"]-1); changed=True
        elif event.key==pygame.K_e: op["detune"]=min(7,op["detune"]+1); changed=True
        elif event.key==pygame.K_d: op["detune"]=max(-7,op["detune"]-1); changed=True
        if changed: self.dirty=True
        return changed
    def run(self):
        running=True
        while running:
            dt=self.clock.tick(60)/1000.0
            self.poll_midi(); self.update_voices(dt)
            for event in pygame.event.get():
                if event.type==pygame.QUIT: running=False
                elif event.type==pygame.VIDEORESIZE:
                    self.geom["w"]=max(980,event.w); self.geom["h"]=max(600,event.h); self.persist_geom()
                elif self.fxdlg.visible:
                    consumed = self.fxdlg.handle(event)
                    if event.type==pygame.KEYDOWN and not consumed and not self.fxdlg.search_focus:
                        self.handle_keydown(event)
                    elif event.type==pygame.KEYUP:
                        self.handle_keyup(event)
                elif self.dialog.visible: self.dialog.handle(event)
                elif self.dropdown.handle(event,self): pass
                elif any(sl.handle(event) for sl in self.sliders): self.read_adsr_from_sliders()
                elif event.type==pygame.MOUSEBUTTONDOWN:
                    for b in self.buttons: b.click(event.pos)
                elif event.type==pygame.KEYDOWN:
                    if self.tweak_with_mods(event): continue
                    self.handle_keydown(event)
                elif event.type==pygame.KEYUP: self.handle_keyup(event)
            self.screen.fill(COL_BG)
            self.screen.blit(self.font.render("YAMAHA-STYLE FM  ·  6 OP",True,COL_ACCENT),(780,20))
            for b in self.buttons:
                if b.label.startswith("OP"): b.on=(b.label==f"OP{self.sel_op+1}")
                b.draw(self.screen,self.small)
            self.draw_ops(); self.draw_keyboard()
            self.dropdown.draw(self.screen,self.font,self.small,self)
            self.dialog.draw(self.screen,self.font,self.small)
            self.fxdlg.draw(self.screen,self.font,self.small)
            pygame.display.flip()
        self.persist_geom()
        if self.midi_in:
            try: self.midi_in.close()
            except Exception: pass
        if HAS_MIDI:
            try:
                if pygame.midi.get_init(): pygame.midi.quit()
            except Exception: pass
        pygame.mixer.quit(); pygame.quit()

if __name__=="__main__":
    App().run()