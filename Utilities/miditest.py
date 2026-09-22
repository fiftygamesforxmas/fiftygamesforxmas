#!/usr/bin/env python3
"""
MIDI Monitor (pygame GUI + pygame.midi)
No tkinter, no mido, no python-rtmidi.
"""

import sys
import time

import pygame
import pygame.midi


WINDOW_W, WINDOW_H = 960, 620
MARGIN = 12
TOP_H = 118
LOG_MAX = 400

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

CC_NAMES = {
    0: "Bank Select MSB",
    1: "Modulation",
    2: "Breath Controller",
    4: "Foot Controller",
    5: "Portamento Time",
    6: "Data Entry MSB",
    7: "Channel Volume",
    8: "Balance",
    10: "Pan",
    11: "Expression",
    64: "Sustain Pedal",
    65: "Portamento On/Off",
    66: "Sostenuto",
    67: "Soft Pedal",
    68: "Legato",
    71: "Filter Resonance",
    74: "Filter Cutoff",
    91: "Reverb Send",
    93: "Chorus Send",
    120: "All Sound Off",
    121: "Reset All Controllers",
    123: "All Notes Off",
}

COLORS = {
    "bg": (28, 30, 34),
    "panel": (40, 43, 48),
    "text": (230, 232, 235),
    "dim": (150, 154, 160),
    "btn": (70, 120, 200),
    "btn_off": (90, 90, 96),
    "btn_on": (40, 150, 80),
    "sel": (70, 120, 200),
    "logbg": (18, 19, 22),
    "NOTE ON": (90, 210, 110),
    "NOTE OFF": (160, 160, 160),
    "CONTROL CHANGE": (90, 160, 255),
    "PROGRAM CHANGE": (190, 130, 255),
    "PITCH BEND": (230, 170, 70),
    "CHANNEL AFTERTOUCH": (80, 190, 190),
    "POLY AFTERTOUCH": (80, 190, 190),
    "SYSEX": (230, 80, 80),
    "SYSTEM REALTIME": (130, 130, 130),
    "SYSTEM COMMON": (150, 150, 150),
    "OTHER": (220, 220, 220),
    "META": (180, 180, 180),
}


def decode_name(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def note_label(note_number):
    octave = (note_number // 12) - 1
    return f"{NOTE_NAMES[note_number % 12]}{octave} ({note_number})"


def classify_raw(status, data1, data2, data3):
    """Return (category, detail, channel_or_None). Channel is 1-16."""
    if status == 0xF0:
        return "SYSEX", f"sysex start  data1={data1} data2={data2}", None
    if status == 0xF7:
        return "SYSEX", "sysex end", None
    if status == 0xF1:
        return "SYSTEM COMMON", f"MTC quarter frame  value={data1}", None
    if status == 0xF2:
        pos = data1 | (data2 << 7)
        return "SYSTEM COMMON", f"song position  beats={pos}", None
    if status == 0xF3:
        return "SYSTEM COMMON", f"song select  song={data1}", None
    if status == 0xF6:
        return "SYSTEM COMMON", "tune request", None
    if status == 0xF8:
        return "SYSTEM REALTIME", "CLOCK", None
    if status == 0xFA:
        return "SYSTEM REALTIME", "START", None
    if status == 0xFB:
        return "SYSTEM REALTIME", "CONTINUE", None
    if status == 0xFC:
        return "SYSTEM REALTIME", "STOP", None
    if status == 0xFE:
        return "SYSTEM REALTIME", "ACTIVE SENSING", None
    if status == 0xFF:
        return "SYSTEM REALTIME", "RESET", None

    msg_type = status & 0xF0
    channel = (status & 0x0F) + 1

    if msg_type == 0x80:
        return "NOTE OFF", f"ch {channel}  {note_label(data1)}  vel={data2}", channel
    if msg_type == 0x90:
        if data2 == 0:
            return (
                "NOTE OFF",
                f"ch {channel}  {note_label(data1)}  vel=0 (note-off via note-on)",
                channel,
            )
        return "NOTE ON", f"ch {channel}  {note_label(data1)}  vel={data2}", channel
    if msg_type == 0xA0:
        return "POLY AFTERTOUCH", f"ch {channel}  {note_label(data1)}  pressure={data2}", channel
    if msg_type == 0xB0:
        name = CC_NAMES.get(data1, f"CC {data1}")
        return "CONTROL CHANGE", f"ch {channel}  {name}  value={data2}", channel
    if msg_type == 0xC0:
        return "PROGRAM CHANGE", f"ch {channel}  program={data1}", channel
    if msg_type == 0xD0:
        return "CHANNEL AFTERTOUCH", f"ch {channel}  pressure={data1}", channel
    if msg_type == 0xE0:
        value = data1 | (data2 << 7)
        signed = value - 8192
        return "PITCH BEND", f"ch {channel}  value={signed} (raw={value})", channel

    return "OTHER", f"status=0x{status:02X}  {data1} {data2} {data3}", channel


class Button:
    def __init__(self, rect, label, kind="normal"):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.kind = kind

    def draw(self, surface, font, listening=False):
        if self.kind == "listen":
            color = COLORS["btn_on"] if listening else COLORS["btn"]
        else:
            color = COLORS["btn_off"]
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        text = font.render(self.label, True, COLORS["text"])
        surface.blit(text, text.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class MidiMonitor:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("MIDI Monitor (pygame)")
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("menlo,consolas,monaco,monospace", 16)
        self.small = pygame.font.SysFont("menlo,consolas,monaco,monospace", 14)

        pygame.midi.init()

        self.inputs = []
        self.port_index = 0
        self.channel = 0
        self.show_clock = False
        self.listening = False
        self.midi_in = None
        self.log_lines = []
        self.scroll = 0

        y = MARGIN
        self.btn_refresh = Button((WINDOW_W - 210, y, 90, 32), "Refresh")
        self.btn_listen = Button((WINDOW_W - 110, y, 98, 32), "Start", kind="listen")
        self.btn_port_prev = Button((220, y, 36, 32), "<")
        self.btn_port_next = Button((WINDOW_W - 230, y, 36, 32), ">")

        y = MARGIN + 42
        self.btn_ch_prev = Button((220, y, 36, 32), "<")
        self.btn_ch_next = Button((360, y, 36, 32), ">")
        self.btn_clock = Button((420, y, 220, 32), "Clock: Off")
        self.btn_clear = Button((WINDOW_W - 110, y, 98, 32), "Clear")

        self.refresh_ports()
        self.add_log("META", "Ready. Select a port and click Start.")

    def add_log(self, category, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_lines.append((category, f"{stamp}  [{category:<18}]  {text}"))
        if len(self.log_lines) > LOG_MAX:
            self.log_lines = self.log_lines[-LOG_MAX:]
        self.scroll = max(0, len(self.log_lines) - self.visible_rows())

    def visible_rows(self):
        log_top = TOP_H + MARGIN
        log_h = WINDOW_H - log_top - MARGIN
        return max(1, log_h // 18)

    def refresh_ports(self):
        was_listening = self.listening
        self.stop_listen(quiet=True)

        pygame.midi.quit()
        pygame.midi.init()

        self.inputs = []
        for i in range(pygame.midi.get_count()):
            info = pygame.midi.get_device_info(i)
            if not info:
                continue
            interf, name, is_input, is_output, opened = info
            if is_input:
                label = f"{decode_name(name)}  [{decode_name(interf)}]"
                self.inputs.append((i, label))

        if self.port_index >= len(self.inputs):
            self.port_index = max(0, len(self.inputs) - 1)

        self.add_log("META", f"Found {len(self.inputs)} MIDI input port(s).")
        if was_listening:
            self.start_listen()

    def current_port(self):
        if not self.inputs:
            return None
        return self.inputs[self.port_index]

    def start_listen(self):
        port = self.current_port()
        if port is None:
            self.add_log("META", "No MIDI input ports available.")
            return
        device_id, name = port
        try:
            self.midi_in = pygame.midi.Input(device_id)
        except pygame.midi.MidiException as exc:
            self.add_log("META", f"Open failed: {exc}")
            self.midi_in = None
            return
        self.listening = True
        self.btn_listen.label = "Stop"
        self.add_log("META", f"--- started: {name} ---")

    def stop_listen(self, quiet=False):
        self.listening = False
        if hasattr(self, "btn_listen"):
            self.btn_listen.label = "Start"
        if self.midi_in is not None:
            try:
                self.midi_in.close()
            except Exception:
                pass
            del self.midi_in
            self.midi_in = None
        if not quiet:
            self.add_log("META", "--- stopped ---")

    def toggle_listen(self):
        if self.listening:
            self.stop_listen()
        else:
            self.start_listen()

    def poll_midi(self):
        if not self.listening or self.midi_in is None:
            return
        if not self.midi_in.poll():
            return
        events = self.midi_in.read(32)
        for event in events:
            data, timestamp = event
            status, data1, data2, data3 = data
            category, detail, channel = classify_raw(status, data1, data2, data3)

            if category == "SYSTEM REALTIME" and not self.show_clock:
                continue
            if self.channel != 0 and channel is not None and channel != self.channel:
                continue

            raw = f"{status:02X} {data1:02X} {data2:02X} {data3:02X}"
            self.add_log(category, f"{detail}    raw=[{raw}]  t={timestamp}")

    def handle_click(self, pos):
        if self.btn_refresh.hit(pos):
            self.refresh_ports()
        elif self.btn_listen.hit(pos):
            self.toggle_listen()
        elif self.btn_port_prev.hit(pos) and self.inputs:
            if self.listening:
                self.stop_listen()
            self.port_index = (self.port_index - 1) % len(self.inputs)
        elif self.btn_port_next.hit(pos) and self.inputs:
            if self.listening:
                self.stop_listen()
            self.port_index = (self.port_index + 1) % len(self.inputs)
        elif self.btn_ch_prev.hit(pos):
            self.channel = 16 if self.channel == 0 else self.channel - 1
        elif self.btn_ch_next.hit(pos):
            self.channel = 0 if self.channel == 16 else self.channel + 1
        elif self.btn_clock.hit(pos):
            self.show_clock = not self.show_clock
            self.btn_clock.label = "Clock: On" if self.show_clock else "Clock: Off"
        elif self.btn_clear.hit(pos):
            self.log_lines = []
            self.scroll = 0

    def draw(self):
        self.screen.fill(COLORS["bg"])

        self.screen.blit(self.font.render("MIDI Input Port:", True, COLORS["text"]), (MARGIN, MARGIN + 6))
        port = self.current_port()
        port_name = port[1] if port else "(no input ports found)"
        box = pygame.Rect(264, MARGIN, WINDOW_W - 510, 32)
        pygame.draw.rect(self.screen, COLORS["panel"], box, border_radius=6)
        self.screen.blit(self.small.render(port_name, True, COLORS["text"]), (box.x + 8, box.y + 7))
        self.btn_port_prev.draw(self.screen, self.font)
        self.btn_port_next.draw(self.screen, self.font)
        self.btn_refresh.draw(self.screen, self.font)
        self.btn_listen.draw(self.screen, self.font, listening=self.listening)

        y = MARGIN + 48
        self.screen.blit(self.font.render("Channel:", True, COLORS["text"]), (MARGIN, y + 6))
        ch_label = "All" if self.channel == 0 else str(self.channel)
        pygame.draw.rect(self.screen, COLORS["panel"], (264, y, 88, 32), border_radius=6)
        self.screen.blit(self.font.render(ch_label, True, COLORS["text"]), (276, y + 6))
        self.btn_ch_prev.draw(self.screen, self.font)
        self.btn_ch_next.draw(self.screen, self.font)
        self.btn_clock.draw(self.screen, self.font)
        self.btn_clear.draw(self.screen, self.font)

        status = "Listening" if self.listening else "Stopped"
        self.screen.blit(self.small.render(status, True, COLORS["dim"]), (MARGIN, TOP_H - 18))

        log_rect = pygame.Rect(MARGIN, TOP_H, WINDOW_W - 2 * MARGIN, WINDOW_H - TOP_H - MARGIN)
        pygame.draw.rect(self.screen, COLORS["logbg"], log_rect, border_radius=6)

        clip = self.screen.get_clip()
        self.screen.set_clip(log_rect.inflate(-8, -8))
        rows = self.visible_rows()
        start = self.scroll
        end = min(len(self.log_lines), start + rows + 2)
        for i, (category, text) in enumerate(self.log_lines[start:end]):
            color = COLORS.get(category, COLORS["OTHER"])
            y = log_rect.y + 6 + i * 18
            self.screen.blit(self.small.render(text, True, color), (log_rect.x + 8, y))
        self.screen.set_clip(clip)

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.MOUSEWHEEL:
                    self.scroll = max(0, min(self.scroll - event.y, max(0, len(self.log_lines) - 1)))

            self.poll_midi()
            self.draw()
            self.clock.tick(60)

        self.stop_listen(quiet=True)
        pygame.midi.quit()
        pygame.quit()


def main():
    try:
        MidiMonitor().run()
    except KeyboardInterrupt:
        pygame.midi.quit()
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()