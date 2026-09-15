"""
The Niner's — Klon-style overdrive plugin.
Discovered automatically by host.py because it exposes get_name / get_knobs /
get_switches / apply_effect.

Requires: numpy, scipy
"""

from dataclasses import dataclass, field
from typing import List

import numpy as np
from scipy.signal import butter, sosfilt


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


_NINER_KNOB = KnobColorScheme(outline="#6B0000", face="#F7F2E8", needle="#B00000")


def _peak_eq_sos(fs, f0, Q, gain_db):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / (2.0 * Q)
    cosw = np.cos(w0)
    b0 = 1.0 + alpha * A
    b1 = -2.0 * cosw
    b2 = 1.0 - alpha * A
    a0 = 1.0 + alpha / A
    a1 = -2.0 * cosw
    a2 = 1.0 - alpha / A
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def _high_shelf_sos(fs, f0, gain_db, S=0.7):
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    alpha = np.sin(w0) / 2.0 * np.sqrt((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0)
    c = np.cos(w0)
    b0 = A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * alpha)
    b1 = -2 * A * ((A - 1) + (A + 1) * c)
    b2 = A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * alpha)
    a0 = (A + 1) - (A - 1) * c + 2 * np.sqrt(A) * alpha
    a1 = 2 * ((A - 1) - (A + 1) * c)
    a2 = (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * alpha
    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]], dtype=np.float64)


def _sat(x, rails=8.5):
    return rails * np.tanh(x / rails)


def _diode_clip(x, vf, softness):
    return vf * np.tanh((1.0 / max(softness, 1e-6)) * (x / vf))


class VolumeBoost:
    def __init__(self):
        self.name = "Klon"
        self.gain = 0.55
        self.treble = 0.50
        self.volume = 0.70
        self.enable = True
        self.fat = False
        self.silicon = False
        self.led = False
        self.oversample = 8
        self.input_volts = 0.30

    def get_name(self) -> str:
        return self.name

    def get_colors(self):
        return {
            "face": "#C8A44E",
            "edge": "#6B0000",
            "text": "#F7F2E8",
            "muted": "#F0D9A0",
            "button": "#B00000",
            "button_hot": "#D02020",
            "button_on": "#B00000",
            "button_text": "#F7F2E8",
            "switch_on": "#B00000",
            "switch_off": "#3A2208",
            "slider": "#6B0000",
            "slider_handle": "#F7F2E8",
            "knob_outline": "#6B0000",
            "knob_face": "#F7F2E8",
            "knob_needle": "#B00000",
        }

    def get_knobs(self) -> List[Knob]:
        return [
            Knob(
                name="Gain",
                min=0.0,
                max=1.0,
                default=0.55,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=_NINER_KNOB,
            ),
            Knob(
                name="Treble",
                min=0.0,
                max=1.0,
                default=0.50,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=_NINER_KNOB,
            ),
            Knob(
                name="Volume",
                min=0.0,
                max=1.0,
                default=0.70,
                click_pts=[0.0, 0.25, 0.5, 0.75, 1.0],
                knob_color_scheme=_NINER_KNOB,
            ),
        ]

    def get_switches(self) -> List[Switch]:
        return [
            Switch(name="Enable", default=True),
            Switch(name="Fat", default=False),
            Switch(name="Silicon", default=False),
            Switch(name="Led", default=False),
        ]

    def apply_effect(self, audio, sample_rate: int):
        if not getattr(self, "enable", True):
            return audio

        src = np.asarray(audio)
        x = np.array(src, dtype=np.float64, copy=True)
        mono = x.ndim == 1
        if mono:
            x = x[:, None]

        g = float(np.clip(getattr(self, "gain", 0.55), 0.0, 1.0))
        tone = float(np.clip(getattr(self, "treble", 0.50), 0.0, 1.0))
        vol = float(np.clip(getattr(self, "volume", 0.70), 0.0, 1.0))
        fat = bool(getattr(self, "fat", False))
        led = bool(getattr(self, "led", False))
        silicon = bool(getattr(self, "silicon", False))
        os_ = max(2, int(getattr(self, "oversample", 8)))
        vin = float(getattr(self, "input_volts", 0.30))
        fs = float(sample_rate) if sample_rate else 44100.0
        fs_os = fs * os_

        if led:
            vf, soft = 1.60, 0.08
        elif silicon:
            vf, soft = 0.70, 0.05
        else:
            vf, soft = 0.35, 0.035

        bass_fc = 70.0 if fat else 106.0
        drive_hp_fc = 80.0 if fat else 120.0
        shelf_f = 280.0 if fat else 408.0
        drive_db = 13.0 + 27.0 * g
        shelf_db = (tone - 0.45) * 22.0

        in_hp = butter(2, 18.0, btype="highpass", fs=fs_os, output="sos")
        drive_hp = butter(1, drive_hp_fc, btype="highpass", fs=fs_os, output="sos")
        drive_lp = butter(1, 6500.0, btype="lowpass", fs=fs_os, output="sos")
        drive_peak = _peak_eq_sos(fs_os, 1000.0, 0.7, drive_db)
        bass_lp = butter(1, bass_fc, btype="lowpass", fs=fs_os, output="sos")
        clean_hp = butter(1, 80.0, btype="highpass", fs=fs_os, output="sos")
        clean_lp = butter(1, 8000.0, btype="lowpass", fs=fs_os, output="sos")
        tone_sos = _high_shelf_sos(fs_os, shelf_f, shelf_db)
        out_hp = butter(1, 12.0, btype="highpass", fs=fs_os, output="sos")
        aa = butter(8, 0.45 * fs, btype="lowpass", fs=fs_os, output="sos")
        up_lpf = butter(8, 0.45 * fs, btype="lowpass", fs=fs_os, output="sos")

        out = np.empty_like(x)
        for c in range(x.shape[1]):
            v = x[:, c] * vin
            up = np.zeros(v.size * os_, dtype=np.float64)
            up[::os_] = v * os_
            up = sosfilt(up_lpf, up)
            up = sosfilt(in_hp, up)

            drive = sosfilt(drive_hp, up)
            drive = sosfilt(drive_peak, drive)
            drive = sosfilt(drive_lp, drive)
            drive = _sat(drive, 8.5)
            drive = _diode_clip(drive, vf, soft)
            drive = _sat(drive * 2.2, 8.5)

            bass = sosfilt(bass_lp, up) * (1.25 if fat else 1.15)
            clean = sosfilt(clean_lp, sosfilt(clean_hp, up))

            mix = g * drive + (1.0 - g) * 0.85 * clean + 0.28 * bass
            mix = sosfilt(tone_sos, mix)
            mix = sosfilt(out_hp, mix)
            mix *= 3.4 * (vol ** 1.4)
            mix = sosfilt(aa, mix)
            y = mix[::os_] / max(vin, 1e-9)
            out[:, c] = np.tanh(y * 0.85) / 0.85

        y = out[:, 0] if mono else out
        return y.astype(src.dtype, copy=False)