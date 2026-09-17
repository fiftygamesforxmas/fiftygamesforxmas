#!/usr/bin/env python3
"""Candiquator — pygame candy-equation drop with shapes, falls, bombs."""

import json
import math
import os
import random
import sys
import array

import pygame

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".candiquator.json")
TEXT_TRIES_START = 10
CLEAR_GOAL = 50
FALL_MS_PER_CELL = 300.0

LEVELS = {
    1: {"add": 20, "mul": 50, "matches": 20, "seconds": 10 * 60},
    2: {"add": 50, "mul": 100, "matches": 15, "seconds": 8 * 60},
    3: {"add": 100, "mul": 300, "matches": 10, "seconds": 5 * 60},
    4: {"add": 500, "mul": 1024, "matches": 5, "seconds": 4 * 60},
}

PALETTE = [
    ((255, 77, 109), (255, 143, 163), (139, 0, 32)),
    ((76, 201, 240), (144, 224, 239), (0, 119, 182)),
    ((128, 185, 24), (181, 228, 140), (36, 85, 1)),
    ((255, 183, 3), (255, 224, 138), (179, 107, 0)),
    ((155, 93, 229), (199, 125, 255), (90, 24, 154)),
    ((247, 37, 133), (255, 153, 200), (157, 2, 8)),
]

SHAPES = ("circle", "oval", "lifesaver", "pretzel")
STRIPE_STYLES = (None, "horiz", "diag", "cross")

OPS = [
    ("+", lambda a, b: a + b, "Addition"),
    ("-", lambda a, b: a - b, "Subtraction"),
    ("x", lambda a, b: a * b, "Multiplication"),
    ("/", lambda a, b: a // b if b and a % b == 0 else None, "Division"),
]


def load_cfg():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def sdl_window():
    try:
        from pygame._sdl2.video import Window
        return Window.from_display_module()
    except Exception:
        return None


def parse_start_level(argv):
    if len(argv) < 2:
        return 1
    try:
        lv = int(argv[1])
    except ValueError:
        print("Usage: python3 Candiquator.py [level]")
        print("Level default is 1. Valid levels: 1-4")
        sys.exit(1)
    return max(1, min(4, lv))


def make_tone(freq, ms, vol=0.35, decay=True):
    sr = 22050
    n = int(sr * ms / 1000)
    buf = array.array("h")
    for i in range(n):
        t = i / sr
        env = (1.0 - i / n) ** 1.6 if decay else 1.0
        sample = int(vol * env * 32767 * math.sin(2 * math.pi * freq * t))
        buf.append(max(-32767, min(32767, sample)))
    return pygame.mixer.Sound(buffer=buf)


def make_soft_boom(ms=900, vol=0.16):
    sr = 22050
    n = int(sr * ms / 1000)
    buf = array.array("h")
    lp = 0.0
    for i in range(n):
        t = i / sr
        env = math.exp(-t * 3.2)
        rumble = (
            0.55 * math.sin(2 * math.pi * 58 * t)
            + 0.28 * math.sin(2 * math.pi * 92 * t)
            + 0.12 * math.sin(2 * math.pi * 41 * t)
        )
        noise = random.random() * 2 - 1
        lp = lp * 0.86 + noise * 0.14
        sample = int(vol * env * 32767 * (rumble + 0.22 * lp))
        buf.append(max(-32767, min(32767, sample)))
    return pygame.mixer.Sound(buffer=buf)


def blit_outlined(surf, font, text, color, outline, center):
    base = font.render(text, True, color)
    ring = font.render(text, True, outline)
    cx, cy = center
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        r = ring.get_rect(center=(cx + dx, cy + dy))
        surf.blit(ring, r)
    surf.blit(base, base.get_rect(center=(cx, cy)))


class Candy:
    def __init__(self, kind, value, bomb=False):
        self.kind = kind
        self.value = value
        self.bomb = bomb
        self.shape = random.choice(SHAPES)
        self.bow = random.random() < 0.28
        self.stripes = random.choice(STRIPE_STYLES)
        self.swirl = random.random() < 0.22
        self.dots = random.random() < 0.28
        self.translucent = random.random() < 0.20
        self.dot_color = random.choice(PALETTE)[0]
        self.swirl_color = random.choice(PALETTE)[1]
        self.visual_y = None
        if bomb:
            self.shape = "circle"
            self.bow = False
            self.stripes = None
            self.swirl = False
            self.dots = False
            self.translucent = False


class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        ang = random.uniform(0, math.tau)
        spd = random.uniform(2, 9)
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd - 3
        self.life = random.randint(18, 36)
        self.color = color
        self.r = random.randint(2, 6)


class Sparkle:
    def __init__(self, r, c):
        self.r, self.c = r, c
        self.ang = random.uniform(0, math.tau)
        self.rad = random.uniform(0.15, 0.7)
        self.life = random.randint(16, 28)
        self.max_life = self.life
        self.size = random.randint(2, 5)


class Game:
    def __init__(self, start_level=1):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Candiquator")
        cfg = load_cfg()
        w = max(int(cfg.get("w", 920)), 640)
        h = max(int(cfg.get("h", 780)), 520)
        self.screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        self.win = sdl_window()
        if self.win is not None and cfg.get("x") is not None:
            try:
                self.win.position = (int(cfg["x"]), int(cfg["y"]))
            except Exception:
                pass
        self.clock = pygame.time.Clock()
        self.snd_pop = make_tone(660, 140, 0.18)
        self.snd_ok = make_tone(740, 220, 0.16)
        self.snd_bad = make_tone(180, 260, 0.16)
        self.snd_boom = make_soft_boom(1100, 0.18)
        self.snd_fuse = make_tone(90, 160, 0.06, decay=True)
        self.op_i = 0
        self.score = 0
        self.level = start_level
        self.tries = TEXT_TRIES_START
        self.cleared = 0
        self.selected = []
        self.over = False
        self.msg = ""
        self.typed = ""
        self.entry_focus = False
        self.particles = []
        self.sparkles = []
        self.fuse_tick = 0
        self.round_end = 0
        self.rows, self.cols = 5, 5
        self.grid = []
        self.new_board()

    def grid_size(self):
        if self.level <= 1:
            return 5, 5
        if self.level == 2:
            return 7, 7
        return 10, 10

    def rules(self):
        return LEVELS.get(self.level, LEVELS[4])

    def cap(self):
        ru = self.rules()
        return ru["add"] if self.op()[0] in ("+", "-") else ru["mul"]

    def min_matches(self):
        return self.rules()["matches"]

    def op(self):
        return OPS[self.op_i]

    def persist(self):
        w, h = self.screen.get_size()
        data = {"w": w, "h": h}
        if self.win is not None:
            try:
                data["x"], data["y"] = self.win.position
            except Exception:
                pass
        save_cfg(data)

    def make_triple(self):
        s = self.op()[0]
        cap = self.cap()
        if s == "+":
            a = random.randint(1, max(1, cap - 1))
            b = random.randint(1, max(1, cap - a))
            return a, b, a + b
        if s == "-":
            c = random.randint(1, max(1, cap - 1))
            b = random.randint(1, max(1, cap - c))
            return b + c, b, c
        if s == "x":
            a = random.randint(1, int(math.sqrt(cap)) + 1)
            bmax = max(1, cap // a)
            b = random.randint(1, bmax)
            return a, b, a * b
        b = random.randint(1, max(1, int(math.sqrt(cap))))
        c = random.randint(1, max(1, cap // b))
        return b * c, b, c

    def rand_val(self):
        return random.randint(1, self.cap())

    def spawn(self, bomb=False, kind=None, value=None, from_above=False):
        k = random.randrange(len(PALETTE)) if kind is None else kind
        v = self.rand_val() if value is None else value
        candy = Candy(k, v, bomb=bomb)
        if from_above:
            candy.visual_y = -1.5 - random.random() * 3
        return candy

    def occupied(self):
        return [(r, c) for r in range(self.rows) for c in range(self.cols) if self.grid[r][c]]

    def compute(self, a, b):
        return self.op()[1](a, b)

    def count_matches(self):
        cells = self.occupied()
        by_val = {}
        for r, c in cells:
            by_val.setdefault(self.grid[r][c].value, []).append((r, c))
        seen = set()
        n = len(cells)
        for i in range(n):
            r1, c1 = cells[i]
            a = self.grid[r1][c1].value
            for j in range(i + 1, n):
                r2, c2 = cells[j]
                b = self.grid[r2][c2].value
                for aa, bb in ((a, b), (b, a)):
                    res = self.compute(aa, bb)
                    if res is None:
                        continue
                    for rr, cc in by_val.get(res, []):
                        if (rr, cc) in ((r1, c1), (r2, c2)):
                            continue
                        seen.add(frozenset(((r1, c1), (r2, c2), (rr, cc))))
        return len(seen)

    def has_move(self):
        return self.count_matches() > 0

    def plant_triple(self):
        cells = self.occupied()
        if len(cells) < 3:
            return False
        a, b, c = self.make_triple()
        p = random.sample(cells, 3)
        self.grid[p[0][0]][p[0][1]].value = a
        self.grid[p[1][0]][p[1][1]].value = b
        self.grid[p[2][0]][p[2][1]].value = c
        return True

    def ensure_matches(self, target=None):
        need = self.min_matches() if target is None else target
        guard = 0
        while self.count_matches() < need and guard < 80:
            self.plant_triple()
            guard += 1

    def start_timer(self):
        self.round_end = pygame.time.get_ticks() + self.rules()["seconds"] * 1000

    def time_left_ms(self):
        return max(0, self.round_end - pygame.time.get_ticks())

    def new_board(self):
        self.rows, self.cols = self.grid_size()
        self.grid = [[None] * self.cols for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                bomb = random.random() < 0.04
                self.grid[r][c] = self.spawn(bomb=bomb, from_above=True)
                self.grid[r][c].visual_y = r - self.rows - random.random() * 2
        self.ensure_matches()
        self.selected = []
        self.cleared = 0
        self.over = False
        self.sparkles = []
        self.start_timer()
        ru = self.rules()
        self.msg = (
            f"Level {self.level} {self.op()[2]} {self.rows}x{self.cols}! "
            f"Remove {CLEAR_GOAL} candies. At least {ru['matches']} matches."
        )

    def layout(self):
        w, h = self.screen.get_size()
        top, bot, pad = 56, 118, 10
        gw, gh = w - pad * 2, h - top - bot - pad
        return top, bot, pad, gw / self.cols, gh / self.rows

    def cell_center(self, r, c, visual_r=None):
        top, bot, pad, cw, ch = self.layout()
        rr = visual_r if visual_r is not None else r
        return pad + c * cw + cw / 2, top + pad + rr * ch + ch / 2

    def cell_at(self, mx, my):
        top, bot, pad, cw, ch = self.layout()
        c = int((mx - pad) / cw)
        r = int((my - top - pad) / ch)
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return r, c
        return None

    def ui_rects(self):
        w, h = self.screen.get_size()
        y = h - 92
        label_w = 210
        entry = pygame.Rect(16 + label_w, y, 120, 36)
        eq = pygame.Rect(entry.right + 10, y, 52, 36)
        clr = pygame.Rect(eq.right + 10, y, 130, 36)
        return entry, eq, clr

    def click(self, pos):
        if self.over:
            return
        entry, eq, clr = self.ui_rects()
        if entry.collidepoint(pos):
            self.entry_focus = True
            return
        if eq.collidepoint(pos):
            self.entry_focus = False
            self.use_text()
            return
        if clr.collidepoint(pos):
            self.entry_focus = False
            self.selected = []
            return
        self.entry_focus = False
        hit = self.cell_at(*pos)
        if not hit:
            return
        r, c = hit
        if not self.grid[r][c]:
            return
        if (r, c) in self.selected:
            self.selected.remove((r, c))
            return
        if len(self.selected) >= 3:
            self.selected = []
        self.selected.append((r, c))
        if len(self.selected) == 3:
            self.try_triple(list(self.selected))

    def try_triple(self, cells):
        (r1, c1), (r2, c2), (r3, c3) = cells
        a = self.grid[r1][c1].value
        b = self.grid[r2][c2].value
        c = self.grid[r3][c3].value
        res = self.compute(a, b)
        s = self.op()[0]
        if res is None or res != c:
            self.msg = f"Nope: {a} {s} {b} != {c}"
            self.snd_bad.play()
            self.selected = []
            return
        same = self.grid[r1][c1].kind == self.grid[r2][c2].kind == self.grid[r3][c3].kind
        self.resolve(cells, same)

    def use_text(self):
        if self.over:
            return
        if self.tries <= 0:
            self.msg = "No text-entry tries left."
            return
        if len(self.selected) != 2:
            self.msg = "Select exactly 2 candies, then type candy1 OP candy2."
            return
        try:
            typed = int(self.typed.strip())
        except ValueError:
            self.msg = "Type a whole number."
            return
        (r1, c1), (r2, c2) = self.selected
        a = self.grid[r1][c1].value
        b = self.grid[r2][c2].value
        res = self.compute(a, b)
        s = self.op()[0]
        self.tries -= 1
        self.typed = ""
        if res is None or res != typed:
            self.msg = f"Wrong: {a} {s} {b} != {typed}. Tries: {self.tries}"
            self.snd_bad.play()
            self.check_over()
            return
        same = self.grid[r1][c1].kind == self.grid[r2][c2].kind
        self.resolve([(r1, c1), (r2, c2)], same)

    def explode_around(self, cells):
        extra = set()
        for r, c in cells:
            cell = self.grid[r][c]
            if not cell or not cell.bomb:
                continue
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    rr, cc = r + dr, c + dc
                    if 0 <= rr < self.rows and 0 <= cc < self.cols and self.grid[rr][cc]:
                        extra.add((rr, cc))
            x, y = self.cell_center(r, c)
            for _ in range(28):
                self.particles.append(Particle(x, y, random.choice(((255, 80, 40), (255, 200, 40), (40, 40, 40)))))
        if extra:
            self.snd_boom.play()
        return extra

    def burst(self, r, c):
        cell = self.grid[r][c]
        x, y = self.cell_center(r, c)
        col = PALETTE[cell.kind][0] if cell else (255, 255, 255)
        for _ in range(10):
            self.particles.append(Particle(x, y, col))

    def drop_bomb_from_sky(self):
        col = random.choice(range(self.cols))
        bomb = self.spawn(bomb=True, from_above=True)
        bomb.visual_y = -2
        placed = False
        for r in range(self.rows):
            if self.grid[r][col] is None:
                self.grid[r][col] = bomb
                placed = True
                break
        if not placed:
            self.grid[0][col] = bomb
        self.msg += "  A cherry bomb drops!"

    def resolve(self, cells, same_color):
        boom_extra = self.explode_around(cells)
        doomed = set(cells) | boom_extra
        pts = 0
        n = 0
        for r, c in doomed:
            cell = self.grid[r][c]
            if not cell:
                continue
            pts += abs(cell.value)
            self.burst(r, c)
            self.grid[r][c] = None
            n += 1
        self.cleared += n
        self.score += pts * (2 if same_color else 1) * self.level
        extra = " Same color! +1 try and a cherry bomb." if same_color else ""
        if same_color:
            self.tries += 1
        self.selected = []
        left = max(0, CLEAR_GOAL - self.cleared)
        self.msg = f"Removed {n}. {self.cleared}/{CLEAR_GOAL} ({left} to go). +{pts} pts.{extra}"
        self.snd_ok.play()
        self.snd_pop.play()
        self.collapse_and_refill()
        if same_color:
            self.drop_bomb_from_sky()
        elif random.random() < 0.12:
            self.drop_bomb_from_sky()
        if self.cleared >= CLEAR_GOAL:
            self.advance()
        else:
            self.check_over()

    def collapse_and_refill(self):
        for c in range(self.cols):
            stack = [self.grid[r][c] for r in range(self.rows) if self.grid[r][c]]
            missing = self.rows - len(stack)
            newbies = []
            for i in range(missing):
                bomb = random.random() < 0.05
                candy = self.spawn(bomb=bomb, from_above=True)
                candy.visual_y = -1 - i - random.random()
                newbies.append(candy)
            col = newbies + stack
            for r in range(self.rows):
                self.grid[r][c] = col[r]
        self.ensure_matches()

    def advance(self):
        self.op_i = (self.op_i + 1) % len(OPS)
        if self.op_i == 0:
            if self.level < 4:
                self.level += 1
            self.tries += 5
            self.msg = f"Round complete! Level {self.level} {self.op()[2]} {self.grid_size()[0]}x{self.grid_size()[1]}."
        else:
            self.tries += 3
            self.msg = f"50 removed! Next: {self.op()[2]}."
        self.new_board()

    def check_over(self):
        if self.time_left_ms() <= 0:
            self.over = True
            self.msg = f"Time's up! Score {self.score}. Removed {self.cleared}/{CLEAR_GOAL}."
            return
        if self.has_move():
            return
        if self.tries > 0 and len(self.occupied()) >= 2:
            self.msg = "No 3-candy matches. Select 2 and type the result."
            return
        self.over = True
        self.msg = f"Game over! Score {self.score}. Removed {self.cleared}/{CLEAR_GOAL}."

    def animate(self):
        if not self.over and self.time_left_ms() <= 0:
            self.check_over()
        step = self.clock.get_time() / FALL_MS_PER_CELL
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.grid[r][c]
                if not cell:
                    continue
                if cell.visual_y is None:
                    cell.visual_y = float(r)
                target = float(r)
                if cell.visual_y < target:
                    cell.visual_y = min(target, cell.visual_y + step)
                else:
                    cell.visual_y = target
                if random.random() < 0.003:
                    self.sparkles.append(Sparkle(r, c))
        for p in self.particles:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.35
            p.life -= 1
        self.particles = [p for p in self.particles if p.life > 0]
        for s in self.sparkles:
            s.life -= 1
        self.sparkles = [
            s for s in self.sparkles
            if s.life > 0 and 0 <= s.r < self.rows and 0 <= s.c < self.cols and self.grid[s.r][s.c]
        ]
        self.fuse_tick += 1
        if self.fuse_tick % 40 == 0 and any(
            self.grid[r][c] and self.grid[r][c].bomb
            for r in range(self.rows) for c in range(self.cols)
        ):
            self.snd_fuse.play()

    def draw_pretzel(self, surf, cx, cy, m, fill, edge):
        pts_a, pts_b = [], []
        for i in range(24):
            t = i / 23 * math.pi
            pts_a.append((cx - m * 0.35 + math.cos(t) * m * 0.45, cy - m * 0.15 + math.sin(t) * m * 0.38))
            pts_b.append((cx + m * 0.35 + math.cos(math.pi - t) * m * 0.45, cy - m * 0.15 + math.sin(math.pi - t) * m * 0.38))
        if len(pts_a) > 2:
            pygame.draw.lines(surf, fill, False, pts_a, max(4, int(m * 0.28)))
            pygame.draw.lines(surf, fill, False, pts_b, max(4, int(m * 0.28)))
        pygame.draw.circle(surf, fill, (int(cx), int(cy + m * 0.35)), int(m * 0.22))
        pygame.draw.circle(surf, edge, (int(cx), int(cy)), int(m), 1)

    def draw_candy(self, cell, cx, cy, m, selected, order):
        fill, hi, edge = PALETTE[cell.kind]
        if cell.bomb:
            fill, hi, edge = (40, 40, 48), (220, 50, 50), (10, 10, 10)
        alpha = 140 if cell.translucent and not cell.bomb else 255
        sprite = pygame.Surface((int(m * 2.6), int(m * 2.8)), pygame.SRCALPHA)
        ox, oy = sprite.get_width() / 2, sprite.get_height() / 2 + 4
        col = (*fill, alpha)
        hi_a = (*hi, alpha)
        edge_a = (*edge, 255)

        if cell.shape == "oval" and not cell.bomb:
            rect = pygame.Rect(0, 0, int(m * 2.1), int(m * 1.55))
            rect.center = (ox, oy)
            pygame.draw.ellipse(sprite, col, rect)
            pygame.draw.ellipse(sprite, edge_a, rect, 3)
        elif cell.shape == "lifesaver" and not cell.bomb:
            pygame.draw.circle(sprite, col, (int(ox), int(oy)), int(m))
            pygame.draw.circle(sprite, (20, 12, 34, 255), (int(ox), int(oy)), int(m * 0.38))
            pygame.draw.circle(sprite, edge_a, (int(ox), int(oy)), int(m), 3)
        elif cell.shape == "pretzel" and not cell.bomb:
            self.draw_pretzel(sprite, ox, oy, m, col, edge_a)
        else:
            pygame.draw.circle(sprite, col, (int(ox), int(oy)), int(m))
            pygame.draw.circle(sprite, edge_a, (int(ox), int(oy)), int(m), 3)

        if cell.swirl and not cell.bomb:
            pts = []
            for i in range(18):
                t = i / 17 * math.tau * 1.2
                rr = m * (0.15 + 0.7 * i / 17)
                pts.append((ox + math.cos(t) * rr, oy + math.sin(t) * rr))
            if len(pts) > 2:
                pygame.draw.lines(sprite, (*cell.swirl_color, alpha), False, pts, 3)

        if cell.dots and not cell.bomb:
            for ang, rad in ((0.4, 0.45), (2.1, 0.5), (3.8, 0.42), (5.2, 0.48)):
                pygame.draw.circle(
                    sprite,
                    (*cell.dot_color, alpha),
                    (int(ox + math.cos(ang) * m * rad), int(oy + math.sin(ang) * m * rad)),
                    max(2, int(m * 0.12)),
                )

        if cell.stripes and not cell.bomb:
            if cell.stripes == "horiz":
                pygame.draw.line(sprite, (255, 255, 255, alpha), (ox - m, oy), (ox + m, oy), 3)
            elif cell.stripes == "diag":
                pygame.draw.line(sprite, (255, 255, 255, alpha), (ox - m * 0.7, oy - m * 0.7), (ox + m * 0.7, oy + m * 0.7), 3)
            else:
                pygame.draw.line(sprite, (255, 255, 255, 200), (ox - m * 0.65, oy - m * 0.15), (ox + m * 0.65, oy + m * 0.35), 3)
                pygame.draw.line(sprite, (255, 240, 250, 200), (ox - m * 0.65, oy + m * 0.35), (ox + m * 0.65, oy - m * 0.15), 3)

        if not cell.bomb:
            pygame.draw.circle(sprite, hi_a, (int(ox - m * 0.28), int(oy - m * 0.38)), max(3, int(m * 0.18)))

        if cell.bow and not cell.bomb:
            pygame.draw.circle(sprite, (220, 30, 70, 255), (int(ox - 8), int(oy - m - 2)), 6)
            pygame.draw.circle(sprite, (220, 30, 70, 255), (int(ox + 8), int(oy - m - 2)), 6)
            pygame.draw.circle(sprite, (255, 210, 220, 255), (int(ox), int(oy - m)), 4)

        if cell.bomb:
            flicker = 4 + int(3 * math.sin(self.fuse_tick * 0.4))
            pygame.draw.line(sprite, (80, 50, 20), (ox, oy - m), (ox + 8, oy - m - 12), 3)
            pygame.draw.circle(sprite, (255, 160 + flicker * 8, 20), (int(ox + 8), int(oy - m - 14)), flicker)
            pygame.draw.circle(sprite, (255, 255, 180), (int(ox + 8), int(oy - m - 14)), max(2, flicker // 2))

        self.screen.blit(sprite, sprite.get_rect(center=(cx, cy)))
        if selected:
            pygame.draw.circle(self.screen, (255, 255, 255), (int(cx), int(cy)), int(m) + 4, 3)
        digits = len(str(cell.value))
        size = max(10, int(m * (0.72 if digits < 3 else 0.52 if digits < 4 else 0.40)))
        numf = pygame.font.SysFont("arial", size, bold=True)
        blit_outlined(self.screen, numf, str(cell.value), (255, 255, 255), (0, 0, 0), (cx, cy + 2))
        if order:
            small = pygame.font.SysFont("arial", 16, bold=True)
            blit_outlined(self.screen, small, str(order), (255, 230, 109), (0, 0, 0), (cx, cy - m - 12))

    def draw_sparkles(self, m):
        for s in self.sparkles:
            cell = self.grid[s.r][s.c]
            if not cell:
                continue
            vr = cell.visual_y if cell.visual_y is not None else s.r
            cx, cy = self.cell_center(s.r, s.c, vr)
            fade = s.life / s.max_life
            px = cx + math.cos(s.ang) * m * s.rad
            py = cy + math.sin(s.ang) * m * s.rad
            col = (255, 255, int(180 + 75 * fade))
            pygame.draw.circle(self.screen, col, (int(px), int(py)), max(1, int(s.size * fade)))
            pygame.draw.line(self.screen, col, (px - 4, py), (px + 4, py), 1)
            pygame.draw.line(self.screen, col, (px, py - 4), (px, py + 4), 1)

    def draw(self):
        scr = self.screen
        w, h = scr.get_size()
        scr.fill((20, 12, 34))
        top, bot, pad, cw, ch = self.layout()
        font = pygame.font.SysFont("arial", 18, bold=True)
        small = pygame.font.SysFont("arial", 15, bold=True)
        s, _, name = self.op()
        left = max(0, CLEAR_GOAL - self.cleared)
        ms = self.time_left_ms()
        sec = ms // 1000
        clock = f"{sec // 60}:{sec % 60:02d}"
        matches = self.count_matches() if not self.over else 0
        hud = (
            f"Lv {self.level} {name} ({s}) {self.rows}x{self.cols}  Score {self.score}  Tries {self.tries}  "
            f"Removed {self.cleared}/{CLEAR_GOAL} ({left} left)  Matches {matches}+  Time {clock}"
        )
        scr.blit(font.render(hud, True, (255, 230, 109)), (14, 16))
        m = min(cw, ch) * 0.40
        for r in range(self.rows):
            for c in range(self.cols):
                cx, cy = self.cell_center(r, c)
                pygame.draw.circle(scr, (30, 18, 51), (int(cx), int(cy)), int(m * 1.15))
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.grid[r][c]
                if not cell:
                    continue
                vr = cell.visual_y if cell.visual_y is not None else r
                cx, cy = self.cell_center(r, c, vr)
                sel = (r, c) in self.selected
                order = self.selected.index((r, c)) + 1 if sel else None
                self.draw_candy(cell, cx, cy, m, sel, order)
        self.draw_sparkles(m)
        for p in self.particles:
            pygame.draw.circle(scr, p.color, (int(p.x), int(p.y)), p.r)

        pygame.draw.rect(scr, (32, 18, 52), pygame.Rect(0, h - 118, w, 118))
        entry, eq, clr = self.ui_rects()
        lbl = small.render("Pick 2, type result:", True, (238, 230, 255))
        scr.blit(lbl, (16, entry.y + 8))
        pygame.draw.rect(scr, (40, 24, 70), entry, border_radius=8)
        pygame.draw.rect(scr, (255, 230, 109) if self.entry_focus else (180, 160, 210), entry, 2, border_radius=8)
        shown = self.typed if self.typed else "result"
        col = (255, 255, 255) if self.typed else (160, 140, 190)
        et = font.render(shown, True, col)
        scr.blit(et, et.get_rect(center=entry.center))
        pygame.draw.rect(scr, (255, 209, 102), eq, border_radius=8)
        eqt = font.render("=", True, (40, 20, 0))
        scr.blit(eqt, eqt.get_rect(center=eq.center))
        pygame.draw.rect(scr, (123, 44, 191), clr, border_radius=8)
        ct = small.render("Clear pick", True, (255, 255, 255))
        scr.blit(ct, ct.get_rect(center=clr.center))

        msg = small.render(self.msg, True, (205, 180, 219))
        hint = small.render("Or click 3 candies: #1 OP #2 = #3. Remove 50 to advance. Esc quits.", True, (189, 224, 254))
        scr.blit(msg, (16, h - 48))
        scr.blit(hint, (16, h - 26))
        pygame.display.flip()

    def handle_key(self, ev):
        if ev.key == pygame.K_ESCAPE:
            self.persist()
            pygame.quit()
            sys.exit(0)
        if self.over:
            return
        if ev.key == pygame.K_RETURN:
            self.use_text()
            return
        if ev.key == pygame.K_BACKSPACE:
            self.typed = self.typed[:-1]
            return
        ch = ev.unicode
        if ch == "-" and not self.typed:
            self.typed = "-"
        elif ch.isdigit() and len(self.typed) < 8:
            self.typed += ch
            self.entry_focus = True

    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    self.persist()
                    pygame.quit()
                    sys.exit(0)
                elif ev.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(ev.size, pygame.RESIZABLE)
                    self.persist()
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    self.click(ev.pos)
                elif ev.type == pygame.KEYDOWN:
                    self.handle_key(ev)
            self.animate()
            self.draw()
            self.clock.tick(60)


if __name__ == "__main__":
    Game(parse_start_level(sys.argv)).run()