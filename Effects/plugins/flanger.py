from dataclasses import dataclass, field
from typing import List

import numpy as np


class Flanger:
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
        knob_color_scheme: object = field(default=None)

        def __post_init__(self):
            if self.knob_color_scheme is None:
                self.knob_color_scheme = Flanger.KnobColorScheme(
                    outline="black", face="white", needle="black"
                )

    @dataclass
    class Switch:
        name: str = "Enable"
        default: bool = True

    def __init__(self):
        self.name = "Flanger"
        self.enable = True
        self.invert = False
        self.rate = 0.35
        self.depth = 0.7
        self.delay = 2.2
        self.feedback = 0.35
        self.mix = 0.5
        self._lfo_phase = 0.0
        self._delay_l = None
        self._delay_r = None
        self._widx = 0
        self._sr = 0
        self._max_delay_s = 0.025

    def get_name(self) -> str:
        return "Flanger"

    def get_colors(self):
        return {
            "face": "#ffffff",
            "edge": "#111111",
            "text": "#111111",
            "muted": "#555555",
            "button": "#e8e8e8",
            "button_hot": "#d0d0d0",
            "button_on": "#222222",
            "button_text": "#111111",
            "switch_on": "#111111",
            "switch_off": "#cccccc",
            "slider": "#dddddd",
            "slider_handle": "#222222",
            "knob_outline": "#000000",
            "knob_face": "#c0c0c8",
            "knob_needle": "#111111",
        }

    def get_knobs(self):
        scheme = Flanger.KnobColorScheme(
            outline="#000000", face="#c0c0c8", needle="#111111"
        )
        K = Flanger.Knob
        return [
            K("Rate", 0.05, 5.0, 0.35, [0.1, 0.2, 0.35, 0.5, 1.0, 2.0, 5.0], scheme),
            K("Depth", 0.0, 1.0, 0.7, [0.0, 0.25, 0.5, 0.7, 0.85, 1.0], scheme),
            K("Delay", 0.3, 10.0, 2.2, [0.5, 1.0, 2.2, 3.5, 5.0, 8.0], scheme),
            K("Feedback", 0.0, 0.92, 0.35, [0.0, 0.2, 0.35, 0.5, 0.7, 0.92], scheme),
            K("Mix", 0.0, 1.0, 0.5, [0.0, 0.25, 0.5, 0.75, 1.0], scheme),
        ]

    def get_switches(self):
        S = Flanger.Switch
        return [
            S("Enable", True),
            S("Invert", False),
        ]

    def _ensure_buffers(self, sample_rate: int):
        n = int(self._max_delay_s * sample_rate) + 8
        if self._delay_l is None or self._sr != sample_rate or len(self._delay_l) != n:
            self._delay_l = np.zeros(n, dtype=np.float64)
            self._delay_r = np.zeros(n, dtype=np.float64)
            self._widx = 0
            self._sr = sample_rate

    def apply_effect(self, audio, sample_rate: int):
        x = np.asarray(audio)
        if x.size == 0:
            return x
        if not bool(getattr(self, "enable", True)):
            return x

        rate = float(np.clip(getattr(self, "rate", 0.35), 0.05, 5.0))
        depth = float(np.clip(getattr(self, "depth", 0.7), 0.0, 1.0))
        delay_ms = float(np.clip(getattr(self, "delay", 2.2), 0.3, 10.0))
        fb = float(np.clip(getattr(self, "feedback", 0.35), 0.0, 0.92))
        mix = float(np.clip(getattr(self, "mix", 0.5), 0.0, 1.0))
        invert = bool(getattr(self, "invert", False))
        sign = -1.0 if invert else 1.0

        self._ensure_buffers(int(sample_rate))
        sr = float(sample_rate)
        buf_n = len(self._delay_l)

        mono = x.ndim == 1
        if mono:
            left = x.astype(np.float64, copy=False)
            right = left
        else:
            left = x[:, 0].astype(np.float64, copy=False)
            right = x[:, 1].astype(np.float64, copy=False) if x.shape[1] > 1 else left

        n = left.shape[0]
        out_l = np.empty(n, dtype=np.float64)
        out_r = np.empty(n, dtype=np.float64)

        base_delay = delay_ms * 0.001 * sr
        sweep = depth * 0.008 * sr
        min_d = 0.5
        phase = self._lfo_phase
        dphase = 2.0 * rate / sr
        widx = self._widx
        dl = self._delay_l
        dr = self._delay_r

        for i in range(n):
            tri = 1.0 - abs((phase % 2.0) - 1.0) * 2.0
            phase += dphase
            dsamps = base_delay + 0.5 * (tri + 1.0) * sweep
            dsamps = min(max(dsamps, min_d), buf_n - 2)

            rpos = widx - dsamps
            while rpos < 0:
                rpos += buf_n
            i0 = int(rpos)
            frac = rpos - i0
            i1 = i0 + 1
            if i1 >= buf_n:
                i1 -= buf_n

            tap_l = dl[i0] + frac * (dl[i1] - dl[i0])
            tap_r = dr[i0] + frac * (dr[i1] - dr[i0])

            in_l = left[i] + fb * tap_l
            in_r = right[i] + fb * tap_r
            dl[widx] = in_l
            dr[widx] = in_r
            widx += 1
            if widx >= buf_n:
                widx = 0

            wet_l = sign * tap_l
            wet_r = sign * tap_r
            out_l[i] = left[i] * (1.0 - mix) + wet_l * mix
            out_r[i] = right[i] * (1.0 - mix) + wet_r * mix

        self._lfo_phase = phase % 2.0
        self._widx = widx

        np.clip(out_l, -1.0, 1.0, out=out_l)
        np.clip(out_r, -1.0, 1.0, out=out_r)

        if mono:
            y = out_l.astype(x.dtype, copy=False)
        else:
            y = np.column_stack([out_l, out_r]).astype(x.dtype, copy=False)
            if x.shape[1] > 2:
                y = np.concatenate([y, x[:, 2:]], axis=1)
        return y