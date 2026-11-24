#!/usr/bin/env python3
"""
WordWheel - computer never gets stuck, never retries guessed letters
Used-phrase tracking, genre selection, radial labels, clacker, etc.
Requires: pygame
"""

import pygame
import random
import math
import os
import glob

CONFIG_FILE = "wordwheel.cfg"
DEFAULT_SIZE = (1280, 720)

def load_window_size():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                w, h = map(int, f.read().split())
                return max(800, w), max(600, h)
        except Exception:
            pass
    return DEFAULT_SIZE

def save_window_size(size):
    try:
        with open(CONFIG_FILE, "w") as f:
            f.write(f"{size[0]} {size[1]}")
    except Exception:
        pass

BASE_PUZZLES = [
    ("A PIECE OF CAKE", "Phrase"),
    ("ACTIONS SPEAK LOUDER THAN WORDS", "Phrase"),
    ("BETTER LATE THAN NEVER", "Phrase"),
    ("BLOOD IS THICKER THAN WATER", "Phrase"),
    ("GOOD THINGS COME TO THOSE WHO WAIT", "Phrase"),
    ("IT TAKES TWO TO TANGO", "Phrase"),
    ("NO NEWS IS GOOD NEWS", "Phrase"),
    ("YOU CANT JUDGE A BOOK BY ITS COVER", "Phrase"),
    ("KEEP IT SIMPLE", "Phrase"),
    ("MONEY TALKS", "Phrase"),
    ("WHAT GOES AROUND COMES AROUND", "Phrase"),
    ("BREAK A LEG", "Phrase"),
    ("EASY COME EASY GO", "Phrase"),
    ("HIT THE NAIL ON THE HEAD", "Phrase"),
    ("NO PAIN NO GAIN", "Phrase"),
]

def load_ww_files():
    subjects = {}
    for path in glob.glob("*.ww.txt"):
        category = os.path.splitext(os.path.basename(path))[0]
        if category.lower().endswith(".ww"):
            category = category[:-3]
        phrases = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        phrases.append(line.upper())
        except Exception:
            continue
        if phrases:
            subjects[category] = phrases
    return subjects

SUBJECTS = load_ww_files()

def load_used(filename):
    used = set()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        used.add(line.upper())
        except Exception:
            pass
    return used

def save_used(filename, used_set):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            for phrase in sorted(used_set):
                f.write(phrase + "\n")
    except Exception:
        pass

def generate_tone(frequency, duration, sample_rate=22050, volume=0.4):
    n_samples = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        sample = math.sin(2 * math.pi * frequency * t)
        val = int(volume * 32767 * sample)
        buf.extend(val.to_bytes(2, "little", signed=True))
    return pygame.mixer.Sound(buffer=buf)

def draw_radial_text(surf, text, cx, cy, mid_angle_deg, outer_radius, inner_radius=50):
    if not text:
        return
    text = str(text).upper()
    n = len(text)
    available = outer_radius - inner_radius - 12
    spacing = available / max(n, 1)
    for i, ch in enumerate(text):
        dist = (i + 0.45) * spacing
        r = outer_radius - 8 - dist
        if r < inner_radius:
            break
        size_ratio = r / outer_radius
        font_size = max(11, int(26 * size_ratio))
        font = pygame.font.SysFont("Arial", font_size, bold=True)
        char_surf = font.render(ch, True, (255, 255, 255))
        rotated = pygame.transform.rotate(char_surf, -(mid_angle_deg + 90))
        rad = math.radians(mid_angle_deg)
        px = cx + r * math.cos(rad)
        py = cy + r * math.sin(rad)
        rect = rotated.get_rect(center=(px, py))
        surf.blit(rotated, rect)

def create_wheel_graphic(values, radius):
    size = int(radius * 2 + 50)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    n = len(values)
    angle_step = 360 / n
    colors = [(180,40,40),(40,140,40),(40,80,180),(180,140,40),(140,40,140),(40,140,140),(180,80,40),(80,80,180)]
    for i, val in enumerate(values):
        start_deg = i * angle_step - 90
        end_deg = (i + 1) * angle_step - 90
        color = colors[i % len(colors)]
        points = [(cx, cy)]
        for a in range(int(start_deg), int(end_deg) + 1):
            rad = math.radians(a)
            points.append((cx + radius * math.cos(rad), cy + radius * math.sin(rad)))
        if len(points) > 2:
            pygame.draw.polygon(surf, color, points)
            pygame.draw.polygon(surf, (25,25,25), points, 2)
        mid_deg = start_deg + angle_step / 2
        label = str(val) if isinstance(val, int) else val
        draw_radial_text(surf, label, cx, cy, mid_deg, radius - 6, 55)
        pin_rad = math.radians(end_deg)
        px = cx + (radius - 5) * math.cos(pin_rad)
        py = cy + (radius - 5) * math.sin(pin_rad)
        pygame.draw.circle(surf, (230,230,230), (int(px), int(py)), 5)
    pygame.draw.circle(surf, (45,45,45), (cx, cy), int(radius * 0.14))
    pygame.draw.circle(surf, (200,200,200), (cx, cy), int(radius * 0.14), 3)
    return surf

class Player:
    def __init__(self, name, is_computer=False):
        self.name = name
        self.money = 0
        self.round_money = 0
        self.overall_score = 0
        self.is_computer = is_computer

class WordWheelGame:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        self.screen_size = load_window_size()
        self.screen = pygame.display.set_mode(self.screen_size, pygame.RESIZABLE)
        pygame.display.set_caption("WordWheel")
        self.clock = pygame.time.Clock()

        self.snd_ding = generate_tone(880, 0.15)
        self.snd_buzz = generate_tone(180, 0.25)
        self.snd_bell = generate_tone(660, 0.4)
        self.snd_whistle = generate_tone(1200, 0.3)
        self.snd_clack = generate_tone(420, 0.05, volume=0.3)

        self.wheel_values = [300,500,700,800,1000,1500,2000,2500,3000,5000,"Zero","Lose Turn",400,600,900,1200,1800,"Free Spin"]
        self.num_slices = len(self.wheel_values)
        self.slice_size = 360.0 / self.num_slices

        self.wheel_base = None
        self.wheel_radius = 200
        self.last_radius = 0
        self.clacker_angle = 0.0
        self.clacker_velocity = 0.0
        self.last_pin_hit = -999.0
        self.rebuild_wheel()

        self.running = True
        self.state = "menu"
        self.vs_computer = False
        self.genre_options = ["Default", "All"] + sorted(SUBJECTS.keys())
        self.puzzles = []
        self.used_phrases = set()
        self.used_file = None
        self.all_mode = False
        self.source_used = {}
        self.players = []
        self.current_player = 0
        self.puzzle = ""
        self.category = ""
        self.revealed = set()
        self.guessed = set()
        self.wheel_angle = 0.0
        self.spinning = False
        self.spin_speed = 0.0
        self.message = ""
        self.can_guess_letter = False
        self.solving = False
        self.solve_input = ""
        self.win_display_until = 0
        self.waiting_for_computer = False
        self.loser_starts_next = 0
        self.after_bonus = False
        self.pending_next = None

    def rebuild_wheel(self):
        w, h = self.screen.get_size()
        radius = max(170, int(w * 0.23))
        if abs(radius - self.last_radius) < 8 and self.wheel_base is not None:
            return
        self.wheel_radius = radius
        self.last_radius = radius
        self.wheel_base = create_wheel_graphic(self.wheel_values, radius)

    def get_fonts(self):
        w, h = self.screen.get_size()
        scale = min(w / 1280.0, h / 720.0)
        med = max(20, int(32 * scale))
        return (
            pygame.font.SysFont("Arial", max(28, int(48 * scale)), bold=True),
            pygame.font.SysFont("Arial", med),
            pygame.font.SysFont("Arial", max(14, int(22 * scale))),
            pygame.font.SysFont("Arial", max(14, int(med * 0.65))),
        )

    def build_puzzles(self, choice):
        self.puzzles = []
        self.used_phrases = set()
        self.used_file = None
        self.all_mode = False
        self.source_used = {}

        if choice == "Default":
            self.puzzles = list(BASE_PUZZLES)
            self.used_file = "phrase.used.txt"
            self.used_phrases = load_used(self.used_file)
        elif choice == "All":
            self.all_mode = True
            self.puzzles = list(BASE_PUZZLES)
            self.source_used["Phrase"] = load_used("phrase.used.txt")
            for cat, phs in SUBJECTS.items():
                for p in phs:
                    self.puzzles.append((p, cat))
                self.source_used[cat] = load_used(f"{cat}.used.txt")
        elif choice in SUBJECTS:
            for p in SUBJECTS[choice]:
                self.puzzles.append((p, choice))
            self.used_file = f"{choice}.used.txt"
            self.used_phrases = load_used(self.used_file)
        if not self.puzzles:
            self.puzzles = list(BASE_PUZZLES)
            self.used_file = "phrase.used.txt"
            self.used_phrases = load_used(self.used_file)

    def get_unused_puzzles(self):
        if self.all_mode:
            unused = []
            for phrase, cat in self.puzzles:
                used_set = self.source_used.get(cat, set())
                if phrase not in used_set:
                    unused.append((phrase, cat))
            return unused
        else:
            return [(p, c) for p, c in self.puzzles if p not in self.used_phrases]

    def mark_used(self, phrase, category):
        if self.all_mode:
            if category not in self.source_used:
                self.source_used[category] = set()
            self.source_used[category].add(phrase)
            fname = "phrase.used.txt" if category == "Phrase" else f"{category}.used.txt"
            save_used(fname, self.source_used[category])
        else:
            self.used_phrases.add(phrase)
            if self.used_file:
                save_used(self.used_file, self.used_phrases)

    def new_puzzle(self, bonus=False):
        unused = self.get_unused_puzzles()
        if not unused:
            if self.all_mode:
                for cat in list(self.source_used.keys()):
                    self.source_used[cat] = set()
                    fname = "phrase.used.txt" if cat == "Phrase" else f"{cat}.used.txt"
                    save_used(fname, set())
            else:
                self.used_phrases = set()
                if self.used_file:
                    save_used(self.used_file, set())
            unused = self.puzzles[:]

        self.puzzle, self.category = random.choice(unused)
        self.puzzle = self.puzzle.upper()
        self.mark_used(self.puzzle, self.category)

        self.revealed = set()
        self.guessed = set()
        for p in self.players:
            p.round_money = 0
        self.can_guess_letter = False
        self.solving = False
        self.current_player = self.loser_starts_next
        self.state = "bonus" if bonus else "play"
        self.message = "BONUS ROUND!" if bonus else f"Category: {self.category}"
        if self.players and self.players[self.current_player].is_computer:
            pygame.time.set_timer(pygame.USEREVENT + 1, 1500, loops=1)
            self.waiting_for_computer = True

    def start_game(self):
        self.players = [Player("You"), Player("Computer", True)] if self.vs_computer else [Player("Player 1"), Player("Player 2")]
        self.loser_starts_next = 0
        self.new_puzzle(False)
        self.snd_bell.play()

    def spin_wheel(self):
        if self.spinning or self.win_display_until:
            return
        self.spinning = True
        self.spin_speed = random.uniform(18, 28)
        self.can_guess_letter = False
        self.snd_whistle.play()

    def update_spin(self):
        if not self.spinning:
            return
        self.wheel_angle += self.spin_speed
        self.spin_speed *= 0.985

        relative = self.wheel_angle % self.slice_size
        if relative < 8 and self.spin_speed > 1.0 and abs(self.wheel_angle - self.last_pin_hit) > self.slice_size * 0.5:
            self.clacker_velocity = 14
            self.snd_clack.play()
            self.last_pin_hit = self.wheel_angle

        self.clacker_angle += self.clacker_velocity
        self.clacker_velocity *= 0.75
        self.clacker_angle *= 0.85

        if self.spin_speed < 0.4:
            self.spinning = False
            self.resolve_spin()

    def resolve_spin(self):
        sector = int(((-self.wheel_angle) % 360) / self.slice_size) % self.num_slices
        result = self.wheel_values[sector]
        player = self.players[self.current_player]
        if result in ("Zero", "Lose Turn"):
            if result == "Zero":
                player.round_money = 0
            self.message = str(result)
            self.snd_buzz.play()
            self.end_turn()
        elif result == "Free Spin":
            self.message = "Free Spin"
            if player.is_computer:
                pygame.time.set_timer(pygame.USEREVENT + 1, 1200, loops=1)
                self.waiting_for_computer = True
        else:
            self.current_value = result
            self.can_guess_letter = True
            self.message = f"${result} - guess a letter"
            self.snd_ding.play()
            if player.is_computer:
                pygame.time.set_timer(pygame.USEREVENT + 1, 1400, loops=1)
                self.waiting_for_computer = True

    def guess_letter(self, letter):
        if not self.can_guess_letter or letter in self.guessed or not letter.isalpha():
            return
        self.guessed.add(letter)
        self.can_guess_letter = False
        count = self.puzzle.count(letter)
        player = self.players[self.current_player]
        if count:
            self.revealed.add(letter)
            player.round_money += count * getattr(self, "current_value", 0)
            self.snd_ding.play()
            if all(c in self.revealed or not c.isalpha() for c in self.puzzle):
                self.solve_puzzle()
            elif player.is_computer:
                pygame.time.set_timer(pygame.USEREVENT + 1, 1200, loops=1)
                self.waiting_for_computer = True
        else:
            self.snd_buzz.play()
            self.end_turn()

    def solve_puzzle(self):
        player = self.players[self.current_player]
        mult = 4 if self.state == "bonus" else 1
        earned = player.round_money * mult
        player.money += earned
        self.message = f"{player.name} +${earned}"
        self.snd_bell.play()
        self.revealed = set(c for c in self.puzzle if c.isalpha())
        self.win_display_until = pygame.time.get_ticks() + 5000
        self.loser_starts_next = 1 - self.current_player
        self.after_bonus = self.state == "bonus"
        self.pending_next = "bonus" if (not self.after_bonus and random.random() < 0.3) else "normal"
        pygame.time.set_timer(pygame.USEREVENT + 4, 5000, loops=1)

    def end_turn(self):
        self.can_guess_letter = False
        self.current_player = 1 - self.current_player
        if self.players[self.current_player].is_computer:
            pygame.time.set_timer(pygame.USEREVENT + 1, 1300, loops=1)
            self.waiting_for_computer = True

    def computer_guess_letter(self):
        """Pick a letter the computer has not already tried. Never gets stuck."""
        all_letters = "RSTLNEAOIUDHBCFGJKMPQVWXYZ"
        available = [c for c in all_letters if c not in self.guessed]
        if not available:
            # No letters left — force end of turn or try to solve
            self.message = "Computer has no letters left"
            self.end_turn()
            return
        letter = random.choice(available)
        self.guess_letter(letter)

    def draw_outlined_text(self, font, text, color, outline_color, pos, outline_width=3):
        x, y = pos
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx*dx + dy*dy <= outline_width*outline_width:
                    outline = font.render(text, True, outline_color)
                    self.screen.blit(outline, (x + dx, y + dy))
        main = font.render(text, True, color)
        self.screen.blit(main, (x, y))

    def draw_wheel(self, cx, cy):
        rotated = pygame.transform.rotate(self.wheel_base, -self.wheel_angle)
        rect = rotated.get_rect(center=(cx, cy))
        self.screen.blit(rotated, rect)

        r = self.wheel_radius
        clacker_len = 22
        base_x = cx
        base_y = cy - r - 6
        tip_x = base_x + clacker_len * math.sin(math.radians(self.clacker_angle))
        tip_y = base_y + clacker_len * math.cos(math.radians(self.clacker_angle))
        pygame.draw.line(self.screen, (230, 190, 60), (base_x, base_y), (tip_x, tip_y), 5)
        pygame.draw.circle(self.screen, (190, 50, 50), (int(tip_x), int(tip_y)), 6)
        pygame.draw.circle(self.screen, (70, 70, 70), (int(base_x), int(base_y)), 4)

    def draw(self):
        self.screen.fill((20, 40, 80))
        w, h = self.screen.get_size()
        font_l, font_m, font_s, font_puzzle = self.get_fonts()

        title = font_l.render("WordWheel", True, (255, 215, 0))
        self.screen.blit(title, (w//2 - title.get_width()//2, 8))

        if self.state == "menu":
            self.screen.blit(font_m.render("1 - vs Computer", True, (255,255,255)), (w//2 - 110, h//2 - 60))
            self.screen.blit(font_m.render("2 - Two Players", True, (255,255,255)), (w//2 - 110, h//2 - 10))
        elif self.state == "genre":
            self.screen.blit(font_m.render("Choose Genre:", True, (255,255,255)), (40, 80))
            y = 140
            for i, opt in enumerate(self.genre_options):
                key = str(i+1) if i < 9 else "0"
                self.screen.blit(font_s.render(f"{key} - {opt}", True, (220,220,255)), (60, y))
                y += 36
            self.screen.blit(font_s.render("Press number to select", True, (180,180,180)), (60, y + 20))
        elif self.state in ("play", "bonus"):
            disp = " ".join(c if (c in self.revealed or not c.isalpha()) else "_" for c in self.puzzle)
            board = font_puzzle.render(disp, True, (255,255,255))
            self.screen.blit(board, (20, int(h * 0.15)))
            self.screen.blit(font_s.render(self.category, True, (200,200,120)), (20, int(h * 0.10)))

            bottom_y = h - 70
            guessed_txt = font_s.render("Guessed: " + " ".join(sorted(self.guessed)), True, (160,200,255))
            self.screen.blit(guessed_txt, (20, bottom_y))
            msg = font_s.render(self.message, True, (255,200,100))
            self.screen.blit(msg, (20, bottom_y - 32))

            box_w, box_h = 340, 110
            box_x = 20 + guessed_txt.get_width() + 40 + int(box_w * 1.4)
            max_x = w - box_w - 20
            centerish = w // 2 - box_w // 2
            box_x = min(max(box_x, centerish - 50), max_x)
            box_y = bottom_y - 30
            box = pygame.Rect(box_x, box_y, box_w, box_h)
            pygame.draw.rect(self.screen, (25, 45, 80), box)
            self.screen.blit(font_s.render("Scores / Round", True, (255,215,0)), (box.x + 8, box.y + 4))
            yy = box.y + 28
            for i, p in enumerate(self.players):
                color = (255, 255, 100) if i == self.current_player else (220, 220, 220)
                line = font_s.render(
                    f"{p.name}: {p.overall_score}pts  Tot${p.money}  Rnd${p.round_money}",
                    True, color
                )
                self.screen.blit(line, (box.x + 8, yy))
                yy += 26

            if self.solving:
                self.screen.blit(font_m.render("Type phrase: " + self.solve_input + "_", True, (255,255,140)), (20, int(h * 0.30)))

            wheel_cx = int(w * 0.73)
            wheel_cy = h // 2
            self.draw_wheel(wheel_cx, wheel_cy)

            if self.state == "bonus":
                self.screen.blit(font_m.render("BONUS x4", True, (255,100,100)), (20, int(h * 0.24)))

            if pygame.time.get_ticks() < self.win_display_until:
                win_text = "WINNER!"
                win_surf = font_l.render(win_text, True, (255, 255, 0))
                win_x = w//2 - win_surf.get_width()//2
                win_y = int(h * 0.38)
                self.draw_outlined_text(font_l, win_text, (255, 255, 0), (0, 0, 0), (win_x, win_y), outline_width=4)

        pygame.display.flip()

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    new_size = (max(800, event.w), max(600, event.h))
                    self.screen = pygame.display.set_mode(new_size, pygame.RESIZABLE)
                    save_window_size(new_size)
                    self.rebuild_wheel()
                elif event.type == pygame.KEYDOWN:
                    if self.state == "menu":
                        if event.key == pygame.K_1:
                            self.vs_computer = True
                            self.state = "genre"
                        elif event.key == pygame.K_2:
                            self.vs_computer = False
                            self.state = "genre"
                    elif self.state == "genre":
                        if event.unicode.isdigit():
                            idx = int(event.unicode) - 1
                            if event.unicode == "0":
                                idx = 9
                            if 0 <= idx < len(self.genre_options):
                                choice = self.genre_options[idx]
                                self.build_puzzles(choice)
                                self.start_game()
                    elif self.state in ("play", "bonus") and self.players and not self.players[self.current_player].is_computer:
                        if self.solving:
                            if event.key == pygame.K_RETURN:
                                guess = " ".join(self.solve_input.upper().split())
                                if guess == " ".join(self.puzzle.split()):
                                    self.solve_puzzle()
                                else:
                                    self.message = "Wrong!"
                                    self.solving = False
                                    self.end_turn()
                            elif event.key == pygame.K_BACKSPACE:
                                self.solve_input = self.solve_input[:-1]
                            elif event.unicode.isprintable():
                                self.solve_input += event.unicode.upper()
                        else:
                            if event.key == pygame.K_SPACE:
                                self.spin_wheel()
                            elif event.unicode.isalpha() and self.can_guess_letter:
                                self.guess_letter(event.unicode.upper())
                            elif event.key == pygame.K_RETURN:
                                self.solving = True
                                self.solve_input = ""
                elif event.type == pygame.USEREVENT + 1 and self.waiting_for_computer:
                    self.waiting_for_computer = False
                    if self.can_guess_letter:
                        self.computer_guess_letter()
                    else:
                        self.spin_wheel()
                elif event.type == pygame.USEREVENT + 4:
                    self.win_display_until = 0
                    if self.after_bonus:
                        winner = max(self.players, key=lambda p: p.money)
                        winner.overall_score += 1
                        self.after_bonus = False
                    self.new_puzzle(self.pending_next == "bonus")

            self.update_spin()
            self.draw()
            self.clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    WordWheelGame().run()