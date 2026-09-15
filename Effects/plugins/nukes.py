"""Nukes — high-quality rotary / Leslie-style plugin (NUX Roctary inspired).

Drop-in host plugin. Requires numpy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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
            outline="#f4efe6", face="#6b3a1f", needle="#ffffff"
        )
    )


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


_KNOB_SCHEME = KnobColorScheme(outline="#f4efe6", face="#6b3a1f", needle="#ffffff")


def _to_2d(audio: np.ndarray) -> Tuple[np.ndarray, bool]:
    x = np.asarray(audio)
    if x.size == 0:
        return x.reshape(0, 1).astype(np.float64, copy=False), False
    if x.ndim == 1:
        return x.reshape(-1, 1).astype(np.float64, copy=False), True
    return x.astype(np.float64, copy=False), False


def _soft_clip(x: np.ndarray, drive: float) -> np.ndarray:
    g = 1.0 + 8.0 * max(0.0, drive)
    y = np.tanh(x * g)
    return y / np.tanh(g) if g > 1e-9 else y


def _onepole_lp(x: np.ndarray, coeff: float, state: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    y = np.empty_like(x)
    s = state.copy()
    a = float(np.clip(coeff, 0.0, 0.9995))
    b = 1.0 - a
    for i in range(x.shape[0]):
        s = a * s + b * x[i]
        y[i] = s
    return y, s


def _onepole_hp(x: np.ndarray, lp: np.ndarray) -> np.ndarray:
    return x - lp


class Nukes:
    def __init__(self) -> None:
        self.name = "Nukes"
        self.enable = True
        self.level = 0.72
        self.slow = 0.45
        self.fast = 6.8
        self.horn = 0.62
        self.balance = 1.0
        self.drive = 0.18
        self.rise = 0.45
        self.octup = 0.0
        self.octdn = 0.0
        self.fastmode = False
        self.brake = False
        self.octave = False
        self.leslie = True

        self._phase_horn = 0.0
        self._phase_drum = 0.0
        self._speed_horn = 0.8
        self._speed_drum = 0.4
        self._lp_state = None
        self._oct_buf = None
        self._oct_w = 0
        self._oct_r_up = 0.0
        self._oct_r_dn = 0.0
        self._sr_cache = 0

    def get_name(self) -> str:
        return "Nukes"

    def get_colors(self) -> dict:
        return {
            "face": "#5c3317",
            "edge": "#2a160c",
            "text": "#ffffff",
            "muted": "#d4b896",
            "button": "#3d2414",
            "button_hot": "#7a4a28",
            "button_on": "#c4782a",
            "button_text": "#ffffff",
            "switch_on": "#e8c36a",
            "switch_off": "#2a160c",
            "slider": "#2a160c",
            "slider_handle": "#f4efe6",
            "knob_outline": "#f4efe6",
            "knob_face": "#6b3a1f",
            "knob_needle": "#ffffff",
        }

    def get_knobs(self) -> List[Knob]:
        return [
            Knob("Level", 0.0, 1.5, 0.72, [0.0, 0.5, 0.72, 1.0, 1.5], _KNOB_SCHEME),
            Knob("Slow", 0.15, 1.6, 0.45, [0.2, 0.35, 0.45, 0.7, 1.0, 1.6], _KNOB_SCHEME),
            Knob("Fast", 3.0, 9.5, 6.8, [3.5, 5.0, 6.8, 8.0, 9.5], _KNOB_SCHEME),
            Knob("Horn", 0.0, 1.0, 0.62, [0.0, 0.25, 0.5, 0.62, 0.8, 1.0], _KNOB_SCHEME),
            Knob("Balance", 0.0, 1.0, 1.0, [0.0, 0.25, 0.5, 0.75, 1.0], _KNOB_SCHEME),
            Knob("Drive", 0.0, 1.0, 0.18, [0.0, 0.1, 0.18, 0.4, 0.7, 1.0], _KNOB_SCHEME),
            Knob("Rise", 0.05, 1.0, 0.45, [0.05, 0.2, 0.45, 0.7, 1.0], _KNOB_SCHEME),
            Knob("Octup", 0.0, 1.0, 0.0, [0.0, 0.25, 0.5, 0.75, 1.0], _KNOB_SCHEME),
            Knob("Octdn", 0.0, 1.0, 0.0, [0.0, 0.25, 0.5, 0.75, 1.0], _KNOB_SCHEME),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch("Enable", True),
            Switch("Fastmode", False),
            Switch("Brake", False),
            Switch("Octave", False),
            Switch("Leslie", True),
        ]

    def _clip_param(self, name: str, default: float, lo: float, hi: float) -> float:
        v = float(getattr(self, name, default))
        if not np.isfinite(v):
            v = default
        return float(np.clip(v, lo, hi))

    def _ensure_state(self, n_ch: int, sr: int) -> None:
        if self._lp_state is None or self._lp_state.shape[0] != n_ch or self._sr_cache != sr:
            self._lp_state = np.zeros(n_ch, dtype=np.float64)
            self._oct_buf = np.zeros((int(sr * 0.08) + 8, n_ch), dtype=np.float64)
            self._oct_w = 0
            self._oct_r_up = 0.0
            self._oct_r_dn = 0.0
            self._sr_cache = sr

    def _octaves(self, x: np.ndarray) -> np.ndarray:
        buf = self._oct_buf
        n, ch = x.shape
        nbuf = buf.shape[0]
        out_up = np.empty_like(x)
        out_dn = np.empty_like(x)
        w = self._oct_w
        ru = self._oct_r_up
        rd = self._oct_r_dn
        for i in range(n):
            buf[w] = x[i]
            w = (w + 1) % nbuf
            i0 = int(ru) % nbuf
            i1 = (i0 + 1) % nbuf
            f = ru - int(ru)
            out_up[i] = buf[i0] * (1.0 - f) + buf[i1] * f
            ru = (ru + 2.0) % nbuf
            j0 = int(rd) % nbuf
            j1 = (j0 + 1) % nbuf
            g = rd - int(rd)
            out_dn[i] = buf[j0] * (1.0 - g) + buf[j1] * g
            rd = (rd + 0.5) % nbuf
        self._oct_w = w
        self._oct_r_up = ru
        self._oct_r_dn = rd
        return out_up, out_dn

    def apply_effect(self, audio, sample_rate: int):
        raw = np.asarray(audio)
        if raw.size == 0:
            return raw.copy() if isinstance(audio, np.ndarray) else np.asarray(audio)

        enable = bool(getattr(self, "enable", True))
        if not enable:
            return raw.copy()

        sr = int(sample_rate) if sample_rate and sample_rate > 0 else 44100
        x, was_1d = _to_2d(raw)
        n, ch = x.shape
        self._ensure_state(ch, sr)

        level = self._clip_param("level", 0.72, 0.0, 1.5)
        slow = self._clip_param("slow", 0.45, 0.15, 1.6)
        fast = self._clip_param("fast", 6.8, 3.0, 9.5)
        horn_mix = self._clip_param("horn", 0.62, 0.0, 1.0)
        balance = self._clip_param("balance", 1.0, 0.0, 1.0)
        drive = self._clip_param("drive", 0.18, 0.0, 1.0)
        rise = self._clip_param("rise", 0.45, 0.05, 1.0)
        octup = self._clip_param("octup", 0.0, 0.0, 1.0)
        octdn = self._clip_param("octdn", 0.0, 0.0, 1.0)
        fastmode = bool(getattr(self, "fastmode", False))
        brake = bool(getattr(self, "brake", False))
        octave_on = bool(getattr(self, "octave", False))
        leslie = bool(getattr(self, "leslie", True))

        dry = x.copy()
        if octave_on and (octup > 1e-6 or octdn > 1e-6):
            up, dn = self._octaves(x)
            x = x * (1.0 - 0.45 * (octup + octdn) * 0.5) + up * octup * 0.55 + dn * octdn * 0.7

        x = _soft_clip(x, drive)

        # ~800 Hz crossover
        fc = 800.0
        coeff = np.exp(-2.0 * np.pi * fc / sr)
        bass, self._lp_state = _onepole_lp(x, coeff, self._lp_state)
        treble = _onepole_hp(x, bass)

        target_h = 0.0 if brake else (fast if fastmode else slow)
        # drum rotor ~ 0.75 of horn (classic Leslie ratio-ish)
        target_d = target_h * 0.72
        # rise: seconds to approach target; low rise = slower ramp
        tau = 0.12 + (1.0 - rise) * 2.8
        alpha = 1.0 - np.exp(-1.0 / max(1.0, tau * sr))

        ph = self._phase_horn
        pd = self._phase_drum
        sh = self._speed_horn
        sd = self._speed_drum

        out = np.empty_like(x)
        two_pi = 2.0 * np.pi
        doppler_h = 0.0045 if leslie else 0.0018
        doppler_d = 0.0030 if leslie else 0.0012
        am_h = 0.55 if leslie else 0.28
        am_d = 0.38 if leslie else 0.22
        stereo = ch > 1

        # cheap 1-sample doppler via phase-modulated allpass-ish mix
        for i in range(n):
            sh += (target_h - sh) * alpha
            sd += (target_d - sd) * alpha
            ph = (ph + two_pi * sh / sr) % two_pi
            pd = (pd + two_pi * sd / sr) % two_pi
            ch_h = np.cos(ph)
            ch_d = np.cos(pd)
            # amplitude + mild spectral tilt via doppler proxy
            horn_g = 1.0 + am_h * ch_h
            drum_g = 1.0 + am_d * ch_d
            horn = treble[i] * horn_g * (1.0 + doppler_h * np.sin(ph) * 40.0)
            drum = bass[i] * drum_g * (1.0 + doppler_d * np.sin(pd) * 28.0)
            wet = drum * (1.0 - horn_mix) + horn * horn_mix
            if stereo:
                # opposite mic for L/R
                pan_h = 0.5 + 0.5 * np.sin(ph)
                pan_d = 0.5 + 0.5 * np.sin(pd + 0.35)
                l = drum[0] * (1.0 - horn_mix) * (1.0 - pan_d) + horn[0] * horn_mix * (1.0 - pan_h)
                r_src = wet[min(1, ch - 1)]
                r = drum[min(1, ch - 1)] * (1.0 - horn_mix) * pan_d + horn[min(1, ch - 1)] * horn_mix * pan_h
                # write per channel from wet vector
                wet_ch = wet.copy()
                wet_ch[0] = l
                if ch > 1:
                    wet_ch[1] = r if ch > 1 else r_src
                wet = wet_ch
            out[i] = wet

        self._phase_horn = ph
        self._phase_drum = pd
        self._speed_horn = sh
        self._speed_drum = sd

        y = dry * (1.0 - balance) + out * balance
        y *= level
        y = np.clip(y, -1.2, 1.2)
        if was_1d:
            y = y[:, 0]
        if raw.dtype == np.float32:
            return y.astype(np.float32)
        return y.astype(np.float64)