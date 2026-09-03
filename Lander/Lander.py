import math
import random
import sys
import pygame

# ---------------------------------------------------------------------------
# Lunar Lander — arcade-style
# Controls: LEFT/RIGHT rotate, UP or SPACE thrust, R restart, ESC quit
# Soft landing: low vertical speed, low horizontal speed, nearly upright,
#               and on a pad.
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 900, 700
FPS = 60

GRAVITY = 0.018
THRUST = 0.055
ROT_SPEED = 2.6
MAX_FUEL = 280
LAND_VY = 1.35
LAND_VX = 0.85
LAND_ANGLE = 12  # degrees from upright

BLACK = (0, 0, 0)
WHITE = (230, 230, 230)
GRAY = (140, 140, 150)
PAD = (80, 220, 90)
FLAME = (255, 170, 40)
FLAME2 = (255, 255, 180)
HUD = (90, 255, 140)
RED = (255, 70, 70)
GOLD = (255, 210, 70)


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
        self.pads = []  # (x0, x1, y)
        self._generate()

    def _generate(self):
        x = 0
        y = h = self.h - 90
        pts = [(0, self.h)]
        pad_slots = [random.randint(140, 280), random.randint(480, 720)]
        while x < self.w:
            is_pad = any(abs(x - s) < 8 for s in pad_slots) and not any(
                abs(x - p[0]) < 80 for p in self.pads
            )
            if is_pad and 80 < x < self.w - 120:
                width = random.choice([70, 90, 110])
                y = min(max(y, self.h - 220), self.h - 70)
                self.pads.append((x, x + width, y))
                pts.append((x, y))
                pts.append((x + width, y))
                x += width
            else:
                step = random.randint(18, 42)
                y += random.randint(-38, 38)
                y = min(max(y, self.h - 280), self.h - 50)
                x += step
                pts.append((min(x, self.w), y))
        pts.append((self.w, self.h))
        pts.append((0, self.h))
        self.points = pts

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
        self.x = random.randint(80, WIDTH - 80)
        self.y = 60
        self.vx = random.uniform(-0.6, 0.6)
        self.vy = 0.2
        self.angle = 0.0  # 0 = upright, + = clockwise
        self.fuel = MAX_FUEL
        self.thrusting = False
        self.alive = True
        self.landed = False
        self.exploding = 0

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

        # classic lander silhouette
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
            fx = self.x - math.sin(rad) * 4
            fy = self.y + math.cos(rad) * 16
            fl = 10 + random.randint(0, 10)
            tip = (fx + math.sin(rad) * fl, fy + math.cos(rad) * fl)
            pygame.draw.polygon(
                surf,
                FLAME,
                [
                    (fx - math.cos(rad) * 5, fy - math.sin(rad) * 5),
                    tip,
                    (fx + math.cos(rad) * 5, fy + math.sin(rad) * 5),
                ],
            )
            pygame.draw.circle(surf, FLAME2, (int(tip[0]), int(tip[1])), 3)

        color = WHITE if self.alive else (180, 180, 180)
        pygame.draw.polygon(surf, color, hull, 2)
        pygame.draw.line(surf, color, *leg_l, 2)
        pygame.draw.line(surf, color, *leg_r, 2)
        pygame.draw.line(surf, color, *foot_l, 2)
        pygame.draw.line(surf, color, *foot_r, 2)
        # window
        rad = math.radians(self.angle)
        wx = self.x + math.sin(rad) * 0
        wy = self.y - math.cos(rad) * 4
        pygame.draw.circle(surf, (80, 180, 255), (int(wx), int(wy)), 3, 1)


def draw_stars(surf, stars):
    for x, y, b in stars:
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

    # fuel bar
    pygame.draw.rect(surf, (40, 40, 40), (WIDTH - 28, 20, 12, 160))
    fh = int(158 * lander.fuel / MAX_FUEL)
    pygame.draw.rect(surf, HUD if lander.fuel > 40 else RED, (WIDTH - 27, 179 - fh, 10, fh))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("LUNAR LANDER")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)
    big = pygame.font.SysFont("consolas", 36, bold=True)
    small = pygame.font.SysFont("consolas", 16)

    stars = [(random.randint(0, WIDTH - 1), random.randint(0, HEIGHT - 1), random.randint(80, 255))
             for _ in range(90)]
    terrain = Terrain(WIDTH, HEIGHT)
    lander = Lander()
    score = 0
    message = ""
    msg_timer = 0

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if e.key == pygame.K_r:
                    terrain = Terrain(WIDTH, HEIGHT)
                    lander.reset()
                    message = ""

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

        screen.blit(small.render("LEFT/RIGHT rotate   UP/SPACE thrust   R new attempt", True, (90, 90, 100)),
                    (16, HEIGHT - 24))
        screen.blit(font.render(f"SCORE {score}", True, GOLD), (WIDTH // 2 - 50, 16))

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