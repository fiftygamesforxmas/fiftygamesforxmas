import json
import math
import os
import random
import sys
import pygame

# ---------------------------------------------------------------------------
# Lunar Lander — arcade-style
# Controls: LEFT/RIGHT rotate, UP or SPACE thrust, R restart, ESC quit
# Window size/position saved. Playfield and pads follow the window size.
# ---------------------------------------------------------------------------

DEFAULT_W, DEFAULT_H = 900, 700
FPS = 60
MIN_WIN_W, MIN_WIN_H = 480, 360

GRAVITY = 0.018
THRUST = 0.055
ROT_SPEED = 2.6
MAX_FUEL = 280
LAND_VY = 1.35
LAND_VX = 0.85
LAND_ANGLE = 12

BLACK = (0, 0, 0)
WHITE = (230, 230, 230)
GRAY = (140, 140, 150)
PAD = (80, 220, 90)
FLAME = (255, 170, 40)
FLAME2 = (255, 255, 180)
HUD = (90, 255, 140)
RED = (255, 70, 70)
GOLD = (255, 210, 70)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lunar_lander_window.json")

WIDTH, HEIGHT = DEFAULT_W, DEFAULT_H


def default_window_config():
    return {"x": 80, "y": 60, "w": DEFAULT_W, "h": DEFAULT_H}


def load_window_config():
    cfg = default_window_config()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in ("x", "y", "w", "h"):
            if key in data:
                cfg[key] = int(data[key])
    except (OSError, ValueError, TypeError):
        pass
    cfg["w"] = max(MIN_WIN_W, cfg["w"])
    cfg["h"] = max(MIN_WIN_H, cfg["h"])
    return cfg


def save_window_config(x, y, w, h):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "x": int(x),
                    "y": int(y),
                    "w": int(max(MIN_WIN_W, w)),
                    "h": int(max(MIN_WIN_H, h)),
                },
                f,
                indent=2,
            )
    except (OSError, TypeError, ValueError):
        pass


def wrap_angle(a):
    while a <= -180:
        a += 360
    while a > 180:
        a -= 360
    return a


class Terrain:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.points = []
        self.pads = []
        self._generate()

    def _generate(self):
        y_min = self.h - int(self.h * 0.40)
        y_max = self.h - int(self.h * 0.07)
        step = max(16, self.w // 40)
        xs = list(range(0, self.w, step))
        if xs[-1] != self.w:
            xs.append(self.w)

        y = self.h - int(self.h * 0.17)
        ys = []
        jitter = max(12, self.h // 20)
        for _ in xs:
            y += random.randint(-jitter, jitter)
            y = min(max(y, y_min), y_max)
            ys.append(y)

        # ~25% smaller than before, with more size variation
        frac_choices = (0.045, 0.055, 0.065, 0.075, 0.090)
        min_w = max(38, int(self.w * 0.04))
        max_w = max(min_w + 8, int(self.w * 0.10))

        def rand_pad_width():
            w = int(self.w * random.choice(frac_choices))
            return max(min_w, min(max_w, w))

        n_pads = 2 if self.w >= 420 else 1
        pad_specs = []
        if n_pads == 1:
            width = rand_pad_width()
            x0 = random.randint(40, max(40, self.w - width - 40))
            pad_specs.append((x0, width))
        else:
            w1 = rand_pad_width()
            w2 = rand_pad_width()
            left_max = max(40, self.w // 2 - w1 - 40)
            x1 = random.randint(40, left_max)
            right_min = self.w // 2 + 20
            right_max = max(right_min, self.w - w2 - 40)
            x2 = random.randint(right_min, right_max)
            if x2 < x1 + w1 + 50:
                x2 = min(self.w - w2 - 40, x1 + w1 + 50)
            pad_specs.append((x1, w1))
            pad_specs.append((x2, w2))

        self.pads = []
        pad_y_lo = self.h - int(self.h * 0.32)
        pad_y_hi = self.h - int(self.h * 0.10)
        for x0, width in pad_specs:
            x1 = min(self.w - 8, x0 + width)
            x0 = max(8, x0)
            if x1 - x0 < min_w:
                x1 = min(self.w - 8, x0 + min_w)
            samples = [ys[i] for i, x in enumerate(xs) if x0 <= x <= x1]
            if not samples:
                i = min(range(len(xs)), key=lambda i: abs(xs[i] - (x0 + x1) / 2))
                samples = [ys[i]]
            pad_y = int(sum(samples) / len(samples))
            pad_y = min(max(pad_y, pad_y_lo), pad_y_hi)
            for i, x in enumerate(xs):
                if x0 <= x <= x1:
                    ys[i] = pad_y
            self.pads.append((x0, x1, pad_y))

        if not self.pads:
            width = rand_pad_width()
            x0 = self.w // 2 - width // 2
            x1 = x0 + width
            pad_y = self.h - int(self.h * 0.16)
            for i, x in enumerate(xs):
                if x0 <= x <= x1:
                    ys[i] = pad_y
            self.pads.append((x0, x1, pad_y))

        pts = [(0, self.h)]
        pts.extend(zip(xs, ys))
        pts.append((self.w, self.h))
        pts.append((0, self.h))
        self.points = pts
        
    def resize(self, new_w, new_h):
        """Stretch ground and pads to the new window size."""
        if self.w <= 0 or self.h <= 0:
            self.w, self.h = new_w, new_h
            self._generate()
            return
        sx = new_w / self.w
        sy = new_h / self.h
        self.points = [(x * sx, y * sy) for x, y in self.points]
        self.pads = [(x0 * sx, x1 * sx, y * sy) for x0, x1, y in self.pads]
        self.w, self.h = new_w, new_h

    def height_at(self, x):
        x = max(0, min(self.w - 1, x))
        for i in range(len(self.points) - 1):
            x0, y0 = self.points[i]
            x1, y1 = self.points[i + 1]
            if x0 <= x <= x1 and x1 != x0:
                t = (x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return self.h - 40

    def on_pad(self, x, tol=6):
        for x0, x1, y in self.pads:
            if x0 + 4 <= x <= x1 - 4:
                return True, y
        return False, None

    def draw(self, surf):
        pygame.draw.polygon(surf, (55, 55, 62), self.points)
        pygame.draw.lines(surf, GRAY, False, self.points[:-2], 2)
        for x0, x1, y in self.pads:
            pygame.draw.line(surf, PAD, (x0, y), (x1, y), 5)
            pygame.draw.line(surf, (30, 90, 40), (x0, y + 3), (x1, y + 3), 2)
            mid = (x0 + x1) / 2
            pygame.draw.line(surf, PAD, (mid, y), (mid, y - 8), 2)


class Lander:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = random.randint(80, max(81, WIDTH - 80))
        self.y = 60
        self.vx = random.uniform(-0.6, 0.6)
        self.vy = 0.2
        self.angle = 0.0
        self.fuel = MAX_FUEL
        self.thrusting = False
        self.alive = True
        self.landed = False
        self.exploding = 0

    def scale(self, sx, sy):
        self.x *= sx
        self.y *= sy
        self.vx *= sx
        self.vy *= sy

    def update(self, keys, terrain):
        if self.exploding:
            self.exploding += 1
            return
        if not self.alive or self.landed:
            return

        if keys[pygame.K_LEFT]:
            self.angle -= ROT_SPEED
        if keys[pygame.K_RIGHT]:
            self.angle += ROT_SPEED
        self.angle = wrap_angle(self.angle)

        self.thrusting = (keys[pygame.K_UP] or keys[pygame.K_SPACE]) and self.fuel > 0
        if self.thrusting:
            rad = math.radians(self.angle)
            self.vx += THRUST * math.sin(rad)
            self.vy -= THRUST * math.cos(rad)
            self.fuel = max(0, self.fuel - 0.55)

        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy

        if self.x < 10:
            self.x, self.vx = 10, abs(self.vx) * 0.3
        if self.x > WIDTH - 10:
            self.x, self.vx = WIDTH - 10, -abs(self.vx) * 0.3

        ground = terrain.height_at(self.x)
        if self.y + 14 >= ground:
            self.y = ground - 14
            on_pad, _ = terrain.on_pad(self.x)
            upright = abs(self.angle) <= LAND_ANGLE
            soft = abs(self.vy) <= LAND_VY and abs(self.vx) <= LAND_VX
            if on_pad and upright and soft:
                self.landed = True
                self.alive = True
                self.vx = self.vy = 0
                self.angle = 0
            else:
                self.alive = False
                self.exploding = 1

    def body_points(self):
        rad = math.radians(self.angle)
        c, s = math.cos(rad), math.sin(rad)

        def rot(px, py):
            return (self.x + px * c - py * s, self.y + px * s + py * c)

        hull = [rot(0, -12), rot(10, 6), rot(6, 10), rot(-6, 10), rot(-10, 6)]
        leg_l = [rot(-6, 10), rot(-14, 16)]
        leg_r = [rot(6, 10), rot(14, 16)]
        foot_l = [rot(-17, 16), rot(-11, 16)]
        foot_r = [rot(11, 16), rot(17, 16)]
        return hull, leg_l, leg_r, foot_l, foot_r

    def draw(self, surf):
        if self.exploding:
            r = 8 + self.exploding * 2
            pygame.draw.circle(surf, (255, 120, 40), (int(self.x), int(self.y)), r, 2)
            pygame.draw.circle(surf, (255, 220, 80), (int(self.x), int(self.y)), max(2, r // 2))
            for i in range(8):
                a = i * 45 + self.exploding * 6
                rr = r + 10
                pygame.draw.circle(
                    surf,
                    FLAME,
                    (
                        int(self.x + math.cos(math.radians(a)) * rr),
                        int(self.y + math.sin(math.radians(a)) * rr * 0.7),
                    ),
                    3,
                )
            return

        hull, leg_l, leg_r, foot_l, foot_r = self.body_points()
        if self.thrusting and self.alive and not self.landed:
            rad = math.radians(self.angle)
            tail_x = -math.sin(rad)
            tail_y = math.cos(rad)
            fx = self.x + tail_x * 12
            fy = self.y + tail_y * 12
            fl = 10 + random.randint(0, 10)
            tip = (fx + tail_x * fl, fy + tail_y * fl)
            side_x = math.cos(rad) * 5
            side_y = math.sin(rad) * 5
            pygame.draw.polygon(
                surf,
                FLAME,
                [(fx - side_x, fy - side_y), tip, (fx + side_x, fy + side_y)],
            )
            pygame.draw.circle(surf, FLAME2, (int(tip[0]), int(tip[1])), 3)

        color = WHITE if self.alive else (180, 180, 180)
        pygame.draw.polygon(surf, color, hull, 2)
        pygame.draw.line(surf, color, *leg_l, 2)
        pygame.draw.line(surf, color, *leg_r, 2)
        pygame.draw.line(surf, color, *foot_l, 2)
        pygame.draw.line(surf, color, *foot_r, 2)
        rad = math.radians(self.angle)
        pygame.draw.circle(
            surf, (80, 180, 255), (int(self.x), int(self.y - math.cos(rad) * 4)), 3, 1
        )


def make_stars(w, h):
    return [
        (random.randint(0, max(0, w - 1)), random.randint(0, max(0, h - 1)), random.randint(80, 255))
        for _ in range(90)
    ]


def scale_stars(stars, sx, sy, w, h):
    return [
        (min(w - 1, max(0, int(x * sx))), min(h - 1, max(0, int(y * sy))), b)
        for x, y, b in stars
    ]


def draw_stars(surf, stars):
    w, h = surf.get_size()
    for x, y, b in stars:
        if 0 <= x < w and 0 <= y < h:
            surf.set_at((x, y), (b, b, b))


def draw_hud(surf, font, lander, terrain):
    alt = max(0, terrain.height_at(lander.x) - (lander.y + 14))
    lines = [
        f"ALT  {alt:6.0f}",
        f"HS   {lander.vx*10:6.1f}",
        f"VS   {lander.vy*10:6.1f}",
        f"ANG  {lander.angle:6.0f}",
        f"FUEL {lander.fuel:6.0f}",
    ]
    for i, t in enumerate(lines):
        col = HUD
        if i == 1 and abs(lander.vx) > LAND_VX:
            col = RED
        if i == 2 and lander.vy > LAND_VY:
            col = RED
        if i == 3 and abs(lander.angle) > LAND_ANGLE:
            col = RED
        if i == 4 and lander.fuel < 40:
            col = RED
        surf.blit(font.render(t, True, col), (16, 16 + i * 22))

    pygame.draw.rect(surf, (40, 40, 40), (WIDTH - 28, 20, 12, 160))
    fh = int(158 * lander.fuel / MAX_FUEL)
    pygame.draw.rect(surf, HUD if lander.fuel > 40 else RED, (WIDTH - 27, 179 - fh, 10, fh))


def main():
    global WIDTH, HEIGHT

    cfg = load_window_config()
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{cfg['x']},{cfg['y']}"

    pygame.init()
    pygame.display.set_caption("LUNAR LANDER")
    screen = pygame.display.set_mode((cfg["w"], cfg["h"]), pygame.RESIZABLE)
    WIDTH, HEIGHT = screen.get_size()
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)
    big = pygame.font.SysFont("consolas", 36, bold=True)
    small = pygame.font.SysFont("consolas", 16)

    win_x, win_y = cfg["x"], cfg["y"]
    win_w, win_h = WIDTH, HEIGHT

    stars = make_stars(WIDTH, HEIGHT)
    terrain = Terrain(WIDTH, HEIGHT)
    lander = Lander()
    score = 0
    message = ""
    msg_timer = 0

    def remember_and_save():
        save_window_config(win_x, win_y, win_w, win_h)

    def apply_resize(new_w, new_h):
        global WIDTH, HEIGHT
        new_w = max(MIN_WIN_W, int(new_w))
        new_h = max(MIN_WIN_H, int(new_h))
        if new_w == WIDTH and new_h == HEIGHT:
            return
        sx = new_w / max(1, WIDTH)
        sy = new_h / max(1, HEIGHT)
        terrain.resize(new_w, new_h)
        lander.scale(sx, sy)
        nonlocal_stars = scale_stars(stars, sx, sy, new_w, new_h)
        stars[:] = nonlocal_stars
        WIDTH, HEIGHT = new_w, new_h

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                remember_and_save()
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    remember_and_save()
                    pygame.quit()
                    sys.exit()
                if e.key == pygame.K_r:
                    terrain = Terrain(WIDTH, HEIGHT)
                    lander.reset()
                    message = ""
            if e.type == pygame.VIDEORESIZE:
                win_w = max(MIN_WIN_W, int(getattr(e, "w", win_w)))
                win_h = max(MIN_WIN_H, int(getattr(e, "h", win_h)))
                apply_resize(win_w, win_h)
                remember_and_save()
            if hasattr(pygame, "WINDOWRESIZED") and e.type == pygame.WINDOWRESIZED:
                win_w = max(MIN_WIN_W, int(getattr(e, "x", win_w)))
                win_h = max(MIN_WIN_H, int(getattr(e, "y", win_h)))
                apply_resize(win_w, win_h)
                remember_and_save()
            if hasattr(pygame, "WINDOWMOVED") and e.type == pygame.WINDOWMOVED:
                win_x = int(getattr(e, "x", win_x))
                win_y = int(getattr(e, "y", win_y))
                remember_and_save()

        surface = pygame.display.get_surface()
        if surface is not None:
            cur_w, cur_h = surface.get_size()
            if cur_w >= MIN_WIN_W and cur_h >= MIN_WIN_H and (cur_w != WIDTH or cur_h != HEIGHT):
                win_w, win_h = cur_w, cur_h
                apply_resize(cur_w, cur_h)

        keys = pygame.key.get_pressed()
        prev_landed = lander.landed
        lander.update(keys, terrain)

        if lander.landed and not prev_landed:
            bonus = int(lander.fuel * 2 + 100)
            score += bonus
            message = f"THE EAGLE HAS LANDED  +{bonus}"
            msg_timer = 180
        if lander.exploding == 2:
            message = "CRASH — PRESS R"
            msg_timer = 9999

        screen.fill(BLACK)
        draw_stars(screen, stars)
        terrain.draw(screen)
        lander.draw(screen)
        draw_hud(screen, font, lander, terrain)
        screen.blit(
            small.render("LEFT/RIGHT rotate   UP/SPACE thrust   R new attempt", True, (90, 90, 100)),
            (16, HEIGHT - 24),
        )
        screen.blit(font.render(f"SCORE {score}", True, GOLD), (max(8, WIDTH // 2 - 50), 16))

        if message:
            msg_timer -= 1
            label = big.render(message, True, GOLD if lander.landed else RED)
            screen.blit(label, label.get_rect(center=(WIDTH // 2, 120)))
            if lander.landed:
                hint = small.render("Press R for another landing site", True, WHITE)
                screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 160)))

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()