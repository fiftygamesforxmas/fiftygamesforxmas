#!/usr/bin/env python3
"""
Pygame effect host with audio input, input gain, live-through, and sampling.
"""

from __future__ import annotations

import importlib.util
import inspect
import math
import os
import sys
import threading
import traceback
import wave
import scipy as sci
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pygame

try:
    import numpy as np
except ImportError:
    print("pip install numpy pygame")
    raise

try:
    import sounddevice as sd
except ImportError:
    sd = None


@dataclass
class KnobColorScheme:
    outline: str = "black"
    face: str = "white"
    needle: str = "black"


DEFAULT_KNOB_COLORS = KnobColorScheme(outline="black", face="white", needle="black")


@dataclass
class Knob:
    name: str = "Generic"
    min: float = 0.0
    max: float = 1.0
    default: float = 0.5
    click_pts: List[float] = field(default_factory=lambda: [0.5])
    knob_color_scheme: KnobColorScheme = field(default_factory=lambda: DEFAULT_KNOB_COLORS)


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


def _looks_like_effect(cls: type) -> bool:
    if not inspect.isclass(cls):
        return False
    needed = ("get_name", "get_knobs", "get_switches", "apply_effect")
    return all(hasattr(cls, name) for name in needed)


def load_effects(plugin_dir: str):
    effects, failures = [], []
    os.makedirs(plugin_dir, exist_ok=True)
    for fname in sorted(os.listdir(plugin_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(plugin_dir, fname)
        mod_name = f"plugins.{os.path.splitext(fname)[0]}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            failures.append({"file": fname, "reason": "Could not create import spec", "detail": path})
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            failures.append({
                "file": fname,
                "reason": f"Import failed: {type(exc).__name__}: {exc}",
                "detail": traceback.format_exc(),
            })
            continue
        found = 0
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if not _looks_like_effect(obj):
                continue
            try:
                effects.append(obj())
                found += 1
            except Exception as exc:
                failures.append({
                    "file": fname,
                    "reason": f"Class {obj.__name__} could not be created: {type(exc).__name__}: {exc}",
                    "detail": traceback.format_exc(),
                })
        if found == 0 and not any(f["file"] == fname for f in failures):
            failures.append({
                "file": fname,
                "reason": "No effect class found (need get_name, get_knobs, get_switches, apply_effect)",
                "detail": path,
            })
    return effects, failures


def _to_attr(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name.strip().lower())


def read_plugin_styles(plugin) -> Dict[str, int]:
    getter = getattr(plugin, "getStyles", None) or getattr(plugin, "get_styles", None)
    if not callable(getter):
        return {}
    try:
        raw = getter() or {}
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    styles = {}
    for key, val in raw.items():
        try:
            styles[str(key)] = int(val)
        except (TypeError, ValueError):
            continue
    return styles


NAMED_COLORS = {
    "black": (20, 20, 20), "white": (245, 245, 245), "red": (200, 50, 50),
    "green": (40, 160, 70), "blue": (50, 90, 200), "gray": (140, 140, 140),
    "grey": (140, 140, 140), "orange": (220, 130, 30), "yellow": (220, 200, 40),
    "silver": (190, 190, 200),
}


def parse_color(value, default=(20, 20, 20)) -> Tuple[int, int, int]:
    if value is None:
        return default
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return default
    text = str(value).strip()
    if not text:
        return default
    if text.startswith("#"):
        hexpart = text[1:]
        if len(hexpart) == 3:
            try:
                return tuple(int(ch * 2, 16) for ch in hexpart)
            except ValueError:
                return default
        if len(hexpart) >= 6:
            try:
                return (int(hexpart[0:2], 16), int(hexpart[2:4], 16), int(hexpart[4:6], 16))
            except ValueError:
                return default
        return default
    return NAMED_COLORS.get(text.lower(), default)


DEFAULT_EFFECT_COLORS = {
    "face": "#1e1e1e", "edge": "#46464e", "text": "#e6e6e6", "muted": "#a0a0a8",
    "button": "#37373e", "button_hot": "#50505c", "button_on": "#326e50",
    "button_text": "#e6e6e6", "switch_on": "#329650", "switch_off": "#46464c",
    "slider": "#323238", "slider_handle": "#468cd4",
    "knob_outline": "#000000", "knob_face": "#ffffff", "knob_needle": "#000000",
    "style_bg": "#000000", "style_text": "#ffff00",
    "style_selected_bg": "#000000", "style_selected_text": "#ffff00",
}


def plugin_colors(effect) -> Dict[str, str]:
    colors = dict(DEFAULT_EFFECT_COLORS)
    extra = {}
    if hasattr(effect, "get_colors") and callable(effect.get_colors):
        try:
            got = effect.get_colors() or {}
            if isinstance(got, dict):
                extra.update(got)
        except Exception:
            pass
    for key in DEFAULT_EFFECT_COLORS:
        if hasattr(effect, key):
            extra[key] = getattr(effect, key)
    aliases = {
        "panel": "face", "panel_face": "face", "face_color": "face",
        "background": "face", "border": "edge", "outline": "edge",
        "button_color": "button", "knob_color": "knob_face",
        "list_bg": "style_bg", "list_text": "style_text",
        "list_selected_bg": "style_selected_bg", "list_selected_text": "style_selected_text",
    }
    for attr, dest in aliases.items():
        if hasattr(effect, attr) and attr not in extra:
            extra[dest] = getattr(effect, attr)
    for key, val in extra.items():
        if val is not None:
            colors[str(key)] = val
    return colors


def _knob_name(knob) -> str:
    return str(getattr(knob, "name", "Generic"))


def _knob_min(knob) -> float:
    return float(getattr(knob, "min", getattr(knob, "min_val", 0.0)))


def _knob_max(knob) -> float:
    return float(getattr(knob, "max", getattr(knob, "max_val", 1.0)))


def _knob_default(knob) -> float:
    return float(getattr(knob, "default", 0.5))


def _knob_clicks(knob):
    pts = getattr(knob, "click_pts", None)
    if pts is None:
        pts = getattr(knob, "clicksPts", None)
    return list(pts or [])


def _knob_scheme(knob):
    return getattr(knob, "knob_color_scheme", None) or getattr(knob, "knobColorScheme", None)


def _clamp_knob(knob, value: float) -> float:
    lo, hi = _knob_min(knob), _knob_max(knob)
    return max(lo, min(hi, float(value)))


def list_input_devices():
    if sd is None:
        return []
    items = []
    try:
        devices = sd.query_devices()
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else None
    except Exception:
        return []
    for i, dev in enumerate(devices):
        ch = int(dev.get("max_input_channels") or 0)
        if ch <= 0:
            continue
        items.append({
            "index": i,
            "name": str(dev.get("name") or f"Device {i}"),
            "channels": ch,
            "rate": int(dev.get("default_samplerate") or 44100),
            "default": i == default_in,
        })
    return items


def read_wav(path: str):
    with wave.open(path, "rb") as wf:
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        ints = a[:, 0].astype(np.int32) | (a[:, 1].astype(np.int32) << 8) | (a[:, 2].astype(np.int32) << 16)
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        data = ints.astype(np.float32) / 8388608.0
    elif sw == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width: {sw}")
    data = data.reshape(-1, nch) if nch > 1 else data.reshape(-1, 1)
    return data, sr


def write_wav(path: str, audio: np.ndarray, sample_rate: int):
    if not path.lower().endswith(".wav"):
        path = path + ".wav"
    arr = np.asarray(audio)
    nch = 1 if arr.ndim == 1 else arr.shape[1]
    pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(nch)
        wf.setsampwidth(2)
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm.tobytes())
    return path


def to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio.astype(np.float32)
    return audio[:, 0].astype(np.float32)


def to_mixer_sound(audio: np.ndarray, sample_rate: int) -> pygame.mixer.Sound:
    if audio.ndim == 1:
        stereo = np.column_stack([audio, audio])
    elif audio.shape[1] == 1:
        stereo = np.repeat(audio, 2, axis=1)
    else:
        stereo = audio[:, :2]
    pcm = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype(np.int16)
    return pygame.sndarray.make_sound(np.ascontiguousarray(pcm))


def mixer_is_playing() -> bool:
    return bool(pygame.mixer.get_init() and pygame.mixer.get_busy())


def major_frequency(mono: np.ndarray, sample_rate: int) -> Optional[float]:
    if mono is None or len(mono) < 64:
        return None
    n = min(len(mono), 8192)
    start = max(0, (len(mono) - n) // 2)
    spec = np.abs(np.fft.rfft(mono[start:start + n] * np.hanning(n)))
    spec[0] = 0.0
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
    lo = np.searchsorted(freqs, 40.0)
    hi = np.searchsorted(freqs, min(sample_rate * 0.45, 4000.0))
    if hi <= lo + 1:
        return None
    peak = int(np.argmax(spec[lo:hi])) + lo
    if spec[peak] < 1e-6:
        return None
    return float(freqs[peak])


def rising_zero_cross(mono: np.ndarray, start: int, period: int) -> int:
    n = len(mono)
    if n < 4 or period < 2:
        return max(0, min(start, n - 1))
    i0 = max(0, min(int(start), n - 2))
    span = min(period, n - 2 - i0)
    for i in range(i0, i0 + max(span, 1)):
        if float(mono[i]) <= 0.0 < float(mono[i + 1]):
            return i
    return i0


class Player:
    def __init__(self):
        self._inited_rate = None
        self.started_at_ms = None
        self.playing_len = 0
        self.sample_rate = 44100

    def ensure_mixer(self, sample_rate: int):
        if self._inited_rate == sample_rate and pygame.mixer.get_init():
            return
        pygame.mixer.quit()
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=1024)
        self._inited_rate = sample_rate

    def play(self, audio, sample_rate: int):
        if audio is None:
            return
        self.ensure_mixer(sample_rate)
        pygame.mixer.stop()
        to_mixer_sound(audio, sample_rate).play()
        self.started_at_ms = pygame.time.get_ticks()
        self.playing_len = int(audio.shape[0])
        self.sample_rate = sample_rate

    def stop(self):
        if pygame.mixer.get_init():
            pygame.mixer.stop()
        self.started_at_ms = None

    def shutdown(self):
        self.stop()
        pygame.mixer.quit()
        self._inited_rate = None

    def play_position(self):
        if not mixer_is_playing() or self.started_at_ms is None:
            return None
        idx = int((pygame.time.get_ticks() - self.started_at_ms) / 1000.0 * self.sample_rate)
        return None if idx >= self.playing_len else idx


class InputEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.stream = None
        self.device_index = None
        self.channels = 1
        self.sample_rate = 44100
        self.preview = np.zeros(1024, dtype=np.float32)
        self.recording = False
        self.live = False
        self.record_chunks = []
        self.effect = None
        self.status = ""
        self.gain = 8.0
        self.gain_min = 0.0
        self.gain_max = 24.0

    def set_gain(self, value: float):
        with self.lock:
            self.gain = max(self.gain_min, min(self.gain_max, float(value)))

    def _stop_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def start_monitor(self, device_index: int, channels: int, sample_rate: int, live: bool, effect=None):
        if sd is None:
            self.status = "Install sounddevice: pip install sounddevice"
            return False
        self._stop_stream()
        self.device_index = device_index
        self.channels = max(1, min(2, int(channels)))
        self.sample_rate = int(sample_rate)
        self.live = bool(live)
        self.effect = effect
        self.recording = False
        self.record_chunks = []

        def callback(indata, outdata, frames, time_info, status):
            block = np.asarray(indata, dtype=np.float32)
            if block.ndim == 1:
                block = block.reshape(-1, 1)
            with self.lock:
                g = float(self.gain)
            block = block * g
            with self.lock:
                mono = block[:, 0].copy()
                n = min(len(mono), len(self.preview))
                if n:
                    self.preview[:-n] = self.preview[n:]
                    self.preview[-n:] = mono[:n]
                if self.recording:
                    self.record_chunks.append(block.copy())
                processed = block
                if self.live and self.effect is not None:
                    try:
                        processed = self.effect.apply_effect(block.copy(), self.sample_rate)
                        processed = np.asarray(processed, dtype=np.float32)
                        if processed.ndim == 1:
                            processed = processed.reshape(-1, 1)
                    except Exception:
                        processed = block
            if outdata is not None:
                out = np.zeros_like(outdata)
                use = processed if self.live else block
                ch_out = out.shape[1]
                ch_in = use.shape[1]
                for c in range(ch_out):
                    out[:, c] = use[:, min(c, ch_in - 1)]
                outdata[:] = np.clip(out, -1.0, 1.0)

        try:
            self.stream = sd.Stream(
                device=(device_index, None),
                samplerate=self.sample_rate,
                channels=(self.channels, 2),
                dtype="float32",
                callback=callback,
                blocksize=256,
            )
            self.stream.start()
            self.status = f"Input {device_index} @ {self.sample_rate} Hz  gain x{self.gain:.1f}"
            return True
        except Exception as exc:
            try:
                self.stream = sd.InputStream(
                    device=device_index,
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    callback=lambda indata, frames, time_info, status: callback(
                        indata, None, frames, time_info, status
                    ),
                    blocksize=256,
                )
                self.stream.start()
                self.live = False
                self.status = f"Input only (no duplex): {exc}"
                return True
            except Exception as exc2:
                self.status = f"Could not open input: {exc2}"
                self.stream = None
                return False

    def start_recording(self):
        with self.lock:
            self.record_chunks = []
            self.recording = True

    def stop_recording(self):
        with self.lock:
            self.recording = False
            chunks = list(self.record_chunks)
            self.record_chunks = []
        if not chunks:
            return None, self.sample_rate
        return np.concatenate(chunks, axis=0).astype(np.float32), self.sample_rate

    def preview_copy(self):
        with self.lock:
            return self.preview.copy()

    def stop(self):
        self.recording = False
        self.live = False
        self._stop_stream()


BG = (18, 18, 20)
PANEL = (30, 30, 34)
PANEL_EDGE = (70, 70, 78)
TEXT = (230, 230, 230)
MUTED = (160, 160, 168)
BTN = (55, 55, 62)
BTN_HOT = (80, 80, 92)
BTN_ON = (50, 110, 80)
ACCENT = (70, 140, 220)
WARN = (220, 180, 70)
SCOPE_BG = (8, 16, 12)
SCOPE_GRID = (20, 50, 28)
SCOPE_TRACE = (40, 220, 90)
STYLE_BG_DEFAULT = (0, 0, 0)
STYLE_TEXT_DEFAULT = (255, 255, 0)
PX_PER_CM = 37.8
STYLE_LIST_THRESHOLD = 3
PLUGIN_TAB_LIMIT = 6
MIN_SCALE = 0.45


class Button:
    def __init__(self, rect, label: str, toggle: bool = False, colors=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.toggle = toggle
        self.on = False
        self.colors = colors or {}

    def draw(self, surf, font, hover: bool):
        c = self.colors
        if self.toggle and self.on:
            color = parse_color(c.get("button_on"), BTN_ON)
        elif hover:
            color = parse_color(c.get("button_hot"), BTN_HOT)
        else:
            color = parse_color(c.get("button"), BTN)
        pygame.draw.rect(surf, color, self.rect, border_radius=6)
        pygame.draw.rect(surf, parse_color(c.get("edge"), PANEL_EDGE), self.rect, 1, border_radius=6)
        text = font.render(self.label, True, parse_color(c.get("button_text", c.get("text")), TEXT))
        surf.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos) -> bool:
        return self.rect.collidepoint(pos)


class KnobWidget:
    def __init__(self, knob, x: int, y: int, theme=None, scale: float = 1.0):
        self.knob = knob
        self.theme = theme or DEFAULT_EFFECT_COLORS
        self.scale = max(MIN_SCALE, float(scale))
        self.size = max(36, int(88 * self.scale))
        self.value = _clamp_knob(knob, _knob_default(knob))
        self.x, self.y = x, y
        self.dragging_knob = False
        self.dragging_slider = False
        self.cx = x + self.size // 2
        self.cy = y + self.size // 2
        self.slider = pygame.Rect(x, y + self.size + int(36 * self.scale),
                                  self.size + int(24 * self.scale), max(8, int(14 * self.scale)))

    def width(self) -> int:
        return self.size + int(28 * self.scale)

    def height(self) -> int:
        return self.size + int(62 * self.scale)

    def set_value(self, value: float):
        lo, hi = _knob_min(self.knob), _knob_max(self.knob)
        value = _clamp_knob(self.knob, value)
        span = hi - lo
        for pt in _knob_clicks(self.knob):
            try:
                pt = float(pt)
            except (TypeError, ValueError):
                continue
            if abs(value - pt) < 0.03 * max(span, 1e-9):
                value = pt
                break
        self.value = value

    def _angle_for(self, value: float) -> float:
        lo, hi = _knob_min(self.knob), _knob_max(self.knob)
        t = (value - lo) / max(1e-9, hi - lo)
        return math.radians(225.0 - t * 270.0)

    def _knob_rgb(self):
        scheme = _knob_scheme(self.knob)
        outline = self.theme.get("knob_outline", "black")
        face = self.theme.get("knob_face", "white")
        needle = self.theme.get("knob_needle", "black")
        if scheme is not None:
            if isinstance(scheme, (list, tuple)) and len(scheme) >= 3:
                outline, face, needle = scheme[0], scheme[1], scheme[2]
            else:
                outline = getattr(scheme, "outline", outline)
                face = getattr(scheme, "face", face)
                needle = getattr(scheme, "needle", needle)
        return parse_color(outline), parse_color(face, (245, 245, 245)), parse_color(needle)

    def draw(self, surf, font, small):
        outline, face, needle = self._knob_rgb()
        r = self.size // 2 - max(3, int(6 * self.scale))
        pygame.draw.circle(surf, face, (self.cx, self.cy), r)
        pygame.draw.circle(surf, outline, (self.cx, self.cy), r, max(1, int(3 * self.scale)))
        for pt in _knob_clicks(self.knob):
            try:
                a = self._angle_for(float(pt))
            except (TypeError, ValueError):
                continue
            inner, outer = r - max(4, int(10 * self.scale)), r - 2
            pygame.draw.line(surf, outline,
                             (self.cx + inner * math.cos(a), self.cy - inner * math.sin(a)),
                             (self.cx + outer * math.cos(a), self.cy - outer * math.sin(a)), 2)
        a = self._angle_for(self.value)
        pygame.draw.line(surf, needle, (self.cx, self.cy),
                         (self.cx + (r - 6) * math.cos(a), self.cy - (r - 6) * math.sin(a)),
                         max(2, int(3 * self.scale)))
        pygame.draw.circle(surf, needle, (self.cx, self.cy), max(2, int(4 * self.scale)))
        text_c = parse_color(self.theme.get("text"), TEXT)
        muted_c = parse_color(self.theme.get("muted"), MUTED)
        label = small.render(_knob_name(self.knob), True, text_c)
        surf.blit(label, label.get_rect(center=(self.cx, self.y + self.size + int(8 * self.scale))))
        val = small.render(f"{self.value:.3f}", True, muted_c)
        surf.blit(val, val.get_rect(center=(self.cx, self.y + self.size + int(22 * self.scale))))
        pygame.draw.rect(surf, parse_color(self.theme.get("slider"), (50, 50, 56)), self.slider, border_radius=4)
        lo, hi = _knob_min(self.knob), _knob_max(self.knob)
        t = (self.value - lo) / max(1e-9, hi - lo)
        pygame.draw.circle(surf, parse_color(self.theme.get("slider_handle"), ACCENT),
                           (int(self.slider.x + t * self.slider.w), self.slider.centery),
                           max(4, int(8 * self.scale)))

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            dx, dy = event.pos[0] - self.cx, event.pos[1] - self.cy
            if dx * dx + dy * dy <= (self.size // 2) ** 2:
                self.dragging_knob = True
                self._from_knob_pos(event.pos)
                return True
            if self.slider.inflate(6, 10).collidepoint(event.pos):
                self.dragging_slider = True
                self._from_slider_pos(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_knob = self.dragging_slider = False
        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_knob:
                self._from_knob_pos(event.pos)
                return True
            if self.dragging_slider:
                self._from_slider_pos(event.pos[0])
                return True
        return False

    def _from_knob_pos(self, pos):
        dx, dy = pos[0] - self.cx, self.cy - pos[1]
        sweep = (225.0 - math.degrees(math.atan2(dy, dx))) % 360.0
        if sweep > 270:
            sweep = 0.0 if sweep > 315 else 270.0
        lo, hi = _knob_min(self.knob), _knob_max(self.knob)
        self.set_value(lo + (sweep / 270.0) * (hi - lo))

    def _from_slider_pos(self, x: int):
        t = max(0.0, min(1.0, (x - self.slider.x) / max(1, self.slider.w)))
        lo, hi = _knob_min(self.knob), _knob_max(self.knob)
        self.set_value(lo + t * (hi - lo))


class SwitchWidget:
    def __init__(self, switch, x: int, y: int, theme=None, scale: float = 1.0):
        self.switch = switch
        self.theme = theme or DEFAULT_EFFECT_COLORS
        self.value = bool(getattr(switch, "default", True))
        w, h = max(28, int(44 * scale)), max(14, int(22 * scale))
        self.rect = pygame.Rect(x, y, w, h)
        self.label_x = x + w + 8

    def draw(self, surf, font):
        on_c = parse_color(self.theme.get("switch_on"), (50, 150, 80))
        off_c = parse_color(self.theme.get("switch_off"), (70, 70, 76))
        text_c = parse_color(self.theme.get("text"), TEXT)
        pygame.draw.rect(surf, on_c if self.value else off_c, self.rect, border_radius=self.rect.h // 2)
        knob_x = self.rect.right - self.rect.h // 2 if self.value else self.rect.x + self.rect.h // 2
        pygame.draw.circle(surf, text_c, (knob_x, self.rect.centery), max(3, self.rect.h // 3))
        surf.blit(font.render(str(getattr(self.switch, "name", "Enable")), True, text_c),
                  (self.label_x, self.rect.y))

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if pygame.Rect(self.rect.x, self.rect.y, 160, self.rect.h).collidepoint(event.pos):
                self.value = not self.value
                return True
        return False


class StylePicker:
    def __init__(self, styles: Dict[str, int], x: int, y: int, theme: dict, current_ordinal=None, scale=1.0):
        self.styles = styles
        self.names = list(styles.keys())
        self.theme = theme
        self.scale = scale
        self.row_h = max(16, int(22 * scale))
        self.width = max(110, int(160 * scale))
        self.dropdown = len(self.names) >= STYLE_LIST_THRESHOLD
        self.open = False
        self.x, self.y = x, y
        self.selected_name = self._name_for_ordinal(current_ordinal)
        self.header = pygame.Rect(x, y, self.width, self.row_h)
        self.row_rects = []
        self._layout_rows()

    def height(self) -> int:
        if not self.names:
            return 0
        if self.dropdown and not self.open:
            return self.row_h + int(18 * self.scale)
        return int(18 * self.scale) + self.row_h * len(self.names)

    def _name_for_ordinal(self, ordinal) -> str:
        if not self.names:
            return ""
        if ordinal is not None:
            for name, value in self.styles.items():
                try:
                    if int(value) == int(ordinal):
                        return name
                except (TypeError, ValueError):
                    continue
        return self.names[0]

    def selected_ordinal(self):
        return int(self.styles[self.selected_name]) if self.selected_name else None

    def _colors(self):
        has = any(k in self.theme and self.theme[k] != DEFAULT_EFFECT_COLORS.get(k)
                  for k in ("style_bg", "style_text", "style_selected_bg", "style_selected_text"))
        if not has:
            return STYLE_BG_DEFAULT, STYLE_TEXT_DEFAULT, STYLE_BG_DEFAULT, STYLE_TEXT_DEFAULT
        return (
            parse_color(self.theme.get("style_bg"), STYLE_BG_DEFAULT),
            parse_color(self.theme.get("style_text"), STYLE_TEXT_DEFAULT),
            parse_color(self.theme.get("style_selected_bg"), STYLE_BG_DEFAULT),
            parse_color(self.theme.get("style_selected_text"), STYLE_TEXT_DEFAULT),
        )

    def _layout_rows(self):
        self.row_rects = []
        if self.dropdown and not self.open:
            return
        top = self.y + (self.row_h if self.dropdown else int(18 * self.scale))
        for i, name in enumerate(self.names):
            self.row_rects.append((pygame.Rect(self.x, top + i * self.row_h, self.width, self.row_h), name))

    def draw(self, surf, small):
        if not self.names:
            return
        bg, fg, sbg, sfg = self._colors()
        surf.blit(small.render("Style", True, parse_color(self.theme.get("text"), TEXT)),
                  (self.x, self.y - int(14 * self.scale)))
        if self.dropdown:
            pygame.draw.rect(surf, bg, self.header)
            pygame.draw.rect(surf, fg, self.header, 1)
            surf.blit(small.render(self.selected_name + "  v", True, fg), (self.header.x + 6, self.header.y + 3))
            if not self.open:
                return
        for rect, name in self.row_rects:
            sel = name == self.selected_name
            pygame.draw.rect(surf, sbg if sel else bg, rect)
            pygame.draw.rect(surf, fg, rect, 1)
            surf.blit(small.render(name, True, sfg if sel else fg), (rect.x + 6, rect.y + 3))

    def handle_event(self, event) -> bool:
        if not self.names or event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        if self.dropdown:
            if self.header.collidepoint(event.pos):
                self.open = not self.open
                self._layout_rows()
                return True
            if self.open:
                for rect, name in self.row_rects:
                    if rect.collidepoint(event.pos):
                        self.selected_name = name
                        self.open = False
                        self._layout_rows()
                        return True
                self.open = False
                self._layout_rows()
                return True
            return False
        for rect, name in self.row_rects:
            if rect.collidepoint(event.pos):
                self.selected_name = name
                return True
        return False


class PluginDropdown:
    def __init__(self, names: List[str], active: int, x: int, y: int, w: int, scale=1.0):
        self.names = names
        self.active = max(0, active) if names else -1
        self.highlight = self.active
        self.open = False
        self.row_h = max(18, int(24 * scale))
        self.header = pygame.Rect(x, y, w, self.row_h)
        self.max_visible = 12
        self.scroll = 0

    def height_closed(self) -> int:
        return self.row_h

    def menu_rect(self):
        n = min(len(self.names), self.max_visible)
        return pygame.Rect(self.header.x, self.header.bottom, self.header.w, n * self.row_h)

    def _rows(self):
        rows = []
        if not self.open:
            return rows
        for i, name in enumerate(self.names[self.scroll:self.scroll + self.max_visible]):
            idx = self.scroll + i
            rows.append((pygame.Rect(self.header.x, self.header.bottom + i * self.row_h,
                                     self.header.w, self.row_h), idx, name))
        return rows

    def move_highlight(self, delta: int):
        if not self.names:
            return
        self.highlight = (self.highlight + delta) % len(self.names)
        if self.highlight < self.scroll:
            self.scroll = self.highlight
        if self.highlight >= self.scroll + self.max_visible:
            self.scroll = self.highlight - self.max_visible + 1

    def draw(self, surf, font):
        if not self.names:
            return
        label = self.names[self.active] if 0 <= self.active < len(self.names) else "Effects"
        pygame.draw.rect(surf, BTN, self.header, border_radius=6)
        pygame.draw.rect(surf, PANEL_EDGE, self.header, 1, border_radius=6)
        surf.blit(font.render(f"{label}  v", True, TEXT), (self.header.x + 8, self.header.y + 4))
        if not self.open:
            return
        menu = self.menu_rect()
        pygame.draw.rect(surf, (10, 10, 12), menu)
        pygame.draw.rect(surf, ACCENT, menu, 2)
        for rect, idx, name in self._rows():
            if idx == self.highlight:
                pygame.draw.rect(surf, BTN_ON, rect)
            elif idx == self.active:
                pygame.draw.rect(surf, (40, 70, 110), rect)
            else:
                pygame.draw.rect(surf, BTN, rect)
            pygame.draw.rect(surf, PANEL_EDGE, rect, 1)
            surf.blit(font.render(name, True, TEXT), (rect.x + 8, rect.y + 4))

    def handle_event(self, event):
        if not self.names:
            return None
        if event.type == pygame.MOUSEWHEEL and self.open:
            self.scroll = max(0, min(max(0, len(self.names) - self.max_visible), self.scroll - event.y))
            return "scroll"
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        if self.header.collidepoint(event.pos):
            self.open = not self.open
            self.highlight = self.active
            return "toggle"
        if self.open:
            for rect, idx, _name in self._rows():
                if rect.collidepoint(event.pos):
                    self.open = False
                    self.active = self.highlight = idx
                    return idx
            if not self.menu_rect().collidepoint(event.pos):
                self.open = False
                return "close"
        return None


class EffectPanel:
    def __init__(self, effect, x: int, y: int, width: int, scale: float = 1.0):
        self.effect = effect
        self.theme = plugin_colors(effect)
        self.scale = scale
        self.x, self.y, self.width = x, y, width
        self.knobs, self.switches = [], []
        self.style_picker = None
        kx, ky = x + 12, y + int(32 * scale)
        for knob in effect.get_knobs() or []:
            w = KnobWidget(knob, kx, ky, self.theme, scale)
            self.knobs.append(w)
            kx += w.width() + int(6 * scale)
        styles = read_plugin_styles(effect)
        if styles:
            self.style_picker = StylePicker(
                styles, min(kx + 4, x + width - int(170 * scale)), ky + int(12 * scale),
                self.theme, getattr(effect, "style", None), scale,
            )
        sy = ky + (self.knobs[0].height() if self.knobs else int(20 * scale))
        if self.style_picker:
            sy = max(sy, ky + self.style_picker.height() + 8)
        sx = x + 12
        for sw in effect.get_switches() or []:
            self.switches.append(SwitchWidget(sw, sx, sy, self.theme, scale))
            sx += int(170 * scale)
        self.height = (sy + int(36 * scale)) - y

    def draw(self, surf, font, small):
        rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surf, parse_color(self.theme.get("face"), PANEL), rect, border_radius=10)
        pygame.draw.rect(surf, parse_color(self.theme.get("edge"), PANEL_EDGE), rect, 1, border_radius=10)
        surf.blit(font.render(str(self.effect.get_name()), True, parse_color(self.theme.get("text"), TEXT)),
                  (self.x + 12, self.y + 6))
        for k in self.knobs:
            k.draw(surf, font, small)
        if self.style_picker:
            self.style_picker.draw(surf, small)
        for s in self.switches:
            s.draw(surf, small)

    def handle_event(self, event) -> bool:
        used = False
        if self.style_picker:
            used = self.style_picker.handle_event(event) or used
        for k in self.knobs:
            used = k.handle_event(event) or used
        for s in self.switches:
            used = s.handle_event(event) or used
        return used

    def push_settings_into_effect(self):
        fx = self.effect
        for kw in self.knobs:
            name = _knob_name(kw.knob)
            setattr(fx, _to_attr(name), kw.value)
            setattr(fx, name, kw.value)
        for sw in self.switches:
            name = str(getattr(sw.switch, "name", "Enable"))
            setattr(fx, _to_attr(name), sw.value)
            setattr(fx, name, sw.value)
        if self.style_picker and self.style_picker.selected_ordinal() is not None:
            fx.style = self.style_picker.selected_ordinal()
        return fx


def draw_mini_scope(surf, rect, samples, color=SCOPE_TRACE):
    pygame.draw.rect(surf, SCOPE_BG, rect)
    pygame.draw.rect(surf, SCOPE_GRID, rect, 1)
    pygame.draw.line(surf, SCOPE_GRID, (rect.x, rect.centery), (rect.right, rect.centery), 1)
    if samples is None or len(samples) < 2:
        return
    last_i = max(1, len(samples) - 1)
    pts = []
    for i, sample in enumerate(samples):
        x = rect.x + int(i * (rect.w - 1) / last_i)
        y = max(rect.y, min(rect.bottom - 1, int(rect.centery - float(sample) * PX_PER_CM)))
        pts.append((x, y))
    if len(pts) >= 2:
        pygame.draw.aalines(surf, color, False, pts)


class Oscilloscope:
    def __init__(self):
        self.frozen = False
        self.sync = False
        self.freq = None
        self.period = 0
        self.last_analyze = 0
        self.freeze_btn = Button((0, 0, 90, 26), "Freeze", toggle=True)
        self.sync_btn = Button((0, 0, 110, 26), "Synchronize", toggle=True)
        self.rect = pygame.Rect(12, 0, 100, 160)
        self.frozen_chunk = None
        self.height = 160

    def layout(self, screen_w: int, y: int, height: int):
        self.height = max(90, height)
        self.rect = pygame.Rect(8, y, max(200, screen_w - 16), self.height)
        bh = max(20, min(26, self.height // 8))
        self.freeze_btn.rect = pygame.Rect(self.rect.right - 210, self.rect.y + 6, 90, bh)
        self.sync_btn.rect = pygame.Rect(self.rect.right - 112, self.rect.y + 6, 104, bh)

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.freeze_btn.hit(event.pos):
                self.frozen = not self.frozen
                self.freeze_btn.on = self.frozen
                if not self.frozen:
                    self.frozen_chunk = None
                return True
            if self.sync_btn.hit(event.pos):
                self.sync = not self.sync
                self.sync_btn.on = self.sync
                self.last_analyze = 0
                return True
        return False

    def _window_len(self, n, sample_rate):
        if self.sync and self.period >= 2:
            return max(self.period * 2, min(2048, n))
        return min(max(256, sample_rate // 40), n)

    def current_chunk(self, audio, sample_rate, play_pos):
        if audio is None or play_pos is None:
            return None
        mono = to_mono(audio)
        n = len(mono)
        if n < 2:
            return None
        window = self._window_len(n, sample_rate)
        start = max(0, min(play_pos, n - 1))
        if self.sync and self.period >= 2:
            start = rising_zero_cross(mono, start, self.period)
        return mono[start:start + window].copy() if start + window <= n else mono[start:].copy()

    def update(self, audio, sample_rate, play_pos):
        if play_pos is None and not self.frozen:
            self.freq = None
            self.frozen_chunk = None
            return
        if play_pos is None or (self.frozen and self.frozen_chunk is not None):
            return
        now = pygame.time.get_ticks()
        if self.sync and now - self.last_analyze > 250:
            self.freq = major_frequency(to_mono(audio), sample_rate)
            self.last_analyze = now
            self.period = max(2, int(round(sample_rate / self.freq))) if self.freq and self.freq > 1 else 0
        if self.frozen:
            self.frozen_chunk = self.current_chunk(audio, sample_rate, play_pos)

    def draw(self, surf, font, small, audio, sample_rate, play_pos, hover):
        pygame.draw.rect(surf, PANEL, self.rect, border_radius=10)
        pygame.draw.rect(surf, PANEL_EDGE, self.rect, 1, border_radius=10)
        surf.blit(font.render("Oscilloscope  1 V/cm", True, TEXT), (self.rect.x + 12, self.rect.y + 6))
        info = "idle" if play_pos is None else "live"
        if self.freq:
            info += f"  {self.freq:.1f} Hz"
        surf.blit(small.render(info, True, MUTED), (self.rect.x + 200, self.rect.y + 10))
        self.freeze_btn.draw(surf, small, self.freeze_btn.hit(hover))
        self.sync_btn.draw(surf, small, self.sync_btn.hit(hover))
        plot = pygame.Rect(self.rect.x + 10, self.rect.y + 34, self.rect.w - 20, self.rect.h - 44)
        chunk = self.frozen_chunk if self.frozen and self.frozen_chunk is not None else None
        if chunk is None and play_pos is not None and audio is not None:
            chunk = self.current_chunk(audio, sample_rate, play_pos)
        draw_mini_scope(surf, plot, chunk)


class FileDialog:
    def __init__(self, start_dir: str):
        self.dir = os.path.abspath(start_dir)
        self.entries, self.row_rects = [], []
        self.scroll = 0
        self.visible = False
        self.mode = "open"
        self.filename = "processed.wav"
        self.cancel_rect = pygame.Rect(0, 0, 0, 0)
        self.save_rect = pygame.Rect(0, 0, 0, 0)
        self.refresh()

    def refresh(self):
        try:
            names = os.listdir(self.dir)
        except OSError:
            names = []
        dirs = sorted(n for n in names if os.path.isdir(os.path.join(self.dir, n)) and not n.startswith("."))
        wavs = sorted(n for n in names if n.lower().endswith(".wav"))
        self.entries = [".."] + dirs + wavs
        self.scroll = 0

    def open_load(self, start_dir=None):
        if start_dir:
            self.dir = os.path.abspath(start_dir)
        self.mode = "open"
        self.refresh()
        self.visible = True
        pygame.key.start_text_input()

    def open_save(self, start_dir=None, suggested="processed.wav"):
        if start_dir:
            self.dir = os.path.abspath(start_dir)
        self.mode = "save"
        self.filename = suggested
        self.refresh()
        self.visible = True
        pygame.key.start_text_input()

    def close(self):
        self.visible = False
        pygame.key.stop_text_input()

    def current_save_path(self) -> str:
        return os.path.join(self.dir, self.filename.strip() or "processed.wav")

    def draw(self, surf, font, small, screen_rect):
        if not self.visible:
            return
        box = pygame.Rect(40, 40, max(240, screen_rect.w - 80), max(180, screen_rect.h - 80))
        pygame.draw.rect(surf, PANEL, box, border_radius=10)
        pygame.draw.rect(surf, ACCENT, box, 2, border_radius=10)
        surf.blit(font.render("Save WAV" if self.mode == "save" else "Open WAV", True, TEXT), (box.x + 16, box.y + 12))
        surf.blit(small.render(self.dir, True, MUTED), (box.x + 16, box.y + 40))
        bottom_extra = 78 if self.mode == "save" else 52
        self.cancel_rect = pygame.Rect(box.right - 110, box.bottom - 40, 90, 28)
        pygame.draw.rect(surf, BTN, self.cancel_rect, border_radius=6)
        surf.blit(small.render("Cancel", True, TEXT), self.cancel_rect.move(18, 6))
        if self.mode == "save":
            self.save_rect = pygame.Rect(box.right - 214, box.bottom - 40, 90, 28)
            pygame.draw.rect(surf, BTN_ON, self.save_rect, border_radius=6)
            surf.blit(small.render("Save", True, TEXT), self.save_rect.move(28, 6))
            name_rect = pygame.Rect(box.x + 16, box.bottom - 78, box.w - 32, 26)
            pygame.draw.rect(surf, (12, 12, 14), name_rect)
            pygame.draw.rect(surf, ACCENT, name_rect, 1)
            surf.blit(small.render(self.filename + "|", True, TEXT), (name_rect.x + 6, name_rect.y + 5))
        list_top, row_h = box.y + 68, 22
        max_rows = max(1, (box.bottom - bottom_extra - list_top) // row_h)
        self.row_rects = []
        for i, name in enumerate(self.entries[self.scroll:self.scroll + max_rows]):
            r = pygame.Rect(box.x + 16, list_top + i * row_h, box.w - 32, row_h)
            self.row_rects.append((r, name))
            full = os.path.join(self.dir, name)
            is_dir = name == ".." or os.path.isdir(full)
            surf.blit(small.render(f"[dir] {name}" if is_dir else name, True, ACCENT if is_dir else TEXT),
                      (r.x + 4, r.y + 3))

    def handle_event(self, event):
        if not self.visible:
            return None
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y)
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
                return None
            if self.mode == "save":
                if event.key == pygame.K_RETURN:
                    return ("save", self.current_save_path())
                if event.key == pygame.K_BACKSPACE:
                    self.filename = self.filename[:-1]
            return None
        if event.type == pygame.TEXTINPUT and self.mode == "save":
            if event.text and event.text not in "/\\":
                self.filename += event.text
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.cancel_rect.collidepoint(event.pos):
                self.close()
                return None
            if self.mode == "save" and self.save_rect.collidepoint(event.pos):
                return ("save", self.current_save_path())
            for rect, name in self.row_rects:
                if rect.collidepoint(event.pos):
                    if name == "..":
                        self.dir = os.path.dirname(self.dir)
                        self.refresh()
                        return None
                    full = os.path.join(self.dir, name)
                    if os.path.isdir(full):
                        self.dir = full
                        self.refresh()
                        return None
                    if name.lower().endswith(".wav"):
                        if self.mode == "open":
                            self.close()
                            return ("open", full)
                        self.filename = name
        return None


def _wrap_text(text: str, font, max_width: int) -> List[str]:
    words = str(text).replace("\t", " ").split(" ")
    lines, cur = [], ""
    for word in words:
        trial = word if not cur else cur + " " + word
        if font.size(trial)[0] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


class PluginErrorDialog:
    def __init__(self, failures: List[dict]):
        self.failures = failures
        self.visible = bool(failures)
        self.scroll = 0
        self.ok_rect = pygame.Rect(0, 0, 0, 0)
        self.selected = 0

    def draw(self, surf, font, small, screen_rect):
        if not self.visible:
            return
        box = pygame.Rect(36, 36, max(280, screen_rect.w - 72), max(200, screen_rect.h - 72))
        pygame.draw.rect(surf, (28, 22, 18), box, border_radius=10)
        pygame.draw.rect(surf, WARN, box, 2, border_radius=10)
        surf.blit(font.render(f"Plugin load failures ({len(self.failures)})", True, WARN), (box.x + 16, box.y + 12))
        self.ok_rect = pygame.Rect(box.centerx - 45, box.bottom - 42, 90, 28)
        pygame.draw.rect(surf, BTN, self.ok_rect, border_radius=6)
        surf.blit(small.render("OK", True, TEXT), self.ok_rect.move(34, 6))
        area = pygame.Rect(box.x + 16, box.y + 66, box.w - 32, box.h - 120)
        pygame.draw.rect(surf, (12, 12, 14), area)
        y = area.y + 6 - self.scroll
        for i, item in enumerate(self.failures):
            for raw in (f"{i + 1}. {item.get('file', '?')}", item.get("reason", "")):
                for line in _wrap_text(raw, small, area.w - 16):
                    if area.y <= y <= area.bottom - 16:
                        surf.blit(small.render(line, True, WARN if i == self.selected else TEXT), (area.x + 8, y))
                    y += 16
            y += 10

    def handle_event(self, event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 24)
            return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self.visible = False
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.ok_rect.collidepoint(event.pos):
            self.visible = False
            return True
        return True


class AudioInputDialog:
    def __init__(self, engine: InputEngine):
        self.engine = engine
        self.visible = False
        self.devices = []
        self.selected = 0
        self.scroll = 0
        self.row_rects = []
        self.close_rect = pygame.Rect(0, 0, 0, 0)
        self.sample_rect = pygame.Rect(0, 0, 0, 0)
        self.live_rect = pygame.Rect(0, 0, 0, 0)
        self.monitor_rect = pygame.Rect(0, 0, 0, 0)
        self.gain_slider = pygame.Rect(0, 0, 0, 0)
        self.dragging_gain = False
        self.message = ""

    def open(self):
        self.visible = True
        self.devices = list_input_devices()
        self.selected = 0
        for i, d in enumerate(self.devices):
            if d.get("default"):
                self.selected = i
                break
        if sd is None:
            self.message = "pip install sounddevice   then restart"
        elif not self.devices:
            self.message = "No input devices found."
        else:
            self.message = "Select an input. Use Input volume if a guitar interface is quiet."

    def current_device(self):
        if 0 <= self.selected < len(self.devices):
            return self.devices[self.selected]
        return None

    def _set_gain_from_x(self, x: int):
        t = (x - self.gain_slider.x) / max(1, self.gain_slider.w)
        t = max(0.0, min(1.0, t))
        self.engine.set_gain(self.engine.gain_min + t * (self.engine.gain_max - self.engine.gain_min))

    def draw(self, surf, font, small, screen_rect, preview):
        if not self.visible:
            return
        box = pygame.Rect(30, 30, max(300, screen_rect.w - 60), max(280, screen_rect.h - 60))
        pygame.draw.rect(surf, PANEL, box, border_radius=10)
        pygame.draw.rect(surf, ACCENT, box, 2, border_radius=10)
        surf.blit(font.render("Audio Input", True, TEXT), (box.x + 16, box.y + 12))
        surf.blit(small.render(self.message, True, MUTED), (box.x + 16, box.y + 40))
        surf.blit(small.render(self.engine.status or "", True, WARN), (box.x + 16, box.y + 58))

        list_area = pygame.Rect(box.x + 16, box.y + 80, min(420, box.w // 2), box.h - 190)
        pygame.draw.rect(surf, (12, 12, 14), list_area)
        row_h, max_rows = 22, max(1, list_area.h // 22)
        self.row_rects = []
        for i, dev in enumerate(self.devices[self.scroll:self.scroll + max_rows]):
            idx = self.scroll + i
            r = pygame.Rect(list_area.x, list_area.y + i * row_h, list_area.w, row_h)
            self.row_rects.append((r, idx))
            pygame.draw.rect(surf, BTN_ON if idx == self.selected else BTN, r)
            mark = "* " if dev.get("default") else ""
            label = f"{mark}{dev['name']}  ({dev['channels']} ch, {dev['rate']} Hz)"
            surf.blit(small.render(label[:70], True, TEXT), (r.x + 6, r.y + 3))

        scope = pygame.Rect(list_area.right + 16, list_area.y, box.right - list_area.right - 32, 120)
        surf.blit(small.render("Input scope  1 V/cm", True, TEXT), (scope.x, scope.y - 16))
        draw_mini_scope(surf, scope, preview)

        surf.blit(small.render(f"Input volume  x{self.engine.gain:.1f}", True, TEXT),
                  (scope.x, scope.bottom + 10))
        self.gain_slider = pygame.Rect(scope.x, scope.bottom + 30, max(80, scope.w), 16)
        pygame.draw.rect(surf, (50, 50, 56), self.gain_slider, border_radius=4)
        t = (self.engine.gain - self.engine.gain_min) / max(1e-9, self.engine.gain_max - self.engine.gain_min)
        pygame.draw.circle(surf, ACCENT,
                           (int(self.gain_slider.x + t * self.gain_slider.w), self.gain_slider.centery), 8)

        by = box.bottom - 44
        self.monitor_rect = pygame.Rect(box.x + 16, by, 90, 28)
        self.sample_rect = pygame.Rect(box.x + 114, by, 110, 28)
        self.live_rect = pygame.Rect(box.x + 232, by, 130, 28)
        self.close_rect = pygame.Rect(box.right - 100, by, 84, 28)
        for rect, label, on in (
            (self.monitor_rect, "Listen", self.engine.stream is not None and not self.engine.live),
            (self.sample_rect, "Stop Sample" if self.engine.recording else "Sample", self.engine.recording),
            (self.live_rect, "Stop Live" if self.engine.live else "Live Through", self.engine.live),
            (self.close_rect, "Close", False),
        ):
            pygame.draw.rect(surf, BTN_ON if on else BTN, rect, border_radius=6)
            pygame.draw.rect(surf, PANEL_EDGE, rect, 1, border_radius=6)
            tsurf = small.render(label, True, TEXT)
            surf.blit(tsurf, tsurf.get_rect(center=rect.center))

    def handle_event(self, event):
        if not self.visible:
            return None
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_gain = False
        if event.type == pygame.MOUSEMOTION and self.dragging_gain:
            self._set_gain_from_x(event.pos[0])
            return "gain"
        if event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y)
            return "scroll"
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "close"
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        if self.gain_slider.inflate(6, 12).collidepoint(event.pos):
            self.dragging_gain = True
            self._set_gain_from_x(event.pos[0])
            return "gain"
        for rect, idx in self.row_rects:
            if rect.collidepoint(event.pos):
                self.selected = idx
                return "select"
        if self.close_rect.collidepoint(event.pos):
            return "close"
        if self.monitor_rect.collidepoint(event.pos):
            return "monitor"
        if self.sample_rect.collidepoint(event.pos):
            return "sample"
        if self.live_rect.collidepoint(event.pos):
            return "live"
        return None


class HostApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Effect Host")
        self.screen = pygame.display.set_mode((980, 760), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        plugin_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
        self.effects, self.load_failures = load_effects(plugin_dir)
        self.error_dialog = PluginErrorDialog(self.load_failures)
        self.sorted_indices = sorted(range(len(self.effects)), key=lambda i: self.effects[i].get_name().lower())
        self.sorted_names = [self.effects[i].get_name() for i in self.sorted_indices]
        self.active_index = 0
        self.panels = []
        self.effect_tabs = []
        self.plugin_dropdown = None
        self.use_plugin_dropdown = len(self.effects) > PLUGIN_TAB_LIMIT
        self.scope = Oscilloscope()
        self.scale = 1.0
        self.original = None
        self.rendered = None
        self.sample_rate = 44100
        self.player = Player()
        self.input_engine = InputEngine()
        self.input_dialog = AudioInputDialog(self.input_engine)
        self.status = "No file loaded."
        if self.effects:
            self.status += " Plugins: " + ", ".join(e.get_name() for e in self.effects)
        if self.load_failures:
            self.status += f"  ({len(self.load_failures)} plugin file(s) failed)"
        self.dialog = FileDialog(os.path.dirname(os.path.abspath(__file__)))
        self.buttons = []
        self._relayout()

    def _fonts(self):
        s = self.scale
        self.font = pygame.font.SysFont("Arial", max(11, int(16 * s)))
        self.small = pygame.font.SysFont("Arial", max(10, int(12 * s)))
        self.big = pygame.font.SysFont("Arial", max(12, int(18 * s)), bold=True)

    def _compute_scale(self):
        w, h = self.screen.get_width(), self.screen.get_height()
        nknobs = 4
        if self.effects:
            try:
                nknobs = max(nknobs, max(len(e.get_knobs() or []) for e in self.effects))
            except Exception:
                pass
        need_w = 16 + nknobs * 116 + 180
        self.scale = max(MIN_SCALE, min(1.0, max(280, w - 24) / max(need_w, 1), max(120, h - 210) / 200.0))

    def active_panel(self):
        if not self.panels:
            return None
        self.active_index = max(0, min(self.active_index, len(self.panels) - 1))
        return self.panels[self.active_index]

    def select_effect(self, index: int):
        if not self.effects:
            return
        self.active_index = index % len(self.effects)
        for i, tab in enumerate(self.effect_tabs):
            tab.on = i == self.active_index
        if self.plugin_dropdown:
            try:
                pos = self.sorted_indices.index(self.active_index)
            except ValueError:
                pos = 0
            self.plugin_dropdown.active = self.plugin_dropdown.highlight = pos
        self.status = f"Active effect: {self.effects[self.active_index].get_name()}"
        if self.input_engine.live:
            self._start_live()

    def _relayout(self):
        saved = {}
        open_drop = self.plugin_dropdown.open if self.plugin_dropdown else False
        highlight = self.plugin_dropdown.highlight if self.plugin_dropdown else 0
        for p in self.panels:
            saved[id(p.effect)] = {
                "knobs": [k.value for k in p.knobs],
                "switches": [s.value for s in p.switches],
                "style": p.style_picker.selected_name if p.style_picker else None,
            }
        self._compute_scale()
        self._fonts()
        s = self.scale
        w = self.screen.get_width()
        labels = ["Open WAV", "Save WAV", "Audio Input", "Render", "Play Processed", "Repeat", "Original", "Stop"]
        if self.load_failures:
            labels.append("Plugin Errors")
        self.buttons = []
        x, y, bh = 8, 8, max(22, int(32 * s))
        for lab in labels:
            bw = max(70, int((150 if lab == "Play Processed" else 112) * s))
            if x + bw > w - 8:
                y += bh + 4
                x = 8
            self.buttons.append(Button((x, y, bw, bh), lab))
            x += bw + 6
        row2 = y + bh + 6
        pw, ph = max(50, int(64 * s)), max(20, int(24 * s))
        self.prev_btn = Button((8, row2, pw, ph), "< Prev")
        self.next_btn = Button((8 + pw + 6, row2, pw, ph), "Next >")
        self.effect_tabs = []
        self.plugin_dropdown = None
        tab_bottom = row2 + ph + 8
        if self.use_plugin_dropdown:
            px = 8 + 2 * (pw + 6) + 8
            try:
                cur = self.sorted_indices.index(self.active_index)
            except ValueError:
                cur = 0
            self.plugin_dropdown = PluginDropdown(self.sorted_names, cur, px, row2, min(320, w - px - 8), s)
            self.plugin_dropdown.open = open_drop
            self.plugin_dropdown.highlight = highlight
            tab_bottom = row2 + self.plugin_dropdown.height_closed() + 8
        else:
            tx = 8 + 2 * (pw + 6) + 8
            ty = row2
            for i, fx in enumerate(self.effects):
                name = str(fx.get_name())
                tw = max(70, min(160, int((10 + 7 * len(name)) * s)))
                if tx + tw > w - 8:
                    ty += ph + 4
                    tx = 8 + 2 * (pw + 6) + 8
                tab = Button((tx, ty, tw, ph), name, toggle=True, colors=plugin_colors(fx))
                tab.on = i == self.active_index
                self.effect_tabs.append(tab)
                tx += tw + 4
            tab_bottom = ty + ph + 8
        self.status_y = tab_bottom
        panel_y = tab_bottom + int(16 * s)
        self.panels = [EffectPanel(fx, 8, panel_y, max(240, w - 16), s) for fx in self.effects]
        for p in self.panels:
            old = saved.get(id(p.effect))
            if not old:
                continue
            for k, val in zip(p.knobs, old["knobs"]):
                k.value = val
            for sw, val in zip(p.switches, old["switches"]):
                sw.value = val
            if p.style_picker and old["style"] in p.style_picker.styles:
                p.style_picker.selected_name = old["style"]
        panel_h = self.panels[self.active_index].height if self.panels else 40
        scope_y = panel_y + panel_h + 8
        self.scope.layout(w, scope_y, max(90, self.screen.get_height() - scope_y - 8))

    def _scope_audio(self):
        return self.rendered if self.rendered is not None else self.original

    def open_wav(self, path: str):
        try:
            data, sr = read_wav(path)
        except Exception as exc:
            self.status = f"Read error: {exc}"
            return
        self.original, self.rendered, self.sample_rate = data, None, sr
        self.player.stop()
        self.status = f"Loaded {os.path.basename(path)}  {sr} Hz"

    def save_wav(self, path: str):
        if self.rendered is None:
            self.status = "Render before saving."
            return
        try:
            written = write_wav(path, self.rendered, self.sample_rate)
        except Exception as exc:
            self.status = f"Save error: {exc}"
            return
        self.status = f"Saved {written}"

    def render(self):
        if self.original is None:
            self.status = "Open a WAV or Sample input first."
            return
        panel = self.active_panel()
        audio = self.original.copy()
        try:
            if panel is not None:
                effect = panel.push_settings_into_effect()
                audio = effect.apply_effect(audio, self.sample_rate)
        except Exception as exc:
            self.status = f"Render failed: {exc}"
            return
        self.rendered = np.asarray(audio, dtype=np.float32)
        self.status = f"Rendered with {panel.effect.get_name() if panel else 'none'}."
        self.player.play(self.rendered, self.sample_rate)

    def _ensure_input_open(self, live: bool):
        dev = self.input_dialog.current_device()
        if not dev:
            self.input_dialog.message = "Pick an input device first."
            return False
        self.player.shutdown()
        panel = self.active_panel()
        effect = panel.push_settings_into_effect() if panel and live else None
        ok = self.input_engine.start_monitor(dev["index"], dev["channels"], dev["rate"], live, effect)
        self.input_dialog.message = self.input_engine.status
        return ok

    def _start_live(self):
        self._ensure_input_open(live=True)

    def click_button(self, label: str):
        if label == "Open WAV":
            self.dialog.open_load(os.path.dirname(os.path.abspath(__file__)))
        elif label == "Save WAV":
            if self.rendered is None:
                self.status = "Render before saving."
            else:
                self.dialog.open_save(os.path.dirname(os.path.abspath(__file__)), "processed.wav")
        elif label == "Audio Input":
            self.input_dialog.open()
        elif label == "Plugin Errors":
            self.error_dialog.visible = True
        elif label == "Render":
            self.render()
        elif label in ("Play Processed", "Repeat"):
            if self.rendered is None:
                self.status = "Click Render first."
            else:
                self.input_engine.stop()
                self.player.play(self.rendered, self.sample_rate)
        elif label == "Original":
            if self.original is None:
                self.status = "Open a WAV or Sample first."
            else:
                self.input_engine.stop()
                self.player.play(self.original, self.sample_rate)
        elif label == "Stop":
            self.player.stop()
            self.input_engine.stop()

    def _handle_input_action(self, action):
        if action == "close":
            if not self.input_engine.live and not self.input_engine.recording:
                self.input_engine.stop()
            self.input_dialog.visible = False
        elif action == "select":
            if self.input_engine.stream is not None:
                self._ensure_input_open(self.input_engine.live)
        elif action == "monitor":
            self._ensure_input_open(live=False)
        elif action == "gain":
            self.input_dialog.message = f"Input volume x{self.input_engine.gain:.1f}"
        elif action == "sample":
            if self.input_engine.recording:
                audio, sr = self.input_engine.stop_recording()
                if audio is None or len(audio) < 16:
                    self.status = "Sample was empty."
                else:
                    self.original = audio
                    self.rendered = None
                    self.sample_rate = sr
                    self.status = f"Sampled {audio.shape} @ {sr} Hz"
                    self.input_dialog.message = self.status
            else:
                if self.input_engine.stream is None:
                    self._ensure_input_open(live=False)
                self.input_engine.start_recording()
                self.input_dialog.message = "Sampling… click Sample again to stop."
        elif action == "live":
            if self.input_engine.live:
                self.input_engine.stop()
                self.input_dialog.message = "Live through stopped."
            else:
                self._start_live()

    def _handle_effect_keys(self, event) -> bool:
        if not self.effects:
            return False
        if self.use_plugin_dropdown and self.plugin_dropdown:
            if event.key in (pygame.K_DOWN, pygame.K_UP):
                if not self.plugin_dropdown.open:
                    self.plugin_dropdown.open = True
                    self.plugin_dropdown.highlight = self.plugin_dropdown.active
                self.plugin_dropdown.move_highlight(-1 if event.key == pygame.K_UP else 1)
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.plugin_dropdown.open:
                self.select_effect(self.sorted_indices[self.plugin_dropdown.highlight])
                self._relayout()
                if self.plugin_dropdown:
                    self.plugin_dropdown.open = False
                return True
            if event.key == pygame.K_ESCAPE and self.plugin_dropdown.open:
                self.plugin_dropdown.open = False
                return True
        if event.key in (pygame.K_LEFT, pygame.K_COMMA):
            self.select_effect(self.active_index - 1)
            self._relayout()
            return True
        if event.key in (pygame.K_RIGHT, pygame.K_PERIOD):
            self.select_effect(self.active_index + 1)
            self._relayout()
            return True
        return False

    def run(self):
        running = True
        while running:
            self.clock.tick(60)
            hover = pygame.mouse.get_pos()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self._relayout()
                elif self.error_dialog.visible:
                    self.error_dialog.handle_event(event)
                elif self.input_dialog.visible:
                    act = self.input_dialog.handle_event(event)
                    if act:
                        self._handle_input_action(act)
                elif self.dialog.visible:
                    result = self.dialog.handle_event(event)
                    if result:
                        kind, path = result
                        if kind == "open":
                            self.open_wav(path)
                        elif kind == "save":
                            self.save_wav(path)
                            self.dialog.close()
                elif event.type == pygame.KEYDOWN:
                    self._handle_effect_keys(event)
                else:
                    used = False
                    if self.plugin_dropdown:
                        got = self.plugin_dropdown.handle_event(event)
                        if got in ("toggle", "scroll", "close"):
                            used = True
                        elif isinstance(got, int):
                            self.select_effect(self.sorted_indices[got])
                            self._relayout()
                            if self.plugin_dropdown:
                                self.plugin_dropdown.open = False
                            used = True
                    if not used:
                        used = self.scope.handle_event(event)
                    panel = self.active_panel()
                    drop_open = bool(self.plugin_dropdown and self.plugin_dropdown.open)
                    if panel is not None and not drop_open:
                        used = panel.handle_event(event) or used
                    if not used and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.prev_btn.hit(event.pos) and self.effects:
                            self.select_effect(self.active_index - 1)
                            self._relayout()
                        elif self.next_btn.hit(event.pos) and self.effects:
                            self.select_effect(self.active_index + 1)
                            self._relayout()
                        else:
                            hit = False
                            for i, tab in enumerate(self.effect_tabs):
                                if tab.hit(event.pos):
                                    self.select_effect(i)
                                    self._relayout()
                                    hit = True
                                    break
                            if not hit:
                                for b in self.buttons:
                                    if b.hit(event.pos):
                                        self.click_button(b.label)

            if self.input_engine.live:
                panel = self.active_panel()
                if panel is not None:
                    self.input_engine.effect = panel.push_settings_into_effect()

            play_pos = self.player.play_position()
            self.scope.update(self._scope_audio(), self.sample_rate, play_pos)
            self.screen.fill(BG)
            blocked = self.dialog.visible or self.error_dialog.visible or self.input_dialog.visible
            for b in self.buttons:
                b.draw(self.screen, self.small, b.hit(hover) and not blocked)
            self.prev_btn.draw(self.screen, self.small, self.prev_btn.hit(hover) and not blocked)
            self.next_btn.draw(self.screen, self.small, self.next_btn.hit(hover) and not blocked)
            for tab in self.effect_tabs:
                tab.draw(self.screen, self.small, tab.hit(hover) and not blocked)
            self.screen.blit(self.small.render(self.status, True, MUTED), (8, self.status_y))
            panel = self.active_panel()
            if panel is not None:
                panel.draw(self.screen, self.big, self.small)
            self.scope.draw(self.screen, self.big, self.small, self._scope_audio(),
                            self.sample_rate, play_pos, hover)
            if self.plugin_dropdown:
                self.plugin_dropdown.draw(self.screen, self.small)
            self.dialog.draw(self.screen, self.big, self.small, self.screen.get_rect())
            self.error_dialog.draw(self.screen, self.big, self.small, self.screen.get_rect())
            self.input_dialog.draw(self.screen, self.big, self.small, self.screen.get_rect(),
                                   self.input_engine.preview_copy())
            pygame.display.flip()
        self.input_engine.stop()
        self.player.stop()
        pygame.quit()


if __name__ == "__main__":
    HostApp().run()
