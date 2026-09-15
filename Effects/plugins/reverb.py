"""
Multi-style reverb plugin.
Discovered by host.py via get_name / get_knobs / get_switches / getStyles /
apply_effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
from scipy import signal


@dataclass
class KnobColorScheme:
    outline: str = "black"
    face: str = "white"
    needle: str = "black"


@dataclass
class Knob:
    name: str = "Generic"
    min: float = 0.0
    max: float = 1.0
    default: float = 0.5
    click_pts: List[float] = field(default_factory=lambda: [0.5])
    knob_color_scheme: KnobColorScheme = field(
        default_factory=lambda: KnobColorScheme(outline="black", face="white", needle="black")
    )


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


# Display name -> ordinal written to self.style
STYLES: Dict[str, int] = {
    "Room": 0,
    "Hall": 1,
    "Chamber": 2,
    "Cathedral": 3,
    "Plate": 4,
    "Algorithmic": 5,
    "Spring": 6,
    "Hybrid": 7,
}

_STYLE_BY_ORDINAL = {v: k.lower() for k, v in STYLES.items()}

_COMB_DELAYS_L = np.array([1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617])
_COMB_DELAYS_R = _COMB_DELAYS_L + 23
_ALLPASS_L = np.array([556, 441, 341, 225])
_ALLPASS_R = _ALLPASS_L + 13


def _to_float_stereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x[:, :2].copy()


def _from_stereo(wet: np.ndarray, like: np.ndarray) -> np.ndarray:
    if like.ndim == 1:
        return wet.mean(axis=1).astype(like.dtype, copy=False)
    if like.shape[1] == 1:
        return wet.mean(axis=1, keepdims=True).astype(like.dtype, copy=False)
    out = np.zeros_like(like, dtype=np.float64)
    ch = min(like.shape[1], 2)
    out[:, :ch] = wet[:, :ch]
    if like.shape[1] > 2:
        out[:, 2:] = like[:, 2:]
    return out.astype(like.dtype, copy=False)


def _peak_normalize(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = np.max(np.abs(x)) + 1e-12
    return x * (peak / m)


def _one_pole_lp(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    a = np.exp(-2.0 * np.pi * np.clip(cutoff, 20.0, sr * 0.45) / sr)
    b = 1.0 - a
    y = np.empty_like(x)
    acc = 0.0
    for i, s in enumerate(x):
        acc = a * acc + b * s
        y[i] = acc
    return y


def _biquad_lp(x: np.ndarray, cutoff: float, sr: int) -> np.ndarray:
    cutoff = np.clip(cutoff, 20.0, sr * 0.45)
    sos = signal.butter(2, cutoff / (sr / 2), btype="low", output="sos")
    return signal.sosfilt(sos, x)


def _comb(x: np.ndarray, delay: int, feedback: float, damp: float) -> np.ndarray:
    delay = max(2, int(delay))
    buf = np.zeros(delay, dtype=np.float64)
    y = np.empty_like(x)
    filt = 0.0
    idx = 0
    for i, s in enumerate(x):
        out = buf[idx]
        filt = out * (1.0 - damp) + filt * damp
        buf[idx] = s + filt * feedback
        y[i] = out
        idx += 1
        if idx >= delay:
            idx = 0
    return y


def _allpass(x: np.ndarray, delay: int, feedback: float = 0.5) -> np.ndarray:
    delay = max(2, int(delay))
    buf = np.zeros(delay, dtype=np.float64)
    y = np.empty_like(x)
    idx = 0
    for i, s in enumerate(x):
        buf_out = buf[idx]
        y[i] = -s + buf_out
        buf[idx] = s + buf_out * feedback
        idx += 1
        if idx >= delay:
            idx = 0
    return y


def _generate_ir(
    sr: int,
    style: str,
    decay: float,
    predelay_ms: float,
    brightness: float,
) -> np.ndarray:
    presets = {
        "room":      dict(scale=0.35, dens=0.85, early=0.18, hf=4500, lf_boost=0.15),
        "hall":      dict(scale=1.00, dens=0.70, early=0.28, hf=3200, lf_boost=0.25),
        "chamber":   dict(scale=0.55, dens=0.92, early=0.14, hf=5000, lf_boost=0.10),
        "cathedral": dict(scale=1.80, dens=0.55, early=0.45, hf=2200, lf_boost=0.40),
        "plate":     dict(scale=0.70, dens=0.98, early=0.06, hf=7000, lf_boost=0.05),
    }
    p = presets.get(style, presets["hall"])
    rt = max(0.15, float(decay) * p["scale"])
    n = int(sr * (rt + predelay_ms / 1000.0 + 0.05))
    n = max(n, int(0.2 * sr))

    rng = np.random.default_rng(42)
    t = np.arange(n) / sr
    pre = int(max(0.0, predelay_ms) * sr / 1000.0)

    noise_l = rng.standard_normal(n)
    noise_r = rng.standard_normal(n)
    shared = rng.standard_normal(n)
    coh = 0.55 if style == "plate" else 0.25
    noise_l = (1 - coh) * noise_l + coh * shared
    noise_r = (1 - coh) * noise_r + coh * shared

    env = np.zeros(n)
    tail = slice(pre, n)
    tt = t[tail] - (t[pre] if pre < n else 0.0)
    env[tail] = 10 ** (-3.0 * tt / rt)

    dens_cut = 800 + 14000 * p["dens"]
    ir_l = _biquad_lp(noise_l, dens_cut, sr) * env
    ir_r = _biquad_lp(noise_r, dens_cut, sr) * env

    hf = p["hf"] * (0.4 + 0.6 * np.clip(brightness, 0.0, 1.0))
    ir_l = _one_pole_lp(ir_l, hf, sr)
    ir_r = _one_pole_lp(ir_r, hf, sr)

    n_taps = 28 if style == "plate" else 18
    times = np.sort(rng.uniform(0.004, p["early"], n_taps))
    amps = rng.uniform(0.15, 0.85, n_taps) * np.exp(-times / max(p["early"], 1e-3))
    pan = rng.uniform(-1.0, 1.0, n_taps)
    for ti, a, pn in zip(times, amps, pan):
        i = pre + int(ti * sr)
        if 0 <= i < n:
            ir_l[i] += a * (0.5 - 0.5 * pn)
            ir_r[i] += a * (0.5 + 0.5 * pn)

    if 0 <= pre < n:
        ir_l[pre] += 0.15
        ir_r[pre] += 0.15

    spread = int(0.35 * 0.012 * sr)
    if spread > 0:
        ir_r = np.concatenate([np.zeros(spread), ir_r[:-spread]])

    if p["lf_boost"] > 0:
        sos = signal.butter(2, 180 / (sr / 2), btype="low", output="sos")
        ir_l = ir_l + signal.sosfilt(sos, ir_l) * p["lf_boost"]
        ir_r = ir_r + signal.sosfilt(sos, ir_r) * p["lf_boost"]

    return _peak_normalize(np.stack([ir_l, ir_r], axis=1), 1.0)


def _convolve(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    outs = [
        signal.fftconvolve(x[:, ch], ir[:, ch], mode="full")
        for ch in range(2)
    ]
    m = min(len(outs[0]), len(outs[1]))
    return np.stack([outs[0][:m], outs[1][:m]], axis=1)


def _algorithmic(x: np.ndarray, sr: int, room_size: float, damp: float) -> np.ndarray:
    scale = sr / 44100.0
    fb = 0.28 + 0.70 * np.clip(room_size, 0.05, 0.98)
    damp = np.clip(damp, 0.0, 0.95)

    def process_ch(sig, comb_d, ap_d):
        acc = np.zeros_like(sig)
        for d in comb_d:
            acc += _comb(sig, int(d * scale), fb, damp)
        acc *= 0.125
        for d in ap_d:
            acc = _allpass(acc, int(d * scale), 0.5)
        return acc

    l = process_ch(x[:, 0], _COMB_DELAYS_L, _ALLPASS_L)
    r = process_ch(x[:, 1], _COMB_DELAYS_R, _ALLPASS_R)
    return np.stack([l, r], axis=1)


def _spring(x: np.ndarray, sr: int, decay: float, twang: float) -> np.ndarray:
    delays_ms = np.array([22.1, 29.7, 37.3, 44.9])
    outs = np.zeros_like(x)
    fb = 0.55 + 0.35 * np.tanh(decay / 3.0)
    twang = np.clip(twang, 0.0, 1.0)
    sos = signal.butter(2, [280 / (sr / 2), 4200 / (sr / 2)], btype="band", output="sos")
    for ch in range(2):
        acc = np.zeros(len(x))
        for k, dms in enumerate(delays_ms):
            d = max(4, int(dms * sr / 1000.0) + (3 if ch else 0) + k)
            line = _comb(x[:, ch], d, fb * (0.92 + 0.05 * k), damp=0.15)
            line = _allpass(line, max(3, d // 7), 0.6)
            line = _allpass(line, max(3, d // 11), 0.4 + 0.2 * twang)
            acc += line
        outs[:, ch] = signal.sosfilt(sos, acc) * 0.28
    return outs


class Reverb:
    """Convolution + algorithmic + spring reverb."""

    def __init__(self):
        self.name = "Reverb"
        self.enable = True
        self.mix = 0.32
        self.decay = 2.0
        self.predelay = 18.0
        self.brightness = 0.6
        self.damp = 0.35
        self.style = STYLES["Hall"]  # ordinal from getStyles()
        self.tail = False

        self._ir_cache_key = None
        self._ir_cache = None

    def get_name(self) -> str:
        return self.name

    def get_colors(self):
        return {
            "face": "#1c2428",
            "edge": "#0e1214",
            "text": "#e8f0f2",
            "muted": "#8aa0a8",
            "button": "#2c3a40",
            "button_hot": "#3d525a",
            "button_on": "#2a7a6a",
            "button_text": "#e8f0f2",
            "switch_on": "#2a7a6a",
            "switch_off": "#1a2226",
            "slider": "#141c20",
            "slider_handle": "#8aa0a8",
            "knob_outline": "#0e1214",
            "knob_face": "#6a8a92",
            "knob_needle": "#f2f7f8",
        }

    def get_knobs(self) -> List[Knob]:
        metal = KnobColorScheme(outline="#0e1214", face="#6a8a92", needle="#f2f7f8")
        return [
            Knob(name="Mix", min=0.0, max=1.0, default=0.32,
                 click_pts=[0.0, 0.15, 0.32, 0.5, 0.75, 1.0], knob_color_scheme=metal),
            Knob(name="Decay", min=0.2, max=8.0, default=2.0,
                 click_pts=[0.4, 0.8, 1.2, 2.0, 3.5, 6.0, 8.0], knob_color_scheme=metal),
            Knob(name="Predelay", min=0.0, max=120.0, default=18.0,
                 click_pts=[0.0, 12.0, 18.0, 30.0, 60.0, 90.0], knob_color_scheme=metal),
            Knob(name="Brightness", min=0.0, max=1.0, default=0.6,
                 click_pts=[0.0, 0.25, 0.45, 0.6, 0.8, 1.0], knob_color_scheme=metal),
            Knob(name="Damp", min=0.0, max=0.95, default=0.35,
                 click_pts=[0.0, 0.2, 0.35, 0.55, 0.75, 0.95], knob_color_scheme=metal),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch(name="Enable", default=True),
            Switch(name="Tail", default=False),
        ]

    def getStyles(self) -> Dict[str, int]:
        """Named styles and the ordinal the host should write to self.style."""
        return dict(STYLES)

    def get_styles(self) -> Dict[str, int]:
        return self.getStyles()

    def _style_key(self) -> str:
        raw = getattr(self, "style", STYLES["Hall"])
        if isinstance(raw, str):
            return raw.strip().lower()
        idx = int(round(float(raw)))
        return _STYLE_BY_ORDINAL.get(idx, "hall")

    def _ir(self, sr: int, style: str, decay: float, predelay: float, brightness: float):
        key = (sr, style, round(decay, 3), round(predelay, 2), round(brightness, 3))
        if key != self._ir_cache_key:
            self._ir_cache = _generate_ir(sr, style, decay, predelay, brightness)
            self._ir_cache_key = key
        return self._ir_cache

    def apply_effect(self, audio, sample_rate: int):
        if not getattr(self, "enable", True):
            return audio

        x = np.asarray(audio)
        if x.size == 0:
            return audio

        dry = _to_float_stereo(x)
        n = len(dry)
        sr = int(sample_rate)
        mix = float(np.clip(getattr(self, "mix", 0.32), 0.0, 1.0))
        decay = float(np.clip(getattr(self, "decay", 2.0), 0.2, 12.0))
        predelay = float(np.clip(getattr(self, "predelay", 18.0), 0.0, 250.0))
        brightness = float(np.clip(getattr(self, "brightness", 0.6), 0.0, 1.0))
        damp = float(np.clip(getattr(self, "damp", 0.35), 0.0, 0.95))
        style = self._style_key()
        keep_length = not bool(getattr(self, "tail", False))

        if style == "algorithmic":
            wet = _algorithmic(dry, sr, room_size=min(decay / 4.0, 0.95), damp=damp)
        elif style == "spring":
            wet = _spring(dry, sr, decay=decay, twang=brightness)
        elif style == "hybrid":
            ir = self._ir(sr, "hall", decay, predelay, brightness)
            wet_c = _convolve(dry, ir)
            wet_a = _algorithmic(dry, sr, room_size=0.7, damp=damp)
            m = min(len(wet_c), len(wet_a))
            wet = 0.7 * wet_c[:m] + 0.3 * wet_a[:m]
        else:
            ir = self._ir(sr, style, decay, predelay, brightness)
            wet = _convolve(dry, ir)

        if keep_length:
            if len(wet) < n:
                wet = np.vstack([wet, np.zeros((n - len(wet), 2))])
            else:
                wet = wet[:n]
            out = (1.0 - mix) * dry + mix * wet
        else:
            if len(wet) > n:
                dry_p = np.zeros((len(wet), 2))
                dry_p[:n] = dry
            else:
                dry_p = dry[: len(wet)]
            out = (1.0 - mix) * dry_p + mix * wet[: len(dry_p)]
            if len(out) > n:
                out = out[:n]

        peak = np.max(np.abs(out))
        if peak > 0.99:
            out *= 0.99 / peak

        return _from_stereo(out, x)