from dataclasses import dataclass, field
from typing import List

import numpy as np
from scipy.signal import sosfilt, sosfilt_zi

try:
    from host import Knob, Switch, KnobColorScheme
except ImportError:
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
        knob_color_scheme: KnobColorScheme = field(default_factory=KnobColorScheme)

    @dataclass
    class Switch:
        name: str = "Enable"
        default: bool = True


_LOW = KnobColorScheme(outline="#081018", face="#2ee6ff", needle="#081018")
_MID = KnobColorScheme(outline="#081018", face="#ffe14a", needle="#081018")
_HI = KnobColorScheme(outline="#081018", face="#ff4ad2", needle="#081018")
_NEU = KnobColorScheme(outline="#081018", face="#f4fff8", needle="#0b3d2e")


class JustTone:
    def __init__(self):
        self.name = "Tone"
        self.enable = True
        self.low = 0.0
        self.mid = 0.0
        self.hi = 0.0
        self.midfreq = 800.0
        self.drive = 0.0
        self._zi = None
        self._cached = None
        self._sos = None

    def get_name(self):
        return "Tone"

    def get_colors(self):
        return {
            "face": "#0b1220",
            "edge": "#f4ff57",
            "text": "#f8fffb",
            "muted": "#8fd7c8",
            "button": "#16324a",
            "button_hot": "#2ee6ff",
            "button_on": "#ff4ad2",
            "button_text": "#081018",
            "switch_on": "#ffe14a",
            "switch_off": "#142033",
            "slider": "#081018",
            "slider_handle": "#2ee6ff",
            "knob_outline": "#081018",
            "knob_face": "#f4fff8",
            "knob_needle": "#0b3d2e",
        }

    def get_knobs(self):
        clicks_db = [-12.0, -6.0, -3.0, 0.0, 3.0, 6.0, 12.0]
        return [
            Knob(name="Low", min=-12.0, max=12.0, default=0.0,
                 click_pts=clicks_db, knob_color_scheme=_LOW),
            Knob(name="Mid", min=-12.0, max=12.0, default=0.0,
                 click_pts=clicks_db, knob_color_scheme=_MID),
            Knob(name="Hi", min=-12.0, max=12.0, default=0.0,
                 click_pts=clicks_db, knob_color_scheme=_HI),
            Knob(name="MidFreq", min=220.0, max=2500.0, default=800.0,
                 click_pts=[220.0, 400.0, 800.0, 1200.0, 2500.0],
                 knob_color_scheme=_NEU),
            Knob(name="Drive", min=0.0, max=1.0, default=0.0,
                 click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                 knob_color_scheme=_NEU),
        ]

    def get_switches(self):
        return [Switch(name="Enable", default=True)]

    def _shelf_sos(self, gain_db, fc, sr, high=False):
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * fc / sr
        cosw = np.cos(w0)
        sinw = np.sin(w0)
        alpha = sinw / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / 1.0 - 1.0) + 2.0)
        if high:
            b0 = A * ((A + 1) + (A - 1) * cosw + 2 * np.sqrt(A) * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cosw)
            b2 = A * ((A + 1) + (A - 1) * cosw - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) - (A - 1) * cosw + 2 * np.sqrt(A) * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cosw)
            a2 = (A + 1) - (A - 1) * cosw - 2 * np.sqrt(A) * alpha
        else:
            b0 = A * ((A + 1) - (A - 1) * cosw + 2 * np.sqrt(A) * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cosw)
            b2 = A * ((A + 1) - (A - 1) * cosw - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) + (A - 1) * cosw + 2 * np.sqrt(A) * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cosw)
            a2 = (A + 1) + (A - 1) * cosw - 2 * np.sqrt(A) * alpha
        return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)

    def _peak_sos(self, gain_db, fc, q, sr):
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * np.pi * fc / sr
        alpha = np.sin(w0) / (2.0 * q)
        cosw = np.cos(w0)
        b0 = 1 + alpha * A
        b1 = -2 * cosw
        b2 = 1 - alpha * A
        a0 = 1 + alpha / A
        a1 = -2 * cosw
        a2 = 1 - alpha / A
        return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)

    def apply_effect(self, audio, sample_rate):
        x = np.asarray(audio)
        if x.size == 0:
            return x
        if not bool(getattr(self, "enable", True)):
            return x

        low = float(np.clip(getattr(self, "low", 0.0), -12.0, 12.0))
        mid = float(np.clip(getattr(self, "mid", 0.0), -12.0, 12.0))
        hi = float(np.clip(getattr(self, "hi", 0.0), -12.0, 12.0))
        midfreq = float(np.clip(getattr(self, "midfreq", 800.0), 220.0, 2500.0))
        drive = float(np.clip(getattr(self, "drive", 0.0), 0.0, 1.0))
        sr = max(int(sample_rate), 1)

        key = (round(low, 3), round(mid, 3), round(hi, 3), round(midfreq, 1), sr)
        if self._cached != key:
            self._sos = np.vstack([
                self._shelf_sos(low, 180.0, sr, high=False),
                self._peak_sos(mid, midfreq, 0.85, sr),
                self._shelf_sos(hi, 3500.0, sr, high=True),
            ])
            self._cached = key
            self._zi = None

        mono = x.ndim == 1
        work = np.asarray(x, dtype=np.float64)
        if mono:
            work = work[:, None]
        n, ch = work.shape
        if self._zi is None or self._zi.shape[1] != ch:
            zi0 = sosfilt_zi(self._sos)
            self._zi = np.repeat(zi0[:, None, :], ch, axis=1)

        out = np.empty_like(work)
        for c in range(ch):
            y, self._zi[:, c, :] = sosfilt(self._sos, work[:, c], zi=self._zi[:, c, :])
            out[:, c] = y

        if drive > 1e-6:
            g = 1.0 + 4.0 * drive
            out = np.tanh(out * g) / np.tanh(g)

        out = np.clip(out, -1.0, 1.0)
        yout = out[:, 0] if mono else out
        if x.dtype == np.float32:
            return yout.astype(np.float32)
        return yout.astype(np.float64, copy=False)

