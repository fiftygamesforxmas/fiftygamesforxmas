"""
phase_a3.py
Eddie Van Halen–style analog phase shifter + 3-band tone.
Stronger sweep / notches than Phase A1.
Host interface 1.0 drop-in module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


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


_SILVER = KnobColorScheme(
    outline="#1a0505",
    face="#c9cdd3",
    needle="#8b0a0a",
)


def _as_2d(audio: np.ndarray) -> tuple[np.ndarray, bool]:
    x = np.asarray(audio)
    if x.size == 0:
        return (
            x.reshape(0, 1) if x.ndim <= 1 else x.reshape(0, max(1, x.shape[-1])),
            x.ndim == 1,
        )
    if x.ndim == 1:
        return x.reshape(-1, 1), True
    return x, False


def _allpass_coeff(fc, sr: float) -> np.ndarray:
    """First-order allpass coeff with -90 degrees at fc (bilinear)."""
    sr = max(float(sr), 1.0)
    fc = np.clip(np.asarray(fc, dtype=np.float64), 20.0, 0.48 * sr)
    w = np.tan(np.pi * fc / sr)
    return (w - 1.0) / (w + 1.0)


def _rbj_lowshelf(gain_db: float, fc: float, sr: float, q: float = 0.707):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = sinw / (2.0 * q)
    two_sqrtA_alpha = 2.0 * np.sqrt(A) * alpha
    b0 = A * ((A + 1) - (A - 1) * cosw + two_sqrtA_alpha)
    b1 = 2.0 * A * ((A - 1) - (A + 1) * cosw)
    b2 = A * ((A + 1) - (A - 1) * cosw - two_sqrtA_alpha)
    a0 = (A + 1) + (A - 1) * cosw + two_sqrtA_alpha
    a1 = -2.0 * ((A - 1) + (A + 1) * cosw)
    a2 = (A + 1) + (A - 1) * cosw - two_sqrtA_alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _rbj_highshelf(gain_db: float, fc: float, sr: float, q: float = 0.707):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = sinw / (2.0 * q)
    two_sqrtA_alpha = 2.0 * np.sqrt(A) * alpha
    b0 = A * ((A + 1) + (A - 1) * cosw + two_sqrtA_alpha)
    b1 = -2.0 * A * ((A - 1) + (A + 1) * cosw)
    b2 = A * ((A + 1) + (A - 1) * cosw - two_sqrtA_alpha)
    a0 = (A + 1) - (A - 1) * cosw + two_sqrtA_alpha
    a1 = 2.0 * ((A - 1) - (A + 1) * cosw)
    a2 = (A + 1) - (A - 1) * cosw - two_sqrtA_alpha
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _rbj_peak(gain_db: float, fc: float, sr: float, q: float = 0.9):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * fc / sr
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = sinw / (2.0 * q)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * cosw
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha / A
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _biquad(x: np.ndarray, b0, b1, b2, a1, a2, zi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = x.shape[0]
    y = np.empty(n, dtype=np.float64)
    s1, s2 = float(zi[0]), float(zi[1])
    for i in range(n):
        xi = float(x[i])
        yi = b0 * xi + s1
        s1 = b1 * xi - a1 * yi + s2
        s2 = b2 * xi - a2 * yi
        y[i] = yi
    return y, np.array([s1, s2], dtype=np.float64)


class PhaseA3:
    """Strong EVH / Phase 90–style analog phaser + 3-band tone."""

    def __init__(self):
        self.name = "Phase 9"

        self.enable = True
        self.script = True

        self.rate = 0.85
        self.depth = 1.0
        self.feedback = 0.88
        self.mix = 0.5
        self.center = 0.35
        self.stages = 6.0

        self.low = 0.0
        self.mid = 1.5
        self.hi = 1.0

        self._sr = 0
        self._lfo_phase = 0.0
        self._ap_x: Optional[np.ndarray] = None
        self._ap_y: Optional[np.ndarray] = None
        self._fb_z: Optional[np.ndarray] = None
        self._tone_zi = None
        self._smooth = {
            "rate": self.rate,
            "depth": self.depth,
            "feedback": self.feedback,
            "mix": self.mix,
            "center": self.center,
        }

    def get_name(self) -> str:
        return "Phase 9"

    def get_colors(self) -> dict:
        return {
            "face": "#8b1010",
            "edge": "#2a0404",
            "text": "#fff6e8",
            "muted": "#f0c9a0",
            "button": "#4a0c0c",
            "button_hot": "#c42a2a",
            "button_on": "#e8d7a0",
            "button_text": "#1a0505",
            "switch_on": "#e8d7a0",
            "switch_off": "#3a0a0a",
            "slider": "#2a0606",
            "slider_handle": "#d8dde4",
            "knob_outline": "#1a0505",
            "knob_face": "#c9cdd3",
            "knob_needle": "#8b0a0a",
        }

    def get_knobs(self) -> List[Knob]:
        return [
            Knob("Rate", 0.02, 8.0, 0.85, [0.05, 0.12, 0.25, 0.85, 1.4, 3.0, 8.0], _SILVER),
            Knob("Depth", 0.0, 1.0, 1.0, [0.0, 0.25, 0.5, 0.75, 1.0], _SILVER),
            Knob("Feedback", 0.0, 0.97, 0.88, [0.0, 0.35, 0.6, 0.88, 0.94, 0.97], _SILVER),
            Knob("Mix", 0.0, 1.0, 0.5, [0.0, 0.25, 0.5, 0.75, 1.0], _SILVER),
            Knob("Center", 0.0, 1.0, 0.35, [0.0, 0.25, 0.35, 0.7, 1.0], _SILVER),
            Knob("Stages", 2.0, 8.0, 6.0, [2, 4, 6, 8], _SILVER),
            Knob("Low", -12.0, 12.0, 0.0, [-12, -6, 0, 6, 12], _SILVER),
            Knob("Mid", -12.0, 12.0, 1.5, [-12, -6, 0, 1.5, 6, 12], _SILVER),
            Knob("Hi", -12.0, 12.0, 1.0, [-12, -6, 0, 1, 6, 12], _SILVER),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch("Enable", True),
            Switch("Script", True),
        ]

    def _clip_params(self):
        rate = float(np.clip(getattr(self, "rate", 0.85), 0.02, 8.0))
        depth = float(np.clip(getattr(self, "depth", 1.0), 0.0, 1.0))
        feedback = float(np.clip(getattr(self, "feedback", 0.88), 0.0, 0.97))
        mix = float(np.clip(getattr(self, "mix", 0.5), 0.0, 1.0))
        center = float(np.clip(getattr(self, "center", 0.35), 0.0, 1.0))
        stages = int(np.clip(np.round(getattr(self, "stages", 6.0)), 2, 8))
        if stages % 2:
            stages = min(stages + 1, 8)
        low = float(np.clip(getattr(self, "low", 0.0), -12.0, 12.0))
        mid = float(np.clip(getattr(self, "mid", 1.5), -12.0, 12.0))
        hi = float(np.clip(getattr(self, "hi", 1.0), -12.0, 12.0))
        enable = bool(getattr(self, "enable", True))
        script = bool(getattr(self, "script", True))
        return rate, depth, feedback, mix, center, stages, low, mid, hi, enable, script

    def _ensure_state(self, nch: int, stages: int, sr: int):
        if self._sr != sr or self._ap_x is None or self._ap_x.shape != (nch, stages):
            self._ap_x = np.zeros((nch, stages), dtype=np.float64)
            self._ap_y = np.zeros((nch, stages), dtype=np.float64)
            self._fb_z = np.zeros(nch, dtype=np.float64)
            self._tone_zi = np.zeros((nch, 3, 2), dtype=np.float64)
            self._sr = sr
            self._lfo_phase = 0.0

    def apply_effect(self, audio, sample_rate: int):
        x_in = np.asarray(audio)
        if x_in.size == 0:
            return x_in

        (
            rate, depth, feedback, mix, center, stages,
            low, mid, hi, enable, script,
        ) = self._clip_params()

        if not enable:
            return x_in

        x2d, was_1d = _as_2d(x_in)
        n, nch = x2d.shape
        sr = int(sample_rate) if sample_rate else 44100
        sr = max(sr, 8000)

        self._ensure_state(nch, stages, sr)

        alpha = 1.0 - np.exp(-1.0 / max(1.0, 0.010 * sr))
        for k, v in (
            ("rate", rate),
            ("depth", depth),
            ("feedback", feedback),
            ("mix", mix),
            ("center", center),
        ):
            self._smooth[k] += alpha * (v - self._smooth[k])
        rate = self._smooth["rate"]
        depth = self._smooth["depth"]
        feedback = self._smooth["feedback"]
        mix = self._smooth["mix"]
        center = self._smooth["center"]

        # Keep depth near full so the sweep always travels
        depth_amt = 0.15 + 0.85 * float(np.clip(depth, 0.0, 1.0))

        if script:
            f_lo, f_hi = 70.0, 4200.0
            fb_amt = min(0.94, 0.20 + feedback * 0.78)
        else:
            f_lo, f_hi = 110.0, 2800.0
            fb_amt = min(0.88, 0.12 + feedback * 0.72)

        cshift = 0.45 + 1.40 * center
        f_lo = float(np.clip(f_lo * cshift, 35.0, sr * 0.08))
        f_hi = float(np.clip(f_hi * cshift, f_lo * 8.0, sr * 0.44))

        t = np.arange(n, dtype=np.float64)
        phase = self._lfo_phase + 2.0 * np.pi * rate * t / sr
        self._lfo_phase = float((self._lfo_phase + 2.0 * np.pi * rate * n / sr) % (2.0 * np.pi))

        tri = 2.0 * np.abs(
            2.0 * (phase / (2.0 * np.pi) - np.floor(phase / (2.0 * np.pi) + 0.5))
        ) - 1.0
        sine = np.sin(phase)
        lfo = 0.88 * tri + 0.12 * sine
        sweep = 0.5 + 0.5 * lfo * depth_amt
        fc = f_lo * (f_hi / f_lo) ** sweep
        a_row = _allpass_coeff(fc, sr)

        dry = x2d.astype(np.float64, copy=False)
        wet = np.empty_like(dry)

        for ch in range(nch):
            d = dry[:, ch]
            xz = self._ap_x[ch]
            yz = self._ap_y[ch]
            fb = float(self._fb_z[ch])
            wch = wet[:, ch]
            for i in range(n):
                ai = a_row[i]
                s = d[i] + fb + 1e-20
                for st in range(stages):
                    xi = s
                    yi = ai * xi + xz[st] - ai * yz[st]
                    xz[st] = xi
                    yz[st] = yi
                    s = yi
                fb = s * fb_amt
                wch[i] = s
            self._fb_z[ch] = fb

        # Bias mix toward 50/50 so notches stay deep even if the knob is off a bit
        mix_eff = 0.5 + 0.5 * (mix - 0.5)
        mix_comp = 1.0 / np.sqrt((1.0 - mix_eff) ** 2 + mix_eff ** 2 + 1e-12)
        evh_boost = 10.0 ** (5.0 / 20.0)
        blended = ((1.0 - mix_eff) * dry - mix_eff * wet) * (mix_comp * evh_boost)

        out = np.empty_like(blended)
        ls = _rbj_lowshelf(low, 160.0, sr)
        pk = _rbj_peak(mid, 750.0, sr, q=0.80)
        hs = _rbj_highshelf(hi, 3500.0, sr)

        for ch in range(nch):
            y = blended[:, ch]
            for bi, c in enumerate((ls, pk, hs)):
                y, self._tone_zi[ch, bi] = _biquad(y, *c, self._tone_zi[ch, bi])
            out[:, ch] = y

        out = np.tanh(out * 1.10) / np.tanh(1.10)
        out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
        out = np.clip(out, -1.0, 1.0)

        if was_1d:
            out = out[:, 0]
        if x_in.dtype == np.float32:
            out = out.astype(np.float32)
        return out