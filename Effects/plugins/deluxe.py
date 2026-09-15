"""
Deluxe — Fender '65 Deluxe Reverb style host plugin.
Blackface panel, silver knobs, Normal / Vibrato channel paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

try:
    from scipy.signal import lfilter
except Exception:  # pragma: no cover
    lfilter = None


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
            outline="black", face="silver", needle="black"
        )
    )


@dataclass
class Switch:
    name: str = "Enable"
    default: bool = True


_KNOB_LOOK = KnobColorScheme(outline="black", face="silver", needle="black")
_CLICK_10 = [0.0, 2.0, 4.0, 5.0, 7.0, 10.0]
_CLICK_PHASE = [0.0, 45.0, 90.0, 135.0, 180.0]


def _clip(val: float, lo: float, hi: float) -> float:
    return float(np.clip(val, lo, hi))


def _as_2d(audio: np.ndarray) -> Tuple[np.ndarray, bool]:
    x = np.asarray(audio, dtype=np.float64)
    if x.size == 0:
        return x.reshape(0, 1) if x.ndim <= 1 else x, x.ndim == 1
    if x.ndim == 1:
        return x[:, None], True
    return x, False


def _rbj_lowshelf(gain_db: float, f0: float, sr: float, S: float = 0.9):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = (sinw / 2.0) * np.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
    sa = 2.0 * np.sqrt(A) * alpha
    b0 = A * ((A + 1.0) - (A - 1.0) * cosw + sa)
    b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cosw)
    b2 = A * ((A + 1.0) - (A - 1.0) * cosw - sa)
    a0 = (A + 1.0) + (A - 1.0) * cosw + sa
    a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cosw)
    a2 = (A + 1.0) + (A - 1.0) * cosw - sa
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _rbj_highshelf(gain_db: float, f0: float, sr: float, S: float = 0.9):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    cosw = np.cos(w0)
    sinw = np.sin(w0)
    alpha = (sinw / 2.0) * np.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
    sa = 2.0 * np.sqrt(A) * alpha
    b0 = A * ((A + 1.0) + (A - 1.0) * cosw + sa)
    b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cosw)
    b2 = A * ((A + 1.0) + (A - 1.0) * cosw - sa)
    a0 = (A + 1.0) - (A - 1.0) * cosw + sa
    a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cosw)
    a2 = (A + 1.0) - (A - 1.0) * cosw - sa
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _biquad_zi(n_ch: int) -> np.ndarray:
    return np.zeros((2, n_ch), dtype=np.float64)


def _lfilter_biquad(
    x: np.ndarray,
    coeffs: Tuple[float, float, float, float, float],
    zi: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    b0, b1, b2, a1, a2 = coeffs
    b = np.array([b0, b1, b2], dtype=np.float64)
    a = np.array([1.0, a1, a2], dtype=np.float64)
    if x.shape[0] == 0:
        return x, zi
    if lfilter is not None:
        y, zf = lfilter(b, a, x, axis=0, zi=zi)
        return y, zf

    # Direct Form II transpose fallback, per channel
    y = np.empty_like(x)
    z = zi.copy()
    for c in range(x.shape[1]):
        z0, z1 = z[0, c], z[1, c]
        col = x[:, c]
        out = np.empty_like(col)
        for i in range(col.shape[0]):
            xn = col[i]
            yn = b0 * xn + z0
            z0 = b1 * xn - a1 * yn + z1
            z1 = b2 * xn - a2 * yn
            out[i] = yn
        y[:, c] = out
        z[0, c], z[1, c] = z0, z1
    return y, z


def _knob_to_db(knob: float, span_db: float = 18.0) -> float:
    """Fender-style 0–10 knob: 5 is flat, 0/10 are ±span_db."""
    return (( _clip(knob, 0.0, 10.0) / 5.0) - 1.0) * span_db


class Deluxe:
    def __init__(self) -> None:
        self.name = "Deluxe"

        self.enable = True
        self.vibratochannel = True

        self.normalvolume = 4.0
        self.normaltreble = 5.0
        self.normalbass = 5.0

        self.vibratovolume = 4.0
        self.vibratotreble = 6.0
        self.vibratobass = 5.0

        self.reverb = 3.0
        self.speed = 4.0
        self.intensity = 0.0
        self.phase = 0.0

        self._sr = 44100
        self._lfo_phase = 0.0
        self._eq_zi_low = _biquad_zi(2)
        self._eq_zi_high = _biquad_zi(2)
        self._comb = [np.zeros(1) for _ in range(4)]
        self._comb_idx = [0, 0, 0, 0]
        self._ap = [np.zeros(1) for _ in range(3)]
        self._ap_idx = [0, 0, 0]
        self._pre = np.zeros(1)
        self._pre_idx = 0

    def get_name(self) -> str:
        return "Deluxe"

    def get_colors(self) -> dict[str, str]:
        return {
            "face": "#0a0a0a",
            "edge": "#000000",
            "text": "#ffffff",
            "muted": "#b0b0b0",
            "button": "#1a1a1a",
            "button_hot": "#2a2a2a",
            "button_on": "#8b0000",
            "button_text": "#ffffff",
            "switch_on": "#c41e3a",
            "switch_off": "#1a1a1a",
            "slider": "#111111",
            "slider_handle": "#c0c0c0",
            "knob_outline": "#000000",
            "knob_face": "#c0c0c0",
            "knob_needle": "#000000",
        }

    def get_knobs(self) -> List[Knob]:
        def k(name: str, default: float, lo: float = 0.0, hi: float = 10.0, clicks=None) -> Knob:
            return Knob(
                name=name,
                min=lo,
                max=hi,
                default=default,
                click_pts=list(clicks if clicks is not None else _CLICK_10),
                knob_color_scheme=_KNOB_LOOK,
            )

        return [
            k("Normal Volume", 4.0),
            k("Normal Treble", 5.0),
            k("Normal Bass", 5.0),
            k("Vibrato Volume", 4.0),
            k("Vibrato Treble", 6.0),
            k("Vibrato Bass", 5.0),
            k("Reverb", 3.0),
            k("Speed", 4.0),
            k("Intensity", 0.0),
            k("Phase", 0.0, 0.0, 180.0, _CLICK_PHASE),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch(name="Enable", default=True),
            Switch(name="Vibrato Channel", default=True),
        ]

    def _ensure_state(self, n_ch: int, sr: int) -> None:
        if self._eq_zi_low.shape[1] != n_ch:
            self._eq_zi_low = _biquad_zi(n_ch)
            self._eq_zi_high = _biquad_zi(n_ch)

        if self._sr != sr or self._comb[0].ndim < 2 or self._comb[0].shape[0] < 2:
            self._sr = int(sr)
            scale = sr / 44100.0
            comb_n = [int(1553 * scale), int(1613 * scale), int(1493 * scale), int(1429 * scale)]
            ap_n = [int(223 * scale), int(557 * scale), int(443 * scale)]
            pre_n = max(1, int(0.018 * sr))
            self._comb = [np.zeros((max(8, n), n_ch)) for n in comb_n]
            self._comb_idx = [0] * 4
            self._ap = [np.zeros((max(8, n), n_ch)) for n in ap_n]
            self._ap_idx = [0] * 3
            self._pre = np.zeros((pre_n, n_ch))
            self._pre_idx = 0
            return

        if self._comb[0].shape[1] != n_ch:
            for i, buf in enumerate(self._comb):
                self._comb[i] = np.zeros((buf.shape[0], n_ch))
            for i, buf in enumerate(self._ap):
                self._ap[i] = np.zeros((buf.shape[0], n_ch))
            self._pre = np.zeros((self._pre.shape[0], n_ch))
            self._comb_idx = [0] * 4
            self._ap_idx = [0] * 3
            self._pre_idx = 0

    def _tone(self, x: np.ndarray, bass: float, treble: float, bright: bool) -> np.ndarray:
        if x.shape[0] == 0:
            return x

        sr = float(self._sr)
        bass_db = _knob_to_db(bass, 18.0)
        treble_db = _knob_to_db(treble, 18.0)
        if bright:
            # Vibrato channel is the brighter blackface path
            treble_db += 3.0

        bass_f = 180.0
        treble_f = 2800.0 if bright else 3500.0

        low_c = _rbj_lowshelf(bass_db, bass_f, sr)
        high_c = _rbj_highshelf(treble_db, treble_f, sr)

        y, self._eq_zi_low = _lfilter_biquad(x, low_c, self._eq_zi_low)
        y, self._eq_zi_high = _lfilter_biquad(y, high_c, self._eq_zi_high)

        # Mild constant mid scoop so the two knobs feel like a Deluxe stack
        y *= 0.96
        y = np.tanh(y * 1.12) / np.tanh(1.12)
        return y

    def _volume(self, x: np.ndarray, knob: float, extra_db: float = 0.0) -> np.ndarray:
        v = _clip(knob, 0.0, 10.0) / 10.0
        gain = (v ** 1.35) * (10.0 ** (extra_db / 20.0)) * 1.55
        return x * gain

    def _delay_read_write(self, buf: np.ndarray, idx: int, x_n: np.ndarray, fb: float):
        y = buf[idx].copy()
        buf[idx] = x_n + y * fb
        return y, (idx + 1) % buf.shape[0]

    def _reverb(self, x: np.ndarray, amount: float) -> np.ndarray:
        n, ch = x.shape
        if n == 0 or amount <= 1e-6:
            return np.zeros_like(x)

        wet = np.zeros_like(x)
        decay = 0.62 + 0.28 * min(amount, 1.0)
        damp = 0.28
        g_ap = 0.6

        for i in range(n):
            s = x[i]
            pre_out = self._pre[self._pre_idx].copy()
            self._pre[self._pre_idx] = s
            self._pre_idx = (self._pre_idx + 1) % self._pre.shape[0]

            acc = np.zeros(ch)
            for c_i in range(4):
                y, self._comb_idx[c_i] = self._delay_read_write(
                    self._comb[c_i], self._comb_idx[c_i], pre_out, decay * (0.96 - 0.04 * c_i)
                )
                acc += y * (1.0 - damp)
            acc *= 0.25

            for a_i in range(3):
                buf = self._ap[a_i]
                idx = self._ap_idx[a_i]
                buf_y = buf[idx]
                ap_in = acc + buf_y * g_ap
                out = buf_y - ap_in * g_ap
                buf[idx] = ap_in
                self._ap_idx[a_i] = (idx + 1) % buf.shape[0]
                acc = out

            wet[i] = acc

        wet = wet - 0.15 * np.roll(wet, 1, axis=0)
        mix = amount * amount * 0.85
        return wet * mix

    def _tremolo(
        self,
        x: np.ndarray,
        speed: float,
        intensity: float,
        phase_deg: float,
        sr: int,
    ) -> np.ndarray:
        if intensity <= 1e-6 or x.shape[0] == 0:
            return x
        hz = 0.55 + (speed / 10.0) ** 1.15 * 11.2
        n = x.shape[0]
        offset = np.deg2rad(_clip(phase_deg, 0.0, 180.0))
        phase = self._lfo_phase + offset + 2.0 * np.pi * hz * np.arange(n) / float(sr)
        lfo = 0.5 * (1.0 + np.sin(phase))
        lfo = lfo ** 1.15
        depth = _clip(intensity / 10.0, 0.0, 1.0)
        gain = 1.0 - depth * (1.0 - lfo)
        self._lfo_phase = float(
            (self._lfo_phase + 2.0 * np.pi * hz * n / float(sr)) % (2.0 * np.pi)
        )
        return x * gain[:, None]

    def apply_effect(self, audio, sample_rate: int):
        raw = np.asarray(audio)
        if raw.size == 0:
            return raw

        if not bool(getattr(self, "enable", True)):
            return raw

        x, was_1d = _as_2d(raw)
        sr = int(sample_rate) if sample_rate else 44100
        self._ensure_state(x.shape[1], sr)

        if bool(getattr(self, "vibratochannel", True)):
            vol = _clip(getattr(self, "vibratovolume", 4.0), 0.0, 10.0)
            tre = _clip(getattr(self, "vibratotreble", 6.0), 0.0, 10.0)
            bas = _clip(getattr(self, "vibratobass", 5.0), 0.0, 10.0)
            rev = _clip(getattr(self, "reverb", 3.0), 0.0, 10.0) / 10.0
            spd = _clip(getattr(self, "speed", 4.0), 0.0, 10.0)
            inten = _clip(getattr(self, "intensity", 0.0), 0.0, 10.0)
            phase = _clip(getattr(self, "phase", 0.0), 0.0, 180.0)
            y = self._volume(x, vol, extra_db=2.5)
            y = self._tone(y, bas, tre, bright=True)
            if rev > 0.0:
                y = y + self._reverb(y, rev)
            y = self._tremolo(y, spd, inten, phase, sr)
        else:
            vol = _clip(getattr(self, "normalvolume", 4.0), 0.0, 10.0)
            tre = _clip(getattr(self, "normaltreble", 5.0), 0.0, 10.0)
            bas = _clip(getattr(self, "normalbass", 5.0), 0.0, 10.0)
            y = self._volume(x, vol, extra_db=0.0)
            y = self._tone(y, bas, tre, bright=False)

        y = np.clip(y, -1.0, 1.0)
        if was_1d:
            y = y[:, 0]
        if raw.dtype == np.float32:
            return y.astype(np.float32)
        return y.astype(np.float64)