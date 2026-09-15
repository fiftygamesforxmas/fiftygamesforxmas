"""
Rodent Distortion plugin.
Discovered automatically by host.py because it exposes get_name / get_knobs /
get_switches / apply_effect.

Classic Rat-style architecture:
  input HPF → frequency-dependent high-gain stage → op-amp sat / slew
  → silicon (or LED) diode clip → Filter LPF → Volume
"""

from dataclasses import dataclass, field
from typing import List

import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi


@dataclass
class KnobColorScheme:
    outline: str = "#222222"
    face: str = "#d9c89a"
    needle: str = "#1a1a1a"


@dataclass
class ButtonColorScheme:
    outline: str = "#222222"
    face: str = "#3a3a3a"
    label: str = "#f2f2f2"
    on: str = "#c43b2b"
    off: str = "#2a2a2a"


@dataclass
class EffectColorScheme:
    enclosure: str = "#2b2b2b"
    panel: str = "#1c1c1c"
    accent: str = "#8a1f14"
    text: str = "#e8dcc0"
    led_on: str = "#ff2a1a"
    led_off: str = "#3a1512"


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
    button_color_scheme: ButtonColorScheme = field(default_factory=ButtonColorScheme)


# Analog-ish constants
V_DIODE_SI = 0.65       # 1N914 / 1N4148
V_DIODE_LED = 1.70      # Turbo-style LEDs
V_OPAMP_RAIL = 4.2
SLEW_V_PER_US = 0.30    # LM308-ish


def _design_sos_lpf(fc: float, sr: float, order: int = 1):
    fc = float(np.clip(fc, 20.0, 0.45 * sr))
    return butter(order, fc, btype="low", fs=sr, output="sos")


def _design_sos_hpf(fc: float, sr: float, order: int = 1):
    fc = float(np.clip(fc, 5.0, 0.45 * sr))
    return butter(order, fc, btype="high", fs=sr, output="sos")


def _apply_sos(x: np.ndarray, sos: np.ndarray) -> np.ndarray:
    zi = sosfilt_zi(sos) * x[0]
    y, _ = sosfilt(sos, x, zi=zi)
    return y


def _soft_sat(x: np.ndarray, drive: float) -> np.ndarray:
    drive = max(float(drive), 1e-6)
    return np.tanh(x * drive) / np.tanh(drive)


def _slew_limit(x: np.ndarray, sr: float, slew_v_per_us: float) -> np.ndarray:
    if slew_v_per_us <= 0:
        return x
    max_step = slew_v_per_us * 1e6 / sr
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        d = x[i] - y[i - 1]
        if d > max_step:
            d = max_step
        elif d < -max_step:
            d = -max_step
        y[i] = y[i - 1] + d
    return y


def _upsample_linear(x: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return x
    n = len(x)
    t = np.arange(n)
    t_up = np.linspace(0, n - 1, n * factor, endpoint=False)
    return np.interp(t_up, t, x)


def _downsample_average(x: np.ndarray, factor: int) -> np.ndarray:
    if factor == 1:
        return x
    n = (len(x) // factor) * factor
    x = x[:n]
    return x.reshape(-1, factor).mean(axis=1)


def _process_mono(
    x: np.ndarray,
    sr: float,
    distortion: float,
    filt: float,
    volume: float,
    input_level: float,
    led_clip: bool,
    oversample: int = 4,
) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64).ravel()
    if x.size == 0:
        return x

    peak = float(np.max(np.abs(x)) + 1e-12)
    x = x * (input_level / min(peak, 1.0))

    osr = sr * oversample
    x = _upsample_linear(x, oversample)

    x = _apply_sos(x, _design_sos_hpf(7.0, osr, 1))
    x = _apply_sos(x, _design_sos_lpf(12000.0, osr, 1))

    bass = _apply_sos(x, _design_sos_hpf(60.0, osr, 1))
    mids = _apply_sos(x, _design_sos_hpf(1500.0, osr, 1))

    g_lin = 1.0 + distortion * 180.0
    pre = x * 0.35 + bass * 0.45 + mids * 0.85
    pre *= g_lin

    hf_cut = 18000.0 - distortion * 10000.0
    pre = _apply_sos(pre, _design_sos_lpf(hf_cut, osr, 1))

    pre = np.clip(pre, -V_OPAMP_RAIL, V_OPAMP_RAIL)
    pre = _slew_limit(pre, osr, SLEW_V_PER_US * (0.4 + 0.6 * distortion))
    pre = _soft_sat(pre / V_OPAMP_RAIL, drive=2.2 + 3.5 * distortion) * V_OPAMP_RAIL

    pre = _apply_sos(pre, _design_sos_hpf(8.0, osr, 1))
    v_diode = V_DIODE_LED if led_clip else V_DIODE_SI
    clipped = np.clip(pre, -v_diode, v_diode)

    fc = 475.0 * (16000.0 / 475.0) ** float(np.clip(filt, 0.0, 1.0))
    y = _apply_sos(clipped, _design_sos_lpf(fc, osr, 1))
    y = _apply_sos(y, _design_sos_hpf(20.0, osr, 1))
    y *= volume * 4.5

    y = _downsample_average(y, oversample)

    m = float(np.max(np.abs(y)))
    if m > 0.98:
        y *= 0.98 / m
    return y.astype(np.float32)


class RodentDistortion:
    """Rat-style hard-clip distortion with Distortion, Filter, Volume, and Turbo clip."""

    def __init__(self):
        self.name = "Rodent Distortion"
        self.distortion = 0.65
        self.filter = 0.40
        self.volume = 0.55
        self.input = 0.22
        self.enable = True
        self.turbo = False
        self.effect_color_scheme = EffectColorScheme(
            enclosure="#2b2b2b",
            panel="#1c1c1c",
            accent="#8a1f14",
            text="#e8dcc0",
            led_on="#ff2a1a",
            led_off="#3a1512",
        )

    def get_name(self) -> str:
        return self.name

    def get_effect_color_scheme(self) -> EffectColorScheme:
        return self.effect_color_scheme

    def get_knobs(self) -> List[Knob]:
        main_knob = KnobColorScheme(outline="#222222", face="#d4c194", needle="#1a1a1a")
        input_knob = KnobColorScheme(outline="#222222", face="#7e8f6d", needle="#1a1a1a")
        return [
            Knob(
                name="Distortion",
                min=0.0,
                max=1.0,
                default=0.65,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=main_knob,
            ),
            Knob(
                name="Filter",
                min=0.0,
                max=1.0,
                default=0.40,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=main_knob,
            ),
            Knob(
                name="Volume",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=main_knob,
            ),
            Knob(
                name="Input",
                min=0.05,
                max=0.60,
                default=0.22,
                click_pts=[0.10, 0.22, 0.35, 0.50],
                knob_color_scheme=input_knob,
            ),
        ]

    def get_switches(self) -> List[Switch]:
        enable_btn = ButtonColorScheme(
            outline="#222222",
            face="#333333",
            label="#f2f2f2",
            on="#c43b2b",
            off="#2a2a2a",
        )
        turbo_btn = ButtonColorScheme(
            outline="#222222",
            face="#333333",
            label="#f2f2f2",
            on="#d4a017",
            off="#2a2a2a",
        )
        return [
            Switch(name="Enable", default=True, button_color_scheme=enable_btn),
            Switch(name="Turbo", default=False, button_color_scheme=turbo_btn),
        ]

    def apply_effect(self, audio, sample_rate: int):
        if not getattr(self, "enable", True):
            return audio

        distortion = float(np.clip(getattr(self, "distortion", 0.65), 0.0, 1.0))
        filt = float(np.clip(getattr(self, "filter", 0.40), 0.0, 1.0))
        volume = float(np.clip(getattr(self, "volume", 0.55), 0.0, 1.0))
        input_level = float(np.clip(getattr(self, "input", 0.22), 0.05, 0.80))
        turbo = bool(getattr(self, "turbo", False))
        sr = float(sample_rate)

        x = np.asarray(audio)
        if x.ndim == 1:
            y = _process_mono(x, sr, distortion, filt, volume, input_level, turbo)
            if len(y) < len(x):
                y = np.pad(y, (0, len(x) - len(y)))
            elif len(y) > len(x):
                y = y[: len(x)]
            return y.astype(x.dtype, copy=False)

        channels = []
        n = x.shape[0]
        for c in range(x.shape[1]):
            yc = _process_mono(x[:, c], sr, distortion, filt, volume, input_level, turbo)
            if len(yc) < n:
                yc = np.pad(yc, (0, n - len(yc)))
            elif len(yc) > n:
                yc = yc[:n]
            channels.append(yc)
        return np.stack(channels, axis=1).astype(x.dtype, copy=False)