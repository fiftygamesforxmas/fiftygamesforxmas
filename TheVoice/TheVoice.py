import pygame
import pyaudio
import numpy as np
import threading
import sys
import time

# ---------------- Configuration ----------------
CHUNK = 4096
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
RECORD_SECONDS = 4

VOICES = [
    "Normal",
    "Feminize",
    "Masculinize",
    "Monster",
    "Darth Vader",
    "Alienize",
    "Chorus",
    "Lost Weight",
    "Disguised",
    "Mexicanize",
    "Huge Crowd"
]

class VoiceChanger:
    def __init__(self):
        self.running = False
        self.selected = 0
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.lock = threading.Lock()

        # Real-time state
        self.history_len = CHUNK * 4
        self.history = np.zeros(self.history_len, dtype=np.float32)
        self.hist_idx = 0
        self.ola_window = np.hanning(CHUNK).astype(np.float32)
        self.prev_tail = np.zeros(CHUNK // 2, dtype=np.float32)

        # Delay buffers
        self.delay_size = RATE
        self.delay_buf = np.zeros(self.delay_size, dtype=np.float32)
        self.delay_idx = 0
        self.delay2 = np.zeros(self.delay_size, dtype=np.float32)
        self.delay3 = np.zeros(self.delay_size, dtype=np.float32)
        self.idx2 = 0
        self.idx3 = 0

        # Sample recording
        self.recorded = None          # float32 array
        self.is_recording = False
        self.record_frames = []

    # ---------- Real-time helpers ----------
    def _push_history(self, data):
        n = len(data)
        end = self.hist_idx + n
        if end <= self.history_len:
            self.history[self.hist_idx:end] = data
        else:
            first = self.history_len - self.hist_idx
            self.history[self.hist_idx:] = data[:first]
            self.history[:n - first] = data[first:]
        self.hist_idx = end % self.history_len

    def _get_recent(self, length):
        if length >= self.history_len:
            return self.history.copy()
        start = (self.hist_idx - length) % self.history_len
        if start + length <= self.history_len:
            return self.history[start:start + length].copy()
        else:
            part1 = self.history[start:]
            part2 = self.history[:length - len(part1)]
            return np.concatenate([part1, part2])

    def pitch_shift_rt(self, data, factor):
        if abs(factor - 1.0) < 0.01 or len(data) == 0:
            return data
        context = self._get_recent(CHUNK * 2)
        if len(context) < CHUNK:
            context = np.pad(context, (CHUNK - len(context), 0))
        new_len = max(1, int(len(context) / factor))
        x_old = np.arange(len(context))
        x_new = np.linspace(0, len(context) - 1, new_len)
        shifted = np.interp(x_new, x_old, context)
        if len(shifted) >= CHUNK:
            shifted = shifted[-CHUNK:]
        else:
            shifted = np.pad(shifted, (CHUNK - len(shifted), 0))
        windowed = shifted * self.ola_window
        out = windowed.copy()
        half = CHUNK // 2
        out[:half] += self.prev_tail * self.ola_window[:half]
        self.prev_tail = windowed[half:] * 0.7
        return out

    def apply_delay(self, data, buf, idx, delay_ms, feedback=0.35, gain=0.5):
        delay_samples = int(RATE * delay_ms / 1000.0)
        out = data.copy()
        for i in range(len(data)):
            read_idx = (idx - delay_samples) % self.delay_size
            delayed = buf[read_idx]
            out[i] += delayed * gain
            buf[idx] = data[i] + delayed * feedback
            idx = (idx + 1) % self.delay_size
        return out, idx

    # ---------- High-quality offline processing ----------
    def pitch_shift_hq(self, data, factor):
        """Better quality pitch shift using larger windows + overlap-add."""
        if abs(factor - 1.0) < 0.01 or len(data) == 0:
            return data.copy()

        win_size = 2048
        hop = 512
        window = np.hanning(win_size).astype(np.float32)
        output = np.zeros(len(data) + win_size, dtype=np.float32)
        norm = np.zeros_like(output)

        for start in range(0, len(data) - win_size, hop):
            frame = data[start:start + win_size]
            # resample frame
            new_len = max(1, int(win_size / factor))
            x_old = np.arange(win_size)
            x_new = np.linspace(0, win_size - 1, new_len)
            shifted = np.interp(x_new, x_old, frame)
            # resize back to win_size
            if len(shifted) > win_size:
                shifted = shifted[:win_size]
            else:
                shifted = np.pad(shifted, (0, win_size - len(shifted)))
            windowed = shifted * window
            output[start:start + win_size] += windowed
            norm[start:start + win_size] += window

        norm[norm < 1e-6] = 1.0
        result = output[:len(data)] / norm[:len(data)]
        return result

    def process_offline(self, audio):
        """High-quality processing of a full sample."""
        effect = VOICES[self.selected]
        if effect == "Normal":
            return audio.copy()

        if effect == "Feminize":
            out = self.pitch_shift_hq(audio, 1.38)
        elif effect == "Masculinize":
            out = self.pitch_shift_hq(audio, 0.78)
        elif effect == "Monster":
            pitched = self.pitch_shift_hq(audio, 0.58)
            out = np.tanh(pitched * 1.6)
        elif effect == "Darth Vader":
            deep = self.pitch_shift_hq(audio, 0.62)
            # simple echo
            delay = int(0.14 * RATE)
            echo = np.zeros_like(deep)
            echo[delay:] = deep[:-delay] * 0.4
            out = deep + echo
        elif effect == "Alienize":
            high = self.pitch_shift_hq(audio, 1.65)
            t = np.arange(len(high)) / RATE
            carrier = np.sin(2 * np.pi * 28 * t)
            out = high * (0.65 + 0.35 * carrier)
        elif effect == "Chorus":
            out = audio.copy()
            for d_ms, g in [(22, 0.35), (48, 0.3), (75, 0.25)]:
                delay = int(d_ms * RATE / 1000)
                delayed = np.zeros_like(audio)
                delayed[delay:] = audio[:-delay] * g
                out += delayed
            out *= 0.55
        elif effect == "Lost Weight":
            high = self.pitch_shift_hq(audio, 1.2)
            out = np.diff(high, prepend=high[0]) * 1.3
        elif effect == "Disguised":
            p = self.pitch_shift_hq(audio, 1.12)
            delay = int(0.028 * RATE)
            c = np.zeros_like(p)
            c[delay:] = p[:-delay] * 0.35
            out = p * 0.7 + c
        elif effect == "Mexicanize":
            out = self.pitch_shift_hq(audio, 1.18)
        elif effect == "Huge Crowd":
            out = np.zeros_like(audio)
            for g, d_ms, pf in [(0.3, 18, 1.015), (0.27, 42, 0.985),
                                (0.24, 68, 1.04), (0.22, 98, 0.96), (0.2, 135, 1.0)]:
                pitched = self.pitch_shift_hq(audio, pf)
                delay = int(d_ms * RATE / 1000)
                delayed = np.zeros_like(pitched)
                delayed[delay:] = pitched[:-delay] * g
                out += delayed
            out = np.tanh(out * 1.05)
        else:
            out = audio.copy()

        return np.clip(out, -1.0, 1.0)

    # ---------- Real-time process ----------
    def process(self, data):
        with self.lock:
            effect = VOICES[self.selected]
            running = self.running

        if not running:
            return data

        audio = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
        self._push_history(audio)

        if effect == "Normal":
            out = audio
        elif effect == "Feminize":
            out = self.pitch_shift_rt(audio, 1.38) * 1.05
        elif effect == "Masculinize":
            out = self.pitch_shift_rt(audio, 0.78) * 1.05
        elif effect == "Monster":
            pitched = self.pitch_shift_rt(audio, 0.58)
            out = np.tanh(pitched * 1.8) * 0.85
        elif effect == "Darth Vader":
            deep = self.pitch_shift_rt(audio, 0.62)
            deep, self.delay_idx = self.apply_delay(deep, self.delay_buf, self.delay_idx, 140, 0.3, 0.4)
            out = deep
        elif effect == "Alienize":
            high = self.pitch_shift_rt(audio, 1.65)
            t = np.arange(len(high)) / RATE
            carrier = np.sin(2 * np.pi * 28 * t)
            out = high * (0.65 + 0.35 * carrier)
        elif effect == "Chorus":
            out = audio.copy()
            d1, self.delay_idx = self.apply_delay(audio, self.delay_buf, self.delay_idx, 22, 0.25, 0.35)
            d2, self.idx2 = self.apply_delay(audio, self.delay2, self.idx2, 48, 0.22, 0.3)
            d3, self.idx3 = self.apply_delay(audio, self.delay3, self.idx3, 75, 0.18, 0.25)
            out = (audio * 0.5 + d1 + d2 + d3) * 0.55
        elif effect == "Lost Weight":
            high = self.pitch_shift_rt(audio, 1.2)
            out = np.diff(high, prepend=high[0]) * 1.4
        elif effect == "Disguised":
            p = self.pitch_shift_rt(audio, 1.12)
            c, self.delay_idx = self.apply_delay(p, self.delay_buf, self.delay_idx, 28, 0.18, 0.28)
            out = (p * 0.65 + c * 0.45) * 1.05
        elif effect == "Mexicanize":
            out = self.pitch_shift_rt(audio, 1.18) * 1.1
        elif effect == "Huge Crowd":
            out = np.zeros_like(audio)
            for g, d, pf in [(0.32, 18, 1.015), (0.28, 42, 0.985),
                             (0.25, 68, 1.04), (0.22, 98, 0.96), (0.2, 135, 1.0)]:
                pitched = self.pitch_shift_rt(audio, pf)
                delayed, _ = self.apply_delay(pitched, self.delay_buf, self.delay_idx, d, 0.12, 1.0)
                out += delayed * g
            out = np.tanh(out * 1.1)
        else:
            out = audio

        out = np.clip(out, -1.0, 1.0)
        return (out * 32767).astype(np.int16).tobytes()

    def callback(self, in_data, frame_count, time_info, status):
        try:
            out_data = self.process(in_data)
        except Exception:
            out_data = in_data
        return (out_data, pyaudio.paContinue)

    def start(self):
        if self.stream is not None:
            return
        self.stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, output=True, frames_per_buffer=CHUNK,
            stream_callback=self.callback
        )
        self.stream.start_stream()

    def stop(self):
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    # ---------- Sample recording ----------
    def start_recording(self):
        self.is_recording = True
        self.record_frames = []
        self.rec_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )

    def stop_recording(self):
        self.is_recording = False
        if hasattr(self, "rec_stream"):
            self.rec_stream.stop_stream()
            self.rec_stream.close()
        if self.record_frames:
            raw = b''.join(self.record_frames)
            self.recorded = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        else:
            self.recorded = None

    def record_chunk(self):
        if self.is_recording and hasattr(self, "rec_stream"):
            try:
                data = self.rec_stream.read(CHUNK, exception_on_overflow=False)
                self.record_frames.append(data)
            except Exception:
                pass

    def play_processed(self):
        if self.recorded is None:
            return
        processed = self.process_offline(self.recorded)
        # convert to int16 and play via pygame
        samples = (np.clip(processed, -1, 1) * 32767).astype(np.int16)
        # make stereo for pygame
        stereo = np.column_stack((samples, samples))
        sound = pygame.sndarray.make_sound(stereo)
        sound.play()

    def terminate(self):
        self.stop()
        if hasattr(self, "rec_stream"):
            try:
                self.rec_stream.close()
            except Exception:
                pass
        self.p.terminate()

# ---------------- GUI ----------------
def main():
    pygame.init()
    pygame.mixer.init(frequency=RATE, size=-16, channels=2)
    WIDTH, HEIGHT = 520, 680
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Voice Changer (Live + Sample)")
    font = pygame.font.SysFont("segoeui", 22)
    small_font = pygame.font.SysFont("segoeui", 18)
    clock = pygame.time.Clock()

    changer = VoiceChanger()

    list_x, list_y = 40, 40
    item_h = 38
    list_w = 280
    selected = 0

    btn_live = pygame.Rect(340, 40, 140, 50)
    btn_record = pygame.Rect(340, 110, 140, 50)
    btn_play = pygame.Rect(340, 180, 140, 50)
    live_text = "Start Live"
    record_text = "Record Sample"
    play_text = "Play Processed"

    recording_start = 0
    status_msg = "Ready"

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos

                # Voice list
                for i in range(len(VOICES)):
                    r = pygame.Rect(list_x, list_y + i * item_h, list_w, item_h - 4)
                    if r.collidepoint(mx, my):
                        selected = i
                        with changer.lock:
                            changer.selected = selected

                # Live button
                if btn_live.collidepoint(mx, my):
                    if not changer.running:
                        changer.running = True
                        changer.start()
                        live_text = "Stop Live"
                    else:
                        changer.running = False
                        changer.stop()
                        live_text = "Start Live"

                # Record button
                if btn_record.collidepoint(mx, my) and not changer.is_recording:
                    changer.start_recording()
                    recording_start = time.time()
                    record_text = "Recording..."
                    status_msg = f"Recording {RECORD_SECONDS}s..."

                # Play button
                if btn_play.collidepoint(mx, my) and changer.recorded is not None:
                    changer.play_processed()
                    status_msg = "Playing processed sample..."

        # Auto-stop recording
        if changer.is_recording and time.time() - recording_start >= RECORD_SECONDS:
            changer.stop_recording()
            record_text = "Record Sample"
            status_msg = "Sample recorded! Select a voice and press Play Processed."

        if changer.is_recording:
            changer.record_chunk()

        # Draw
        screen.fill((30, 30, 40))

        title = font.render("Voice Changer", True, (255, 255, 255))
        screen.blit(title, (40, 8))

        # List
        pygame.draw.rect(screen, (50, 50, 70), (list_x - 4, list_y - 4, list_w + 8, len(VOICES) * item_h + 8), border_radius=6)
        for i, name in enumerate(VOICES):
            color = (70, 130, 200) if i == selected else (60, 60, 80)
            r = pygame.Rect(list_x, list_y + i * item_h, list_w, item_h - 4)
            pygame.draw.rect(screen, color, r, border_radius=4)
            text = small_font.render(name, True, (255, 255, 255))
            screen.blit(text, (r.x + 12, r.y + 8))

        # Buttons
        def draw_btn(rect, text, active=False):
            col = (200, 60, 60) if active else (60, 160, 80)
            pygame.draw.rect(screen, col, rect, border_radius=8)
            pygame.draw.rect(screen, (255, 255, 255), rect, 2, border_radius=8)
            t = font.render(text, True, (255, 255, 255))
            screen.blit(t, t.get_rect(center=rect.center))

        draw_btn(btn_live, live_text, changer.running)
        draw_btn(btn_record, record_text, changer.is_recording)
        draw_btn(btn_play, play_text, changer.recorded is not None)

        # Status
        st = small_font.render(status_msg, True, (200, 220, 255))
        screen.blit(st, (40, 620))

        hint = small_font.render("Live = real-time | Sample = higher quality playback", True, (160, 160, 160))
        screen.blit(hint, (40, 645))

        pygame.display.flip()
        clock.tick(60)

    changer.terminate()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()