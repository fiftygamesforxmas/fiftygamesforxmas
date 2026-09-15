"""
Fuzz — Fuzz Face style plugin.
Discovered automatically by host.py because it exposes get_name / get_knobs /
get_switches / apply_effect.
"""

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


class Fuzz:
    """
    Two-transistor Fuzz Face style fuzz.

    Host-written members (from knob / switch names, lowercased):
        fuzz, volume, bias, input
        enable, germanium
    """

    def __init__(self):
        self.name = "Fuzz"

        # live parameters — GUI writes these before apply_effect()
        self.fuzz = 0.85
        self.volume = 0.70
        self.bias = 0.55
        self.input = 1.0
        self.enable = True
        self.germanium = True

        # per-channel filter state: [hp, lp1, lp2]
        self._state = None
        self._last_sr = None
        self._last_channels = None

    def get_name(self) -> str:
        return self.name

    def get_colors(self):
            return {
                "face": "#3a2a18",
                "edge": "#222222",
                "text": "#f0e6d0",
                "muted": "#c4b48a",
                "button": "#5a4030",
                "button_hot": "#7a5840",
                "button_on": "#2e6b3a",
                "button_text": "#f0e6d0",
                "switch_on": "#2e6b3a",
                "switch_off": "#222222",
                "slider": "#2a2018",
                "slider_handle": "#c4b48a",
                "knob_outline": "#222222",
                "knob_face": "#c4b48a",
                "knob_needle": "#1a1a1a",
            }
    
    def get_knobs(self) -> List[Knob]:
        silver = KnobColorScheme(outline="#222222", face="#c9c9c9", needle="#111111")
        cream = KnobColorScheme(outline="#3a2a12", face="#e8d9b0", needle="#5a1a1a")
        rust = KnobColorScheme(outline="#2b1208", face="#8b3a1e", needle="#1a0a04")
        olive = KnobColorScheme(outline="#1c2414", face="#6e7a4a", needle="#101408")
        return [
            Knob(
                name="Fuzz",
                min=0.0,
                max=1.0,
                default=0.85,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=rust,
            ),
            Knob(
                name="Volume",
                min=0.0,
                max=1.0,
                default=0.70,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=cream,
            ),
            Knob(
                name="Bias",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.25, 0.5, 0.55, 0.65, 0.75],
                knob_color_scheme=olive,
            ),
            Knob(
                name="Input",
                min=0.0,
                max=1.0,
                default=1.0,
                click_pts=[0.0, 0.4, 0.7, 1.0],
                knob_color_scheme=silver,
            ),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch(name="Enable", default=True),
            Switch(name="Germanium", default=True),
        ]

    @staticmethod
    def _audio_taper(x: float) -> float:
        x = float(np.clip(x, 0.0, 1.0))
        return (10.0 ** (x * 1.5) - 1.0) / (10.0 ** 1.5 - 1.0)

    @staticmethod
    def _asym_sat(x, pos_lim, neg_lim, softness):
        xp = np.maximum(x, 0.0)
        xn = np.minimum(x, 0.0)
        yp = pos_lim * np.tanh(xp / (pos_lim * softness + 1e-12))
        yn = -neg_lim * np.tanh((-xn) / (neg_lim * softness + 1e-12))
        return yp + yn

    def _ensure_state(self, channels: int, sample_rate: int):
        if (
            self._state is None
            or self._last_channels != channels
            or self._last_sr != sample_rate
        ):
            self._state = np.zeros((channels, 3), dtype=np.float64)
            self._last_channels = channels
            self._last_sr = sample_rate

    def _process_mono(self, x: np.ndarray, sample_rate: int, ch: int) -> np.ndarray:
        sr = float(sample_rate)
        germanium = bool(getattr(self, "germanium", True))
        fuzz = float(np.clip(getattr(self, "fuzz", 0.85), 0.0, 1.0))
        volume = float(np.clip(getattr(self, "volume", 0.70), 0.0, 1.0))
        bias = float(np.clip(getattr(self, "bias", 0.55), 0.0, 1.0))
        guitar_vol = float(np.clip(getattr(self, "input", 1.0), 0.0, 1.0))

        xin = x.astype(np.float64, copy=False) * (guitar_vol ** 1.6)

        hp_hz = 90.0 if germanium else 140.0
        lp1_hz = 4200.0 if germanium else 7200.0
        lp2_hz = 2800.0 if germanium else 4500.0
        a_hp = np.exp(-2.0 * np.pi * hp_hz / sr)
        a1 = np.exp(-2.0 * np.pi * lp1_hz / sr)
        a2 = np.exp(-2.0 * np.pi * lp2_hz / sr)

        drive = 18.0 + 70.0 * (fuzz ** 1.35)
        offset = (0.55 - bias) * (0.35 if germanium else 0.22)
        pos_lim = 0.55 + 0.35 * bias
        neg_lim = 0.95 - 0.40 * bias
        softness = 0.85 if germanium else 0.38
        out_gain = 0.15 + 1.35 * self._audio_taper(volume)

        hp, s1, s2 = self._state[ch]
        y = np.empty_like(xin)

        for i, sample in enumerate(xin):
            hp = a_hp * hp + (1.0 - a_hp) * sample
            hped = sample - hp

            s1 = a1 * s1 + (1.0 - a1) * hped
            st1 = self._asym_sat(s1 * (3.2 + 4.0 * fuzz), 0.9, 0.7, softness + 0.25)

            driven = st1 * drive + offset
            fuzzed = self._asym_sat(driven, pos_lim, neg_lim, softness)
            fuzzed *= 1.0 - 0.08 * np.tanh(abs(driven) * 0.15)

            s2 = a2 * s2 + (1.0 - a2) * fuzzed
            y[i] = s2 * out_gain

        self._state[ch] = (hp, s1, s2)
        return np.clip(y, -1.5, 1.5).astype(np.float32)

    def apply_effect(self, audio, sample_rate: int):
        """
        audio: float32 array in [-1, 1], shape (n,) or (n, channels)
        Uses members set by the host rather than a long argument list.
        """
        if not getattr(self, "enable", True):
            return audio

        x = np.asarray(audio)
        if x.ndim == 1:
            self._ensure_state(1, sample_rate)
            return self._process_mono(x, sample_rate, 0)

        if x.ndim == 2:
            n, ch = x.shape
            self._ensure_state(ch, sample_rate)
            out = np.empty_like(x, dtype=np.float32)
            for c in range(ch):
                out[:, c] = self._process_mono(x[:, c], sample_rate, c)
            return out

        raise ValueError("audio must be shape (n,) or (n, channels)")

