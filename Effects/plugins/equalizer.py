"""the_equalizer.py — 10-band graphic EQ plugin for host.py"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

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


try:
    from scipy.signal import sosfilt, sosfilt_zi
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


# name is the UI label AND the live attribute source (must be a valid identifier after
# strip/lower/remove-spaces — do NOT start with a digit)
_BANDS: List[Tuple[str, float]] = [
    ("Hz31", 31.0),
    ("Hz62", 62.0),
    ("Hz125", 125.0),
    ("Hz250", 250.0),
    ("Hz500", 500.0),
    ("Hz1k", 1000.0),
    ("Hz2k", 2000.0),
    ("Hz4k", 4000.0),
    ("Hz8k", 8000.0),
    ("Hz16k", 16000.0),
]

_KNOB_SCHEME = KnobColorScheme(outline="black", face="silver", needle="black")

_GAIN_MIN = -12.0
_GAIN_MAX = 12.0
_GAIN_DEFAULT = 0.0
_GAIN_CLICKS = [-12.0, -6.0, -3.0, 0.0, 3.0, 6.0, 12.0]
_Q = 2.0


def _key(label: str) -> str:
    return label.strip().lower().replace(" ", "").replace("-", "")


def _peaking_sos(fc: float, gain_db: float, q: float, sr: int) -> np.ndarray:
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * (fc / float(sr))
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / A
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def _biquad_filt(sos: np.ndarray, x: np.ndarray, zi: Optional[np.ndarray] = None):
    b0, b1, b2, _, a1, a2 = sos[0]
    n = x.shape[0]
    y = np.empty(n, dtype=np.float64)
    if zi is None:
        w1 = 0.0
        w2 = 0.0
    else:
        w1 = float(zi[0])
        w2 = float(zi[1])
    for i in range(n):
        w = x[i] - a1 * w1 - a2 * w2
        y[i] = b0 * w + b1 * w1 + b2 * w2
        w2 = w1
        w1 = w
    return y, np.array([w1, w2], dtype=np.float64)


class TheEqualizer:
    def __init__(self) -> None:
        self.name = "Equalizer"
        self.enable = True
        for label, _fc in _BANDS:
            setattr(self, _key(label), float(_GAIN_DEFAULT))

        self._cache_key: Optional[tuple] = None
        self._sos_list: List[np.ndarray] = []
        self._zi: Dict[Tuple[int, int], np.ndarray] = {}

    def get_name(self) -> str:
        return "Equalizer"

    def get_colors(self) -> dict:
        return {
            "face": "#FFD400",
            "edge": "#111111",
            "text": "#111111",
            "muted": "#5a5a5a",
            "button": "#222222",
            "button_hot": "#333333",
            "button_on": "#111111",
            "button_text": "#FFD400",
            "switch_on": "#111111",
            "switch_off": "#888888",
            "slider": "#222222",
            "slider_handle": "#C0C0C0",
            "knob_outline": "black",
            "knob_face": "silver",
            "knob_needle": "black",
        }

    def get_knobs(self) -> List[Knob]:
        return [
            Knob(
                name=label,
                min=_GAIN_MIN,
                max=_GAIN_MAX,
                default=_GAIN_DEFAULT,
                click_pts=list(_GAIN_CLICKS),
                knob_color_scheme=_KNOB_SCHEME,
            )
            for label, _fc in _BANDS
        ]

    def get_switches(self) -> List[Switch]:
        return [Switch(name="Enable", default=True)]

    def _read_gain(self, label: str) -> float:
        keys = (
            _key(label),
            label,
            label.strip(),
            label.strip().lower(),
            label.strip().lower().replace(" ", "_"),
            label.strip().lower().replace(" ", ""),
        )
        for k in keys:
            if k in self.__dict__:
                try:
                    return float(np.clip(float(self.__dict__[k]), _GAIN_MIN, _GAIN_MAX))
                except (TypeError, ValueError):
                    continue
            if hasattr(self, k):
                try:
                    return float(np.clip(float(getattr(self, k)), _GAIN_MIN, _GAIN_MAX))
                except (TypeError, ValueError):
                    continue
        return _GAIN_DEFAULT

    def _gains(self) -> List[float]:
        return [self._read_gain(label) for label, _fc in _BANDS]

    def _rebuild(self, sample_rate: int, gains: List[float]) -> None:
        key = (int(sample_rate), tuple(round(g, 4) for g in gains))
        if key == self._cache_key:
            return
        nyq = 0.45 * float(sample_rate)
        sos_list: List[np.ndarray] = []
        for (_label, fc), g in zip(_BANDS, gains):
            if abs(g) < 0.05:
                continue
            f = min(float(fc), nyq)
            if f < 20.0:
                continue
            sos_list.append(_peaking_sos(f, g, _Q, sample_rate))
        self._sos_list = sos_list
        self._cache_key = key
        self._zi = {}

    def apply_effect(self, audio, sample_rate: int):
        if audio is None:
            return np.zeros(0, dtype=np.float32)

        x = np.asarray(audio)
        print(audio)
        if x.size == 0:
            return x

        enable = getattr(self, "enable", True)
        if enable in (False, 0, "0", "false", "False", "off", "Off"):
            return x

        sr = int(sample_rate) if sample_rate else 44100
        sr = max(sr, 8000)

        gains = self._gains()
        if max(abs(g) for g in gains) < 0.05:
            return x

        self._rebuild(sr, gains)
        if not self._sos_list:
            return x

        mono = x.ndim == 1
        work = np.atleast_2d(x.astype(np.float64, copy=False))
        if mono:
            work = work.reshape(-1, 1)
        elif work.shape[0] < work.shape[1] and work.shape[0] <= 8:
            # host sometimes passes (channels, n)
            work = work.T
            transposed = True
        else:
            transposed = False

        y = work
        n_ch = y.shape[1]
        for si, sos in enumerate(self._sos_list):
            if _HAS_SCIPY:
                chans = []
                for c in range(n_ch):
                    zkey = (si, c)
                    zi = self._zi.get(zkey)
                    if zi is None:
                        zi = sosfilt_zi(sos) * y[0, c]
                    yc, zf = sosfilt(sos, y[:, c], zi=zi)
                    self._zi[zkey] = zf
                    chans.append(yc)
                y = np.stack(chans, axis=1)
            else:
                chans = []
                for c in range(n_ch):
                    zkey = (si, c)
                    yc, zf = _biquad_filt(sos, y[:, c], self._zi.get(zkey))
                    self._zi[zkey] = zf
                    chans.append(yc)
                y = np.stack(chans, axis=1)

        y = np.clip(y, -1.0, 1.0)
        if mono:
            out = y[:, 0]
        elif transposed:
            out = y.T
        else:
            out = y

        if np.issubdtype(x.dtype, np.floating) and x.dtype != np.float64:
            out = out.astype(x.dtype, copy=False)
        return out