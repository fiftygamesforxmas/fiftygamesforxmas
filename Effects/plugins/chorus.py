# chorus.py
"""Danelectro FAB-style analog chorus plugin."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

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
        default_factory=lambda: KnobColorScheme(outline="black", face="white", needle="black")
    )


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


_KNOB_SCHEME = KnobColorScheme(
    outline="#000000",
    face="#F5D400",
    needle="#111111",
)


class Chorus:
    """Two-voice analog-style chorus: Mix, Speed, Depth."""

    def __init__(self):
        self.name = "Chorus"
        self.enable = True
        self.mix = 0.65
        self.speed = 0.45
        self.depth = 0.55

        self._phase1 = 0.0
        self._phase2 = 0.0
        self._buf_l = None
        self._buf_r = None
        self._w = 0
        self._sr = 0
        self._max_delay = 0

    def get_name(self) -> str:
        return "Chorus"

    def get_colors(self):
        return {
            "face": "#4EC8F5",
            "edge": "#0A2A3A",
            "text": "#FFE44D",
            "muted": "#0E3A4A",
            "button": "#0E2C38",
            "button_hot": "#16485C",
            "button_on": "#FFE44D",
            "button_text": "#0A2A3A",
            "switch_on": "#FFE44D",
            "switch_off": "#123844",
            "slider": "#0A2A3A",
            "slider_handle": "#FFE44D",
            "knob_outline": "#000000",
            "knob_face": "#F5D400",
            "knob_needle": "#111111",
        }

    def get_knobs(self) -> List[Knob]:
        return [
            Knob(
                name="Mix",
                min=0.0,
                max=1.0,
                default=0.65,
                click_pts=[0.0, 0.25, 0.5, 0.65, 0.85, 1.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
            Knob(
                name="Speed",
                min=0.05,
                max=8.0,
                default=0.45,
                click_pts=[0.15, 0.3, 0.45, 0.8, 1.5, 3.0, 6.0, 8.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
            Knob(
                name="Depth",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.0, 0.2, 0.4, 0.55, 0.75, 1.0],
                knob_color_scheme=_KNOB_SCHEME,
            ),
        ]

    def get_switches(self) -> List[Switch]:
        return [Switch(name="Enable", default=True)]

    def _ensure_state(self, sample_rate: int, channels: int):
        sr = int(sample_rate)
        # ~40 ms max delay covers base + modulation
        max_delay = max(64, int(0.045 * sr) + 8)
        if (
            self._buf_l is None
            or self._sr != sr
            or self._max_delay != max_delay
            or self._buf_l.ndim != 2
            or self._buf_l.shape[1] != channels
        ):
            self._buf_l = np.zeros((max_delay, channels), dtype=np.float64)
            self._buf_r = np.zeros((max_delay, channels), dtype=np.float64)
            self._w = 0
            self._sr = sr
            self._max_delay = max_delay

    def apply_effect(self, audio, sample_rate: int):
        x = np.asarray(audio)
        if x.size == 0:
            return x

        enable = bool(getattr(self, "enable", True))
        if not enable:
            return x

        mix = float(np.clip(getattr(self, "mix", 0.65), 0.0, 1.0))
        speed = float(np.clip(getattr(self, "speed", 0.45), 0.05, 8.0))
        depth = float(np.clip(getattr(self, "depth", 0.55), 0.0, 1.0))

        # FAB-like taper: subtle until the last stretch of the knobs
        depth_eff = depth ** 1.6
        speed_eff = 0.08 + (speed - 0.05) / (8.0 - 0.05) * 7.2
        speed_eff = speed_eff ** 1.25

        mono = x.ndim == 1
        if mono:
            work = x.astype(np.float64, copy=False)[:, None]
        else:
            work = x.astype(np.float64, copy=False)

        n, ch = work.shape
        sr = int(sample_rate)
        self._ensure_state(sr, ch)

        buf_l = self._buf_l
        buf_r = self._buf_r
        w = self._w
        maxd = self._max_delay

        base_ms = 18.0
        mod_ms = 0.4 + 11.5 * depth_eff
        base_samp = base_ms * 0.001 * sr
        mod_samp = mod_ms * 0.001 * sr

        t = np.arange(n, dtype=np.float64)
        w1 = 2.0 * np.pi * speed_eff / sr
        w2 = 2.0 * np.pi * (speed_eff * 0.97) / sr
        lfo1 = np.sin(self._phase1 + w1 * t)
        lfo2 = np.sin(self._phase2 + w2 * t + 2.0943951023931953)  # ~120 deg
        self._phase1 = (self._phase1 + w1 * n) % (2.0 * np.pi)
        self._phase2 = (self._phase2 + w2 * n) % (2.0 * np.pi)

        d1 = base_samp + mod_samp * lfo1
        d2 = (base_samp + 4.0) + mod_samp * 0.82 * lfo2
        d1 = np.clip(d1, 1.01, maxd - 2.01)
        d2 = np.clip(d2, 1.01, maxd - 2.01)

        wet = np.empty_like(work)
        idx = np.arange(maxd)

        # mild one-pole BBD-ish darkening on wet voices
        lp_a = np.exp(-2.0 * np.pi * 5200.0 / sr)
        s1 = np.zeros(ch, dtype=np.float64)
        s2 = np.zeros(ch, dtype=np.float64)

        for i in range(n):
            buf_l[w] = work[i]
            buf_r[w] = work[i]

            f1 = d1[i]
            f2 = d2[i]
            i1 = int(f1)
            i2 = int(f2)
            frac1 = f1 - i1
            frac2 = f2 - i2
            r1 = (w - i1) % maxd
            r1n = (r1 - 1) % maxd
            r2 = (w - i2) % maxd
            r2n = (r2 - 1) % maxd

            v1 = buf_l[r1] * (1.0 - frac1) + buf_l[r1n] * frac1
            v2 = buf_r[r2] * (1.0 - frac2) + buf_r[r2n] * frac2
            s1 = lp_a * s1 + (1.0 - lp_a) * v1
            s2 = lp_a * s2 + (1.0 - lp_a) * v2
            wet[i] = 0.55 * s1 + 0.45 * s2
            w = (w + 1) % maxd

        self._w = w

        # Mix: 0 = dry, 1 = wet only (matches FAB manual)
        y = (1.0 - mix) * work + mix * wet
        # slight makeup so wet isn't quieter
        y *= 1.0 + 0.08 * mix
        y = np.clip(y, -1.0, 1.0)

        if mono:
            y = y[:, 0]
        if np.issubdtype(x.dtype, np.floating) and x.dtype != np.float64:
            y = y.astype(x.dtype, copy=False)
        return y