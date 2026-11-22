import pygame
import pyaudio
import numpy as np
from scipy import signal
import json
import os
import glob

CHUNK = 1024
RATE = 44100
FORMAT = pyaudio.paInt16
CHANNELS = 1
SETTINGS_FILE = "hearing_aid_settings.json"
NOISE_DIR = "."  # current directory

class HearingAidProcessor:
    def __init__(self):
        self.input_gain = 3.0
        self.output_volume = 0.7
        self.voice_boost = 1.0
        self.noise_reduction = 0.4
        self.compression = 0.5
        self.bypass = False
        self.background_boost = False
        self.noise_sub_strength = 0.6          # NEW
        self.noise_spectrum = None             # average |FFT|^2 of unwanted sound
        self.noise_filter_name = None

        self.hp_zi = None
        self.presence_zi = None
        self.shelf_zi = None
        self._setup_filters()

        self.input_level = 0.0
        self.output_level = 0.0

    def _setup_filters(self):
        self.b_hp, self.a_hp = signal.butter(2, 120 / (RATE / 2), btype='high')
        self.hp_zi = signal.lfilter_zi(self.b_hp, self.a_hp)

        self.b_pres, self.a_pres = signal.iirpeak(3000 / (RATE / 2), Q=1.5)
        self.presence_zi = signal.lfilter_zi(self.b_pres, self.a_pres)

        self.b_shelf, self.a_shelf = signal.butter(1, 5000 / (RATE / 2), btype='high')
        self.shelf_zi = signal.lfilter_zi(self.b_shelf, self.a_shelf)

    def set_noise_profile(self, spectrum, name=None):
        self.noise_spectrum = spectrum
        self.noise_filter_name = name

    def process(self, in_data, frame_count, time_info, status):
        if self.bypass:
            audio = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
            audio *= self.output_volume
            self.input_level = np.sqrt(np.mean(audio**2))
            self.output_level = self.input_level
            return (np.clip(audio * 32767, -32768, 32767).astype(np.int16).tobytes(),
                    pyaudio.paContinue)

        audio = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0

        audio *= self.input_gain
        self.input_level = 0.9 * self.input_level + 0.1 * np.sqrt(np.mean(audio**2))

        # Spectral subtraction (if a noise profile is loaded)
        if self.noise_spectrum is not None and self.noise_sub_strength > 0.01:
            # Pad/truncate to match CHUNK if needed
            n = len(audio)
            if len(self.noise_spectrum) != n // 2 + 1:
                # simple resize of spectrum
                target_bins = n // 2 + 1
                noise_spec = np.interp(
                    np.linspace(0, 1, target_bins),
                    np.linspace(0, 1, len(self.noise_spectrum)),
                    self.noise_spectrum
                )
            else:
                noise_spec = self.noise_spectrum

            fft = np.fft.rfft(audio)
            mag = np.abs(fft)
            phase = np.angle(fft)
            # Subtract (with over-subtraction)
            mag_clean = mag - self.noise_sub_strength * 1.5 * np.sqrt(noise_spec)
            mag_clean = np.maximum(mag_clean, 0.02 * mag)  # spectral floor
            fft_clean = mag_clean * np.exp(1j * phase)
            audio = np.fft.irfft(fft_clean, n=n).astype(np.float32)

        audio, self.hp_zi = signal.lfilter(self.b_hp, self.a_hp, audio, zi=self.hp_zi)

        if self.voice_boost > 0.1:
            boosted, self.presence_zi = signal.lfilter(self.b_pres, self.a_pres, audio, zi=self.presence_zi)
            audio = audio + (boosted - audio) * self.voice_boost * 0.6

            shelf, self.shelf_zi = signal.lfilter(self.b_shelf, self.a_shelf, audio, zi=self.shelf_zi)
            audio = audio + (shelf - audio) * self.voice_boost * 0.35

        rms = np.sqrt(np.mean(audio**2))
        gate_threshold = 0.008 * (1.0 + self.noise_reduction * 2)
        if self.background_boost:
            gate_threshold *= 0.45
        if rms < gate_threshold:
            audio *= 0.15 if not self.background_boost else 0.45

        comp_amount = self.compression
        if self.background_boost:
            comp_amount = min(1.0, comp_amount + 0.35)

        if comp_amount > 0.05:
            peak = np.max(np.abs(audio))
            if peak > 0.01:
                target = np.tanh(peak * 2.2) / 2.2
                gain_comp = (target / peak) ** comp_amount
                if self.background_boost and peak < 0.08:
                    gain_comp *= 1.4
                audio *= gain_comp

        audio *= self.output_volume
        audio = np.tanh(audio * 1.2) / 1.2

        self.output_level = 0.9 * self.output_level + 0.1 * np.sqrt(np.mean(audio**2))

        return (np.clip(audio * 32767, -32768, 32767).astype(np.int16).tobytes(),
                pyaudio.paContinue)


class HearingAidApp:
    def __init__(self):
        pygame.init()
        self.width = 900
        self.height = 720
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        pygame.display.set_caption("Hearing Aid Assistant – Voice Boost")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 18)
        self.font_small = pygame.font.SysFont("segoeui", 15)
        self.font_big = pygame.font.SysFont("segoeui", 22, bold=True)

        self.pa = pyaudio.PyAudio()
        self.processor = HearingAidProcessor()
        self.stream = None
        self.running = True
        self.streaming = False

        self.input_devices = []
        self.output_devices = []
        self.selected_input = 0
        self.selected_output = None
        self.refresh_devices()

        self.sliders = [
            {"x": 480, "y": 160, "w": 380, "value": 3.0, "min": 0.5, "max": 12.0, "label": "Input Gain"},
            {"x": 480, "y": 220, "w": 380, "value": 0.7, "min": 0.0, "max": 1.5, "label": "Output Volume"},
            {"x": 480, "y": 280, "w": 380, "value": 1.0, "min": 0.0, "max": 2.0, "label": "Voice Boost (Presence + Highs)"},
            {"x": 480, "y": 340, "w": 380, "value": 0.4, "min": 0.0, "max": 1.0, "label": "Noise Reduction"},
            {"x": 480, "y": 400, "w": 380, "value": 0.5, "min": 0.0, "max": 1.0, "label": "Compression"},
            {"x": 480, "y": 460, "w": 380, "value": 0.6, "min": 0.0, "max": 1.5, "label": "Noise Subtraction Strength"},  # NEW
        ]
        self.dragging = None

        self.noise_files = []
        self.selected_noise_idx = -1
        self.recording_noise = False
        self.noise_buffer = []
        self.refresh_noise_files()

        self.load_settings()

    def refresh_noise_files(self):
        self.noise_files = sorted(glob.glob(os.path.join(NOISE_DIR, "*_noise.npy")))
        self.noise_files = [os.path.basename(f) for f in self.noise_files]

    def record_noise_sample(self, duration_sec=4):
        """Record a short noise sample and create a spectral profile."""
        if not self.input_devices:
            print("No input device")
            return
        print("Recording noise sample...")
        in_idx = self.input_devices[self.selected_input][0]
        frames = []
        try:
            rec_stream = self.pa.open(
                format=FORMAT, channels=CHANNELS, rate=RATE,
                input=True, input_device_index=in_idx,
                frames_per_buffer=CHUNK
            )
            for _ in range(int(RATE / CHUNK * duration_sec)):
                data = rec_stream.read(CHUNK, exception_on_overflow=False)
                frames.append(np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0)
            rec_stream.stop_stream()
            rec_stream.close()
        except Exception as e:
            print("Recording error:", e)
            return

        audio = np.concatenate(frames)
        # Compute average power spectrum
        window = np.hanning(CHUNK)
        spectra = []
        for i in range(0, len(audio) - CHUNK, CHUNK // 2):
            chunk = audio[i:i+CHUNK] * window
            spec = np.abs(np.fft.rfft(chunk))**2
            spectra.append(spec)
        if spectra:
            avg_spectrum = np.mean(spectra, axis=0)
            # Save
            base = f"noise_{int(pygame.time.get_ticks())}"
            filename = os.path.join(NOISE_DIR, base + "_noise.npy")
            np.save(filename, avg_spectrum)
            print(f"Saved noise profile: {filename}")
            self.refresh_noise_files()
            # Auto-load it
            self.load_noise_profile(filename)

    def load_noise_profile(self, path_or_name):
        if not path_or_name.endswith(".npy"):
            path_or_name = os.path.join(NOISE_DIR, path_or_name)
        try:
            spectrum = np.load(path_or_name)
            name = os.path.basename(path_or_name)
            self.processor.set_noise_profile(spectrum, name)
            self.selected_noise_idx = self.noise_files.index(name) if name in self.noise_files else -1
            print(f"Loaded noise filter: {name}")
            self.save_settings()
        except Exception as e:
            print("Failed to load noise profile:", e)

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)

            self.sliders[0]["value"] = data.get("input_gain", self.sliders[0]["value"])
            self.sliders[1]["value"] = data.get("output_volume", self.sliders[1]["value"])
            self.sliders[2]["value"] = data.get("voice_boost", self.sliders[2]["value"])
            self.sliders[3]["value"] = data.get("noise_reduction", self.sliders[3]["value"])
            self.sliders[4]["value"] = data.get("compression", self.sliders[4]["value"])
            self.sliders[5]["value"] = data.get("noise_sub_strength", self.sliders[5]["value"])
            self.processor.background_boost = data.get("background_boost", False)
            self.processor.bypass = data.get("bypass", False)
            self.update_processor()

            saved_input_name = data.get("input_device_name")
            saved_output_name = data.get("output_device_name")
            saved_noise = data.get("noise_filter_name")

            if saved_input_name:
                for i, (idx, name) in enumerate(self.input_devices):
                    if name == saved_input_name:
                        self.selected_input = i
                        break
            if saved_output_name:
                for idx, name in self.output_devices:
                    if name == saved_output_name:
                        self.selected_output = idx
                        break
            if saved_noise and os.path.exists(os.path.join(NOISE_DIR, saved_noise)):
                self.load_noise_profile(saved_noise)

            print("Settings loaded")
        except Exception as e:
            print("Could not load settings:", e)

    def save_settings(self):
        input_name = None
        if self.input_devices and 0 <= self.selected_input < len(self.input_devices):
            input_name = self.input_devices[self.selected_input][1]

        output_name = None
        if self.selected_output is not None:
            for idx, name in self.output_devices:
                if idx == self.selected_output:
                    output_name = name
                    break

        data = {
            "input_gain": self.sliders[0]["value"],
            "output_volume": self.sliders[1]["value"],
            "voice_boost": self.sliders[2]["value"],
            "noise_reduction": self.sliders[3]["value"],
            "compression": self.sliders[4]["value"],
            "noise_sub_strength": self.sliders[5]["value"],
            "background_boost": self.processor.background_boost,
            "bypass": self.processor.bypass,
            "input_device_name": input_name,
            "output_device_name": output_name,
            "noise_filter_name": self.processor.noise_filter_name,
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Could not save settings:", e)

    def refresh_devices(self):
        self.input_devices = []
        self.output_devices = []
        for i in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                self.input_devices.append((i, info["name"]))
            if info["maxOutputChannels"] > 0:
                self.output_devices.append((i, info["name"]))
        if self.output_devices and self.selected_output is None:
            self.selected_output = self.output_devices[0][0]

    def start_stream(self):
        if self.streaming:
            self.stop_stream()
        if not self.input_devices or self.selected_output is None:
            print("No input or output selected")
            return
        in_idx = self.input_devices[self.selected_input][0]
        try:
            self.stream = self.pa.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                output=True,
                input_device_index=in_idx,
                output_device_index=self.selected_output,
                frames_per_buffer=CHUNK,
                stream_callback=self.processor.process
            )
            self.stream.start_stream()
            self.streaming = True
            print("Stream started")
        except Exception as e:
            print("Stream error:", e)
            self.streaming = False

    def stop_stream(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        self.streaming = False
        print("Stream stopped")

    def draw_slider(self, s):
        pygame.draw.rect(self.screen, (60, 60, 70), (s["x"], s["y"] + 8, s["w"], 8), border_radius=4)
        ratio = (s["value"] - s["min"]) / (s["max"] - s["min"])
        handle_x = s["x"] + int(ratio * s["w"])
        pygame.draw.circle(self.screen, (100, 180, 255), (handle_x, s["y"] + 12), 10)
        label = self.font_small.render(f"{s['label']}: {s['value']:.2f}", True, (220, 220, 220))
        self.screen.blit(label, (s["x"], s["y"] - 22))

    def draw_meter(self, x, y, level, label):
        pygame.draw.rect(self.screen, (40, 40, 50), (x, y, 20, 120))
        h = int(min(1.0, level * 4) * 120)
        color = (80, 220, 100) if level < 0.6 else (220, 180, 60) if level < 0.9 else (220, 70, 70)
        pygame.draw.rect(self.screen, color, (x, y + 120 - h, 20, h))
        txt = self.font_small.render(label, True, (200, 200, 200))
        self.screen.blit(txt, (x - 5, y + 125))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.save_settings()
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.width, self.height = event.size
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos

                for i, s in enumerate(self.sliders):
                    if s["x"] <= mx <= s["x"] + s["w"] and s["y"] <= my <= s["y"] + 24:
                        self.dragging = i
                        break

                for i in range(min(12, len(self.input_devices))):
                    rect = pygame.Rect(20, 80 + i * 28, 400, 26)
                    if rect.collidepoint(mx, my):
                        self.selected_input = i
                        self.save_settings()
                        break

                for i in range(min(8, len(self.output_devices))):
                    rect = pygame.Rect(20, 320 + i * 28, 400, 26)
                    if rect.collidepoint(mx, my):
                        self.selected_output = self.output_devices[i][0]
                        self.save_settings()
                        break

                # Noise filter list
                for i in range(min(6, len(self.noise_files))):
                    rect = pygame.Rect(20, 520 + i * 22, 400, 20)
                    if rect.collidepoint(mx, my):
                        self.load_noise_profile(self.noise_files[i])
                        break

                if 480 <= mx <= 620 and 520 <= my <= 555:
                    self.start_stream()
                if 640 <= mx <= 780 and 520 <= my <= 555:
                    self.stop_stream()
                if 480 <= mx <= 620 and 565 <= my <= 595:
                    self.apply_preset("conversation")
                    self.save_settings()
                if 640 <= mx <= 780 and 565 <= my <= 595:
                    self.apply_preset("bypass")
                    self.save_settings()
                if 480 <= mx <= 780 and 605 <= my <= 635:
                    self.processor.background_boost = not self.processor.background_boost
                    self.save_settings()
                if 480 <= mx <= 780 and 645 <= my <= 675:
                    # Record noise (stop stream first if running)
                    was_streaming = self.streaming
                    if was_streaming:
                        self.stop_stream()
                    self.record_noise_sample(4)
                    if was_streaming:
                        self.start_stream()

            elif event.type == pygame.MOUSEBUTTONUP:
                if self.dragging is not None:
                    self.save_settings()
                self.dragging = None
            elif event.type == pygame.MOUSEMOTION and self.dragging is not None:
                s = self.sliders[self.dragging]
                ratio = max(0, min(1, (event.pos[0] - s["x"]) / s["w"]))
                s["value"] = s["min"] + ratio * (s["max"] - s["min"])
                self.update_processor()

    def update_processor(self):
        self.processor.input_gain = self.sliders[0]["value"]
        self.processor.output_volume = self.sliders[1]["value"]
        self.processor.voice_boost = self.sliders[2]["value"]
        self.processor.noise_reduction = self.sliders[3]["value"]
        self.processor.compression = self.sliders[4]["value"]
        self.processor.noise_sub_strength = self.sliders[5]["value"]

    def apply_preset(self, name):
        if name == "conversation":
            self.sliders[0]["value"] = 4.5
            self.sliders[1]["value"] = 0.85
            self.sliders[2]["value"] = 1.6
            self.sliders[3]["value"] = 0.6
            self.sliders[4]["value"] = 0.7
            self.processor.bypass = False
        elif name == "bypass":
            self.sliders[2]["value"] = 0.0
            self.sliders[3]["value"] = 0.0
            self.sliders[4]["value"] = 0.0
            self.processor.bypass = True
        self.update_processor()

    def draw(self):
        self.screen.fill((28, 30, 38))

        title = self.font_big.render("Hearing Aid Assistant", True, (230, 240, 255))
        self.screen.blit(title, (30, 20))

        self.screen.blit(self.font.render("Input Devices", True, (180, 200, 255)), (20, 55))
        for i, (idx, name) in enumerate(self.input_devices[:10]):
            color = (100, 220, 140) if i == self.selected_input else (200, 200, 210)
            txt = self.font_small.render(f"{i}: {name[:40]}", True, color)
            self.screen.blit(txt, (25, 80 + i * 28))

        self.screen.blit(self.font.render("Output Devices", True, (180, 200, 255)), (20, 295))
        for i, (idx, name) in enumerate(self.output_devices[:8]):
            color = (100, 220, 140) if idx == self.selected_output else (200, 200, 210)
            txt = self.font_small.render(f"{i}: {name[:40]}", True, color)
            self.screen.blit(txt, (25, 320 + i * 28))

        # Noise filters
        self.screen.blit(self.font.render("Noise Filters (click to load)", True, (180, 200, 255)), (20, 495))
        for i, fname in enumerate(self.noise_files[:6]):
            color = (100, 220, 140) if i == self.selected_noise_idx else (200, 200, 210)
            txt = self.font_small.render(fname[:40], True, color)
            self.screen.blit(txt, (25, 520 + i * 22))

        for s in self.sliders:
            self.draw_slider(s)

        self.draw_meter(min(850, self.width - 50), 160, self.processor.input_level, "In")
        self.draw_meter(min(850, self.width - 50), 320, self.processor.output_level, "Out")

        # Buttons
        pygame.draw.rect(self.screen, (50, 140, 80) if self.streaming else (40, 90, 160), (480, 520, 140, 35), border_radius=6)
        pygame.draw.rect(self.screen, (160, 60, 60), (640, 520, 140, 35), border_radius=6)
        self.screen.blit(self.font_small.render("START" if not self.streaming else "RUNNING", True, (255, 255, 255)), (515, 528))
        self.screen.blit(self.font_small.render("STOP", True, (255, 255, 255)), (685, 528))

        pygame.draw.rect(self.screen, (80, 100, 160), (480, 565, 140, 30), border_radius=5)
        pygame.draw.rect(self.screen, (100, 100, 100), (640, 565, 140, 30), border_radius=5)
        self.screen.blit(self.font_small.render("Voice Preset", True, (255, 255, 255)), (500, 570))
        self.screen.blit(self.font_small.render("Bypass", True, (255, 255, 255)), (680, 570))

        bg_color = (50, 160, 90) if self.processor.background_boost else (70, 70, 90)
        pygame.draw.rect(self.screen, bg_color, (480, 605, 300, 30), border_radius=5)
        boost_label = "Background Boost: ON" if self.processor.background_boost else "Background Boost: OFF"
        self.screen.blit(self.font_small.render(boost_label, True, (255, 255, 255)), (530, 610))

        pygame.draw.rect(self.screen, (180, 100, 40), (480, 645, 300, 30), border_radius=5)
        self.screen.blit(self.font_small.render("Record Noise (4 sec)", True, (255, 255, 255)), (540, 650))

        status = "LIVE" if self.streaming else "STOPPED"
        self.screen.blit(self.font.render(f"Status: {status}", True, (150, 220, 150) if self.streaming else (220, 120, 120)), (30, self.height - 35))

        pygame.display.flip()

    def run(self):
        while self.running:
            self.handle_events()
            self.draw()
            self.clock.tick(60)
        self.save_settings()
        self.stop_stream()
        self.pa.terminate()
        pygame.quit()


if __name__ == "__main__":
    app = HearingAidApp()
    app.run()