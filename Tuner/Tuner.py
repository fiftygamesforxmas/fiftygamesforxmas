#!/usr/bin/env python3
"""
Chromatic Instrument Tuner in pure Pygame.
Supports voice, string, and wind instruments via microphone.
Resizable window. No tkinter.

Dependencies:
    pip install pygame numpy sounddevice
"""

import json
import math
import os
import queue
from collections import deque

import numpy as np
import pygame
import sounddevice as sd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONFIG_FILE = "tunings.json"

DEFAULT_TUNINGS = {
    "chromatic": [],
    "guitar": ["E2", "A2", "D3", "G3", "B3", "E4"],
    "bass": ["E1", "A1", "D2", "G2"],
    "violin": ["G3", "D4", "A4", "E5"],
    "charango": ["G4", "C5", "E5", "A4", "E5"],
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
DEFAULT_A4 = 440.0

SAMPLE_RATE = 44100
BLOCK_SIZE = 2048
HOP_SIZE = 1024

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ensure_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_TUNINGS, f, indent=2)
        print(f"Created {CONFIG_FILE}")
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def note_to_freq(note_str, a4=DEFAULT_A4):
    if not note_str:
        return None
    name = note_str[:-1]
    octave = int(note_str[-1])
    try:
        idx = NOTE_NAMES.index(name)
    except ValueError:
        return None
    midi = (octave + 1) * 12 + idx
    return a4 * (2 ** ((midi - 69) / 12.0))

def freq_to_note(freq, a4=DEFAULT_A4):
    if freq is None or freq < 20 or freq > 5000:
        return None, 0, 0, ""
    midi = 69 + 12 * math.log2(freq / a4)
    midi_rounded = int(round(midi))
    cents = (midi - midi_rounded) * 100
    name = NOTE_NAMES[midi_rounded % 12]
    octave = (midi_rounded // 12) - 1
    return name, octave, cents, f"{name}{octave}"

def detect_pitch(audio, sr):
    if len(audio) < 100:
        return None
    audio = audio - np.mean(audio)
    energy = np.sqrt(np.mean(audio ** 2))
    if energy < 0.005:
        return None

    corr = np.correlate(audio, audio, mode="full")
    corr = corr[len(corr) // 2 :]
    corr /= corr[0] + 1e-10

    min_lag = int(sr / 1200)
    max_lag = int(sr / 50)
    if max_lag >= len(corr):
        max_lag = len(corr) - 1

    segment = corr[min_lag:max_lag]
    if len(segment) == 0:
        return None
    peak_idx = np.argmax(segment) + min_lag
    if corr[peak_idx] < 0.3:
        return None

    if 1 < peak_idx < len(corr) - 1:
        alpha = corr[peak_idx - 1]
        beta = corr[peak_idx]
        gamma = corr[peak_idx + 1]
        denom = alpha - 2 * beta + gamma
        if abs(denom) > 1e-6:
            peak_idx += 0.5 * (alpha - gamma) / denom

    freq = sr / peak_idx
    return freq if 40 < freq < 2000 else None

# ---------------------------------------------------------------------------
# Audio stream
# ---------------------------------------------------------------------------
class AudioInput:
    def __init__(self):
        self.q = queue.Queue()
        self.stream = None
        self.device = None
        self.running = False

    def list_inputs(self):
        devices = sd.query_devices()
        inputs = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                inputs.append((i, d["name"]))
        return inputs

    def start(self, device=None):
        self.stop()
        self.device = device
        try:
            self.stream = sd.InputStream(
                device=device,
                channels=1,
                samplerate=SAMPLE_RATE,
                blocksize=HOP_SIZE,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
            self.running = True
        except Exception as e:
            print(f"Audio start failed: {e}")
            self.running = False

    def _callback(self, indata, frames, time, status):
        if status:
            print(status)
        self.q.put(indata[:, 0].copy())

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.running = False
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def get_chunk(self):
        try:
            return self.q.get_nowait()
        except queue.Empty:
            return None

# ---------------------------------------------------------------------------
# Guide tone generator
# ---------------------------------------------------------------------------
class GuideTone:
    def __init__(self, sample_rate=44100):
        self.sr = sample_rate
        self.channel = None
        self.enabled = False
        self.current_sound = None
        pygame.mixer.init(frequency=self.sr, size=-16, channels=1, buffer=512)

    def _make_tone(self, freq, volume, duration=0.15):
        """Generate a short grumbling tone (sine + a bit of low-frequency noise)."""
        t = np.linspace(0, duration, int(self.sr * duration), endpoint=False)
        # Base sine
        sine = np.sin(2 * np.pi * freq * t)
        # Soft noise for grumble character
        noise = np.random.uniform(-0.3, 0.3, len(t))
        noise *= np.sin(2 * np.pi * 12 * t)  # amplitude modulate the noise
        wave = (0.7 * sine + 0.3 * noise) * volume
        # Fade in/out to avoid clicks
        fade = int(0.02 * self.sr)
        if fade > 0:
            wave[:fade] *= np.linspace(0, 1, fade)
            wave[-fade:] *= np.linspace(1, 0, fade)
        wave = np.clip(wave, -1, 1)
        # Convert to 16-bit
        audio = (wave * 32767).astype(np.int16)
        return pygame.sndarray.make_sound(audio)

    def update(self, cents):
        if not self.enabled or cents is None:
            if self.current_sound:
                self.current_sound.stop()
                self.current_sound = None
            return

        abs_cents = abs(cents)
        # Only active within roughly ±100 cents
        if abs_cents > 110 or abs_cents < 2:
            if self.current_sound:
                self.current_sound.stop()
                self.current_sound = None
            return

        # Volume peaks at 100 cents, zero at 0
        volume = max(0.0, min(1.0, abs_cents / 100.0)) * 0.45

        if cents < 0:
            # Flat → low grumble (~55–70 Hz)
            freq = 55 + (abs_cents / 100.0) * 15
        else:
            # Sharp → higher grumble (~140–180 Hz)
            freq = 140 + (abs_cents / 100.0) * 40

        # Only regenerate if significantly different or not playing
        if self.current_sound is None or not self.channel or not self.channel.get_busy():
            if self.current_sound:
                self.current_sound.stop()
            self.current_sound = self._make_tone(freq, volume)
            self.channel = self.current_sound.play(loops=-1)

    def set_enabled(self, state):
        self.enabled = state
        if not state and self.current_sound:
            self.current_sound.stop()
            self.current_sound = None

    def stop(self):
        if self.current_sound:
            self.current_sound.stop()
        pygame.mixer.quit()

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
class TunerApp:
    def __init__(self):
        pygame.init()
        self.width, self.height = 900, 700
        self.screen = pygame.display.set_mode(
            (self.width, self.height), pygame.RESIZABLE
        )
        pygame.display.set_caption("Chromatic Instrument Tuner")

        self.clock = pygame.time.Clock()
        self.font_big = None
        self.font_med = None
        self.font_small = None
        self.update_fonts()

        self.tunings = ensure_config()
        self.instruments = list(self.tunings.keys())
        self.current_inst_idx = 0

        # Master pitch (A4)
        self.a4_freq = DEFAULT_A4
        self.a4_cents = 0.0          # offset in cents from 440

        self.audio = AudioInput()
        self.input_devices = self.audio.list_inputs()
        self.selected_device = None
        if self.input_devices:
            self.selected_device = self.input_devices[0][0]
            self.audio.start(self.selected_device)

        self.guide = GuideTone()
        self.guide_enabled = False

        self.show_frequency = False
        self.current_freq = None
        self.current_note = None
        self.current_octave = 0
        self.current_cents = 0
        self.history = deque(maxlen=5)

        self.buttons = {}
        self.running = True

    def update_fonts(self):
        scale = min(self.width, self.height) / 700
        self.font_big = pygame.font.SysFont("arial", int(180 * scale), bold=True)
        self.font_med = pygame.font.SysFont("arial", int(36 * scale))
        self.font_small = pygame.font.SysFont("arial", int(22 * scale))

    def current_instrument(self):
        return self.instruments[self.current_inst_idx]

    def set_a4_cents(self, cents):
        """Set master offset in cents (-200 … +200)."""
        self.a4_cents = max(-200.0, min(200.0, cents))
        self.a4_freq = DEFAULT_A4 * (2 ** (self.a4_cents / 1200.0))

    def draw_needle(self, surface, center, radius, cents):
        cents = max(-50, min(50, cents))
        angle = math.radians(-90 + (cents / 50.0) * 70)
        end_x = center[0] + radius * math.cos(angle)
        end_y = center[1] + radius * math.sin(angle)

        pygame.draw.arc(
            surface,
            (60, 60, 60),
            (center[0] - radius, center[1] - radius, radius * 2, radius * 2),
            math.radians(20),
            math.radians(160),
            8,
        )
        pygame.draw.line(
            surface,
            (100, 100, 100),
            (center[0], center[1]),
            (center[0], center[1] - radius * 0.7),
            2,
        )
        color = (80, 200, 80) if abs(cents) < 5 else (220, 80, 80)
        pygame.draw.line(surface, color, center, (end_x, end_y), 4)
        pygame.draw.circle(surface, color, center, 8)

    def draw_button(self, rect, text, active=False):
        color = (70, 130, 180) if active else (50, 50, 50)
        pygame.draw.rect(self.screen, color, rect, border_radius=6)
        pygame.draw.rect(self.screen, (180, 180, 180), rect, 2, border_radius=6)
        txt = self.font_small.render(text, True, (255, 255, 255))
        self.screen.blit(
            txt, (rect.centerx - txt.get_width() // 2, rect.centery - txt.get_height() // 2)
        )
        return rect

    def layout(self):
        w, h = self.width, self.height
        # Instrument cycle
        self.buttons["instrument"] = pygame.Rect(w // 2 - 120, 20, 240, 40)
        # Frequency toggle
        self.buttons["freq_toggle"] = pygame.Rect(w - 180, 20, 160, 40)
        # Guide tone toggle
        self.buttons["guide"] = pygame.Rect(w - 180, 70, 160, 40)
        # Master pitch controls
        self.buttons["a4_down"] = pygame.Rect(20, 20, 50, 40)
        self.buttons["a4_up"] = pygame.Rect(200, 20, 50, 40)
        # Input panel
        self.input_panel_y = h - 180
        self.buttons["inputs"] = []
        for i, (dev_id, name) in enumerate(self.input_devices[:6]):
            y = self.input_panel_y + i * 28
            r = pygame.Rect(20, y, 300, 26)
            self.buttons["inputs"].append((r, dev_id, name))

    def draw(self):
        self.screen.fill((20, 20, 25))
        w, h = self.width, self.height
        self.layout()

        # Instrument
        inst = self.current_instrument()
        self.draw_button(self.buttons["instrument"], f"Instrument: {inst.title()}")

        # Frequency toggle
        label = "Show Hz: ON" if self.show_frequency else "Show Hz: OFF"
        self.draw_button(self.buttons["freq_toggle"], label, self.show_frequency)

        # Guide tone
        glabel = "Guide: ON" if self.guide_enabled else "Guide: OFF"
        self.draw_button(self.buttons["guide"], glabel, self.guide_enabled)

        # Master pitch
        self.draw_button(self.buttons["a4_down"], "–")
        self.draw_button(self.buttons["a4_up"], "+")
        a4_text = self.font_small.render(
            f"A4 = {self.a4_freq:.1f} Hz  ({self.a4_cents:+.0f}¢)", True, (220, 220, 180)
        )
        self.screen.blit(a4_text, (80, 28))

        # Big note
        if self.current_note:
            note_surf = self.font_big.render(self.current_note, True, (255, 255, 255))
            self.screen.blit(
                note_surf,
                (w // 2 - note_surf.get_width() // 2, h // 2 - 220),
            )
            if abs(self.current_cents) > 3:
                sign = "♯" if self.current_cents > 0 else "♭"
                sign_surf = self.font_med.render(sign, True, (255, 200, 100))
                self.screen.blit(
                    sign_surf,
                    (w // 2 + note_surf.get_width() // 2 + 10, h // 2 - 160),
                )

        # Needle
        center = (w // 2, h // 2 + 40)
        radius = min(w, h) * 0.22
        self.draw_needle(self.screen, center, radius, self.current_cents)

        # Cents
        cents_txt = self.font_med.render(
            f"{self.current_cents:+.1f} cents", True, (200, 200, 200)
        )
        self.screen.blit(
            cents_txt,
            (w // 2 - cents_txt.get_width() // 2, center[1] + radius + 10),
        )

        # Frequency
        if self.show_frequency and self.current_freq:
            freq_txt = self.font_med.render(
                f"{self.current_freq:.1f} Hz", True, (150, 220, 255)
            )
            self.screen.blit(
                freq_txt,
                (w // 2 - freq_txt.get_width() // 2, center[1] + radius + 50),
            )

        # Reference notes
        notes = self.tunings.get(inst, [])
        if notes:
            ref = "Open: " + "  ".join(notes)
            ref_surf = self.font_small.render(ref, True, (160, 160, 160))
            self.screen.blit(ref_surf, (w // 2 - ref_surf.get_width() // 2, 80))

        # Inputs panel
        panel_title = self.font_small.render("Audio Inputs", True, (200, 200, 200))
        self.screen.blit(panel_title, (20, self.input_panel_y - 28))
        for rect, dev_id, name in self.buttons["inputs"]:
            active = dev_id == self.selected_device
            short_name = name[:28] + "…" if len(name) > 28 else name
            self.draw_button(rect, short_name, active)

        # Status
        status = "Listening…" if self.audio.running else "No audio input"
        st = self.font_small.render(
            status, True, (120, 200, 120) if self.audio.running else (200, 80, 80)
        )
        self.screen.blit(st, (w - 200, h - 40))

    def handle_click(self, pos):
        if self.buttons["instrument"].collidepoint(pos):
            self.current_inst_idx = (self.current_inst_idx + 1) % len(self.instruments)
        elif self.buttons["freq_toggle"].collidepoint(pos):
            self.show_frequency = not self.show_frequency
        elif self.buttons["guide"].collidepoint(pos):
            self.guide_enabled = not self.guide_enabled
            self.guide.set_enabled(self.guide_enabled)
        elif self.buttons["a4_down"].collidepoint(pos):
            self.set_a4_cents(self.a4_cents - 10)   # 10 cents steps
        elif self.buttons["a4_up"].collidepoint(pos):
            self.set_a4_cents(self.a4_cents + 10)
        else:
            for rect, dev_id, name in self.buttons["inputs"]:
                if rect.collidepoint(pos):
                    self.selected_device = dev_id
                    self.audio.start(dev_id)
                    break

    def process_audio(self):
        chunk = self.audio.get_chunk()
        if chunk is None:
            return
        self.history.append(chunk)
        if len(self.history) < 2:
            return
        audio = np.concatenate(list(self.history))
        freq = detect_pitch(audio, SAMPLE_RATE)
        if freq:
            self.current_freq = freq
            name, octv, cents, full = freq_to_note(freq, self.a4_freq)
            self.current_note = name
            self.current_octave = octv
            self.current_cents = cents
        else:
            self.current_cents *= 0.95

        # Update guide tone
        self.guide.update(self.current_cents if self.current_note else None)

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.width, self.height = event.w, event.h
                    self.screen = pygame.display.set_mode(
                        (self.width, self.height), pygame.RESIZABLE
                    )
                    self.update_fonts()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)

            self.process_audio()
            self.draw()
            pygame.display.flip()
            self.clock.tick(60)

        self.audio.stop()
        self.guide.stop()
        pygame.quit()

if __name__ == "__main__":
    app = TunerApp()
    app.run()