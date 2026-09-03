#!/usr/bin/env python3
"""Sight-reading tutor."""

from __future__ import annotations

import json
import os
import random
import struct
from dataclasses import dataclass, asdict, fields

import numpy as np
import pygame

WIDTH_DEFAULT, HEIGHT_DEFAULT = 1480, 920
FPS = 60
BARS_VISIBLE = 3
BEATS_PER_BAR = 4
DEFAULT_BPM = 40.0
SETTINGS_FILE = "settings.json"
KEYMAP_FILE = "site.key"
TONES_FILE = "custom_tones.json"
SONGS_DIR = "songs"
SAMPLE_RATE = 44100
DEFAULT_QUIZ_LENGTH = 100
HUD_H = 118
PPQ = 480
MIN_W, MIN_H = 1100, 700

A0, C8 = 21, 108
MIDDLE_C = 60
QUIZ_LO, QUIZ_HI = 36, 84

BG = (18, 20, 28)
STAFF_BG = (248, 244, 232)
INK = (20, 20, 24)
LINE = (40, 40, 48)
NOTE_COLOR = (25, 25, 30)
NOTE_HIT = (30, 140, 70)
NOTE_MISS = (160, 50, 50)
NOTE_GHOST = (40, 90, 200)
NOTE_CUR = (200, 90, 30)
WHITE_KEY = (245, 245, 248)
WHITE_DOWN = (180, 210, 255)
BLACK_KEY = (25, 25, 30)
BLACK_DOWN = (80, 130, 220)
HUD = (220, 225, 235)
GOOD = (120, 210, 150)
BTN = (46, 58, 82)
BTN_HOT = (70, 110, 180)
BTN_REC = (160, 40, 50)
BTN_REC_BLINK = (255, 70, 80)
BTN_TEXT = (240, 244, 250)
PANEL = (28, 32, 44)

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
LETTERS = ["C", "D", "E", "F", "G", "A", "B"]
MAJOR_KEYS = ["C", "G", "D", "A", "E", "B", "F#", "C#", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
KEY_TONIC = {
    "C": 0, "G": 7, "D": 2, "A": 9, "E": 4, "B": 11, "F#": 6, "C#": 1,
    "F": 5, "Bb": 10, "Eb": 3, "Ab": 8, "Db": 1, "Gb": 6, "Cb": 11,
}
MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
PROGRESSIONS = [
    [0, 4, 5, 3],
    [0, 3, 4, 0],
    [1, 4, 0],
    [0, 5, 3, 4],
    [0, 4, 0, 3, 4],
]
QUIZ_STYLES = ["Random", "Chords", "Progressions", "Arpeggios", "Mixed"]
KEY_SIG = {
    "C": {}, "G": {"F": 1}, "D": {"F": 1, "C": 1}, "A": {"F": 1, "C": 1, "G": 1},
    "E": {"F": 1, "C": 1, "G": 1, "D": 1}, "B": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1},
    "F#": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1, "E": 1},
    "C#": {"F": 1, "C": 1, "G": 1, "D": 1, "A": 1, "E": 1, "B": 1},
    "F": {"B": -1}, "Bb": {"B": -1, "E": -1}, "Eb": {"B": -1, "E": -1, "A": -1},
    "Ab": {"B": -1, "E": -1, "A": -1, "D": -1},
    "Db": {"B": -1, "E": -1, "A": -1, "D": -1, "G": -1},
    "Gb": {"B": -1, "E": -1, "A": -1, "D": -1, "G": -1, "C": -1},
    "Cb": {"B": -1, "E": -1, "A": -1, "D": -1, "G": -1, "C": -1, "F": -1},
}
SHARP_ORDER = ["F", "C", "G", "D", "A", "E", "B"]
FLAT_ORDER = ["B", "E", "A", "D", "G", "C", "F"]
USES_FLATS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"}
TREBLE_SHARP_STEPS = [4.0, 2.5, 5.0, 3.0, 1.5, 3.5, 2.0]
TREBLE_FLAT_STEPS = [2.0, 3.5, 1.5, 3.0, 1.0, 2.5, 0.5]
BASS_SHARP_STEPS = [3.0, 1.5, 4.0, 2.0, 0.5, 2.5, 1.0]
BASS_FLAT_STEPS = [1.0, 2.5, 0.5, 2.0, 0.0, 1.5, -0.5]
SHARP_SPELL = {
    0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1), 4: ("E", 0),
    5: ("F", 0), 6: ("F", 1), 7: ("G", 0), 8: ("G", 1), 9: ("A", 0),
    10: ("A", 1), 11: ("B", 0),
}
FLAT_SPELL = {
    0: ("C", 0), 1: ("D", -1), 2: ("D", 0), 3: ("E", -1), 4: ("E", 0),
    5: ("F", 0), 6: ("G", -1), 7: ("G", 0), 8: ("A", -1), 9: ("A", 0),
    10: ("B", -1), 11: ("B", 0),
}
SONG_EXTS = (".mid", ".midi")

HELP_TEXT = [
    "SIGHT TUTOR — CONTROLS",
    "",
    "SONG QUIZ uses the MIDI file's real beat times and note lengths.",
    "RANDOM QUIZ: style = Random / Chords / Progressions / Arpeggios / Mixed.",
    "simul 1–8 chooses how many pitches sound together (chords) or in a row (arpeggio).",
    "off-key accidentals: occasional sharps/flats outside the selected key.",
    "Accidentals next to a note apply only to that note.",
    "LOAD / SAVE MIDI in songs/ (last folder remembered).",
    "STOP ends quiz, playback, or recording.",
]


def default_songs_dir():
    path = os.path.abspath(SONGS_DIR)
    os.makedirs(path, exist_ok=True)
    return path


def usable_dir(path):
    if path and os.path.isdir(path):
        return os.path.abspath(path)
    return default_songs_dir()


def abbrev_name(name, limit=22):
    base = os.path.splitext(os.path.basename(name or ""))[0]
    if not base:
        return ""
    return base if len(base) <= limit else base[: limit - 1] + "…"


def scale_pcs(key):
    tonic = KEY_TONIC.get(key, 0)
    return [(tonic + step) % 12 for step in MAJOR_STEPS]


def in_key(midi, key):
    return (midi % 12) in scale_pcs(key)


def midi_to_freq(midi):
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def midi_name(midi):
    return "{}{}".format(NOTE_NAMES[midi % 12], (midi // 12) - 1)


def is_black(midi):
    return (midi % 12) in (1, 3, 6, 8, 10)


def event_key_char(event):
    if event.unicode:
        return event.unicode.lower()
    special = {
        pygame.K_MINUS: "-", pygame.K_KP_MINUS: "-", pygame.K_EQUALS: "=",
        pygame.K_PLUS: "+", pygame.K_KP_PLUS: "+", pygame.K_UNDERSCORE: "_",
    }
    return special.get(event.key, "")


def spell_midi(midi, key):
    pc = midi % 12
    octave = (midi // 12) - 1
    table = FLAT_SPELL if key in USES_FLATS else SHARP_SPELL
    letter, acc = table[pc]
    if letter == "C" and acc < 0:
        octave += 1
    if letter == "B" and acc > 0:
        octave -= 1
    sig = KEY_SIG.get(key, {}).get(letter, 0)
    return letter, acc, octave, None if acc == sig else acc


def letter_octave_to_diatonic(letter, octave):
    return octave * 7 + LETTERS.index(letter)


def staff_y_spelled(letter, octave, treble_top, bass_top, spacing, midi):
    which = "bass" if midi < MIDDLE_C else "treble"
    if which == "treble":
        ref, top = letter_octave_to_diatonic("E", 4), treble_top
    else:
        ref, top = letter_octave_to_diatonic("G", 2), bass_top
    steps = letter_octave_to_diatonic(letter, octave) - ref
    return top + 4 * spacing - steps * (spacing / 2), which


def list_dir_entries(folder):
    folders, files = [], []
    try:
        names = os.listdir(folder)
    except OSError:
        return folders, files
    for name in sorted(names, key=str.lower):
        if name.startswith("."):
            continue
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            folders.append(name)
        elif os.path.splitext(name)[1].lower() in SONG_EXTS:
            files.append(name)
    return folders, files


def resolve_song_path(name, folder):
    name = (name or "").strip().strip('"').strip("'")
    if not name:
        return ""
    if os.path.isabs(name):
        return name
    return os.path.join(folder, name)


def clamp_midi(midi):
    return max(A0, min(C8, int(midi)))


def triad_for_degree(key, degree, octave=4, count=3):
    pcs = scale_pcs(key)
    tones = []
    for i in range(max(1, count)):
        pc = pcs[(degree + i * 2) % 7]
        octv = octave + ((degree + i * 2) // 7)
        tones.append(clamp_midi((octv + 1) * 12 + pc))
    # unique-ish rising set
    out, seen = [], set()
    for m in tones:
        while m in seen:
            m += 12
        seen.add(m)
        out.append(clamp_midi(m))
    return out


def maybe_color(midi, key, allow_offkey):
    if not allow_offkey or random.random() > 0.28:
        return midi
    shift = random.choice((-1, 1))
    colored = clamp_midi(midi + shift)
    if in_key(colored, key):
        colored = clamp_midi(midi + 2 * shift)
    return colored


@dataclass
class SongNote:
    beat: float
    midi: int
    dur: float = 1.0


@dataclass
class Song:
    title: str = "Untitled"
    key: str = "C"
    bpm: float = DEFAULT_BPM
    notes: list = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    def sorted_notes(self):
        return sorted(self.notes, key=lambda n: (n.beat, n.midi))


def song_events(song):
    """Group notes that share a beat into simultaneous events."""
    grouped = []
    for n in song.sorted_notes():
        if grouped and abs(grouped[-1][0] - n.beat) < 1e-4:
            grouped[-1][1].append(n)
        else:
            grouped.append((n.beat, [n]))
    return grouped


def vlq(value):
    bits = [value & 0x7F]
    value >>= 7
    while value:
        bits.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(bits))


def write_midi(path, song):
    events = []
    tempo = int(60000000 / max(song.bpm, 1.0))
    events.append((0, bytes([0xFF, 0x51, 0x03]) + struct.pack(">I", tempo)[1:]))
    for n in song.sorted_notes():
        on = int(round(n.beat * PPQ))
        off = int(round((n.beat + max(n.dur, 0.25)) * PPQ))
        events.append((on, bytes([0x90, n.midi & 0x7F, 0x64])))
        events.append((off, bytes([0x80, n.midi & 0x7F, 0x40])))
    events.sort(key=lambda e: (e[0], e[1][0]))
    body, last = b"", 0
    for tick, data in events:
        body += vlq(max(0, tick - last)) + data
        last = tick
    body += vlq(0) + bytes([0xFF, 0x2F, 0x00])
    if not os.path.splitext(path)[1]:
        path += ".mid"
    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ))
        f.write(b"MTrk" + struct.pack(">I", len(body)) + body)
    return path


def _read_vlq(data, i):
    value = 0
    while True:
        if i >= len(data):
            return value, i
        b = data[i]
        i += 1
        value = (value << 7) | (b & 0x7F)
        if b < 0x80:
            return value, i


def read_midi_bytes(data, title="song"):
    if data[:4] != b"MThd":
        raise ValueError("Not a MIDI file")
    hdr_len = struct.unpack(">I", data[4:8])[0]
    _fmt, ntr, div = struct.unpack(">HHH", data[8:14])
    ppq = div if div < 0x8000 else 480
    song = Song(title=title, notes=[])
    pos = 8 + hdr_len
    opens, bpm = {}, DEFAULT_BPM
    for _ in range(max(1, ntr)):
        if pos + 8 > len(data) or data[pos:pos + 4] != b"MTrk":
            break
        tlen = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        track = data[pos + 8:pos + 8 + tlen]
        pos += 8 + tlen
        i = tick = running = 0
        while i < len(track):
            delta, i = _read_vlq(track, i)
            tick += delta
            if i >= len(track):
                break
            if track[i] == 0xFF:
                i += 1
                if i >= len(track):
                    break
                meta = track[i]
                i += 1
                ln, i = _read_vlq(track, i)
                payload = track[i:i + ln]
                i += ln
                if meta == 0x51 and ln == 3:
                    tempo = (payload[0] << 16) | (payload[1] << 8) | payload[2]
                    bpm = 60000000.0 / max(tempo, 1)
                continue
            if track[i] in (0xF0, 0xF7):
                i += 1
                ln, i = _read_vlq(track, i)
                i += ln
                continue
            st = track[i]
            if st < 0x80:
                st = running
            else:
                running = st
                i += 1
            kind = st & 0xF0
            if kind in (0x90, 0x80) and i + 1 < len(track):
                note, vel = track[i], track[i + 1]
                i += 2
                beat = tick / float(max(ppq, 1))
                on = kind == 0x90 and vel > 0
                if on:
                    opens.setdefault(note, []).append(beat)
                elif note in opens and opens[note]:
                    start = opens[note].pop(0)
                    song.notes.append(SongNote(start, note, max(0.25, beat - start)))
            elif kind in (0xA0, 0xB0, 0xE0) and i + 1 < len(track):
                i += 2
            elif kind in (0xC0, 0xD0) and i < len(track):
                i += 1
            else:
                i += 1
    for note, starts in opens.items():
        for start in starts:
            song.notes.append(SongNote(start, note, 1.0))
    song.bpm = bpm
    song.notes.sort(key=lambda n: (n.beat, n.midi))
    return song


def load_song_file(path):
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    data = open(path, "rb").read()
    if data[:4] != b"MThd":
        raise ValueError("Not a MIDI file (need .mid with MThd header)")
    return read_midi_bytes(data, os.path.basename(path))


def save_song_file(path, song):
    return write_midi(path, song)


@dataclass
class Patch:
    name: str
    attack: float = 0.006
    decay: float = 2.5
    sustain: float = 0.0
    h1: float = 1.0
    h2: float = 0.45
    h3: float = 0.22
    h4: float = 0.12
    h5: float = 0.06
    h6: float = 0.03
    h7: float = 0.0
    h8: float = 0.0
    inharm: float = 0.0
    noise: float = 0.0
    vib_rate: float = 0.0
    vib_depth: float = 0.0
    fm: float = 0.0
    detune: float = 0.0
    pair: str = ""
    pair_mix: float = 0.5
    pan_rate: float = 0.0
    pan_depth: float = 0.0
    pan_square: float = 0.0
    chorus_rate: float = 0.0
    chorus_depth: float = 0.0
    chorus_mix: float = 0.0
    trem_rate: float = 0.0
    trem_depth: float = 0.0
    trem_square: float = 0.0
    phaser_rate: float = 0.0
    phaser_depth: float = 0.0
    delay_time: float = 0.0
    delay_mix: float = 0.0
    distortion: float = 0.0
    wah_rate: float = 0.0
    wah_depth: float = 0.0


def P(name, **kw):
    return Patch(name, **kw)


def builtin_patches():
    return [
        P("Piano", attack=0.006, decay=2.5, h1=1, h2=0.45, h3=0.22, h4=0.12, h5=0.06, h6=0.03),
        P("Church Organ", attack=0.04, decay=0.35, sustain=0.55, h1=0.9, h2=0.7, h3=0.45, h4=0.35, h6=0.25, h8=0.15),
        P("Inca Flute", attack=0.05, decay=1.6, h1=1, h2=0.12, h3=0.06, noise=0.04, vib_rate=5.2, vib_depth=0.03),
        P("Charango", attack=0.003, decay=4.8, h1=0.7, h2=0.6, h3=0.5, h4=0.35, h5=0.22, h7=0.12, inharm=0.0008),
        P("Banjo", attack=0.002, decay=5.5, h1=0.55, h2=0.7, h3=0.4, h4=0.45, h5=0.25, h6=0.2, inharm=0.0015),
        P("Violin", attack=0.12, decay=0.7, sustain=0.35, h1=1, h2=0.5, h3=0.33, noise=0.015, vib_rate=5.5, vib_depth=0.04),
        P("Sci-Fi Organ", attack=0.03, decay=0.5, sustain=0.4, h1=1, h2=0.3, fm=0.015, detune=0.007),
        P("Guitar", attack=0.005, decay=3.1, h1=1, h2=0.38, h3=0.28, h4=0.16, inharm=0.0004),
        P("Human Voice", attack=0.08, decay=1.1, sustain=0.25, h1=1, h2=0.5, h3=0.35, vib_rate=5.8, vib_depth=0.04),
        P("Sitar", attack=0.008, decay=2.8, h1=0.7, h2=0.9, h3=0.55, h4=0.4, h5=0.5, h7=0.35, inharm=0.004, noise=0.02),
        P("Koto", attack=0.004, decay=3.6, h1=1, h2=0.25, h3=0.55, h5=0.35, inharm=0.0012),
        P("Harp", attack=0.004, decay=2.4, h1=1, h2=0.4, h3=0.18),
        P("Flute", attack=0.07, decay=1.2, sustain=0.3, h1=1, h2=0.15, noise=0.03, vib_rate=5.0, vib_depth=0.02),
        P("Trumpet", attack=0.04, decay=0.9, sustain=0.35, h1=0.7, h2=0.8, h3=0.55),
        P("Cello", attack=0.11, decay=0.7, sustain=0.4, h1=1, h2=0.45, vib_rate=5.2, vib_depth=0.035),
        P("Synth Pad", attack=0.18, decay=0.5, sustain=0.55, h1=1, h2=0.4, chorus_mix=0.45, pan_rate=0.15, pan_depth=0.35),
        P("Space Echo", attack=0.02, decay=1.2, h1=1, delay_time=0.28, delay_mix=0.4, pan_rate=0.35, pan_depth=0.6),
        P("Leslie", attack=0.04, decay=0.45, sustain=0.55, h1=0.8, h2=0.6, pan_rate=5.5, pan_depth=0.7, trem_rate=5.5, trem_depth=0.25),
        P("Theremin", attack=0.15, decay=0.6, sustain=0.45, h1=1, vib_rate=6.5, vib_depth=0.08),
        P("Distortion Guitar", attack=0.006, decay=2.2, h1=0.6, h2=0.7, distortion=0.45),
        P("Bass Guitar", attack=0.008, decay=2.0, h1=1, h2=0.35),
        P("Ukulele", attack=0.004, decay=3.4, h1=1, h2=0.45, h3=0.25),
        P("Marimba", attack=0.004, decay=3.2, h1=1, h3=0.45),
        P("Kalimba", attack=0.004, decay=3.0, h1=1, h3=0.35, inharm=0.0006),
        P("Choir Aahs", attack=0.16, decay=0.6, sustain=0.5, h1=1, h2=0.4, chorus_mix=0.4),
        P("Saxophone", attack=0.06, decay=0.8, sustain=0.4, h1=0.8, h2=0.6, distortion=0.06),
        P("Clarinet", attack=0.06, decay=0.9, sustain=0.4, h1=0.9, h3=0.7, h5=0.4),
        P("Handpan", attack=0.01, decay=2.3, h1=0.8, h3=0.55, inharm=0.001),
        P("FM Bell", attack=0.005, decay=2.4, h1=0.5, h3=0.8, fm=0.04),
        P("Organ Combo", attack=0.03, decay=0.4, sustain=0.6, h1=0.8, h2=0.6, trem_rate=6.5, trem_depth=0.35),
    ]


def load_custom_patches():
    if not os.path.isfile(TONES_FILE):
        return []
    try:
        raw = json.load(open(TONES_FILE, encoding="utf-8"))
        names = {f.name for f in fields(Patch)}
        out = []
        for item in raw:
            p = Patch(name=item.get("name", "Custom"))
            for k, v in item.items():
                if k in names and k != "name":
                    try:
                        setattr(p, k, type(getattr(p, k))(v))
                    except (TypeError, ValueError):
                        pass
            out.append(p)
        return out
    except Exception:
        return []


def save_custom_patches(patches):
    try:
        json.dump([asdict(p) for p in patches], open(TONES_FILE, "w", encoding="utf-8"), indent=2)
    except OSError:
        pass


def default_settings():
    return {
        "bpm": DEFAULT_BPM, "simultaneous": 1, "instrument": "Piano",
        "limit_to_keymap": False, "quiz_length": DEFAULT_QUIZ_LENGTH, "key": "C",
        "use_song": False, "preview": True, "quiz_style": "Random",
        "offkey": False,
        "win_w": WIDTH_DEFAULT, "win_h": HEIGHT_DEFAULT,
        "last_dir": default_songs_dir(),
    }


def load_settings():
    default_songs_dir()
    cfg = default_settings()
    if os.path.isfile(SETTINGS_FILE):
        try:
            cfg.update(json.load(open(SETTINGS_FILE, encoding="utf-8")))
        except Exception:
            pass
    cfg["bpm"] = float(max(20.0, min(240.0, cfg.get("bpm", DEFAULT_BPM))))
    cfg["simultaneous"] = int(max(1, min(8, cfg.get("simultaneous", 1))))
    cfg["quiz_length"] = int(max(1, min(500, cfg.get("quiz_length", DEFAULT_QUIZ_LENGTH))))
    cfg["limit_to_keymap"] = bool(cfg.get("limit_to_keymap", False))
    cfg["use_song"] = bool(cfg.get("use_song", False))
    cfg["preview"] = bool(cfg.get("preview", True))
    cfg["offkey"] = bool(cfg.get("offkey", False))
    if cfg.get("quiz_style") not in QUIZ_STYLES:
        cfg["quiz_style"] = "Random"
    cfg["win_w"] = int(max(MIN_W, cfg.get("win_w", WIDTH_DEFAULT)))
    cfg["win_h"] = int(max(MIN_H, cfg.get("win_h", HEIGHT_DEFAULT)))
    cfg["last_dir"] = usable_dir(cfg.get("last_dir"))
    if cfg.get("key") not in MAJOR_KEYS:
        cfg["key"] = "C"
    return cfg


def save_settings(cfg):
    try:
        json.dump(cfg, open(SETTINGS_FILE, "w", encoding="utf-8"), indent=2)
    except OSError:
        pass


def load_keymap(path=KEYMAP_FILE):
    mapping = {}
    if not os.path.isfile(path):
        return mapping
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if line and not line.startswith("#"):
            try:
                mapping[line[0].lower()] = int(line[1:])
            except ValueError:
                pass
    return mapping


def _env(t, attack, decay, sustain=0.0):
    a = np.minimum(t / max(attack, 1e-4), 1.0)
    d = np.exp(-decay * np.maximum(t - attack, 0.0))
    return a * ((1.0 - sustain) * d + sustain)


def _lfo(t, rate, square):
    s = np.sin(2 * np.pi * rate * t)
    if square <= 0:
        return s
    return (1.0 - square) * s + square * np.sign(s)


def render_mono(patch, midi, duration=1.7):
    freq = midi_to_freq(midi)
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0.0, duration, n, endpoint=False)
    w = np.zeros(n, dtype=np.float64)
    amps = [patch.h1, patch.h2, patch.h3, patch.h4, patch.h5, patch.h6, patch.h7, patch.h8]
    for i, amp in enumerate(amps, start=1):
        if amp <= 0:
            continue
        f = freq * i * (1.0 + patch.inharm * (i - 1))
        phase = patch.fm * np.sin(2 * np.pi * freq * 2.0 * t) if patch.fm else 0.0
        w += amp * np.sin(2 * np.pi * f * t + phase)
    if patch.noise:
        w += np.random.randn(n) * patch.noise
    if patch.vib_depth and patch.vib_rate:
        w *= 1.0 + patch.vib_depth * np.sin(2 * np.pi * patch.vib_rate * t)
    w *= _env(t, patch.attack, patch.decay, patch.sustain)
    if patch.sustain > 0:
        w *= np.linspace(1.0, 0.15, n)
    if patch.distortion:
        w = np.tanh(w * (1.0 + 8.0 * patch.distortion))
    if patch.trem_depth and patch.trem_rate:
        trem = _lfo(t, patch.trem_rate, patch.trem_square)
        w *= 1.0 - patch.trem_depth * 0.5 * (1.0 - trem)
    if patch.chorus_mix > 0:
        depth = max(patch.chorus_depth, 0.002)
        delay = (0.012 + depth * np.sin(2 * np.pi * max(patch.chorus_rate, 0.2) * t)) * SAMPLE_RATE
        idx = np.clip(np.arange(n) - delay, 0, n - 1)
        i0 = idx.astype(int)
        frac = idx - i0
        chorus = (1 - frac) * w[i0] + frac * w[np.clip(i0 + 1, 0, n - 1)]
        w = (1.0 - patch.chorus_mix) * w + patch.chorus_mix * chorus
    if patch.delay_mix > 0 and patch.delay_time > 0:
        d = int(patch.delay_time * SAMPLE_RATE)
        delayed = np.zeros(n)
        if 0 < d < n:
            delayed[d:] = w[:n - d] * 0.65
        w = w + patch.delay_mix * delayed
    peak = np.max(np.abs(w)) or 1.0
    return w / peak


def to_stereo(w, patch):
    n = len(w)
    t = np.linspace(0.0, n / SAMPLE_RATE, n, endpoint=False)
    if patch.pan_depth and patch.pan_rate:
        pan = patch.pan_depth * _lfo(t, patch.pan_rate, patch.pan_square)
        left = w * (1.0 - 0.5 * (1.0 + pan))
        right = w * (1.0 - 0.5 * (1.0 - pan))
    else:
        left = right = w * 0.707
    stereo = np.column_stack((left, right))
    peak = np.max(np.abs(stereo)) or 1.0
    return (stereo / peak * 0.42 * 32767).astype(np.int16)


def render_patch_named(get_patch, patch, midi):
    w = render_mono(patch, midi)
    if patch.pair:
        other = get_patch(patch.pair)
        if other is not None and other.name != patch.name:
            w2 = render_mono(other, midi)
            m = max(0.0, min(1.0, patch.pair_mix))
            n = min(len(w), len(w2))
            w = (1.0 - m) * w[:n] + m * w2[:n]
    return to_stereo(w, patch)


def make_sound(get_patch, patch, midi):
    return pygame.sndarray.make_sound(np.ascontiguousarray(render_patch_named(get_patch, patch, midi)))


class MidiIn:
    def __init__(self):
        self.inputs, self.available = [], False
        self._mod = None
        try:
            import pygame.midi as pgmidi
            pgmidi.init()
            for i in range(pgmidi.get_count()):
                info = pgmidi.get_device_info(i)
                if info and info[2]:
                    try:
                        self.inputs.append(pgmidi.Input(i))
                    except Exception:
                        pass
            self.available = bool(self.inputs)
            self._mod = pgmidi
        except Exception as e:
            print("MIDI unavailable:", e)

    def poll_note_ons(self):
        notes = []
        if not self.available:
            return notes
        for device in self.inputs:
            if device.poll():
                for event in device.read(32):
                    status, data1, data2 = event[0][0], event[0][1], event[0][2]
                    if status & 0xF0 == 0x90 and data2 > 0:
                        notes.append(int(data1))
        return notes

    def close(self):
        for d in self.inputs:
            try:
                d.close()
            except Exception:
                pass
        if self._mod:
            try:
                self._mod.quit()
            except Exception:
                pass


class Button:
    def __init__(self, rect, label):
        self.rect, self.label = pygame.Rect(rect), label

    def draw(self, surf, font, hover, fill=None):
        color = fill if fill is not None else (BTN_HOT if hover else BTN)
        pygame.draw.rect(surf, color, self.rect, border_radius=8)
        pygame.draw.rect(surf, (120, 140, 180), self.rect, 1, border_radius=8)
        txt = font.render(self.label, True, BTN_TEXT)
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class ComboBox:
    def __init__(self, rect, options, value, max_drop=10):
        self.rect = rect
        self.options = list(options)
        self.value = value if value in self.options else self.options[0]
        self.open = False
        self.max_drop = max_drop
        self.scroll = 0

    def set_options(self, options, value=None):
        self.options = list(options)
        if value in self.options:
            self.value = value
        elif self.value not in self.options:
            self.value = self.options[0]

    def visible(self):
        return self.options[self.scroll:self.scroll + self.max_drop]

    def option_rect(self, i):
        return pygame.Rect(self.rect.x, self.rect.bottom + i * self.rect.height, self.rect.width, self.rect.height)

    def draw(self, surf, font, hover):
        pygame.draw.rect(surf, BTN_HOT if hover else BTN, self.rect, border_radius=6)
        pygame.draw.rect(surf, (120, 140, 180), self.rect, 1, border_radius=6)
        txt = font.render(self.value, True, BTN_TEXT)
        surf.blit(txt, txt.get_rect(midleft=(self.rect.x + 8, self.rect.centery)))
        if self.open:
            for i, opt in enumerate(self.visible()):
                r = self.option_rect(i)
                pygame.draw.rect(surf, (90, 130, 200) if opt == self.value else (40, 48, 66), r)
                t = font.render(opt, True, BTN_TEXT)
                surf.blit(t, t.get_rect(midleft=(r.x + 8, r.centery)))

    def handle_click(self, pos):
        if self.rect.collidepoint(pos):
            self.open = not self.open
            return True
        if self.open:
            for i, opt in enumerate(self.visible()):
                if self.option_rect(i).collidepoint(pos):
                    self.value, self.open = opt, False
                    return True
            self.open = False
        return False

    def handle_wheel(self, pos, dy):
        if not self.open:
            return False
        box = pygame.Rect(self.rect.x, self.rect.bottom, self.rect.width, self.rect.height * self.max_drop)
        if box.collidepoint(pos):
            self.scroll = max(0, min(max(0, len(self.options) - self.max_drop), self.scroll - int(dy)))
            return True
        return False


class Stepper:
    def __init__(self, rect, value, lo, hi, label, step=1):
        self.rect, self.value, self.lo, self.hi, self.label, self.step = rect, value, lo, hi, label, step
        self.minus = pygame.Rect(rect.x, rect.y, 28, rect.height)
        self.plus = pygame.Rect(rect.right - 28, rect.y, 28, rect.height)

    def draw(self, surf, font, small):
        pygame.draw.rect(surf, BTN, self.rect, border_radius=6)
        for r, ch in ((self.minus, "-"), (self.plus, "+")):
            pygame.draw.rect(surf, BTN_HOT, r, border_radius=6)
            t = font.render(ch, True, BTN_TEXT)
            surf.blit(t, t.get_rect(center=r.center))
        body = font.render(str(self.value), True, BTN_TEXT)
        surf.blit(body, body.get_rect(center=self.rect.center))
        surf.blit(small.render(self.label, True, (170, 175, 190)), (self.rect.x, self.rect.y - 14))

    def handle_click(self, pos):
        if self.minus.collidepoint(pos):
            self.value = max(self.lo, self.value - self.step)
            return True
        if self.plus.collidepoint(pos):
            self.value = min(self.hi, self.value + self.step)
            return True
        return False


class CheckBox:
    def __init__(self, rect, label, checked=False):
        self.box = pygame.Rect(rect.x, rect.y + (rect.height - 20) // 2, 20, 20)
        self.rect, self.label, self.checked = rect, label, checked

    def draw(self, surf, font):
        pygame.draw.rect(surf, (240, 244, 250) if self.checked else (40, 48, 66), self.box, border_radius=4)
        pygame.draw.rect(surf, (120, 140, 180), self.box, 2, border_radius=4)
        if self.checked:
            pygame.draw.line(surf, (30, 90, 50), (self.box.x + 4, self.box.centery), (self.box.x + 8, self.box.bottom - 5), 3)
            pygame.draw.line(surf, (30, 90, 50), (self.box.x + 8, self.box.bottom - 5), (self.box.right - 4, self.box.y + 4), 3)
        txt = font.render(self.label, True, HUD)
        surf.blit(txt, (self.box.right + 8, self.rect.y + (self.rect.height - txt.get_height()) // 2))

    def handle_click(self, pos):
        if pygame.Rect(self.box.x, self.rect.y, self.rect.width, self.rect.height).collidepoint(pos):
            self.checked = not self.checked
            return True
        return False


class Slider:
    def __init__(self, rect, label, value, lo, hi):
        self.rect, self.label, self.lo, self.hi = rect, label, float(lo), float(hi)
        self.value, self.dragging = float(value), False

    def knob_x(self):
        t = (self.value - self.lo) / (self.hi - self.lo) if self.hi != self.lo else 0
        return int(self.rect.x + t * self.rect.width)

    def set_from_x(self, x):
        t = max(0.0, min(1.0, (x - self.rect.x) / max(self.rect.width, 1)))
        self.value = self.lo + t * (self.hi - self.lo)

    def draw(self, surf, font):
        pygame.draw.rect(surf, (60, 68, 88), self.rect, border_radius=4)
        pygame.draw.circle(surf, BTN_HOT, (self.knob_x(), self.rect.centery), 7)
        surf.blit(font.render("{} {:.3f}".format(self.label, self.value), True, HUD), (self.rect.x, self.rect.y - 14))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.inflate(0, 12).collidepoint(event.pos):
            self.dragging = True
            self.set_from_x(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.set_from_x(event.pos[0])
            return True
        return False


class TextField:
    def __init__(self, rect, text=""):
        self.rect, self.text, self.active = pygame.Rect(rect), text, False

    def draw(self, surf, font):
        pygame.draw.rect(surf, (20, 24, 34), self.rect, border_radius=6)
        pygame.draw.rect(surf, BTN_HOT if self.active else (120, 140, 180), self.rect, 2, border_radius=6)
        surf.blit(font.render((self.text + ("|" if self.active else ""))[:60], True, HUD), (self.rect.x + 8, self.rect.y + 6))

    def handle_key(self, event):
        if not self.active or event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
            return True
        if event.unicode and event.unicode.isprintable() and len(self.text) < 80:
            self.text += event.unicode
            return True
        return False


class FileDialog:
    ROW_H = 28
    VISIBLE = 9

    def __init__(self):
        self.visible = False
        self.mode = "load"
        self.result = None
        self.folder = default_songs_dir()
        self.entries = []
        self.scroll = 0
        self.selected = -1
        self.field = TextField(pygame.Rect(0, 0, 100, 32), "")
        self.ok_btn = Button(pygame.Rect(0, 0, 100, 32), "OK")
        self.cancel_btn = Button(pygame.Rect(0, 0, 100, 32), "Cancel")
        self.home_btn = Button(pygame.Rect(0, 0, 90, 24), "songs/")
        self.box = pygame.Rect(0, 0, 720, 460)
        self.list_rect = pygame.Rect(0, 0, 100, 100)
        self.message = ""
        self._last_click = 0

    def layout(self, screen_size):
        sw, sh = screen_size
        self.box = pygame.Rect(0, 0, min(720, sw - 40), min(480, sh - 40))
        self.box.center = (sw // 2, sh // 2)
        self.field.rect = pygame.Rect(self.box.x + 20, self.box.y + 58, self.box.width - 40, 32)
        self.list_rect = pygame.Rect(self.box.x + 20, self.box.y + 120, self.box.width - 40, self.VISIBLE * self.ROW_H)
        self.ok_btn.rect = pygame.Rect(self.box.x + 20, self.box.bottom - 50, 100, 32)
        self.cancel_btn.rect = pygame.Rect(self.box.x + 130, self.box.bottom - 50, 100, 32)
        self.home_btn.rect = pygame.Rect(self.box.right - 110, self.box.bottom - 46, 90, 24)

    def refresh(self):
        self.folder = usable_dir(self.folder)
        folders, files = list_dir_entries(self.folder)
        self.entries = [("dir", "..")] + [("dir", name) for name in folders] + [("file", name) for name in files]
        self.scroll = 0
        files_only = [e for e in self.entries if e[0] == "file"]
        if files_only:
            self.selected = self.entries.index(files_only[0])
            self.field.text = files_only[0][1]
        else:
            self.selected = 0 if self.entries else -1
            self.field.text = ""

    def open(self, mode, folder=None):
        self.mode = mode
        self.visible = True
        self.result = None
        self.folder = usable_dir(folder)
        self.refresh()
        self.field.active = True
        self.message = ""
        self._last_click = 0

    def row_rect(self, i):
        return pygame.Rect(self.list_rect.x, self.list_rect.y + i * self.ROW_H, self.list_rect.width, self.ROW_H)

    def shown(self):
        return self.entries[self.scroll:self.scroll + self.VISIBLE]

    def enter_dir(self, name):
        if name == "..":
            parent = os.path.dirname(self.folder)
            self.folder = usable_dir(parent) if parent else self.folder
        else:
            self.folder = usable_dir(os.path.join(self.folder, name))
        self.refresh()

    def _accept(self):
        if 0 <= self.selected < len(self.entries) and self.entries[self.selected][0] == "dir":
            self.enter_dir(self.entries[self.selected][1])
            return False
        name = self.field.text.strip()
        if 0 <= self.selected < len(self.entries) and self.entries[self.selected][0] == "file":
            name = self.entries[self.selected][1]
            self.field.text = name
        path = resolve_song_path(name, self.folder)
        if self.mode == "load":
            if not path or not os.path.isfile(path):
                self.message = "File not found: {}".format(name or "(empty)")
                self.result = None
                return False
            self.result = path
            self.visible = False
            return True
        if not path:
            self.message = "Type a file name ending in .mid"
            return False
        if not os.path.splitext(path)[1]:
            path += ".mid"
        self.result = path
        self.visible = False
        return True

    def handle_event(self, event):
        if not self.visible:
            return False
        if event.type == pygame.MOUSEWHEEL and self.list_rect.collidepoint(pygame.mouse.get_pos()):
            max_scroll = max(0, len(self.entries) - self.VISIBLE)
            self.scroll = max(0, min(max_scroll, self.scroll - int(event.y)))
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.visible, self.result = False, None
                return True
            if event.key == pygame.K_RETURN:
                self._accept()
                return True
            if event.key == pygame.K_DOWN and self.entries:
                self.selected = min(len(self.entries) - 1, max(0, self.selected) + 1)
                kind, name = self.entries[self.selected]
                if kind == "file":
                    self.field.text = name
                if self.selected >= self.scroll + self.VISIBLE:
                    self.scroll = self.selected - self.VISIBLE + 1
                return True
            if event.key == pygame.K_UP and self.entries:
                self.selected = max(0, self.selected - 1)
                kind, name = self.entries[self.selected]
                if kind == "file":
                    self.field.text = name
                if self.selected < self.scroll:
                    self.scroll = self.selected
                return True
            self.field.handle_key(event)
            self.selected = -1
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self.cancel_btn.hit(pos):
                self.visible, self.result = False, None
                return True
            if self.ok_btn.hit(pos):
                self._accept()
                return True
            if self.home_btn.hit(pos):
                self.folder = default_songs_dir()
                self.refresh()
                return True
            if self.list_rect.collidepoint(pos):
                for i, (kind, name) in enumerate(self.shown()):
                    if self.row_rect(i).collidepoint(pos):
                        idx = self.scroll + i
                        now = pygame.time.get_ticks()
                        double = (idx == self.selected and now - self._last_click < 400)
                        self.selected = idx
                        self.field.active = False
                        self._last_click = now
                        if kind == "dir":
                            if double:
                                self.enter_dir(name)
                            return True
                        self.field.text = name
                        if double and self.mode == "load":
                            self._accept()
                        return True
                return True
            self.field.active = self.field.rect.collidepoint(pos)
            return True
        return True

    def draw(self, surf, font, small):
        if not self.visible:
            return
        self.layout(surf.get_size())
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((8, 10, 16, 180))
        surf.blit(shade, (0, 0))
        pygame.draw.rect(surf, PANEL, self.box, border_radius=14)
        pygame.draw.rect(surf, (120, 140, 180), self.box, 2, border_radius=14)
        title = "Load MIDI" if self.mode == "load" else "Save MIDI (.mid)"
        surf.blit(font.render(title, True, HUD), (self.box.x + 20, self.box.y + 16))
        self.field.draw(surf, small)
        surf.blit(small.render("Folder: {}".format(self.folder), True, (170, 175, 190)),
                  (self.box.x + 20, self.box.y + 98))
        pygame.draw.rect(surf, (20, 24, 34), self.list_rect, border_radius=6)
        mouse = pygame.mouse.get_pos()
        shown = self.shown()
        if not shown:
            surf.blit(small.render("Empty folder", True, (140, 145, 160)),
                      (self.list_rect.x + 8, self.list_rect.y + 8))
        for i, (kind, name) in enumerate(shown):
            r = self.row_rect(i)
            idx = self.scroll + i
            hot = r.collidepoint(mouse) or idx == self.selected
            if idx == self.selected:
                color = (70, 110, 180)
            elif hot:
                color = (50, 70, 110)
            elif kind == "dir":
                color = (38, 48, 62)
            else:
                color = (32, 38, 52)
            pygame.draw.rect(surf, color, r)
            label = "[{}]".format(name) if kind == "dir" else name
            surf.blit(small.render(label, True, (200, 210, 160) if kind == "dir" else BTN_TEXT), (r.x + 8, r.y + 6))
        if self.message:
            surf.blit(small.render(self.message, True, (220, 120, 120)), (self.box.x + 250, self.box.bottom - 42))
        self.ok_btn.draw(surf, small, self.ok_btn.hit(mouse))
        self.cancel_btn.draw(surf, small, self.cancel_btn.hit(mouse))
        self.home_btn.draw(surf, small, self.home_btn.hit(mouse))


class HelpDialog:
    def __init__(self):
        self.visible = False
        self.scroll = 0
        self.close_btn = Button(pygame.Rect(0, 0, 100, 34), "Close")

    def handle_event(self, event):
        if not self.visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.close_btn.hit(event.pos):
            self.visible = False
            return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
            self.visible = False
            return True
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y)
            return True
        return True

    def draw(self, surf, font, small):
        if not self.visible:
            return
        w, h = surf.get_size()
        box = pygame.Rect(60, 40, w - 120, h - 100)
        self.close_btn.rect = pygame.Rect(box.centerx - 50, box.bottom - 48, 100, 34)
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((8, 10, 16, 180))
        surf.blit(shade, (0, 0))
        pygame.draw.rect(surf, PANEL, box, border_radius=14)
        pygame.draw.rect(surf, (120, 140, 180), box, 2, border_radius=14)
        clip = pygame.Rect(box.x + 16, box.y + 16, box.width - 32, box.height - 80)
        surf.set_clip(clip)
        y = clip.y - self.scroll * 16
        for line in HELP_TEXT:
            surf.blit(small.render(line, True, GOOD if line and not line.startswith(" ") else HUD), (clip.x, y))
            y += 20
        surf.set_clip(None)
        self.close_btn.draw(surf, font, self.close_btn.hit(pygame.mouse.get_pos()))


@dataclass
class FlyingNote:
    midi: int
    x: float
    born: float
    hit: bool = False
    missed: bool = False
    quiz: bool = False
    ghost: bool = False
    current: bool = False
    song_index: int = -1
    previewed: bool = False
    dur: float = 1.0


def draw_sharp(surf, x, y):
    pygame.draw.line(surf, INK, (x - 2, y - 8), (x - 2, y + 8), 2)
    pygame.draw.line(surf, INK, (x + 3, y - 8), (x + 3, y + 8), 2)
    pygame.draw.line(surf, INK, (x - 6, y - 3), (x + 7, y - 6), 2)
    pygame.draw.line(surf, INK, (x - 6, y + 5), (x + 7, y + 2), 2)


def draw_flat(surf, x, y):
    pygame.draw.line(surf, INK, (x - 2, y - 10), (x - 2, y + 6), 2)
    pygame.draw.arc(surf, INK, pygame.Rect(x - 2, y - 2, 10, 10), 4.2, 1.8, 2)


def draw_natural(surf, x, y):
    pygame.draw.line(surf, INK, (x - 3, y - 9), (x - 3, y + 5), 2)
    pygame.draw.line(surf, INK, (x + 3, y - 5), (x + 3, y + 9), 2)
    pygame.draw.line(surf, INK, (x - 3, y - 2), (x + 3, y - 5), 2)
    pygame.draw.line(surf, INK, (x - 3, y + 5), (x + 3, y + 2), 2)


def draw_clef_g(surf, x, top, spacing):
    pygame.draw.circle(surf, INK, (x + 16, int(top + 3 * spacing)), int(spacing * 0.7), 3)
    pygame.draw.line(surf, INK, (x + 22, int(top - spacing * 0.6)), (x + 10, int(top + 5.4 * spacing)), 3)
    pygame.draw.circle(surf, INK, (x + 8, int(top + 5.2 * spacing)), 5)


def draw_clef_f(surf, x, top, spacing):
    f3_y = top + spacing
    pygame.draw.circle(surf, INK, (x + 14, int(f3_y)), int(spacing * 0.55))
    pygame.draw.circle(surf, INK, (x + 32, int(f3_y - 8)), 4)
    pygame.draw.circle(surf, INK, (x + 32, int(f3_y + 8)), 4)


def draw_staff(surf, left, right, top, spacing):
    for i in range(5):
        pygame.draw.line(surf, LINE, (left, int(top + i * spacing)), (right, int(top + i * spacing)), 2)


def draw_barlines(surf, left, right, top, bottom, bars, middle_hl=False):
    width = right - left
    bar_w = width / bars
    if middle_hl:
        pygame.draw.rect(surf, (220, 232, 210), pygame.Rect(int(left + bar_w), top, int(bar_w), bottom - top))
    for i in range(bars + 1):
        x = left + int(i * width / bars)
        pygame.draw.line(surf, LINE, (x, top), (x, bottom), 3 if i in (0, bars) else 2)


def draw_key_signature(surf, left, top, spacing, key, bass=False):
    sig = KEY_SIG.get(key, {})
    if not sig:
        return
    flats = key in USES_FLATS
    order = FLAT_ORDER if flats else SHARP_ORDER
    steps = (BASS_FLAT_STEPS if bass else TREBLE_FLAT_STEPS) if flats else (BASS_SHARP_STEPS if bass else TREBLE_SHARP_STEPS)
    x, count = left + 8, 0
    for letter in order:
        if letter not in sig:
            break
        y = top + 4 * spacing - steps[count] * spacing
        (draw_flat if flats else draw_sharp)(surf, x, int(y))
        x += 14
        count += 1


def draw_ledger(surf, cx, y, staff_top, spacing):
    half = 12
    line_y = staff_top - spacing
    while y <= line_y + 1:
        pygame.draw.line(surf, LINE, (cx - half, int(line_y)), (cx + half, int(line_y)), 2)
        line_y -= spacing
    line_y = staff_top + 4 * spacing + spacing
    while y >= line_y - 1:
        pygame.draw.line(surf, LINE, (cx - half, int(line_y)), (cx + half, int(line_y)), 2)
        line_y += spacing


def draw_notehead(surf, x, y, spacing, color=NOTE_COLOR, alpha=255, dur=1.0):
    rx, ry = int(spacing * 0.72), int(spacing * 0.50)
    filled = dur < 1.75
    flag = dur <= 0.6
    stem = dur < 3.6
    if alpha >= 255:
        rect = pygame.Rect(0, 0, rx * 2, ry * 2)
        rect.center = (int(x), int(y))
        if filled:
            pygame.draw.ellipse(surf, color, rect)
        else:
            pygame.draw.ellipse(surf, color, rect, 2)
        if stem:
            pygame.draw.line(surf, color, (rect.right - 2, int(y)), (rect.right - 2, int(y - spacing * 3.2)), 2)
        if flag:
            pygame.draw.line(surf, color, (rect.right - 2, int(y - spacing * 3.2)),
                             (rect.right + 8, int(y - spacing * 2.2)), 2)
    else:
        tmp = pygame.Surface((rx * 4 + 12, int(spacing * 4)), pygame.SRCALPHA)
        cx, cy = rx * 2, int(spacing * 3.2)
        col = color + (alpha,)
        if filled:
            pygame.draw.ellipse(tmp, col, pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2))
        else:
            pygame.draw.ellipse(tmp, col, pygame.Rect(cx - rx, cy - ry, rx * 2, ry * 2), 2)
        if stem:
            pygame.draw.line(tmp, col, (cx + rx - 2, cy), (cx + rx - 2, cy - int(spacing * 3.2)), 2)
        surf.blit(tmp, (int(x) - cx, int(y) - cy))


def draw_accidental(surf, x, y, shown):
    if shown is None:
        return
    if shown > 0:
        draw_sharp(surf, x - 16, y)
    elif shown < 0:
        draw_flat(surf, x - 16, y)
    else:
        draw_natural(surf, x - 16, y)


class Piano:
    def __init__(self, rect):
        self.rect = rect
        self.pressed = set()
        self._layout()

    def _layout(self):
        r = self.rect
        whites = [m for m in range(A0, C8 + 1) if not is_black(m)]
        self.white_w = r.width / max(len(whites), 1)
        self.white_keys, self.black_keys = [], []
        i = 0
        for m in range(A0, C8 + 1):
            if not is_black(m):
                self.white_keys.append((m, pygame.Rect(int(r.x + i * self.white_w), r.y, int(self.white_w) - 1, r.height)))
                i += 1
        bw, bh = self.white_w * 0.58, r.height * 0.62
        white_index = {m: idx for idx, (m, _) in enumerate(self.white_keys)}
        for m in range(A0, C8 + 1):
            if is_black(m):
                prev = m - 1
                while is_black(prev):
                    prev -= 1
                bx = r.x + white_index[prev] * self.white_w + self.white_w - bw / 2
                self.black_keys.append((m, pygame.Rect(int(bx), r.y, int(bw), int(bh))))

    def relayout(self, rect):
        self.rect = rect
        self._layout()

    def draw(self, surf, font):
        pygame.draw.rect(surf, (12, 12, 16), self.rect.inflate(8, 8), border_radius=6)
        for midi, rect in self.white_keys:
            pygame.draw.rect(surf, WHITE_DOWN if midi in self.pressed else WHITE_KEY, rect)
            pygame.draw.rect(surf, (160, 160, 170), rect, 1)
            if midi % 12 == 0:
                label = font.render(midi_name(midi), True, (80, 80, 90))
                surf.blit(label, label.get_rect(midbottom=(rect.centerx, rect.bottom - 4)))
        for midi, rect in self.black_keys:
            pygame.draw.rect(surf, BLACK_DOWN if midi in self.pressed else BLACK_KEY, rect, border_radius=2)

    def note_at(self, pos):
        for midi, rect in self.black_keys:
            if rect.collidepoint(pos):
                return midi
        for midi, rect in self.white_keys:
            if rect.collidepoint(pos):
                return midi
        return None


class SynthDialog:
    FIELDS = [
        ("attack", 0.001, 0.25), ("decay", 0.1, 8.0), ("sustain", 0.0, 0.9),
        ("h1", 0.0, 1.0), ("h2", 0.0, 1.0), ("h3", 0.0, 1.0), ("h4", 0.0, 1.0),
        ("h5", 0.0, 1.0), ("h6", 0.0, 1.0), ("h7", 0.0, 1.0), ("h8", 0.0, 1.0),
        ("noise", 0.0, 0.12), ("vib_rate", 0.0, 8.0), ("vib_depth", 0.0, 0.12),
        ("fm", 0.0, 0.08), ("pair_mix", 0.0, 1.0),
        ("pan_rate", 0.0, 8.0), ("pan_depth", 0.0, 1.0), ("pan_square", 0.0, 1.0),
        ("chorus_rate", 0.0, 4.0), ("chorus_mix", 0.0, 1.0),
        ("trem_rate", 0.0, 12.0), ("trem_depth", 0.0, 1.0),
        ("delay_time", 0.0, 0.5), ("delay_mix", 0.0, 0.8), ("distortion", 0.0, 1.0),
    ]

    def __init__(self, patch, names):
        self.visible = False
        self.box = pygame.Rect(40, 40, 1200, 700)
        self.name = TextField(pygame.Rect(56, 84, 220, 30), patch.name)
        self.pair = ComboBox(pygame.Rect(290, 84, 180, 30), ["(none)"] + list(names), "(none)")
        self.sliders = []
        for i, (field, lo, hi) in enumerate(self.FIELDS):
            col, row = divmod(i, 9)
            self.sliders.append(Slider(pygame.Rect(56 + col * 340, 140 + row * 48, 250, 8), field, getattr(patch, field), lo, hi))
        self.save_btn = Button(pygame.Rect(490, 84, 80, 30), "Save")
        self.preview_btn = Button(pygame.Rect(580, 84, 90, 30), "Preview")
        self.close_btn = Button(pygame.Rect(1140, 52, 80, 28), "Close")

    def load_patch(self, patch, names):
        self.name.text = patch.name
        self.pair.set_options(["(none)"] + [n for n in names if n != patch.name], patch.pair or "(none)")
        for sl in self.sliders:
            sl.value = float(getattr(patch, sl.label))

    def to_patch(self):
        p = Patch(self.name.text.strip() or "Custom")
        for sl in self.sliders:
            setattr(p, sl.label, sl.value)
        p.pair = "" if self.pair.value == "(none)" else self.pair.value
        return p

    def draw(self, surf, font, small):
        if not self.visible:
            return
        w, h = surf.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((8, 10, 16, 170))
        surf.blit(shade, (0, 0))
        pygame.draw.rect(surf, PANEL, self.box, border_radius=14)
        pygame.draw.rect(surf, (120, 140, 180), self.box, 2, border_radius=14)
        surf.blit(font.render("Synthesizer", True, HUD), (56, 50))
        self.name.draw(surf, small)
        mouse = pygame.mouse.get_pos()
        self.save_btn.draw(surf, small, self.save_btn.hit(mouse))
        self.preview_btn.draw(surf, small, self.preview_btn.hit(mouse))
        self.close_btn.draw(surf, small, self.close_btn.hit(mouse))
        for sl in self.sliders:
            sl.draw(surf, small)
        self.pair.draw(surf, small, self.pair.rect.collidepoint(mouse))


class Tutor:
    def __init__(self):
        pygame.mixer.pre_init(SAMPLE_RATE, size=-16, channels=2, buffer=512)
        pygame.init()
        pygame.mixer.set_num_channels(32)
        self.cfg = load_settings()
        self.sw, self.sh = self.cfg["win_w"], self.cfg["win_h"]
        self.screen = pygame.display.set_mode((self.sw, self.sh), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("georgia", 20)
        self.small = pygame.font.SysFont("consolas", 14)
        self.big = pygame.font.SysFont("georgia", 26, bold=True)
        self.huge = pygame.font.SysFont("georgia", 42, bold=True)
        self.keymap = load_keymap()
        self.mapped_pitches = sorted(set(self.keymap.values()))
        self.builtins = builtin_patches()
        self.custom = load_custom_patches()
        self.sounds, self.notes = {}, []
        self.held_keys, self.held_midi = set(), set()
        self.spacing = 14
        names = self.tone_names()
        inst = self.cfg["instrument"] if self.cfg["instrument"] in names else "Piano"
        self.combo = ComboBox(pygame.Rect(16, 84, 150, 26), names, inst, max_drop=12)
        self.key_combo = ComboBox(pygame.Rect(172, 84, 58, 26), MAJOR_KEYS, self.cfg.get("key", "C"))
        self.style_combo = ComboBox(pygame.Rect(236, 84, 120, 26), QUIZ_STYLES, self.cfg.get("quiz_style", "Random"))
        self.stepper = Stepper(pygame.Rect(364, 84, 86, 26), self.cfg["simultaneous"], 1, 8, "voices")
        self.length_stepper = Stepper(pygame.Rect(458, 84, 110, 26), self.cfg["quiz_length"], 1, 500, "quiz/rec", 5)
        self.limit_box = CheckBox(pygame.Rect(580, 80, 130, 30), "site.key", self.cfg["limit_to_keymap"])
        self.use_song_box = CheckBox(pygame.Rect(720, 80, 150, 30), "Use song", self.cfg.get("use_song", False))
        self.preview_box = CheckBox(pygame.Rect(880, 80, 150, 30), "half-vol", self.cfg.get("preview", True))
        self.offkey_box = CheckBox(pygame.Rect(1030, 80, 160, 30), "off-key acc.", self.cfg.get("offkey", False))
        self.rec_btn = Button(pygame.Rect(250, 10, 86, 28), "Record")
        self.play_btn = Button(pygame.Rect(344, 10, 70, 28), "Play")
        self.stop_btn = Button(pygame.Rect(422, 10, 70, 28), "Stop")
        self.load_btn = Button(pygame.Rect(500, 10, 70, 28), "Load")
        self.save_btn = Button(pygame.Rect(578, 10, 70, 28), "Save")
        self.quiz_btn = Button(pygame.Rect(656, 10, 150, 28), self.quiz_button_label())
        self.synth_btn = Button(pygame.Rect(814, 10, 110, 28), "Synthesizer")
        self.help_btn = Button(pygame.Rect(932, 10, 70, 28), "Help")
        self.bpm_minus = Button(pygame.Rect(self.sw - 268, 10, 36, 28), "-")
        self.bpm_plus = Button(pygame.Rect(self.sw - 54, 10, 36, 28), "+")
        self.piano = Piano(pygame.Rect(16, self.sh - self.sh // 3 + 8, self.sw - 32, self.sh // 3 - 24))
        self.staff_left, self.staff_right = 90, self.sw - 30
        self.treble_top = HUD_H + 24
        self.bass_top = int(self.treble_top + 4 * self.spacing + 48)
        self.synth = SynthDialog(self.current_patch(), names)
        self.help = HelpDialog()
        self.files = FileDialog()
        self.midi = MidiIn()
        self.running, self.time = True, 0.0
        self.quiz_active = False
        self.quiz_events = []
        self.quiz_index = 0
        self.quiz_beat = 0.0
        self.quiz_spawned = 0
        self.quiz_total = self.cfg["quiz_length"]
        self.score = 0
        self.show_results = False
        self.result_ok = Button(pygame.Rect(self.sw // 2 - 60, self.sh // 2 + 80, 120, 40), "OK")
        self.song = Song(key=self.cfg["key"], bpm=self.cfg["bpm"])
        self.play_list = []
        self.recording = False
        self.record_started = 0.0
        self.playback = False
        self.play_index = 0
        self.play_beat = 0.0
        self.pending_file_mode = None
        self.status = "Songs folder: {}".format(self.song_folder())
        self.refresh_caption()

    def refresh_caption(self):
        name = abbrev_name(self.song.title)
        title = "Sight Tutor - {}".format(name) if name and name != "Untitled" else "Sight Tutor"
        pygame.display.set_caption(title)

    def song_folder(self):
        return usable_dir(self.cfg.get("last_dir"))

    def remember_dir(self, path):
        folder = os.path.dirname(os.path.abspath(path)) if os.path.splitext(path)[1] else path
        self.cfg["last_dir"] = usable_dir(folder)
        self.persist()

    def apply_size(self, w, h):
        w, h = max(MIN_W, w), max(MIN_H, h)
        self.sw, self.sh = w, h
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self.cfg["win_w"], self.cfg["win_h"] = w, h
        self.staff_right = w - 30
        piano_h = h // 3
        self.piano.relayout(pygame.Rect(16, h - piano_h + 8, w - 32, piano_h - 24))
        self.bpm_minus.rect = pygame.Rect(w - 268, 10, 36, 28)
        self.bpm_plus.rect = pygame.Rect(w - 54, 10, 36, 28)
        self.result_ok.rect = pygame.Rect(w // 2 - 60, h // 2 + 80, 120, 40)
        self.persist()

    def tone_names(self):
        return [p.name for p in self.builtins] + [p.name for p in self.custom]

    def find_patch(self, name):
        for p in self.custom + self.builtins:
            if p.name == name:
                return p
        return None

    def current_patch(self):
        return self.find_patch(self.combo.value) or self.builtins[0]

    def quiz_button_label(self):
        if getattr(self, "use_song_box", None) and self.use_song_box.checked:
            return "Start song quiz"
        return "Start {}-note quiz".format(self.length_stepper.value)

    def sound_for(self, midi):
        key = (self.combo.value, midi)
        if key not in self.sounds:
            self.sounds[key] = make_sound(self.find_patch, self.current_patch(), midi)
        return self.sounds[key]

    def play_quiet(self, midi):
        snd = self.sound_for(midi)
        ch = snd.play()
        if ch is not None:
            ch.set_volume(0.5)

    def persist(self):
        self.cfg.update({
            "simultaneous": self.stepper.value, "instrument": self.combo.value,
            "limit_to_keymap": self.limit_box.checked, "quiz_length": self.length_stepper.value,
            "key": self.key_combo.value, "use_song": self.use_song_box.checked,
            "preview": self.preview_box.checked, "offkey": self.offkey_box.checked,
            "quiz_style": self.style_combo.value,
            "win_w": self.sw, "win_h": self.sh,
            "last_dir": usable_dir(self.cfg.get("last_dir")),
        })
        save_settings(self.cfg)

    def pixels_per_second(self):
        seconds = (BARS_VISIBLE * BEATS_PER_BAR) * 60.0 / max(self.cfg["bpm"], 1.0)
        return (self.staff_right - self.staff_left) / seconds

    def bar_bounds(self):
        bw = (self.staff_right - self.staff_left) / BARS_VISIBLE
        return self.staff_left + bw, self.staff_left + 2 * bw, bw

    def still_in_or_before_middle(self, note):
        return note.x >= self.bar_bounds()[0]

    def quiz_pool(self):
        if self.limit_box.checked and self.mapped_pitches:
            return list(self.mapped_pitches)
        return list(range(QUIZ_LO, QUIZ_HI + 1))

    def build_random_events(self):
        key = self.key_combo.value
        style = self.style_combo.value
        voices = self.stepper.value
        length = self.length_stepper.value
        offkey = self.offkey_box.checked
        pool = self.quiz_pool()
        events = []
        beat = 0.0
        remaining = length
        prog = random.choice(PROGRESSIONS)
        step = 0
        while remaining > 0:
            pick = style if style != "Mixed" else random.choice(["Random", "Chords", "Progressions", "Arpeggios"])
            octave = random.choice((3, 4, 5))
            if pick == "Chords":
                deg = random.randint(0, 6)
                tones = [maybe_color(m, key, offkey) for m in triad_for_degree(key, deg, octave, voices)]
                notes = [SongNote(beat, m, 2.0) for m in tones[:remaining]]
                events.append((beat, notes))
                remaining -= len(notes)
                beat += 2.0
            elif pick == "Progressions":
                deg = prog[step % len(prog)]
                step += 1
                tones = [maybe_color(m, key, offkey) for m in triad_for_degree(key, deg, octave, max(3, voices))]
                notes = [SongNote(beat, m, 2.0) for m in tones[:remaining]]
                events.append((beat, notes))
                remaining -= len(notes)
                beat += 2.0
            elif pick == "Arpeggios":
                deg = random.randint(0, 6)
                tones = [maybe_color(m, key, offkey) for m in triad_for_degree(key, deg, octave, max(3, voices))]
                if random.random() < 0.5:
                    tones = list(reversed(tones))
                for m in tones:
                    if remaining <= 0:
                        break
                    events.append((beat, [SongNote(beat, m, 0.5)]))
                    remaining -= 1
                    beat += 0.5
            else:
                n = min(voices, remaining, max(1, len(pool)))
                if self.limit_box.checked and pool:
                    chosen = random.sample(pool, n) if n <= len(pool) else [random.choice(pool) for _ in range(n)]
                else:
                    pcs = scale_pcs(key)
                    chosen = []
                    for _ in range(n):
                        pc = random.choice(pcs)
                        octv = random.choice((3, 4, 5))
                        chosen.append(maybe_color(clamp_midi((octv + 1) * 12 + pc), key, offkey))
                events.append((beat, [SongNote(beat, m, 1.0) for m in chosen]))
                remaining -= len(chosen)
                beat += 1.0
        return events

    def start_quiz(self):
        use_song = self.use_song_box.checked and bool(self.song.notes)
        if self.use_song_box.checked and not self.song.notes:
            self.status = "No song in memory"
            return
        if use_song:
            events = song_events(self.song)
            length = sum(len(notes) for _, notes in events)
        else:
            events = self.build_random_events()
            length = sum(len(notes) for _, notes in events)
        self.quiz_events = events
        self.quiz_index = 0
        self.quiz_beat = 0.0
        self.quiz_spawned = 0
        self.quiz_total = length
        self.score = 0
        self.quiz_active = True
        self.playback = False
        self.show_results = False
        self.notes = []
        self.quiz_btn.label = "Quiz running..."
        self.status = "Song quiz ({} notes, MIDI timing)".format(length) if use_song else "Random quiz ({})".format(self.style_combo.value)

    def spawn_quiz_group(self, group):
        for sn in group:
            self.notes.append(FlyingNote(
                int(sn.midi), float(self.staff_right - 18), self.time,
                quiz=True, dur=max(0.25, float(sn.dur))))
            self.quiz_spawned += 1

    def update_quiz(self, dt):
        if not self.quiz_active:
            return
        self.quiz_beat += dt * self.cfg["bpm"] / 60.0
        while self.quiz_index < len(self.quiz_events) and self.quiz_events[self.quiz_index][0] <= self.quiz_beat + 1e-6:
            _, group = self.quiz_events[self.quiz_index]
            self.spawn_quiz_group(group)
            self.quiz_index += 1

    def finish_quiz(self, stopped=False):
        self.quiz_active = False
        self.quiz_events = []
        self.show_results = True
        self.quiz_btn.label = self.quiz_button_label()
        self.status = "Quiz stopped" if stopped else "Quiz finished"

    def maybe_finish_quiz(self):
        if not self.quiz_active:
            return
        pending = [n for n in self.notes if n.quiz and not n.hit and not n.missed and not n.ghost]
        if self.quiz_index >= len(self.quiz_events) and not pending:
            self.finish_quiz(False)

    def stop_all(self):
        if self.recording:
            self.recording = False
            self.rec_btn.label = "Record"
            self.status = "Recording stopped ({} notes)".format(len(self.song.notes))
        if self.playback:
            self.playback = False
            self.status = "Playback stopped"
        if self.quiz_active:
            self.finish_quiz(True)

    def spawn_ghost(self, midi):
        mid_left, mid_right, _ = self.bar_bounds()
        self.notes.append(FlyingNote(midi, (mid_left + mid_right) / 2.0, self.time, ghost=True))

    def play_pitch(self, midi, from_user=True):
        midi = max(A0, min(C8, midi))
        if self.recording and from_user:
            beat = (self.time - self.record_started) * self.cfg["bpm"] / 60.0
            self.song.notes.append(SongNote(beat, midi, 1.0))
            self.status = "Recording {}/{}".format(len(self.song.notes), self.length_stepper.value)
            if len(self.song.notes) >= self.length_stepper.value:
                self.stop_record()
        if self.quiz_active:
            targets = [n for n in self.notes if n.quiz and not n.hit and not n.missed and not n.ghost
                       and n.midi == midi and self.still_in_or_before_middle(n)]
            self.sound_for(midi).play()
            self.piano.pressed.add(midi)
            self.spawn_ghost(midi)
            if targets:
                targets[0].hit = True
                self.score += 1
            return
        self.sound_for(midi).play()
        if from_user and not self.playback:
            self.notes.append(FlyingNote(midi, float(self.staff_right - 18), self.time))
        self.piano.pressed.add(midi)

    def start_record(self):
        self.recording, self.playback, self.quiz_active = True, False, False
        self.song = Song(key=self.key_combo.value, bpm=self.cfg["bpm"], title="Recording")
        self.record_started = self.time
        self.rec_btn.label = "Stop rec"
        self.status = "Recording 0/{}".format(self.length_stepper.value)
        self.refresh_caption()

    def stop_record(self):
        self.recording = False
        self.rec_btn.label = "Record"
        self.song.key, self.song.bpm = self.key_combo.value, self.cfg["bpm"]
        self.status = "Song in memory: {} notes".format(len(self.song.notes))
        self.refresh_caption()
        if self.song.notes:
            self.pending_file_mode = "save"
            self.files.open("save", self.song_folder())

    def finish_file_dialog(self):
        path = self.files.result
        if not path:
            self.remember_dir(self.files.folder)
            return
        if self.pending_file_mode == "save":
            try:
                path = save_song_file(path, self.song)
                self.song.title = os.path.basename(path)
                self.remember_dir(path)
                self.refresh_caption()
                self.status = "Saved {} ({} notes)".format(path, len(self.song.notes))
            except Exception as e:
                self.status = "Save failed: {}".format(e)
        elif self.pending_file_mode == "load":
            try:
                loaded = load_song_file(path)
            except Exception as e:
                self.status = "Load failed: {}".format(e)
                return
            self.song = loaded
            self.song.title = os.path.basename(path)
            self.play_list = []
            self.playback = False
            if self.song.bpm:
                self.cfg["bpm"] = max(20.0, min(240.0, float(self.song.bpm)))
            self.remember_dir(path)
            self.refresh_caption()
            self.status = "Loaded {} ({} notes)".format(path, len(self.song.notes))
        self.pending_file_mode = None

    def start_playback(self):
        if not self.song.notes:
            self.status = "No song in memory"
            return
        self.playback = True
        self.quiz_active = False
        self.play_list = list(self.song.sorted_notes())
        self.play_index = 0
        self.play_beat = 0.0
        self.notes = []
        self.status = "Playing 0/{} {}".format(len(self.play_list), self.song.title)

    def update_playback(self, dt):
        if not self.playback:
            return
        notes = self.play_list
        if not notes:
            self.playback = False
            self.status = "Playback: song has 0 notes"
            return
        self.play_beat += dt * self.cfg["bpm"] / 60.0
        while self.play_index < len(notes) and notes[self.play_index].beat <= self.play_beat + 1e-6:
            sn = notes[self.play_index]
            self.sound_for(int(sn.midi)).play()
            self.notes.append(FlyingNote(
                int(sn.midi), float(self.staff_right - 18), self.time,
                current=True, song_index=self.play_index, dur=max(0.25, float(sn.dur))))
            self.play_index += 1
            self.status = "Playing {}/{}  beat {:.1f}".format(
                self.play_index, len(notes), self.play_beat)
        cur = self.play_index - 1
        for n in self.notes:
            n.current = (n.song_index == cur)
        if self.play_index >= len(notes) and not [n for n in self.notes if not n.ghost]:
            self.playback = False
            self.status = "Playback done — {} notes in memory".format(len(notes))

    def change_bpm(self, delta):
        self.cfg["bpm"] = max(20.0, min(240.0, self.cfg["bpm"] + delta))
        self.persist()

    def save_tone(self):
        patch = self.synth.to_patch()
        self.custom = [p for p in self.custom if p.name != patch.name] + [patch]
        save_custom_patches(self.custom)
        self.combo.set_options(self.tone_names(), patch.name)
        self.sounds = {}
        self.persist()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                continue
            if event.type == pygame.VIDEORESIZE:
                self.apply_size(event.w, event.h)
                continue
            if self.files.visible:
                self.files.layout(self.screen.get_size())
                self.files.handle_event(event)
                if not self.files.visible:
                    self.finish_file_dialog()
                continue
            if self.help.visible:
                self.help.handle_event(event)
                continue
            if event.type == pygame.MOUSEWHEEL:
                pos = pygame.mouse.get_pos()
                if self.synth.visible:
                    self.synth.pair.handle_wheel(pos, event.y)
                self.combo.handle_wheel(pos, event.y)
                self.style_combo.handle_wheel(pos, event.y)
                continue
            if self.synth.visible:
                if event.type == pygame.KEYDOWN:
                    self.synth.name.handle_key(event)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.synth.name.active = self.synth.name.rect.collidepoint(event.pos)
                    if self.synth.pair.handle_click(event.pos):
                        continue
                    if self.synth.close_btn.hit(event.pos):
                        self.synth.visible = False
                    elif self.synth.save_btn.hit(event.pos):
                        self.save_tone()
                    elif self.synth.preview_btn.hit(event.pos):
                        make_sound(self.find_patch, self.synth.to_patch(), 60).play()
                any(sl.handle_event(event) for sl in self.synth.sliders)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if self.show_results:
                    if self.result_ok.hit(pos):
                        self.show_results = False
                    continue
                if self.help_btn.hit(pos):
                    self.help.visible, self.help.scroll = True, 0
                    continue
                if self.bpm_minus.hit(pos):
                    self.change_bpm(-2)
                    continue
                if self.bpm_plus.hit(pos):
                    self.change_bpm(2)
                    continue
                if self.combo.handle_click(pos):
                    self.cfg["instrument"] = self.combo.value
                    self.sounds = {}
                    self.persist()
                    continue
                if self.key_combo.handle_click(pos):
                    self.cfg["key"] = self.key_combo.value
                    self.persist()
                    continue
                if self.style_combo.handle_click(pos):
                    self.persist()
                    continue
                if self.stepper.handle_click(pos) or self.limit_box.handle_click(pos):
                    self.persist()
                    continue
                if self.use_song_box.handle_click(pos) or self.preview_box.handle_click(pos) or self.offkey_box.handle_click(pos):
                    self.quiz_btn.label = self.quiz_button_label()
                    self.persist()
                    continue
                if self.length_stepper.handle_click(pos):
                    if not self.quiz_active:
                        self.quiz_btn.label = self.quiz_button_label()
                    self.persist()
                    continue
                if self.synth_btn.hit(pos):
                    self.synth.load_patch(self.current_patch(), self.tone_names())
                    self.synth.visible = True
                    continue
                if self.stop_btn.hit(pos):
                    self.stop_all()
                    continue
                if self.rec_btn.hit(pos):
                    self.stop_record() if self.recording else self.start_record()
                    continue
                if self.save_btn.hit(pos):
                    if not self.song.notes:
                        self.status = "Nothing to save"
                    else:
                        self.pending_file_mode = "save"
                        self.files.open("save", self.song_folder())
                    continue
                if self.load_btn.hit(pos):
                    self.pending_file_mode = "load"
                    self.files.open("load", self.song_folder())
                    continue
                if self.play_btn.hit(pos):
                    self.start_playback()
                    continue
                if self.quiz_btn.hit(pos) and not self.quiz_active:
                    self.start_quiz()
                    continue
                note = self.piano.note_at(pos)
                if note is not None:
                    self.held_midi.add(note)
                    self.play_pitch(note)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                note = self.piano.note_at(event.pos)
                if note is not None:
                    self.held_midi.discard(note)
                else:
                    self.held_midi.clear()
            elif event.type == pygame.KEYDOWN:
                if self.show_results and event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                    self.show_results = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                    continue
                ch = event_key_char(event)
                if ch and ch in self.keymap and ch not in self.held_keys:
                    self.held_keys.add(ch)
                    self.play_pitch(self.keymap[ch])
                    continue
                if event.key == pygame.K_UP:
                    self.change_bpm(10 if event.mod & pygame.KMOD_SHIFT else 2)
                elif event.key == pygame.K_DOWN:
                    self.change_bpm(-10 if event.mod & pygame.KMOD_SHIFT else -2)
                elif event.key == pygame.K_LEFT:
                    self.change_bpm(-1)
                elif event.key == pygame.K_RIGHT:
                    self.change_bpm(1)
            elif event.type == pygame.KEYUP:
                ch = event_key_char(event)
                if ch:
                    self.held_keys.discard(ch)
        for n in self.midi.poll_note_ons():
            self.play_pitch(n)

    def update(self, dt):
        self.time += dt
        self.update_quiz(dt)
        self.update_playback(dt)
        speed = self.pixels_per_second()
        mid_left, mid_right, _ = self.bar_bounds()
        alive = []
        for note in self.notes:
            if note.ghost:
                if self.time - note.born < 1.0:
                    alive.append(note)
                continue
            note.x -= speed * dt
            if note.quiz and not note.previewed and note.x <= mid_right:
                note.previewed = True
                if self.preview_box.checked and not note.hit and not note.missed:
                    self.play_quiet(note.midi)
            if note.quiz and not note.hit and not note.missed and note.x < mid_left:
                note.missed = True
            if note.x > self.staff_left - 24:
                alive.append(note)
        self.notes = alive
        mapped = {self.keymap[k] for k in self.held_keys if k in self.keymap}
        recent = {n.midi for n in self.notes if self.time - n.born < 0.16}
        self.piano.pressed = recent | mapped | set(self.held_midi)
        self.maybe_finish_quiz()

    def draw_grand_staff(self):
        left, right, key = self.staff_left, self.staff_right, self.key_combo.value
        paper = pygame.Rect(left - 70, self.treble_top - 28, right - left + 90,
                            (self.bass_top + 4 * self.spacing) - (self.treble_top - 28) + 28)
        pygame.draw.rect(self.screen, STAFF_BG, paper, border_radius=10)
        top, bottom = self.treble_top, int(self.bass_top + 4 * self.spacing)
        draw_barlines(self.screen, left, right, top, bottom, BARS_VISIBLE, True)
        draw_staff(self.screen, left, right, self.treble_top, self.spacing)
        draw_staff(self.screen, left, right, self.bass_top, self.spacing)
        draw_clef_g(self.screen, left - 58, self.treble_top, self.spacing)
        draw_clef_f(self.screen, left - 54, self.bass_top, self.spacing)
        draw_key_signature(self.screen, left + 4, self.treble_top, self.spacing, key, False)
        draw_key_signature(self.screen, left + 4, self.bass_top, self.spacing, key, True)
        mid_left, mid_right, _ = self.bar_bounds()
        lab = self.small.render("hit zone", True, (70, 110, 70))
        self.screen.blit(lab, (int((mid_left + mid_right) / 2 - lab.get_width() / 2), top - 16))
        for note in self.notes:
            letter, acc, octave, shown = spell_midi(note.midi, key)
            y, which = staff_y_spelled(letter, octave, self.treble_top, self.bass_top, self.spacing, note.midi)
            staff_top = self.treble_top if which == "treble" else self.bass_top
            draw_ledger(self.screen, int(note.x), y, staff_top, self.spacing)
            if note.ghost:
                draw_notehead(self.screen, note.x, y, self.spacing, NOTE_GHOST,
                              max(30, int(180 * (1.0 - (self.time - note.born)))), note.dur)
                continue
            col = NOTE_CUR if note.current else NOTE_HIT if note.hit else NOTE_MISS if note.missed else NOTE_COLOR
            draw_accidental(self.screen, note.x, y, shown)
            draw_notehead(self.screen, note.x, y, self.spacing, col, 255, note.dur)

    def draw_hud(self):
        pygame.draw.rect(self.screen, (14, 16, 24), pygame.Rect(0, 0, self.sw, HUD_H))
        self.screen.blit(self.big.render("Sight Tutor", True, HUD), (16, 8))
        self.screen.blit(self.big.render("{:.0f} BPM".format(self.cfg["bpm"]), True, GOOD), (self.sw - 220, 10))
        mouse = pygame.mouse.get_pos()
        rec_fill = None
        if self.recording:
            rec_fill = BTN_REC_BLINK if int(self.time * 3) % 2 == 0 else BTN_REC
        self.rec_btn.draw(self.screen, self.small, self.rec_btn.hit(mouse), rec_fill)
        for b in (self.play_btn, self.stop_btn, self.load_btn, self.save_btn, self.synth_btn, self.help_btn, self.bpm_minus, self.bpm_plus):
            b.draw(self.screen, self.small, b.hit(mouse))
        self.quiz_btn.draw(self.screen, self.small, self.quiz_btn.hit(mouse) and not self.quiz_active)
        self.stepper.draw(self.screen, self.small, self.small)
        self.length_stepper.draw(self.screen, self.small, self.small)
        self.limit_box.draw(self.screen, self.small)
        self.use_song_box.draw(self.screen, self.small)
        self.preview_box.draw(self.screen, self.small)
        self.offkey_box.draw(self.screen, self.small)
        mode = "SONG" if self.use_song_box.checked else self.style_combo.value.upper()
        self.screen.blit(self.small.render("{}  {}".format(mode, self.status), True, GOOD), (16, 58))

    def draw_combos(self):
        mouse = pygame.mouse.get_pos()
        self.combo.draw(self.screen, self.small, self.combo.rect.collidepoint(mouse))
        self.key_combo.draw(self.screen, self.small, self.key_combo.rect.collidepoint(mouse))
        self.style_combo.draw(self.screen, self.small, self.style_combo.rect.collidepoint(mouse))

    def draw_results(self):
        overlay = pygame.Surface((self.sw, self.sh), pygame.SRCALPHA)
        overlay.fill((8, 10, 16, 180))
        self.screen.blit(overlay, (0, 0))
        box = pygame.Rect(self.sw // 2 - 240, self.sh // 2 - 140, 480, 280)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=16)
        title = self.huge.render("Quiz complete", True, HUD)
        self.screen.blit(title, title.get_rect(midtop=(box.centerx, box.y + 24)))
        pct = 100.0 * self.score / max(self.quiz_total, 1)
        score = self.big.render("{} / {}   ({:.0f}%)".format(self.score, self.quiz_total, pct), True, GOOD)
        self.screen.blit(score, score.get_rect(center=(box.centerx, box.centery)))
        self.result_ok.draw(self.screen, self.font, self.result_ok.hit(pygame.mouse.get_pos()))

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.screen.fill(BG)
            self.draw_hud()
            self.draw_grand_staff()
            self.piano.draw(self.screen, self.small)
            self.draw_combos()
            if self.show_results:
                self.draw_results()
            self.synth.draw(self.screen, self.big, self.small)
            self.help.draw(self.screen, self.font, self.small)
            self.files.draw(self.screen, self.big, self.small)
            pygame.display.flip()
        self.persist()
        self.midi.close()
        pygame.quit()


if __name__ == "__main__":
    Tutor().run()