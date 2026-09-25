import pygame
import random
import math
import sys
import array

pygame.init()
pygame.mixer.pre_init(22050, -16, 1, 512)
pygame.mixer.init(22050, -16, 1, 512)

MIN_W, MIN_H = 980, 600
START_W, START_H = 1280, 760
COLS, ROWS = 5, 3
START_CREDITS = 20.0
BET_PER_LINE_OPTIONS = [0.05, 0.10, 0.25, 0.50, 1.00]
STRIP_LEN = 48
BIG_WIN_MULT = 8.0
WIN_SHOW_MS = 3000

PAYLINES = [
    [1, 1, 1, 1, 1], [0, 0, 0, 0, 0], [2, 2, 2, 2, 2],
    [0, 1, 2, 1, 0], [2, 1, 0, 1, 2], [0, 0, 1, 2, 2],
    [2, 2, 1, 0, 0], [1, 0, 0, 0, 1], [1, 2, 2, 2, 1],
    [0, 1, 1, 1, 0], [2, 1, 1, 1, 2], [1, 0, 1, 2, 1],
    [1, 2, 1, 0, 1], [0, 1, 0, 1, 0], [2, 1, 2, 1, 2],
    [0, 2, 0, 2, 0], [2, 0, 2, 0, 2], [0, 0, 2, 0, 0],
    [2, 2, 0, 2, 2], [1, 1, 0, 1, 1],
]
LINE_COLORS = [
    (255, 80, 80), (80, 200, 255), (255, 210, 60), (140, 255, 120),
    (255, 140, 255), (255, 160, 80), (100, 255, 220), (200, 180, 255),
    (255, 100, 160), (160, 255, 80), (80, 160, 255), (255, 230, 140),
    (180, 255, 200), (255, 120, 90), (120, 220, 255), (220, 255, 90),
    (255, 90, 220), (90, 255, 180), (255, 190, 110), (170, 140, 255),
]

BASE_SYMBOLS = [
    ("apple",  "APPLE", 13, (2, 5, 12)),
    ("orange", "ORANGE", 13, (2, 5, 12)),
    ("grape",  "GRAPE", 11, (3, 6, 15)),
    ("banana", "BANANA", 11, (3, 6, 15)),
    ("plus",   "+", 9, (4, 10, 25)),
    ("minus",  "−", 9, (4, 10, 25)),
    ("times",  "×", 7, (6, 15, 40)),
    ("div",    "÷", 7, (6, 15, 40)),
    ("inf",    "∞", 3, (10, 30, 80)),
    ("undef",  "T", 3, (15, 40, 120)),
    ("eye",    "EYE", 14, (0, 0, 0)),
]
for n in range(10):
    BASE_SYMBOLS.append((f"n{n}", str(n), 5, (1, 3, 8)))

WEIGHTS = [s[2] for s in BASE_SYMBOLS]
SYM_BY_ID = {s[0]: s for s in BASE_SYMBOLS}
MATH_IDS = {"plus", "minus", "times", "div"}
SR = 22050


def pick_symbol():
    return random.choices(BASE_SYMBOLS, weights=WEIGHTS, k=1)[0][0]


def make_strip():
    return [pick_symbol() for _ in range(STRIP_LEN)]


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def draw_round_rect(surf, color, rect, radius=10, width=0):
    pygame.draw.rect(surf, color, rect, width=width, border_radius=radius)


def _tone(freq, ms, vol=0.25, decay=True, kind="sine"):
    n = int(SR * ms / 1000)
    buf = array.array("h")
    for i in range(n):
        t = i / SR
        env = (1.0 - i / n) if decay else 1.0
        env *= min(1.0, i / (0.01 * SR + 1))
        ph = 2 * math.pi * freq * t
        if kind == "sine":
            v = math.sin(ph)
        elif kind == "square":
            v = 1.0 if math.sin(ph) >= 0 else -1.0
        elif kind == "noise":
            v = random.uniform(-1, 1)
        else:
            v = math.sin(ph) + 0.35 * math.sin(2 * ph)
        buf.append(int(max(-32767, min(32767, v * env * vol * 32767))))
    return pygame.mixer.Sound(buffer=buf)


def _seq(notes, vol=0.18):
    parts = []
    for f, ms in notes:
        n = int(SR * ms / 1000)
        for i in range(n):
            t = i / SR
            env = 0.15 + 0.85 * (1.0 - i / max(1, n))
            if f <= 0:
                v = 0.0
            else:
                v = math.sin(2 * math.pi * f * t) * 0.7 + math.sin(4 * math.pi * f * t) * 0.3
            parts.append(int(max(-32767, min(32767, v * env * vol * 32767))))
    return pygame.mixer.Sound(buffer=array.array("h", parts))


def build_sounds():
    click = _tone(1800, 40, 0.12, True, "square")
    stop = _tone(140, 90, 0.28, True, "sine")
    win = _seq([(523, 90), (659, 90), (784, 140), (1046, 180)])
    big = _seq([(392, 120), (523, 120), (659, 120), (784, 160),
                (659, 100), (784, 100), (1046, 280)], 0.22)
    boom = _tone(90, 220, 0.35, True, "sine")
    crack = _tone(2400, 80, 0.15, True, "noise")
    melody = [
        (523, 140), (659, 140), (784, 140), (659, 140),
        (587, 140), (659, 140), (784, 180), (880, 200),
        (784, 140), (659, 140), (587, 140), (523, 200), (0, 80),
    ]
    tune = _seq(melody, 0.16)
    bonus_ok = _seq([(659, 80), (784, 80), (988, 140)], 0.2)
    bonus_bad = _seq([(330, 120), (247, 180)], 0.2)
    return {
        "click": click, "stop": stop, "win": win, "big": big,
        "boom": boom, "crack": crack, "tune": tune,
        "ok": bonus_ok, "bad": bonus_bad,
    }


def two_digit():
    """1.00–99.99, two decimals (up to 2 digits before decimal)."""
    return round(random.uniform(1.00, 99.99), 2)


def make_bonus_question():
    """One +, −, ×, or ÷. Mul/div operands have at most 2 integer digits.
    Product/quotient integer part is at most 3 digits. No divide by zero.
    """
    kind = random.choice(["add", "sub", "mul", "div"])
    if kind == "add":
        a, b = two_digit(), two_digit()
        ans = round(a + b, 2)
        return f"{a:.2f} + {b:.2f} =", ans
    if kind == "sub":
        a, b = two_digit(), two_digit()
        if b > a:
            a, b = b, a
        ans = round(a - b, 2)
        return f"{a:.2f} − {b:.2f} =", ans
    if kind == "mul":
        while True:
            a, b = two_digit(), two_digit()
            ans = round(a * b, 2)
            if ans < 1000:
                return f"{a:.2f} × {b:.2f} =", ans
    # division: pick divisor and quotient so dividend = q * d has 2 integer digits
    while True:
        d = two_digit()
        if abs(d) < 0.01:
            continue
        q = round(random.uniform(1.00, 99.99), 2)
        dividend = round(q * d, 2)
        if 1.00 <= dividend <= 99.99 and abs(d) >= 0.01:
            ans = round(dividend / d, 2)
            if ans < 1000:
                return f"{dividend:.2f} ÷ {d:.2f} =", ans


class Firework:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.life = 0.0
        self.dur = random.uniform(0.7, 1.2)
        self.n = random.randint(18, 32)
        self.col = random.choice([
            (255, 80, 80), (255, 200, 60), (80, 200, 255),
            (180, 255, 80), (255, 120, 220), (255, 255, 255),
        ])
        self.ang = [i * (2 * math.pi / self.n) + random.uniform(-0.1, 0.1) for i in range(self.n)]
        self.spd = [random.uniform(80, 220) for _ in range(self.n)]

    def update(self, dt):
        self.life += dt
        return self.life < self.dur

    def draw(self, surf):
        t = self.life / self.dur
        fade = 1.0 - t
        for a, s in zip(self.ang, self.spd):
            d = s * self.life
            x = int(self.x + math.cos(a) * d)
            y = int(self.y + math.sin(a) * d + 40 * self.life * self.life)
            pygame.draw.circle(surf, tuple(int(c * fade) for c in self.col), (x, y), max(1, int(4 * fade)))


class Bubble:
    def __init__(self, tank):
        self.tank = tank
        self.reset(True)

    def reset(self, spawn=False):
        tw, th, tx, ty = self.tank
        self.x = tx + random.uniform(10, max(11, tw - 10))
        self.y = ty + th + random.uniform(0, 40) if not spawn else ty + random.uniform(0, th)
        self.r = random.uniform(3, 10)
        self.speed = random.uniform(20, 55)
        self.wobble = random.uniform(0.6, 2.0)
        self.phase = random.uniform(0, 6.28)
        self.alpha = random.randint(80, 180)

    def update(self, dt, tank):
        self.tank = tank
        tw, th, tx, ty = tank
        self.phase += dt * self.wobble
        self.y -= self.speed * dt
        self.x += math.sin(self.phase) * 18 * dt
        if self.y + self.r < ty:
            self.reset()

    def draw(self, surf):
        s = pygame.Surface((int(self.r * 2 + 2), int(self.r * 2 + 2)), pygame.SRCALPHA)
        pygame.draw.circle(s, (180, 230, 255, self.alpha), (int(self.r + 1), int(self.r + 1)), int(self.r), 1)
        surf.blit(s, (self.x - self.r, self.y - self.r))


class Fish:
    def __init__(self, tank):
        self.tank = tank
        self.reset(True)

    def reset(self, spawn=False):
        tw, th, tx, ty = self.tank
        self.size = random.uniform(14, 38)
        self.dir = random.choice([-1, 1])
        self.speed = random.uniform(25, 70) * self.dir
        self.y = ty + random.uniform(20, max(30, th - 30))
        self.x = tx + random.uniform(0, tw) if spawn else (tx - 40 if self.dir > 0 else tx + tw + 40)
        self.color = random.choice([
            (255, 90, 70), (255, 170, 40), (70, 200, 255),
            (255, 80, 180), (120, 255, 140), (255, 230, 70),
        ])
        self.fin = tuple(max(0, c - 40) for c in self.color)
        self.phase = random.uniform(0, 6.28)
        self.amp = random.uniform(8, 18)

    def update(self, dt, tank):
        self.tank = tank
        tw, th, tx, ty = tank
        self.phase += dt * 4
        self.x += self.speed * dt
        self.y += math.sin(self.phase) * self.amp * dt
        self.y = max(ty + 10, min(ty + th - 10, self.y))
        if (self.dir > 0 and self.x > tx + tw + 50) or (self.dir < 0 and self.x < tx - 50):
            self.reset()

    def draw(self, surf):
        s, d = self.size, (1 if self.dir > 0 else -1)
        body = [(self.x + d * s, self.y), (self.x - d * s * 0.3, self.y - s * 0.45),
                (self.x - d * s * 0.9, self.y), (self.x - d * s * 0.3, self.y + s * 0.45)]
        pygame.draw.polygon(surf, self.color, body)
        tail = [(self.x - d * s * 0.85, self.y), (self.x - d * s * 1.45, self.y - s * 0.4),
                (self.x - d * s * 1.45, self.y + s * 0.4)]
        pygame.draw.polygon(surf, self.fin, tail)
        pygame.draw.circle(surf, (20, 20, 30), (int(self.x + d * s * 0.45), int(self.y)), max(2, int(s * 0.12)))


class Button:
    def __init__(self, label, fn=None):
        self.label, self.fn = label, fn
        self.rect = pygame.Rect(0, 0, 10, 10)
        self.hover = False
        self.enabled = True

    def set_rect(self, r):
        self.rect = pygame.Rect(r)

    def handle(self, event):
        if self.enabled and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos) and self.fn:
                self.fn()

    def draw(self, surf, font):
        col = (50, 90, 140) if not self.enabled else ((70, 160, 230) if self.hover else (40, 110, 180))
        draw_round_rect(surf, col, self.rect, 8)
        draw_round_rect(surf, (180, 220, 255), self.rect, 8, 2)
        text = font.render(self.label, True, (255, 255, 255))
        surf.blit(text, text.get_rect(center=self.rect.center))

    def update_hover(self, pos):
        self.hover = self.rect.collidepoint(pos) and self.enabled


class Reel:
    def __init__(self, col):
        self.col = col
        self.strip = make_strip()
        self.pos = float(random.randint(0, STRIP_LEN - 1))
        self.spinning = False
        self.t = 0.0
        self.duration = 1.0
        self.start_pos = self.pos
        self.travel = 0.0
        self.last_tick = 0

    def visible_ids(self):
        return [self.strip[int(math.floor(self.pos) + r) % STRIP_LEN] for r in range(ROWS)]

    def start_spin(self, delay_boost):
        land_top = random.randint(0, STRIP_LEN - 1)
        revs = random.uniform(4.5, 7.5) + delay_boost * 0.8
        current = self.pos
        forward = (land_top - (current % STRIP_LEN)) % STRIP_LEN
        self.travel = revs * STRIP_LEN + forward
        self.start_pos = current
        self.target = current + self.travel
        self.t = 0.0
        self.duration = 1.15 + delay_boost * 0.32 + random.uniform(-0.05, 0.08)
        self.spinning = True
        self.last_tick = int(self.pos)

    def update(self, dt):
        if not self.spinning:
            return False, False
        self.t += dt
        u = ease_out_cubic(self.t / self.duration)
        self.pos = self.start_pos + self.travel * u
        tick = False
        cell = int(self.pos)
        if cell != self.last_tick:
            self.last_tick = cell
            tick = True
        stopped = False
        if self.t >= self.duration:
            self.pos = float(round(self.target) % STRIP_LEN)
            self.spinning = False
            stopped = True
        return tick, stopped


def draw_eye(surf, rect, t, blink_phase, look_x, look_y):
    cx, cy = rect.center
    w = min(rect.w, rect.h) * 0.42
    tri = [(cx, cy - w), (cx - w * 0.95, cy + w * 0.75), (cx + w * 0.95, cy + w * 0.75)]
    pygame.draw.polygon(surf, (40, 30, 10), tri)
    pygame.draw.polygon(surf, (220, 190, 70), tri, 3)
    pygame.draw.polygon(surf, (60, 50, 20), [
        (cx, cy - w * 0.7), (cx - w * 0.65, cy + w * 0.5), (cx + w * 0.65, cy + w * 0.5)])
    cycle = blink_phase % (2 * math.pi)
    open_amt = 1.0
    if cycle > 5.6:
        open_amt = max(0.05, 1.0 - (cycle - 5.6) / 0.35)
    elif cycle > 5.2:
        open_amt = max(0.05, 1.0 - (cycle - 5.2) / 0.2)
    ew, eh = w * 0.55, w * 0.28 * open_amt
    eye_rect = pygame.Rect(0, 0, ew * 2, max(2, eh * 2))
    eye_rect.center = (cx, cy + w * 0.05)
    pygame.draw.ellipse(surf, (240, 235, 220), eye_rect)
    if open_amt > 0.15:
        ix = cx + look_x * ew * 0.45
        iy = cy + w * 0.05 + look_y * eh * 0.45
        ir = max(3, int(w * 0.16))
        pygame.draw.circle(surf, (40, 120, 90), (int(ix), int(iy)), ir)
        pygame.draw.circle(surf, (15, 20, 25), (int(ix), int(iy)), max(2, ir // 2))
        pygame.draw.circle(surf, (255, 255, 255), (int(ix + 2), int(iy - 2)), max(1, ir // 4))


def symbol_color(sid):
    if sid.startswith("n"):
        return (230, 230, 240)
    return {
        "apple": (220, 50, 50), "orange": (240, 140, 30),
        "grape": (140, 70, 200), "banana": (230, 200, 40),
        "plus": (80, 200, 120), "minus": (80, 180, 200),
        "times": (70, 130, 230), "div": (230, 100, 160),
        "inf": (255, 220, 80), "undef": (240, 240, 250),
        "eye": (220, 190, 70),
    }.get(sid, (255, 255, 255))


class MathSlots:
    def __init__(self):
        self.screen = pygame.display.set_mode((START_W, START_H), pygame.RESIZABLE)
        pygame.display.set_caption("Math Fruit Slots")
        self.clock = pygame.time.Clock()
        self.w, self.h = START_W, START_H
        self.credits = START_CREDITS
        self.bet_idx = 1
        self.active_lines = set(range(5))
        self.reels = [Reel(c) for c in range(COLS)]
        self.spinning = False
        self.last_win = 0.0
        self.spin_payout = 0.0
        self.win_lines = []
        self.show_paytable = False
        self.flash_lines_until = 0
        self.message = "Pick lines, then SPIN"
        self.time = 0.0
        self.bubbles, self.fish = [], []
        self.bonus = None
        self.snd = build_sounds()
        self.tune_ch = pygame.mixer.Channel(0)
        self.fx_ch = pygame.mixer.Channel(1)
        self.fw_ch = pygame.mixer.Channel(2)
        self.win_until = 0
        self.celebration = None
        self.fireworks = []
        self.fw_timer = 0.0
        self._init_buttons()
        self._rebuild_fonts()
        self._layout()
        self._spawn_aqua()

    def _init_buttons(self):
        self.btn_spin = Button("SPIN", self.try_spin)
        self.btn_pay = Button("PAYOUTS", self.toggle_pay)
        self.btn_all = Button("ALL LINES", self.select_all)
        self.btn_clear = Button("CLEAR", self.clear_lines)
        self.btn_bet_up = Button("BET +", self.bet_up)
        self.btn_bet_dn = Button("BET −", self.bet_dn)
        self.line_btns = [Button(str(i + 1), lambda i=i: self.toggle_line(i)) for i in range(len(PAYLINES))]
        self.buttons = [self.btn_spin, self.btn_pay, self.btn_all, self.btn_clear,
                        self.btn_bet_up, self.btn_bet_dn] + self.line_btns

    def _rebuild_fonts(self):
        scale = max(0.7, min(self.w / 1280, self.h / 760))
        self.font = pygame.font.SysFont("segoeui,arial,dejavusans", int(18 * scale))
        self.font_sm = pygame.font.SysFont("segoeui,arial,dejavusans", int(14 * scale))
        self.font_lg = pygame.font.SysFont("segoeui,arial,dejavusans", int(32 * scale), bold=True)
        self.font_xl = pygame.font.SysFont("segoeui,arial,dejavusans", int(42 * scale), bold=True)
        self.font_title = pygame.font.SysFont("segoeui,arial", int(22 * scale), bold=True)
        self.font_q = pygame.font.SysFont("consolas,couriernew,monospace", int(26 * scale), bold=True)

    def _layout(self):
        w, h, pad = self.w, self.h, int(min(self.w, self.h) * 0.02)
        self.aqua_rect = pygame.Rect(pad, pad, int(w * 0.17), h - pad * 2)
        top_h, bot_h = int(h * 0.10), int(h * 0.22)
        self.header = pygame.Rect(self.aqua_rect.right + pad, pad, w - self.aqua_rect.right - pad * 2, top_h)
        self.footer = pygame.Rect(self.aqua_rect.right + pad, h - pad - bot_h,
                                  w - self.aqua_rect.right - pad * 2, bot_h)
        self.reel_area = pygame.Rect(
            self.aqua_rect.right + pad, self.header.bottom + pad,
            w - self.aqua_rect.right - pad * 2, self.footer.top - self.header.bottom - pad * 2)
        cw, rh = self.reel_area.width / COLS, self.reel_area.height / ROWS
        self.cell_size = (cw, rh)
        self.cell_rects = [
            [pygame.Rect(self.reel_area.x + c * cw + 3, self.reel_area.y + r * rh + 3, cw - 6, rh - 6)
             for c in range(COLS)] for r in range(ROWS)]
        fw, fh = self.footer.width, self.footer.height
        by, bh, gap = self.footer.y + int(fh * 0.52), int(fh * 0.38), 8
        labels = [self.btn_bet_dn, self.btn_bet_up, self.btn_clear, self.btn_all, self.btn_pay, self.btn_spin]
        bw = (fw - gap * (len(labels) + 1)) / len(labels)
        for i, b in enumerate(labels):
            b.set_rect((self.footer.x + gap + i * (bw + gap), by, bw, bh))
        n = len(self.line_btns)
        lw = (fw - 6 * (n + 1)) / n
        for i, b in enumerate(self.line_btns):
            b.set_rect((self.footer.x + 6 + i * (lw + 6), self.footer.y + 8, lw, int(fh * 0.32)))

    def _spawn_aqua(self):
        tank = self._tank()
        self.bubbles = [Bubble(tank) for _ in range(28)]
        self.fish = [Fish(tank) for _ in range(9)]

    def _tank(self):
        r = self.aqua_rect
        return (r.w, r.h, r.x, r.y)

    @property
    def bet_per_line(self):
        return BET_PER_LINE_OPTIONS[self.bet_idx]

    @property
    def total_bet(self):
        return self.bet_per_line * len(self.active_lines)

    def toggle_pay(self):
        if self.bonus or self.celebration:
            return
        self.show_paytable = not self.show_paytable

    def select_all(self):
        self.active_lines = set(range(len(PAYLINES)))
        self.flash_lines_until = pygame.time.get_ticks() + 2000

    def clear_lines(self):
        self.active_lines = set()
        self.flash_lines_until = pygame.time.get_ticks() + 2000

    def toggle_line(self, i):
        self.active_lines.symmetric_difference_update({i})
        self.flash_lines_until = pygame.time.get_ticks() + 2000

    def bet_up(self):
        self.bet_idx = min(len(BET_PER_LINE_OPTIONS) - 1, self.bet_idx + 1)

    def bet_dn(self):
        self.bet_idx = max(0, self.bet_idx - 1)

    def grid(self):
        cols = [r.visible_ids() for r in self.reels]
        return [[cols[c][r] for c in range(COLS)] for r in range(ROWS)]

    def try_spin(self):
        if self.spinning or self.show_paytable or self.bonus or self.celebration:
            return
        if not self.active_lines:
            self.message = "Select at least one line"
            return
        if self.credits < self.total_bet:
            self.message = "Not enough credits"
            return
        self.credits = round(self.credits - self.total_bet, 2)
        self.spinning = True
        self.last_win = 0.0
        self.spin_payout = 0.0
        self.win_lines = []
        self.message = "Spinning..."
        self.tune_ch.play(self.snd["tune"], loops=-1)
        for i, reel in enumerate(self.reels):
            reel.start_spin(i)

    def evaluate(self):
        g = self.grid()
        won = 0.0
        self.win_lines = []
        for li in sorted(self.active_lines):
            rows = PAYLINES[li]
            ids = [g[rows[c]][c] for c in range(COLS)]
            line_pay = self._line_payout(ids)
            if line_pay > 0:
                cash = line_pay * self.bet_per_line
                won += cash
                self.win_lines.append((li, ids, cash))
        eyes = sum(1 for r in range(ROWS) for c in range(COLS) if g[r][c] == "eye")
        go_bonus = eyes >= 3
        if eyes >= 3:
            scatter_pay = {3: 5, 4: 15, 5: 50}.get(min(eyes, 5), 5) * max(self.total_bet, self.bet_per_line)
            won += scatter_pay
        self.spin_payout = round(won, 2)
        self.last_win = self.spin_payout
        self.credits = round(self.credits + self.last_win, 2)
        self.win_until = pygame.time.get_ticks() + WIN_SHOW_MS
        if self.last_win > 0:
            self.fx_ch.play(self.snd["win"])
            self.message = f"You won ${self.last_win:.2f}"
        else:
            self.message = "No win — try again"
        big = self.total_bet > 0 and self.last_win >= self.total_bet * BIG_WIN_MULT and self.last_win > 0
        if big and not go_bonus:
            self.start_celebration(self.last_win, "BIG WIN!", after=None)
        elif go_bonus:
            if big:
                self.start_celebration(self.last_win, "BIG WIN!  3 EYES", after="bonus")
            else:
                self.start_bonus()

    def _line_payout(self, ids):
        first, run = ids[0], 1
        for s in ids[1:]:
            if s == first:
                run += 1
            else:
                break
        pay = 0
        if run >= 3 and first != "eye":
            m3, m4, m5 = SYM_BY_ID[first][3]
            pay = {3: m3, 4: m4, 5: m5}[min(run, 5)]
        math_run = 0
        for s in ids:
            if s in MATH_IDS:
                math_run += 1
            else:
                break
        if math_run >= 3:
            pay += {3: 3, 4: 8, 5: 20}[math_run]
        if "inf" in ids and "undef" in ids:
            pay += 7
        return pay

    def start_celebration(self, amount, title, after=None):
        self.celebration = {"amount": amount, "title": title, "after": after, "t": 0.0, "dur": 3.2}
        self.fireworks = []
        self.fw_timer = 0.0
        self.fx_ch.play(self.snd["big"])
        self.fw_ch.play(self.snd["boom"])

    def end_celebration(self):
        after = self.celebration["after"] if self.celebration else None
        self.celebration = None
        self.fireworks = []
        if after == "bonus":
            self.start_bonus()
        elif after == "machine":
            self.message = "Back to the reels"

    def start_bonus(self):
        text, ans = make_bonus_question()
        self.bonus = {
            "text": text,
            "ans": ans,
            "typed": "",
            "feedback": "3 Eyes! One question — 2 decimal places.",
            "base_payout": self.spin_payout,
            "bet": self.total_bet,
        }

    def bonus_submit(self):
        b = self.bonus
        try:
            val = float(b["typed"].strip())
        except ValueError:
            b["feedback"] = "Enter a number to 2 decimal places."
            return
        ans = b["ans"]
        correct = abs(val - ans) < 0.015 or abs(round(val, 2) - round(ans, 2)) < 0.001
        prize = 0.0
        if correct:
            prize = round(5.0 * b["bet"] + 2.0 * b["base_payout"], 2)
            self.fx_ch.play(self.snd["ok"])
        else:
            self.fx_ch.play(self.snd["bad"])
        self.credits = round(self.credits + prize, 2)
        self.last_win = round(self.last_win + prize, 2)
        self.win_until = pygame.time.get_ticks() + WIN_SHOW_MS
        self.bonus = None
        if correct and prize > 0:
            self.start_celebration(prize, f"BONUS WIN!  +${prize:.2f}", after="machine")
        elif correct:
            self.message = "Correct — back to slots"
        else:
            self.message = f"Wrong (answer {ans:.2f}) — back to slots"

    def handle(self, event):
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)
        if event.type == pygame.VIDEORESIZE:
            self.w, self.h = max(MIN_W, event.w), max(MIN_H, event.h)
            self.screen = pygame.display.set_mode((self.w, self.h), pygame.RESIZABLE)
            self._rebuild_fonts()
            self._layout()
        if self.celebration:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE):
                self.end_celebration()
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.end_celebration()
            return
        if self.bonus:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    self.bonus_submit()
                elif event.key == pygame.K_BACKSPACE:
                    self.bonus["typed"] = self.bonus["typed"][:-1]
                else:
                    ch = event.unicode
                    if ch in "0123456789.-" and len(self.bonus["typed"]) < 12:
                        self.bonus["typed"] += ch
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.show_paytable:
                    self.show_paytable = False
                else:
                    pygame.quit()
                    sys.exit(0)
            if event.key == pygame.K_SPACE:
                self.try_spin()
            if event.key == pygame.K_p:
                self.toggle_pay()
        if self.show_paytable:
            if event.type == pygame.MOUSEBUTTONDOWN:
                self.show_paytable = False
            return
        for b in self.buttons:
            b.handle(event)

    def update(self, dt):
        self.time += dt
        pos = pygame.mouse.get_pos()
        for b in self.buttons:
            b.update_hover(pos)
        busy = self.spinning or self.bonus or self.celebration
        self.btn_spin.enabled = (not busy) and self.credits >= self.total_bet and bool(self.active_lines)
        tank = self._tank()
        for bb in self.bubbles:
            bb.update(dt, tank)
        for f in self.fish:
            f.update(dt, tank)

        if self.spinning:
            any_spin = False
            for reel in self.reels:
                tick, stopped = reel.update(dt)
                if tick and reel.spinning:
                    self.snd["click"].play()
                if stopped:
                    self.snd["stop"].play()
                if reel.spinning:
                    any_spin = True
            if not any_spin:
                self.spinning = False
                self.tune_ch.stop()
                self.evaluate()

        if self.celebration:
            self.celebration["t"] += dt
            self.fw_timer -= dt
            if self.fw_timer <= 0:
                self.fw_timer = random.uniform(0.12, 0.28)
                x = random.randint(int(self.w * 0.2), int(self.w * 0.8))
                y = random.randint(int(self.h * 0.15), int(self.h * 0.55))
                self.fireworks.append(Firework(x, y))
                self.fw_ch.play(self.snd["crack"])
                if random.random() < 0.35:
                    self.fw_ch.play(self.snd["boom"])
            self.fireworks = [fw for fw in self.fireworks if fw.update(dt)]
            if self.celebration["t"] >= self.celebration["dur"]:
                self.end_celebration()

    def draw_symbol(self, surf, cell, sid, t):
        cx, cy = cell.center
        rad = int(min(cell.w, cell.h) * 0.30)
        col = symbol_color(sid)
        if sid == "eye":
            look_x = math.sin(t * 0.7 + cx * 0.01) * 0.85
            look_y = math.cos(t * 0.5 + cy * 0.01) * 0.5
            draw_eye(surf, cell, t, t * 1.3, look_x, look_y)
            return
        if sid == "apple":
            pygame.draw.circle(surf, col, (cx, cy + 4), rad)
            pygame.draw.circle(surf, (40, 140, 50), (cx + 4, cy - rad + 4), 5)
        elif sid == "orange":
            pygame.draw.circle(surf, col, (cx, cy), rad)
        elif sid == "grape":
            for dx, dy in [(-10, 6), (0, -4), (10, 6), (-5, 16), (6, 16)]:
                pygame.draw.circle(surf, col, (cx + dx, cy + dy - 6), max(6, rad // 2))
        elif sid == "banana":
            rect = pygame.Rect(0, 0, rad * 2, rad)
            rect.center = (cx, cy)
            pygame.draw.ellipse(surf, col, rect)
        elif sid == "inf":
            pygame.draw.circle(surf, col, (cx - rad // 2, cy), rad // 2, 4)
            pygame.draw.circle(surf, col, (cx + rad // 2, cy), rad // 2, 4)
        elif sid == "undef":
            ts = self.font_lg.render("T", True, col)
            surf.blit(ts, ts.get_rect(center=(cx, cy - 6)))
            sub = self.font_sm.render("undef", True, (180, 180, 200))
            surf.blit(sub, sub.get_rect(center=(cx, cy + rad - 4)))
            return
        elif sid.startswith("n"):
            ts = self.font_lg.render(sid[1], True, col)
            pygame.draw.circle(surf, (50, 55, 80), (cx, cy), rad + 4, 2)
            surf.blit(ts, ts.get_rect(center=(cx, cy)))
            return
        else:
            ts = self.font_lg.render(SYM_BY_ID[sid][1], True, col)
            surf.blit(ts, ts.get_rect(center=(cx, cy)))
            return
        if sid in ("apple", "orange", "grape", "banana"):
            ts = self.font_sm.render(sid[:3].upper(), True, (20, 20, 30))
            surf.blit(ts, ts.get_rect(center=(cx, cy + rad + 2)))

    def draw_reels(self, surf):
        draw_round_rect(surf, (18, 22, 40), self.reel_area, 12)
        cw, rh = self.cell_size
        for c, reel in enumerate(self.reels):
            col_x = self.reel_area.x + c * cw
            frac = reel.pos - math.floor(reel.pos)
            top_idx = int(math.floor(reel.pos))
            for k in range(-1, ROWS + 1):
                sid = reel.strip[(top_idx + k) % STRIP_LEN]
                y = self.reel_area.y + (k - frac) * rh
                cell = pygame.Rect(col_x + 3, y + 3, cw - 6, rh - 6)
                if cell.bottom < self.reel_area.y - 4 or cell.top > self.reel_area.bottom + 4:
                    continue
                pygame.draw.rect(surf, (30, 36, 58), cell.clip(self.reel_area.inflate(-2, -2)), border_radius=10)
                self.draw_symbol(surf, cell, sid, self.time)
                pygame.draw.rect(surf, (70, 90, 130), cell.clip(self.reel_area), 2, border_radius=10)
        pygame.draw.rect(surf, (18, 22, 40), self.reel_area, 6, border_radius=12)
        flashing = pygame.time.get_ticks() < self.flash_lines_until
        if (flashing or (self.win_lines and not self.spinning)) and not self.bonus:
            lines_to_draw = list(self.active_lines) if flashing else [w[0] for w in self.win_lines]
            for li in lines_to_draw:
                color = LINE_COLORS[li % len(LINE_COLORS)]
                pts = [self.cell_rects[PAYLINES[li][c]][c].center for c in range(COLS)]
                pygame.draw.lines(surf, color, False, pts, 4)
                for p in pts:
                    pygame.draw.circle(surf, color, p, 6)

    def draw_aquarium(self, surf):
        r = self.aqua_rect
        draw_round_rect(surf, (8, 40, 70), r, 16)
        for i in range(6):
            pygame.draw.rect(surf, (10 + i * 6, 55 + i * 8, 95 + i * 10),
                             pygame.Rect(r.x + 6, r.y + 6 + i * (r.h // 6), r.w - 12, r.h // 6))
        pygame.draw.rect(surf, (120, 200, 230), r, 3, border_radius=16)
        surf.blit(self.font_sm.render("AQUARIUM", True, (180, 230, 255)), (r.x + 12, r.y + 8))
        for f in self.fish:
            f.draw(surf)
        for b in self.bubbles:
            b.draw(surf)

    def draw_header(self, surf):
        draw_round_rect(surf, (24, 28, 50), self.header, 10)
        surf.blit(self.font_title.render("MATH FRUIT SLOTS", True, (255, 220, 120)),
                  (self.header.x + 16, self.header.y + 8))
        info = self.font.render(
            f"Credits  ${self.credits:.2f}    Bet/line  ${self.bet_per_line:.2f}    "
            f"Lines  {len(self.active_lines)}    Total  ${self.total_bet:.2f}    Last  ${self.last_win:.2f}",
            True, (220, 230, 255))
        surf.blit(info, (self.header.x + 16, self.header.y + self.header.h * 0.48))

    def draw_footer(self, surf):
        draw_round_rect(surf, (24, 28, 50), self.footer, 10)
        for i, b in enumerate(self.line_btns):
            if i in self.active_lines:
                pygame.draw.rect(surf, LINE_COLORS[i], b.rect.inflate(4, 4), border_radius=8)
            b.draw(surf, self.font_sm)
        for b in (self.btn_bet_dn, self.btn_bet_up, self.btn_clear, self.btn_all, self.btn_pay, self.btn_spin):
            b.draw(surf, self.font)
        surf.blit(self.font_sm.render(self.message + "   (Space spin · P paytable · Esc quit)",
                                      True, (160, 200, 180)),
                  (self.header.x + 16, self.header.bottom - 1))

    def draw_win_banner(self, surf):
        if pygame.time.get_ticks() > self.win_until or self.last_win <= 0:
            return
        if self.celebration or self.bonus:
            return
        box = pygame.Rect(0, 0, int(self.w * 0.36), 56)
        box.center = (self.reel_area.centerx, self.reel_area.top + 36)
        s = pygame.Surface(box.size, pygame.SRCALPHA)
        s.fill((20, 30, 20, 170))
        surf.blit(s, box.topleft)
        pygame.draw.rect(surf, (120, 255, 160), box, 2, border_radius=10)
        txt = self.font_title.render(f"WIN  ${self.last_win:.2f}", True, (180, 255, 160))
        surf.blit(txt, txt.get_rect(center=box.center))

    def draw_celebration(self, surf):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 10, 120))
        surf.blit(overlay, (0, 0))
        for fw in self.fireworks:
            fw.draw(surf)
        box = pygame.Rect(0, 0, int(self.w * 0.5), int(self.h * 0.28))
        box.center = (self.w // 2, self.h // 2)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill((10, 16, 40, 150))
        surf.blit(panel, box.topleft)
        pygame.draw.rect(surf, (255, 220, 80), box, 3, border_radius=16)
        t1 = self.font_xl.render(self.celebration["title"], True, (255, 230, 120))
        t2 = self.font_lg.render(f"${self.celebration['amount']:.2f}", True, (160, 255, 170))
        t3 = self.font_sm.render("Click or press Space  ·  returning shortly", True, (200, 210, 230))
        surf.blit(t1, t1.get_rect(center=(box.centerx, box.y + 50)))
        surf.blit(t2, t2.get_rect(center=(box.centerx, box.y + 110)))
        surf.blit(t3, t3.get_rect(center=(box.centerx, box.bottom - 28)))

    def draw_paytable(self, surf):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surf.blit(overlay, (0, 0))
        box = pygame.Rect(int(self.w * 0.14), int(self.h * 0.06), int(self.w * 0.72), int(self.h * 0.88))
        draw_round_rect(surf, (28, 34, 60), box, 14)
        surf.blit(self.font_title.render("PAYOUTS  (× bet per line)", True, (255, 220, 120)), (box.x + 20, box.y + 14))
        y = box.y + 50
        for sid, lab, _, pays in BASE_SYMBOLS:
            if sid == "eye":
                line = "EYE scatter (anywhere): 3+ starts BONUS.  Pay 3=5× total bet  4=15×  5=50×"
            elif sid.startswith("n"):
                if sid != "n0":
                    continue
                line = "Numbers 0–9 on a line:  3=x1   4=x3   5=x8"
            else:
                line = f"{lab:8} {sid:8}   3=x{pays[0]}   4=x{pays[1]}   5=x{pays[2]}"
            surf.blit(self.font.render(line, True, symbol_color(sid) if not sid.startswith("n") else (230, 230, 240)),
                      (box.x + 24, y))
            y += 22
        for e in [
            "3 triangle-eyes → 1 math question (+ − × ÷). Answer to 2 decimals.",
            "Correct bonus: 5× total bet + 2× that spin's payout, then fireworks.",
            "× and ÷ use 2-digit operands; answers stay under 1000.00. No ÷0.",
            "Wins stay 3 seconds. Big win (≥ 8× total bet) gets fireworks.",
            "Click to close.",
        ]:
            surf.blit(self.font_sm.render(e, True, (210, 220, 230)), (box.x + 24, y))
            y += 22

    def draw_bonus(self, surf):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 20, 200))
        surf.blit(overlay, (0, 0))
        box = pygame.Rect(int(self.w * 0.18), int(self.h * 0.22), int(self.w * 0.64), int(self.h * 0.52))
        draw_round_rect(surf, (30, 36, 70), box, 14)
        pygame.draw.rect(surf, (255, 210, 80), box, 3, border_radius=14)
        b = self.bonus
        surf.blit(self.font_title.render("EYE SCATTER BONUS  —  1 question", True, (255, 220, 100)),
                  (box.x + 24, box.y + 18))
        hint = f"Correct pays  5× bet (${b['bet']:.2f})  +  2× payout (${b['base_payout']:.2f})"
        surf.blit(self.font.render(hint, True, (180, 200, 230)), (box.x + 24, box.y + 60))
        surf.blit(self.font_q.render(b["text"], True, (255, 255, 255)), (box.x + 24, box.y + 100))
        typed = b["typed"] + ("|" if int(self.time * 2) % 2 == 0 else "")
        field = pygame.Rect(box.x + 24, box.y + 150, box.w - 48, 44)
        pygame.draw.rect(surf, (15, 18, 32), field, border_radius=8)
        pygame.draw.rect(surf, (120, 160, 220), field, 2, border_radius=8)
        surf.blit(self.font_q.render(typed, True, (180, 255, 180)), (field.x + 12, field.y + 6))
        surf.blit(self.font.render(b["feedback"], True, (220, 200, 140)), (box.x + 24, box.y + 210))
        surf.blit(self.font_sm.render("Type answer to 2 decimals. Enter to submit.", True, (180, 190, 210)),
                  (box.x + 24, box.y + box.h - 40))

    def draw(self):
        self.screen.fill((12, 14, 24))
        self.draw_aquarium(self.screen)
        self.draw_header(self.screen)
        self.draw_reels(self.screen)
        self.draw_footer(self.screen)
        self.draw_win_banner(self.screen)
        if self.show_paytable:
            self.draw_paytable(self.screen)
        if self.bonus:
            self.draw_bonus(self.screen)
        if self.celebration:
            self.draw_celebration(self.screen)
        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                self.handle(event)
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    MathSlots().run()