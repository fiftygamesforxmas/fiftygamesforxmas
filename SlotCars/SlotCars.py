#!/usr/bin/env python3
"""Slot Car Racing — figure-8, oil slicks, stereo V8."""

import math
import random
import sys
import array
import pygame

pygame.mixer.pre_init(22050, -16, 2, 512)
pygame.init()
pygame.mixer.set_num_channels(16)
pygame.display.set_caption("Slot Car Racing")

WIDTH, HEIGHT = 1280, 800
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT))
CLOCK = pygame.time.Clock()
FPS = 60
SR = 22050

FONT = pygame.font.SysFont("consolas", 22)
BIG = pygame.font.SysFont("consolas", 48, bold=True)
MED = pygame.font.SysFont("consolas", 32, bold=True)

ACCEL = 620.0
DRAG = 0.28
COAST_DECEL = 50.0
LAPS_TO_WIN = 3
LANE_OFFSET = 16.0
ROAD_HALF = LANE_OFFSET + 16.0
OIL_LENGTH = 70.0
OIL_THROTTLE = 0.18
MAX_SPEED = 900.0
SLICK_SAFE_SPEED = MAX_SPEED * 0.5


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a, b, t):
    return a + (b - a) * t


def make_v8_sound(rpm, seconds=0.18):
    n = max(256, int(SR * seconds))
    rpm = clamp(rpm, 700.0, 6200.0)
    fire = rpm / 60.0 * 4.0
    raw = array.array("h")
    for i in range(n):
        t = i / float(SR)
        phase = (t * fire) % 1.0
        bank_a = 1.0 if phase < 0.10 else 0.0
        bank_b = 1.0 if 0.48 < phase < 0.58 else 0.0
        pulse = bank_a + 0.85 * bank_b
        base = math.sin(2 * math.pi * fire * t)
        h2 = math.sin(2 * math.pi * fire * 2 * t)
        h3 = math.sin(2 * math.pi * fire * 3 * t)
        exhaust = math.sin(2 * math.pi * (fire * 0.5) * t)
        growl = math.sin(2 * math.pi * 55 * t)
        noise = ((i * 1103515245 + 12345) & 0x7FFF) / 32768.0 - 0.5
        v = 0.55 * pulse * (0.7 * base + 0.35 * h2 + 0.18 * h3)
        v += 0.18 * exhaust + 0.10 * growl + 0.08 * noise
        v = math.tanh(v * 2.4)
        sample = int(clamp(v, -1.0, 1.0) * 22000)
        raw.append(sample)
        raw.append(sample)
    return pygame.mixer.Sound(buffer=raw.tobytes())


class EngineAudio:
    def __init__(self):
        self.ch_self = pygame.mixer.Channel(0)
        self.ch_other = pygame.mixer.Channel(1)
        self.snd_self = make_v8_sound(900)
        self.snd_other = make_v8_sound(900)
        self.timer = 0.0
        self.ch_self.play(self.snd_self, loops=-1)
        self.ch_other.play(self.snd_other, loops=-1)

    def _rpm(self, speed, throttle, spinning):
        if spinning:
            return 750.0
        return 850.0 + (speed / MAX_SPEED) * 4800.0 + throttle * 350.0

    def update(self, dt, p1, p2, track):
        self.timer += dt
        if self.timer > 0.12:
            self.timer = 0.0
            r1 = self._rpm(p1.speed, p1.throttle, p1.deslot_timer > 0)
            r2 = self._rpm(p2.speed, p2.throttle, p2.deslot_timer > 0)
            self.snd_self = make_v8_sound(r1)
            self.snd_other = make_v8_sound(r2)
            self.ch_self.play(self.snd_self, loops=-1)
            self.ch_other.play(self.snd_other, loops=-1)

        self_vol = 0.22 + 0.55 * (p1.speed / MAX_SPEED) + 0.15 * p1.throttle
        if p1.deslot_timer > 0:
            self_vol = 0.12
        self.ch_self.set_volume(clamp(self_vol * 1.05, 0.05, 0.95), clamp(self_vol * 0.80, 0.05, 0.95))

        x1, y1, _ = track.pos_on_lane(p1.lane, p1.s)
        x2, y2, _ = track.pos_on_lane(p2.lane, p2.s)
        d = math.hypot(x2 - x1, y2 - y1)
        pan = clamp((x2 - x1) / 280.0, -1.0, 1.0)
        atten = clamp(1.15 - d / 620.0, 0.08, 1.0)
        other_vol = (0.16 + 0.50 * (p2.speed / MAX_SPEED) + 0.12 * p2.throttle) * atten
        if p2.deslot_timer > 0:
            other_vol *= 0.35
        left = other_vol * (1.0 - pan) * 0.5
        right = other_vol * (1.0 + pan) * 0.5
        self.ch_other.set_volume(clamp(left, 0.0, 0.9), clamp(right, 0.0, 0.9))

class Track:
    def __init__(self):
        self.center = []
        self.lanes = [[], []]
        self.tangents = []
        self.normals = []
        self.radius = []
        self.cumlen = []
        self.height = []
        self.total_len = 1.0
        self.cross = (WIDTH / 2, HEIGHT / 2)
        self.start_index = 0
        self.start_s = 0.0
        self.oil = [0.0, 0.0]
        self.generate()

    def generate(self):
        cx, cy = WIDTH / 2, HEIGHT / 2 + 8
        ax = min(WIDTH, HEIGHT) * random.uniform(0.46, 0.52)
        ay = min(WIDTH, HEIGHT) * random.uniform(0.34, 0.40)
        n = 480
        pts = []
        height = []
        for i in range(n):
            t = 2 * math.pi * i / n
            x = ax * math.sin(t)
            y = ay * math.sin(t) * math.cos(t)
            pts.append((cx + x, cy + y))
            height.append(0.5 + 0.5 * math.cos(t))

        sm = pts[:]
        for _ in range(2):
            nxt = []
            for i in range(n):
                a, b, c = sm[(i - 1) % n], sm[i], sm[(i + 1) % n]
                nxt.append(((a[0] + 2 * b[0] + c[0]) / 4.0, (a[1] + 2 * b[1] + c[1]) / 4.0))
            sm = nxt
        pts = sm

        self.center = pts
        self.height = height
        self.cross = (cx, cy)

        self.tangents = []
        self.normals = []
        for i in range(n):
            prv, nxtp = pts[(i - 1) % n], pts[(i + 1) % n]
            tx, ty = nxtp[0] - prv[0], nxtp[1] - prv[1]
            L = math.hypot(tx, ty) or 1.0
            tx, ty = tx / L, ty / L
            self.tangents.append((tx, ty))
            self.normals.append((-ty, tx))

        self.lanes = [[], []]
        for i in range(n):
            x, y = pts[i]
            nx, ny = self.normals[i]
            self.lanes[0].append((x - nx * LANE_OFFSET, y - ny * LANE_OFFSET))
            self.lanes[1].append((x + nx * LANE_OFFSET, y + ny * LANE_OFFSET))

        self.cumlen = [0.0]
        for i in range(1, n):
            self.cumlen.append(self.cumlen[-1] + dist(pts[i - 1], pts[i]))
        self.total_len = self.cumlen[-1] + dist(pts[-1], pts[0])
        if self.total_len < 100:
            self.total_len = 100.0

        self.radius = [800.0] * n
        span = max(8, n // 28)
        for i in range(n):
            arc = 0.0
            ang_sum = 0.0
            for k in range(span):
                a = self.tangents[(i + k) % n]
                b = self.tangents[(i + k + 1) % n]
                dot = clamp(a[0] * b[0] + a[1] * b[1], -1.0, 1.0)
                cr = a[0] * b[1] - a[1] * b[0]
                ang_sum += math.atan2(cr, dot)
                arc += dist(pts[(i + k) % n], pts[(i + k + 1) % n])
            self.radius[i] = clamp(arc / max(0.04, abs(ang_sum)), 90.0, 5000.0)

        i0 = max(range(n), key=lambda i: abs(self.center[i][0] - self.cross[0]))
        self.start_index = i0
        self.start_s = self.cumlen[i0]
        L = self.total_len
        self.oil[0] = (self.start_s + L * 0.28) % L
        self.oil[1] = (self.start_s + L * 0.72) % L

    def index_at(self, s):
        s = s % self.total_len
        lo, hi = 0, len(self.cumlen) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.cumlen[mid] <= s:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def height_at(self, s):
        return self.height[self.index_at(s)]

    def on_oil(self, lane, s):
        L = self.total_len
        local = s % L
        start = self.oil[lane]
        end = (start + OIL_LENGTH) % L
        if start < end:
            return start <= local <= end
        return local >= start or local <= end

    def dist_to_oil(self, lane, s):
        L = self.total_len
        local = s % L
        start = self.oil[lane]
        return (start - local) % L

    def pos_on_lane(self, lane, s):
        i = self.index_at(s)
        n = len(self.center)
        j = (i + 1) % n
        s0 = self.cumlen[i]
        s1 = self.cumlen[j] if j else self.total_len
        seg = s1 - s0 if s1 > s0 else (self.total_len - s0)
        local = s % self.total_len
        t = 0.0 if seg <= 1e-6 else clamp((local - s0) / seg, 0.0, 1.0)
        p0, p1 = self.lanes[lane][i], self.lanes[lane][j]
        x = lerp(p0[0], p1[0], t)
        y = lerp(p0[1], p1[1], t)
        tx, ty = self.tangents[i]
        return x, y, math.atan2(ty, tx)

    def _ribbon_segment(self, indices):
        if len(indices) < 2:
            return None
        outer, inner = [], []
        w = ROAD_HALF
        for i in indices:
            nx, ny = self.normals[i]
            x, y = self.center[i]
            outer.append((x + nx * w, y + ny * w))
            inner.append((x - nx * w, y - ny * w))
        return outer + inner[::-1]

    def _oil_points(self, lane):
        pts = []
        s = self.oil[lane]
        steps = 14
        for k in range(steps + 1):
            pts.append(self.pos_on_lane(lane, s + k * (OIL_LENGTH / steps))[:2])
        return pts

    def draw(self, surf):
        surf.fill((34, 92, 42))
        n = len(self.center)
        under_runs, over_runs = [], []
        current = [0]
        over_mode = self.height[0] >= 0.5
        for i in range(1, n):
            is_over = self.height[i] >= 0.5
            if is_over == over_mode:
                current.append(i)
            else:
                (over_runs if over_mode else under_runs).append(current)
                current = [i]
                over_mode = is_over
        (over_runs if over_mode else under_runs).append(current)

        def draw_runs(runs, asphalt, edge, width_edge=3):
            for run in runs:
                if len(run) < 2:
                    continue
                ext = run + [(run[-1] + 1) % n]
                poly = self._ribbon_segment(ext)
                if poly:
                    pygame.draw.polygon(surf, asphalt, poly)
                    pygame.draw.polygon(surf, edge, poly, width_edge)

        draw_runs(under_runs, (48, 48, 52), (210, 210, 210))
        draw_runs(over_runs, (48, 48, 52), (210, 210, 210))

        def draw_slots(runs):
            for run in runs:
                if len(run) < 2:
                    continue
                ext = run + [(run[-1] + 1) % n]
                for lane in (0, 1):
                    pygame.draw.lines(surf, (20, 20, 20), False, [self.lanes[lane][i] for i in ext], 3)

        draw_slots(under_runs)

        for run in over_runs:
            if len(run) < 2:
                continue
            near = [i for i in run if dist(self.center[i], self.cross) < 95]
            if len(near) < 2:
                near = run
            ext = near + [(near[-1] + 1) % n]
            shadow = [(self.center[i][0] + 8, self.center[i][1] + 14) for i in ext]
            if len(shadow) >= 2:
                pygame.draw.lines(surf, (20, 50, 25), False, shadow, int(ROAD_HALF * 2 + 10))
            poly = self._ribbon_segment(ext)
            if poly:
                raised = [(x, y - 7) for (x, y) in poly]
                pygame.draw.polygon(surf, (62, 62, 68), raised)
                pygame.draw.polygon(surf, (240, 220, 90), raised, 4)
            for lane in (0, 1):
                pts = [(self.lanes[lane][i][0], self.lanes[lane][i][1] - 7) for i in ext]
                pygame.draw.lines(surf, (20, 20, 20), False, pts, 3)

        oil_cols = [(18, 18, 22), (40, 70, 90), (70, 40, 90), (30, 90, 50)]
        for lane in (0, 1):
            pts = self._oil_points(lane)
            if len(pts) < 2:
                continue
            pygame.draw.lines(surf, (12, 12, 16), False, pts, 22)
            pygame.draw.lines(surf, oil_cols[lane * 2], False, pts, 16)
            pygame.draw.lines(surf, oil_cols[lane * 2 + 1], False, pts, 8)
            pygame.draw.lines(surf, (180, 220, 255), False, pts, 2)
            mid = pts[len(pts) // 2]
            tag = FONT.render("OIL", True, (255, 230, 80))
            surf.blit(tag, tag.get_rect(center=(mid[0], mid[1] - 18)))

        i0 = self.start_index
        nx, ny = self.normals[i0]
        x, y = self.center[i0]
        w = ROAD_HALF + 4
        a = (x - nx * w, y - ny * w)
        b = (x + nx * w, y + ny * w)
        for k in range(8):
            t0, t1 = k / 8.0, (k + 1) / 8.0
            p0 = (lerp(a[0], b[0], t0), lerp(a[1], b[1], t0))
            p1 = (lerp(a[0], b[0], t1), lerp(a[1], b[1], t1))
            col = (255, 255, 255) if k % 2 == 0 else (20, 20, 20)
            pygame.draw.line(surf, col, p0, p1, 6)

class Car:
    def __init__(self, name, lane, color, is_ai=False):
        self.name = name
        self.lane = lane
        self.color = color
        self.is_ai = is_ai
        self.reset()

    def reset(self, start_s=40.0):
        self.s = start_s + self.lane * 14.0
        self.speed = 0.0
        self.throttle = 0.0
        self.laps_done = 0
        self.deslot_timer = 0.0
        self.finished = False
        self.finish_time = None
        self.best_lap = None
        self.lap_start_t = 0.0
        self.start_s = start_s
        self.roll_ai_plan(1.0)

    def roll_ai_plan(self, track_len):
        if random.random() < 0.10:
            self.ai_plan = "risk"
        elif random.random() < 0.50:
            self.ai_plan = "before"
        else:
            self.ai_plan = "after"
        self.ai_coast_len = track_len * random.uniform(0.05, 0.20)

    def roll_ai_plan44(self, track_len):
        if random.random() < 0.10:
            self.ai_plan = "risk"
        elif random.random() < 0.50:
            self.ai_plan = "before"
        else:
            self.ai_plan = "after"
        self.ai_coast_len = track_len * random.uniform(0.05, 0.20)

    def laps_from_s(self, track):
        return int(max(0.0, self.s - self.start_s) // track.total_len)

    def update(self, dt, track, race_time, throttle_input):
        if self.finished:
            self.speed = max(0.0, self.speed - 600.0 * dt)
            return
        if self.deslot_timer > 0:
            self.deslot_timer -= dt
            self.speed = 0.0
            return

        prev_laps = self.laps_from_s(track)
        self.throttle = clamp(throttle_input, 0.0, 1.0)
        on_slick = track.on_oil(self.lane, self.s)
        fast = self.speed > SLICK_SAFE_SPEED
        if on_slick and self.throttle > OIL_THROTTLE and fast:
            self.deslot_timer = 0.85
            self.speed = 0.0
            return

        if self.throttle > 0.05:
            self.speed += ACCEL * self.throttle * dt
        else:
            self.speed -= (DRAG * self.speed + COAST_DECEL) * dt
        self.speed = max(0.0, min(self.speed, MAX_SPEED))

        self.s += self.speed * dt
        new_laps = self.laps_from_s(track)
        if new_laps > prev_laps:
            self.laps_done = new_laps
            lap_time = race_time - self.lap_start_t
            if self.laps_done >= 1 and lap_time > 0.4:
                if self.best_lap is None or lap_time < self.best_lap:
                    self.best_lap = lap_time
            self.lap_start_t = race_time
            if self.is_ai:
                self.roll_ai_plan(track.total_len)
            if self.laps_done >= LAPS_TO_WIN:
                self.finished = True
                self.finish_time = race_time

    def draw(self, surf, track, lift=False):
        x, y, ang = track.pos_on_lane(self.lane, self.s)
        if lift:
            y -= 7
        body = pygame.Surface((28, 14), pygame.SRCALPHA)
        pygame.draw.rect(body, self.color, (0, 0, 28, 14), border_radius=3)
        pygame.draw.rect(body, (240, 240, 240), (18, 2, 8, 10), border_radius=2)
        draw_ang = ang + (self.deslot_timer * 12 if self.deslot_timer > 0 else 0)
        rot = pygame.transform.rotate(body, -math.degrees(draw_ang))
        surf.blit(rot, rot.get_rect(center=(x, y)))


def ai_throttle(car, track):
    if car.deslot_timer > 0 or car.finished:
        return 0.0

    L = track.total_len
    on_slick = track.on_oil(car.lane, car.s)
    d_to = track.dist_to_oil(car.lane, car.s)
    oil_end = (track.oil[car.lane] + OIL_LENGTH) % L
    d_after = (car.s % L - oil_end) % L

    # 1-in-10: only "risk" keeps the throttle down on oil
    if on_slick:
        return 1.0 if car.ai_plan == "risk" else 0.0

    if car.ai_plan == "before" and d_to < car.ai_coast_len:
        return 0.0

    if car.ai_plan == "after" and d_after < car.ai_coast_len and d_to > L * 0.5:
        return 0.0

    return 1.0

def ai_throttle44(car, track):
    if car.deslot_timer > 0 or car.finished:
        return 0.0
    L = track.total_len
    on_slick = track.on_oil(car.lane, car.s)
    d_to = track.dist_to_oil(car.lane, car.s)
    oil_end = (track.oil[car.lane] + OIL_LENGTH) % L
    d_after = (car.s % L - oil_end) % L
    if car.ai_plan == "risk":
        return 1.0
    if car.ai_plan == "before":
        if on_slick or d_to < car.ai_coast_len:
            return 0.0
        return 1.0
    if on_slick:
        return 1.0
    if d_after < car.ai_coast_len and d_to > L * 0.5:
        return 0.0
    return 1.0


def draw_text(surf, text, font, color, pos, center=False):
    img = font.render(text, True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surf.blit(img, rect)


def menu():
    sel = 0
    options = ["Player vs Computer", "2 Players", "Quit"]
    while True:
        CLOCK.tick(FPS)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_UP, pygame.K_w):
                    sel = (sel - 1) % len(options)
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    sel = (sel + 1) % len(options)
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if sel == 2:
                        pygame.quit()
                        sys.exit()
                    return sel
        SCREEN.fill((18, 18, 22))
        draw_text(SCREEN, "SLOT CAR RACING", BIG, (255, 210, 60), (WIDTH // 2, 160), True)
        draw_text(SCREEN, "Lift off the OIL if you are fast, or you spin.", FONT, (200, 200, 200), (WIDTH // 2, 230), True)
        draw_text(SCREEN, "P1: W or UP    P2: Numpad 8 or RSHIFT", FONT, (160, 160, 160), (WIDTH // 2, 268), True)
        for i, opt in enumerate(options):
            col = (255, 230, 80) if i == sel else (210, 210, 210)
            prefix = "> " if i == sel else "  "
            draw_text(SCREEN, prefix + opt, MED, col, (WIDTH // 2, 380 + i * 56), True)
        pygame.display.flip()


def race(vs_ai):
    track = Track()
    audio = EngineAudio()
    start_s = track.start_s + 30.0
    p1 = Car("P1", 0, (220, 40, 40), is_ai=False)
    p2 = Car("CPU" if vs_ai else "P2", 1, (40, 90, 220), is_ai=vs_ai)
    p1.reset(start_s)
    p2.reset(start_s)
    p2.roll_ai_plan(track.total_len)
    cars = [p1, p2]
    countdown = 3.2
    race_time = 0.0
    winner = None

    while True:
        dt = min(CLOCK.tick(FPS) / 1000.0, 0.05)
        keys = pygame.key.get_pressed()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.mixer.stop()
                return
            if e.type == pygame.KEYDOWN and e.key == pygame.K_n and winner:
                pygame.mixer.stop()
                return race(vs_ai)

        if countdown > 0:
            countdown -= dt
            t1 = t2 = 0.0
        else:
            race_time += dt
            t1 = 1.0 if (keys[pygame.K_w] or keys[pygame.K_UP]) else 0.0
            if vs_ai:
                t2 = ai_throttle(p2, track)
            else:
                t2 = 1.0 if (keys[pygame.K_RSHIFT] or keys[pygame.K_KP8]) else 0.0

        p1.update(dt, track, race_time, t1)
        p2.update(dt, track, race_time, t2)
        audio.update(dt, p1, p2, track)

        if winner is None:
            done = [c for c in cars if c.finished]
            if done:
                winner = min(done, key=lambda c: c.finish_time)

        track.draw(SCREEN)
        under = [c for c in cars if track.height_at(c.s) < 0.5]
        over = [c for c in cars if track.height_at(c.s) >= 0.5]
        for c in under:
            c.draw(SCREEN, track, lift=False)
        for c in over:
            c.draw(SCREEN, track, lift=True)

        label = "CPU" if vs_ai else "P2"
        draw_text(SCREEN, "P1  Lap %d/%d  %5.0f" % (min(p1.laps_done + 1, LAPS_TO_WIN), LAPS_TO_WIN, p1.speed), FONT, p1.color, (20, 16))
        draw_text(SCREEN, "%s  Lap %d/%d  %5.0f" % (label, min(p2.laps_done + 1, LAPS_TO_WIN), LAPS_TO_WIN, p2.speed), FONT, p2.color, (WIDTH - 430, 16))
        if countdown <= 0:
            draw_text(SCREEN, "%5.2fs" % race_time, FONT, (255, 255, 255), (WIDTH // 2, 16), True)
        draw_text(SCREEN, "ESC menu   N new track after finish", FONT, (180, 180, 180), (20, HEIGHT - 28))
        if p1.deslot_timer > 0:
            draw_text(SCREEN, "P1 HIT OIL!", MED, (255, 80, 80), (WIDTH // 2, 80), True)
        if p2.deslot_timer > 0:
            draw_text(SCREEN, label + " HIT OIL!", MED, (80, 140, 255), (WIDTH // 2, 120), True)
        if countdown > 0:
            msg = "GO!" if countdown < 0.55 else str(max(1, math.ceil(countdown)))
            draw_text(SCREEN, msg, BIG, (255, 255, 255), (WIDTH // 2, HEIGHT // 2), True)
        if winner:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 140))
            SCREEN.blit(overlay, (0, 0))
            draw_text(SCREEN, winner.name + " WINS", BIG, (255, 220, 70), (WIDTH // 2, HEIGHT // 2 - 40), True)
            draw_text(SCREEN, "Time %.2fs   N = new race   ESC = menu" % winner.finish_time, FONT, (230, 230, 230), (WIDTH // 2, HEIGHT // 2 + 20), True)
        pygame.display.flip()


def main():
    while True:
        mode = menu()
        race(vs_ai=(mode == 0))


if __name__ == "__main__":
    main()