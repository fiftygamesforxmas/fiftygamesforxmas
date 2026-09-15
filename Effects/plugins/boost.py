"""
Volume boost plugin.
Discovered automatically by host.py because it exposes get_name / get_knobs /
get_switches / apply_effect.
"""

from dataclasses import dataclass, field
from typing import List


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


class VolumeBoost:
    """Raise (or lower) output level by the Gain knob when Enable is on."""

    def __init__(self):
        self.name = "Boost"
        # live parameter members — GUI writes these before apply_effect()
        self.gain = 1.0
        self.enable = True

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
        return [
            Knob(
                name="Gain",
                min=0.0,
                max=5.0,
                default=1.0,
                click_pts=[0.0, 0.5, 1.0, 1.5, 2.0],
                knob_color_scheme=KnobColorScheme(
                    outline="black", face="white", needle="black"
                ),
            )
        ]

    def get_switches(self) -> List[Switch]:
        return [Switch(name="Enable", default=True)]

    def apply_effect(self, audio, sample_rate: int):
        """
        audio: float32 array in [-1, 1], shape (n,) or (n, channels)
        Uses members set by the host (gain, enable) rather than a long argument list.
        """
        if not getattr(self, "enable", True):
            return audio
        gain = float(getattr(self, "gain", 1.0))
        return audio * gain