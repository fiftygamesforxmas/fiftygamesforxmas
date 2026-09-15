"""Overdrive — Ibanez Tube Screamer–style plugin for the host interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
from scipy.signal import bilinear, lfilter, lfilter_zi, tf2sos

# ---------------------------------------------------------------------------
# Shared dataclasses (identical to host definitions)
# ---------------------------------------------------------------------------


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
        default_factory=lambda: KnobColorScheme(
            outline="black", face="white", needle="black"
        )
    )


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


# ---------------------------------------------------------------------------
# Colors — bright grass-adjacent green face, black type, silver-face knobs
# ---------------------------------------------------------------------------

_KNOB_SCHEME = KnobColorScheme(
    outline="#0a0a0a",
    face="#d8dce0",  # silver face
    needle="#111111",
)

# Face is a light grassy green so black labels stay readable.
_COLORS = {
    "face": "#7BC95A",
    "edge": "#1A2E14",
    "text": "#0A0A0A",
    "muted": "#2C4A22",
    "button": "#1E3218",
    "button_hot": "#2E4A24",
    "button_on": "#0E1A0C",
    "button_text": "#F4FFF0",
    "switch_on": "#1A3A12",
    "switch_off": "#3A5A32",
    "slider": "#1A2E14",
    "slider_handle": "#D8DCE0",
    "knob_outline": "#0A0A0A",
    "knob_face": "#D8DCE0",
    "knob_needle": "#111111",
}


# ---------------------------------------------------------------------------
# Small IIR helpers (per-channel state, safe on empty buffers)
# ---------------------------------------------------------------------------


class _Biquad:
    """Direct-form II SOS section with per-channel zi."""

    def __init__(self):
        self.sos = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
        self.zi: Optional[np.ndarray] = None  # (n_sections, n_ch, 2)
        self._sr = 0
        self._key: Tuple = ()

    def configure(self, b, a, sample_rate: int, n_ch: int, key: Tuple):
        sos = tf2sos(np.asarray(b, dtype=np.float64), np.asarray(a, dtype=np.float64))
        if self._sr != sample_rate or self._key != key or self.zi is None or self.zi.shape[1] != n_ch:
            zi = []
            for section in sos:
                bsec, asec = section[:3], section[3:]
                z0 = lfilter_zi(bsec, asec)
                zi.append(np.tile(z0[:, None], (1, n_ch)).T * 0.0)  # (n_ch, 2)
            self.zi = np.stack(zi, axis=0)  # (n_sec, n_ch, 2)
            self._sr = sample_rate
            self._key = key
        self.sos = sos

    def process(self, x: np.ndarray) -> np.ndarray:
        """x: (n, ch) float64."""
        y = x
        for i, section in enumerate(self.sos):
            b, a = section[:3], section[3:]
            out_ch = []
            new_zi = []
            for c in range(y.shape[1]):
                yc, zf = lfilter(b, a, y[:, c], zi=self.zi[i, c])
                out_ch.append(yc)
                new_zi.append(zf)
            y = np.stack(out_ch, axis=1)
            self.zi[i] = np.stack(new_zi, axis=0)
        return y


def _one_pole_hp(fc: float, sr: int):
    w = 2.0 * np.pi * fc
    b_s = np.array([1.0, 0.0])
    a_s = np.array([1.0, w])
    return bilinear(b_s, a_s, fs=sr)


def _one_pole_lp(fc: float, sr: int):
    w = 2.0 * np.pi * fc
    b_s = np.array([w])
    a_s = np.array([1.0, w])
    return bilinear(b_s, a_s, fs=sr)


def _highshelf(fc: float, gain_db: float, sr: int):
    """First-order high shelf (RBJ-ish via bilinear analog prototype)."""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    # Simple bilinear shelf
    K = np.tan(w0 * 0.5)
    V = 10.0 ** (gain_db / 20.0)
    # Low-cut / high-boost form
    b0 = V * K + 1.0
    b1 = V * K - 1.0
    a0 = K + 1.0
    a1 = K - 1.0
    if abs(gain_db) < 1e-9:
        return np.array([1.0, 0.0]), np.array([1.0, 0.0])
    # For negative gain, invert roles so highs are cut
    if gain_db < 0:
        b0, a0 = a0, V * K + 1.0
        b1, a1 = a1, V * K - 1.0
        a0 = K + 1.0
        a1 = K - 1.0
        Vn = 10.0 ** (gain_db / 20.0)
        b0 = Vn * K + 1.0
        b1 = Vn * K - 1.0
        a0 = K + 1.0
        a1 = K - 1.0
    return np.array([b0 / a0, b1 / a0]), np.array([1.0, a1 / a0])


def _peaking(fc: float, q: float, gain_db: float, sr: int):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    alpha = np.sin(w0) / (2.0 * q)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * np.cos(w0)
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * np.cos(w0)
    a2 = 1.0 - alpha / A
    return np.array([b0 / a0, b1 / a0, b2 / a0]), np.array([1.0, a1 / a0, a2 / a0])


def _soft_clip_diodes(x: np.ndarray, drive: float) -> np.ndarray:
    """
    Silicon-diode-ish soft clip in the feedback path.
    Asymptotes near ±1 after normalization; rounded knees (odd harmonics).
    """
    # Drive maps 0..1 → extra gain before the diodes (TS ~ +0 dB to ~+30 dB)
    g = 10.0 ** ((1.0 + 29.0 * drive) / 20.0)
    y = g * x
    # Smooth diode: tanh is a good silicon-ish curve; blend with cubic for body
    t = np.tanh(y)
    # Slight residual of the unclipped path (non-inverting clipper mix)
    return 0.82 * t + 0.18 * np.tanh(0.45 * y)


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class Overdrive:
    def __init__(self):
        self.name = "Overdrive"
        self.enable = True
        self.overdrive = 0.35
        self.tone = 0.55
        self.level = 0.55

        self._hp = _Biquad()
        self._lp_fb = _Biquad()
        self._mid = _Biquad()
        self._tone = _Biquad()
        self._post_lp = _Biquad()
        self._last_sr = 0

    def get_name(self) -> str:
        return "Overdrive"

    def get_colors(self):
        return dict(_COLORS)

    def get_knobs(self) -> List[Knob]:
        return [
            Knob(
                name="Overdrive",
                min=0.0,
                max=1.0,
                default=0.35,
                click_pts=[0.0, 0.15, 0.35, 0.5, 0.7, 1.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
            Knob(
                name="Tone",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.0, 0.25, 0.4, 0.55, 0.75, 1.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
            Knob(
                name="Level",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.0, 0.25, 0.4, 0.55, 0.75, 1.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
        ]

    def get_switches(self) -> List[Switch]:
        return [Switch(name="Enable", default=True)]

    def apply_effect(self, audio, sample_rate: int):
        x = np.asarray(audio)
        if x.size == 0:
            return x

        if not bool(getattr(self, "enable", True)):
            return x

        sr = int(sample_rate)
        drive = float(np.clip(getattr(self, "overdrive", 0.35), 0.0, 1.0))
        tone = float(np.clip(getattr(self, "tone", 0.55), 0.0, 1.0))
        level = float(np.clip(getattr(self, "level", 0.55), 0.0, 1.0))

        orig_dtype = x.dtype
        orig_ndim = x.ndim
        if x.ndim == 1:
            work = x.astype(np.float64, copy=False)[:, None]
        else:
            work = x.astype(np.float64, copy=False)
        n_ch = work.shape[1]

        # --- TS-like pre-emphasis: HPF ~720 Hz so bass clips less ---
        b_hp, a_hp = _one_pole_hp(720.0, sr)
        self._hp.configure(b_hp, a_hp, sr, n_ch, ("hp", sr))
        pre = self._hp.process(work)

        # Mild feedback LPF (~3–5 kHz) standing in for the 51 pF across diodes
        b_fb, a_fb = _one_pole_lp(4200.0, sr)
        self._lp_fb.configure(b_fb, a_fb, sr, n_ch, ("fblp", sr))
        pre_s = self._lp_fb.process(pre)

        clipped = _soft_clip_diodes(pre_s, drive)

        # Non-inverting clipper: dry fundamentals + clipped path
        # (keeps pick attack / dynamics — the TS “secret”)
        mix_dry = 0.22 + 0.10 * (1.0 - drive)
        driven = mix_dry * work + (1.0 - mix_dry) * clipped

        # Signature mid hump ~720–900 Hz
        b_m, a_m = _peaking(780.0, 0.85, 5.5 + 1.5 * drive, sr)
        self._mid.configure(b_m, a_m, sr, n_ch, ("mid", sr, round(drive, 3)))
        driven = self._mid.process(driven)

        # Tone: clockwise = more treble (high shelf around 3.2 kHz)
        shelf_db = np.interp(tone, [0.0, 1.0], [-10.0, 7.5])
        b_t, a_t = _highshelf(3200.0, float(shelf_db), sr)
        self._tone.configure(b_t, a_t, sr, n_ch, ("tone", sr, round(tone, 3)))
        driven = self._tone.process(driven)

        # Post LPF ~3.2 kHz (tone-stack residual + anti-fizz)
        b_pl, a_pl = _one_pole_lp(3200.0 + 1800.0 * tone, sr)
        self._post_lp.configure(b_pl, a_pl, sr, n_ch, ("plp", sr, round(tone, 3)))
        driven = self._post_lp.process(driven)

        # Level: unity-ish around 0.5, up to ~+6 dB at 1.0
        gain = 10.0 ** ((np.interp(level, [0.0, 0.5, 1.0], [-18.0, 0.0, 6.0])) / 20.0)
        out = driven * gain

        out = np.clip(out, -1.0, 1.0)
        out = np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=-1.0)

        if orig_ndim == 1:
            out = out[:, 0]
        if orig_dtype == np.float32:
            out = out.astype(np.float32)
        return out

