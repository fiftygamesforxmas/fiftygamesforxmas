#!/usr/bin/env python3
"""Quiz player.

Usage:
    python3 quiz.py [quizfile.txt]

With no argument, load remedial.txt if it exists, otherwise default_quiz.txt.
"""

import json
import os
import random
import re
import sys
from pathlib import Path

import pygame

DEFAULT_SIZE = (1100, 760)
STATE_PATH = Path(__file__).with_name("quiz_window.json")
LAUNCH_ROOT = Path.cwd()
QUIZZES_DIR = LAUNCH_ROOT / "quizzes"
REMEDIAL_PATH = LAUNCH_ROOT / "remedial.txt"
DEFAULT_QUIZ = LAUNCH_ROOT / "default_quiz.txt"

BG = (18, 22, 28)
PANEL = (28, 34, 44)
TEXT = (236, 240, 245)
MUTED = (160, 170, 184)
ACCENT = (88, 166, 255)
GOOD = (72, 187, 120)
BAD = (240, 98, 98)
CHOICE = (40, 48, 62)
CHOICE_HOVER = (52, 64, 84)
BOX = (24, 30, 40)
STOP = (120, 64, 64)
LOAD = (46, 78, 112)


def collapse(text):
    return re.sub(r"\s+", " ", text.strip().lower())


def parse_quiz(path):
    questions = []
    current = {}
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.strip() == "---":
                if current:
                    questions.append(current)
                    current = {}
                continue
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            current[key] = value
    if current:
        questions.append(current)
    required = ("ID", "TYPE", "COMMAND", "QUESTION", "1", "2", "3", "4", "5", "ANSWER", "EXPLANATION")
    for q in questions:
        missing = [key for key in required if key not in q]
        if missing:
            raise ValueError(f"Question {q.get('ID', '?')} missing {', '.join(missing)}")
        answer = int(q["ANSWER"])
        if answer not in (1, 2, 3, 4, 5):
            raise ValueError(f"Question {q['ID']} ANSWER must be 1-5")
        accept_raw = [part.strip() for part in q.get("ACCEPT", "").split("|") if part.strip()]
        correct_text = q[str(answer)]
        if collapse(correct_text) not in [collapse(part) for part in accept_raw]:
            accept_raw.append(correct_text)
        q["ACCEPT_RAW"] = accept_raw
        q["ACCEPT"] = [collapse(part) for part in accept_raw]
        q["ANSWER"] = answer
        q["EXPLAINER"] = q.get("EXPLAINER", "").strip()
        q["ORIG"] = [q["1"], q["2"], q["3"], q["4"], q["5"]]
        q["ORIG_ANSWER"] = answer
    return questions


def wrap(font, text, max_width):
    words = text.split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        trial = current + " " + word
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def free_text_ok(user_text, accept_phrases):
    normalized = collapse(user_text)
    return any(phrase and phrase in normalized for phrase in accept_phrases)


def load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def save_state(screen, last_dir):
    data = load_state()
    w, h = screen.get_size()
    data["w"] = w
    data["h"] = h
    data["last_dir"] = str(last_dir)
    getter = getattr(pygame.display, "get_window_position", None)
    if callable(getter):
        try:
            x, y = getter()
            data["x"] = int(x)
            data["y"] = int(y)
        except pygame.error:
            pass
    STATE_PATH.write_text(json.dumps(data), encoding="utf-8")


def initial_directory(state):
    remembered = state.get("last_dir")
    if remembered and Path(remembered).is_dir():
        return Path(remembered)
    QUIZZES_DIR.mkdir(parents=True, exist_ok=True)
    return QUIZZES_DIR


def startup_quiz_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    if REMEDIAL_PATH.is_file():
        return REMEDIAL_PATH
    return DEFAULT_QUIZ


def write_remedial(failed, unanswered):
    lines = [
        "# QUIZ: Remedial",
        "# Incorrect answers, then unanswered questions, in source format.",
        "",
    ]
    for q in failed + unanswered:
        fields = [
            ("ID", q["ID"]),
            ("TYPE", q["TYPE"]),
            ("COMMAND", q["COMMAND"]),
            ("QUESTION", q["QUESTION"]),
            ("1", q["ORIG"][0]),
            ("2", q["ORIG"][1]),
            ("3", q["ORIG"][2]),
            ("4", q["ORIG"][3]),
            ("5", q["ORIG"][4]),
            ("ANSWER", q["ORIG_ANSWER"]),
        ]
        if q["ACCEPT_RAW"]:
            fields.append(("ACCEPT", " | ".join(q["ACCEPT_RAW"])))
        if q["EXPLAINER"]:
            fields.append(("EXPLAINER", q["EXPLAINER"]))
        fields.append(("EXPLANATION", q["EXPLANATION"]))
        for key, value in fields:
            lines.append(f"{key}: {value}")
        lines.append("---")
    REMEDIAL_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class Editor:
    def __init__(self):
        self.text = ""
        self.cursor = 0

    def clear(self):
        self.text = ""
        self.cursor = 0

    def handle(self, event):
        if event.key == pygame.K_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif event.key == pygame.K_RIGHT:
            self.cursor = min(len(self.text), self.cursor + 1)
        elif event.key == pygame.K_HOME:
            self.cursor = 0
        elif event.key == pygame.K_END:
            self.cursor = len(self.text)
        elif event.key == pygame.K_BACKSPACE and self.cursor:
            self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
            self.cursor -= 1
        elif event.key == pygame.K_DELETE:
            self.text = self.text[: self.cursor] + self.text[self.cursor + 1 :]
        elif event.unicode and event.unicode.isprintable():
            self.text = self.text[: self.cursor] + event.unicode + self.text[self.cursor :]
            self.cursor += 1

    def before_after(self):
        return self.text[: self.cursor], self.text[self.cursor :]


class FileDialog:
    def __init__(self, start_dir):
        self.directory = start_dir
        self.entries = []
        self.scroll = 0
        self.selected = None
        self.error = ""
        self.cancel_rect = None
        self.open_rect = None
        self.up_rect = None
        self.row_rects = []
        self.refresh()

    def refresh(self):
        self.selected = None
        self.row_rects = []
        items = []
        try:
            for entry in self.directory.iterdir():
                if entry.name.startswith("."):
                    continue
                if entry.is_dir() or entry.suffix.lower() == ".txt":
                    items.append(entry)
            items.sort(key=lambda path: (not path.is_dir(), path.name.lower()))
            self.error = ""
        except OSError as exc:
            items = []
            self.error = str(exc)
        self.entries = items

    def draw(self, screen, font, small):
        w, h = screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        screen.blit(overlay, (0, 0))
        panel = pygame.Rect(50, 50, w - 100, h - 100)
        pygame.draw.rect(screen, PANEL, panel, border_radius=10)
        screen.blit(font.render("Load quiz", True, TEXT), (panel.x + 16, panel.y + 14))
        screen.blit(small.render(str(self.directory), True, MUTED), (panel.x + 16, panel.y + 48))
        self.up_rect = pygame.Rect(panel.right - 150, panel.y + 14, 60, 30)
        self.open_rect = pygame.Rect(panel.right - 80, panel.bottom - 48, 64, 32)
        self.cancel_rect = pygame.Rect(panel.right - 160, panel.bottom - 48, 70, 32)
        pygame.draw.rect(screen, CHOICE, self.up_rect, border_radius=6)
        pygame.draw.rect(screen, ACCENT, self.open_rect, border_radius=6)
        pygame.draw.rect(screen, STOP, self.cancel_rect, border_radius=6)
        screen.blit(small.render("Up", True, TEXT), small.render("Up", True, TEXT).get_rect(center=self.up_rect.center))
        screen.blit(small.render("Open", True, TEXT), small.render("Open", True, TEXT).get_rect(center=self.open_rect.center))
        screen.blit(small.render("Cancel", True, TEXT), small.render("Cancel", True, TEXT).get_rect(center=self.cancel_rect.center))
        view = pygame.Rect(panel.x + 12, panel.y + 80, panel.width - 24, panel.height - 144)
        pygame.draw.rect(screen, BOX, view, border_radius=6)
        self.row_rects = []
        clip = screen.get_clip()
        screen.set_clip(view)
        y = view.y + 6 - self.scroll
        for path in self.entries:
            rect = pygame.Rect(view.x + 6, y, view.width - 12, 32)
            self.row_rects.append((path, rect))
            if path == self.selected:
                pygame.draw.rect(screen, CHOICE_HOVER, rect, border_radius=4)
            label = ("[dir] " if path.is_dir() else "") + path.name
            screen.blit(font.render(label, True, TEXT), (rect.x + 8, rect.y + 4))
            y += 36
        screen.set_clip(clip)
        self.max_scroll = max(0, len(self.entries) * 36 - view.height + 8)
        self.scroll = max(0, min(self.scroll, self.max_scroll))
        if self.error:
            screen.blit(small.render(self.error, True, BAD), (panel.x + 16, panel.bottom - 78))

    def click(self, pos):
        if self.cancel_rect and self.cancel_rect.collidepoint(pos):
            return "cancel"
        if self.up_rect and self.up_rect.collidepoint(pos):
            self.directory = self.directory.parent
            self.scroll = 0
            self.refresh()
            return None
        if self.open_rect and self.open_rect.collidepoint(pos):
            return self.activate()
        for path, rect in self.row_rects:
            if rect.collidepoint(pos):
                self.selected = path
                if path.is_dir():
                    self.directory = path
                    self.scroll = 0
                    self.refresh()
                return None
        return None

    def activate(self):
        if self.selected and self.selected.is_file():
            return self.selected
        return None

    def wheel(self, amount):
        self.scroll = max(0, min(self.max_scroll, self.scroll - amount * 36))


class QuizApp:
    def __init__(self, questions, source, last_dir):
        self.questions = questions
        self.source = str(source)
        self.last_dir = last_dir
        self.index = 0
        self.correct = 0
        self.answered = 0
        self.failed = []
        self.phase = "ask"
        self.editor = Editor()
        self.hover = None
        self.checked = False
        self.scroll = 0
        self.max_scroll = 0
        self.last_right = False
        self.last_detail = ""
        self.choice_rects = []
        self.check_rect = None
        self.continue_rect = None
        self.stop_rect = None
        self.load_rect = None
        self.dialog = None
        self.remedial_written = False
        self.message = ""
        random.shuffle(self.questions)
        self.deal()
        self.begin()

    def deal(self):
        for q in self.questions:
            hidden = random.choice([1, 2, 3, 4, 5])
            shown_ids = [n for n in (1, 2, 3, 4, 5) if n != hidden]
            random.shuffle(shown_ids)
            q["SHOWN_IDS"] = shown_ids
            q["SHOWN"] = {str(i + 1): q["ORIG"][n - 1] for i, n in enumerate(shown_ids)}
            q["DISPLAY_ANSWER"] = shown_ids.index(q["ORIG_ANSWER"]) + 1 if q["ORIG_ANSWER"] in shown_ids else None
            q["HIDDEN_CORRECT"] = q["DISPLAY_ANSWER"] is None

    def begin(self):
        if not self.questions or self.index >= len(self.questions):
            self.finish()
            return
        self.checked = False
        self.scroll = 0
        self.editor.clear()
        self.phase = "explainer" if self.question()["EXPLAINER"] else "ask"

    def question(self):
        return self.questions[self.index]

    def unanswered(self):
        if not self.questions or self.phase == "done":
            return []
        start = self.index if self.phase != "result" else self.index + 1
        return self.questions[start:]

    def finish(self, stop=False):
        if not self.remedial_written:
            write_remedial(self.failed, self.unanswered() if stop else [])
            self.remedial_written = True
        self.phase = "done"

    def load_new(self, path):
        if self.phase != "done":
            self.finish(stop=True)
        questions = parse_quiz(path)
        self.questions = questions
        self.source = str(path)
        self.last_dir = path.parent
        self.index = 0
        self.correct = 0
        self.answered = 0
        self.failed = []
        self.remedial_written = False
        self.message = ""
        self.dialog = None
        random.shuffle(self.questions)
        self.deal()
        self.begin()

    def draw_lines(self, screen, font, lines, x, y, color, gap=6, bottom=None):
        for line in lines:
            if bottom is not None and y > bottom:
                break
            surf = font.render(line, True, color)
            screen.blit(surf, (x, y))
            y += surf.get_height() + gap
        return y

    def draw_buttons(self, screen, small):
        w, _h = screen.get_size()
        self.load_rect = pygame.Rect(w - 310, 12, 132, 32)
        self.stop_rect = pygame.Rect(w - 168, 12, 132, 32)
        pygame.draw.rect(screen, LOAD, self.load_rect, border_radius=6)
        pygame.draw.rect(screen, STOP, self.stop_rect, border_radius=6)
        load = small.render("Load quiz", True, TEXT)
        stop = small.render("Stop quiz", True, TEXT)
        screen.blit(load, load.get_rect(center=self.load_rect.center))
        screen.blit(stop, stop.get_rect(center=self.stop_rect.center))

    def draw(self, screen, font, small, title, mono):
        screen.fill(BG)
        if self.phase == "done":
            header = f"{self.source}    final {self.correct}/{self.answered} answered"
        else:
            header = f"{self.source}    {self.correct}/{self.answered} correct    {self.index + 1}/{max(1, len(self.questions))}"
        screen.blit(small.render(header, True, MUTED), (36, 18))
        self.draw_buttons(screen, small)
        if self.phase == "done":
            self.draw_done(screen, font, small, title)
        elif self.phase == "explainer":
            self.draw_explainer(screen, font, small, title)
        elif self.questions:
            self.draw_question(screen, font, small, title, mono)
        else:
            screen.blit(title.render(self.message or "No quiz loaded.", True, TEXT), (36, 160))
        if self.dialog:
            self.dialog.draw(screen, font, small)
        pygame.display.flip()

    def draw_explainer(self, screen, font, small, title):
        w, h = screen.get_size()
        q = self.question()
        y = 58
        y = self.draw_lines(screen, title, wrap(title, "Read the explainer", w - 80), 36, y, TEXT)
        y = self.draw_lines(screen, small, wrap(small, q["COMMAND"], w - 80), 36, y + 6, ACCENT)
        view = pygame.Rect(36, y + 12, w - 72, h - y - 130)
        pygame.draw.rect(screen, PANEL, view, border_radius=8)
        lines = wrap(font, q["EXPLAINER"], view.width - 28)
        clip = screen.get_clip()
        screen.set_clip(view.inflate(-8, -8))
        text_y = view.y + 12 - self.scroll
        for line in lines:
            screen.blit(font.render(line, True, TEXT), (view.x + 14, text_y))
            text_y += 30
        screen.set_clip(clip)
        self.max_scroll = max(0, len(lines) * 30 - view.height + 20)
        self.scroll = max(0, min(self.scroll, self.max_scroll))
        self.check_rect = pygame.Rect(36, h - 78, 28, 28)
        pygame.draw.rect(screen, BOX, self.check_rect, border_radius=4)
        pygame.draw.rect(screen, ACCENT, self.check_rect, 2, border_radius=4)
        if self.checked:
            pygame.draw.line(screen, GOOD, (42, h - 64), (48, h - 56), 3)
            pygame.draw.line(screen, GOOD, (48, h - 56), (58, h - 70), 3)
        screen.blit(font.render("I have read this", True, TEXT), (74, h - 76))
        self.continue_rect = pygame.Rect(w - 220, h - 82, 180, 40)
        color = ACCENT if self.checked else (70, 78, 90)
        pygame.draw.rect(screen, color, self.continue_rect, border_radius=8)
        label = font.render("Continue", True, TEXT if self.checked else MUTED)
        screen.blit(label, label.get_rect(center=self.continue_rect.center))

    def draw_question(self, screen, font, small, title, mono):
        w, h = screen.get_size()
        q = self.question()
        y = 52
        hidden = "Correct answer is hidden; use Other." if q["HIDDEN_CORRECT"] else "Correct answer may be on screen."
        y = self.draw_lines(screen, small, [f"ID {q['ID']}  ·  {q['TYPE']}  ·  {hidden}"], 36, y, ACCENT)
        y = self.draw_lines(screen, mono, wrap(mono, q["COMMAND"], w - 80), 36, y + 2, (186, 214, 255))
        prompt = f"{q['QUESTION']} (choose 1-4 or other)"
        y = self.draw_lines(screen, title, wrap(title, prompt, w - 80), 36, y + 10, TEXT, gap=4)
        self.choice_rects = []
        y += 16
        row_h = 52 if h < 760 else 60
        labels = [(str(i), q["SHOWN"][str(i)]) for i in range(1, 5)]
        labels.append(("5", "Other (type your own answer)"))
        for key, text in labels:
            rect = pygame.Rect(36, y, w - 72, row_h)
            if rect.bottom > h - 16:
                break
            self.choice_rects.append((key, rect))
            color = CHOICE_HOVER if self.hover == key and self.phase == "ask" else CHOICE
            pygame.draw.rect(screen, color, rect, border_radius=8)
            screen.blit(font.render(f"{key}.  {text}", True, TEXT), (rect.x + 16, rect.y + 14))
            y += row_h + 8
        if self.phase == "other":
            self.draw_editor(screen, font, small, y)
        elif self.phase == "result":
            color = GOOD if self.last_right else BAD
            label = "Correct" if self.last_right else "Incorrect"
            screen.blit(title.render(label, True, color), (36, y))
            y += 38
            y = self.draw_lines(screen, font, wrap(font, self.last_detail, w - 80), 36, y, TEXT)
            self.draw_lines(screen, small, wrap(small, q["EXPLANATION"], w - 80), 36, y + 6, MUTED, bottom=h - 36)
            screen.blit(small.render("Enter, Space, or click for the next question.", True, ACCENT), (36, h - 32))

    def draw_editor(self, screen, font, small, y):
        w, _h = screen.get_size()
        box = pygame.Rect(36, y, w - 72, 46)
        pygame.draw.rect(screen, PANEL, box, border_radius=8)
        pygame.draw.rect(screen, ACCENT, box, 2, border_radius=8)
        before, after = self.editor.before_after()
        shown = font.render(before, True, TEXT)
        rest = font.render(after, True, TEXT)
        screen.blit(shown, (box.x + 12, box.y + 10))
        caret_x = box.x + 12 + shown.get_width()
        pygame.draw.line(screen, TEXT, (caret_x, box.y + 8), (caret_x, box.bottom - 8), 2)
        screen.blit(rest, (caret_x + 2, box.y + 10))
        screen.blit(small.render("Arrow keys move the cursor. Enter submits. Esc cancels.", True, MUTED), (36, box.bottom + 8))

    def draw_done(self, screen, font, small, title):
        total = len(self.questions)
        self.draw_lines(screen, title, [f"Score: {self.correct} / {self.answered} answered, {total} in quiz"], 36, 160, TEXT)
        screen.blit(font.render(f"Saved to {REMEDIAL_PATH}", True, MUTED), (36, 230))
        screen.blit(small.render("Load quiz starts another file. Esc quits.", True, MUTED), (36, 280))

    def grade(self, choice, free_text=None):
        q = self.question()
        self.answered += 1
        correct_text = q["ORIG"][q["ORIG_ANSWER"] - 1]
        if choice == "5":
            self.last_right = free_text_ok(free_text or "", q["ACCEPT"])
            self.last_detail = f"You typed: {free_text}. Correct answer: {correct_text}"
        else:
            picked = q["SHOWN_IDS"][int(choice) - 1]
            self.last_right = picked == q["ORIG_ANSWER"]
            self.last_detail = f"Correct answer: {correct_text}"
        if self.last_right:
            self.correct += 1
        else:
            self.failed.append(q)
        self.phase = "result"

    def advance(self):
        self.index += 1
        self.begin()

    def open_dialog(self):
        self.dialog = FileDialog(self.last_dir if self.last_dir.is_dir() else QUIZZES_DIR)

    def run(self, screen, clock, font, small, title, mono):
        try:
            while True:
                self.hover = None
                if self.phase == "ask" and not self.dialog:
                    mouse = pygame.mouse.get_pos()
                    for key, rect in self.choice_rects:
                        if rect.collidepoint(mouse):
                            self.hover = key
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type in (pygame.VIDEORESIZE, pygame.WINDOWRESIZED):
                        size = event.size if hasattr(event, "size") else (event.x, event.y)
                        screen = pygame.display.set_mode(size, pygame.RESIZABLE)
                        save_state(screen, self.last_dir)
                    if self.dialog:
                        if event.type == pygame.MOUSEWHEEL:
                            self.dialog.wheel(event.y)
                        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            result = self.dialog.click(event.pos)
                            if result == "cancel":
                                self.dialog = None
                            elif isinstance(result, Path):
                                try:
                                    self.load_new(result)
                                except (OSError, ValueError) as exc:
                                    self.dialog.error = str(exc)
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                            self.dialog = None
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                            chosen = self.dialog.activate()
                            if chosen:
                                try:
                                    self.load_new(chosen)
                                except (OSError, ValueError) as exc:
                                    self.dialog.error = str(exc)
                        continue
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self.load_rect and self.load_rect.collidepoint(event.pos):
                            self.open_dialog()
                            continue
                        if self.phase != "done" and self.stop_rect and self.stop_rect.collidepoint(event.pos):
                            self.finish(stop=True)
                            continue
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                        if self.phase == "other":
                            self.phase = "ask"
                            self.editor.clear()
                        else:
                            return
                    if self.phase == "explainer":
                        if event.type == pygame.MOUSEWHEEL:
                            self.scroll = max(0, min(self.max_scroll, self.scroll - event.y * 30))
                        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            if self.check_rect and self.check_rect.collidepoint(event.pos):
                                self.checked = not self.checked
                            elif self.checked and self.continue_rect and self.continue_rect.collidepoint(event.pos):
                                self.phase = "ask"
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                            self.checked = not self.checked
                        elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN and self.checked:
                            self.phase = "ask"
                    elif self.phase == "ask":
                        if event.type == pygame.KEYDOWN and event.unicode in "12345":
                            if event.unicode == "5":
                                self.phase = "other"
                                self.editor.clear()
                            else:
                                self.grade(event.unicode)
                        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hover:
                            if self.hover == "5":
                                self.phase = "other"
                                self.editor.clear()
                            else:
                                self.grade(self.hover)
                    elif self.phase == "other" and event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN:
                            self.grade("5", self.editor.text)
                        else:
                            self.editor.handle(event)
                    elif self.phase == "result":
                        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self.advance()
                        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            if not (self.stop_rect and self.stop_rect.collidepoint(event.pos)):
                                if not (self.load_rect and self.load_rect.collidepoint(event.pos)):
                                    self.advance()
                self.draw(screen, font, small, title, mono)
                clock.tick(60)
        finally:
            if not self.remedial_written and self.questions:
                self.finish(stop=self.phase != "done")
            save_state(screen, self.last_dir)
            pygame.quit()


def main():
    state = load_state()
    if "x" in state and "y" in state:
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{int(state['x'])},{int(state['y'])}"
    else:
        os.environ["SDL_VIDEO_WINDOW_POS"] = "80,60"
    size = (max(720, int(state.get("w", DEFAULT_SIZE[0]))), max(520, int(state.get("h", DEFAULT_SIZE[1]))))
    pygame.init()
    pygame.display.set_caption("Quiz")
    screen = pygame.display.set_mode(size, pygame.RESIZABLE)
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("segoeui", 22)
    small = pygame.font.SysFont("segoeui", 18)
    title = pygame.font.SysFont("segoeui", 28, bold=True)
    mono = pygame.font.SysFont("consolas", 18)
    last_dir = initial_directory(state)
    path = startup_quiz_path()
    message = ""
    questions = []
    try:
        if path.is_file():
            questions = parse_quiz(path)
        else:
            message = f"No quiz file found. Looked for {path}"
    except (OSError, ValueError) as exc:
        message = str(exc)
    app = QuizApp(questions, path, last_dir)
    app.message = message
    if not questions:
        app.phase = "done"
        app.remedial_written = True
    app.run(screen, clock, font, small, title, mono)


if __name__ == "__main__":
    main()