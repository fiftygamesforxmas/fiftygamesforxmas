import pygame
import random
import math
import numpy as np
import os
import pickle
from pygame import mixer

pygame.init()
mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

WIDTH, HEIGHT = 1400, 800
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("humans")
clock = pygame.time.Clock()
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED = (255, 50, 50)
ORANGE = (255, 140, 0)
GREEN = (50, 255, 50)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)
BLUE = (50, 100, 255)
PURPLE = (180, 50, 255)
DARK_GRAY = (40, 40, 40)
OIL = (30, 20, 10)
WATER = (20, 60, 140)
FIRE = (255, 100, 0)
PINK = (255, 150, 180)
TEAL = (0, 180, 180)
GOLD = (220, 180, 60)
BUILDING_COLORS = [(180, 80, 60), (100, 140, 180), (160, 160, 80), (120, 80, 140), (80, 160, 120)]

try:
    title_font = pygame.font.SysFont("arial", 48, bold=True)
    crawl_font = pygame.font.SysFont("arial", 32)
    ui_font = pygame.font.SysFont("consolas", 24)
    small_font = pygame.font.SysFont("consolas", 18)
    store_font = pygame.font.SysFont("consolas", 22)
except:
    title_font = pygame.font.Font(None, 48)
    crawl_font = pygame.font.Font(None, 32)
    ui_font = pygame.font.Font(None, 24)
    small_font = pygame.font.Font(None, 18)
    store_font = pygame.font.Font(None, 22)

VOLUME = 0.6
UI_BAR_HEIGHT = 42
GROUND_OFFSET = UI_BAR_HEIGHT + 12
SAVE_FILE = "humans_save.pkl"

def make_sound(freq, duration=0.15, volume=0.3, wave="sine"):
    sample_rate = 22050
    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, False)
    if wave == "sine":
        wave_data = np.sin(2 * np.pi * freq * t)
    elif wave == "square":
        wave_data = np.sign(np.sin(2 * np.pi * freq * t))
    else:
        wave_data = np.random.uniform(-1, 1, n_samples)
    wave_data *= volume * 32767
    wave_data = wave_data.astype(np.int16)
    stereo = np.column_stack((wave_data, wave_data))
    return mixer.Sound(stereo)

snd_bomb = make_sound(80, 0.25, 0.4, "sine")
snd_strafe = make_sound(440, 0.08, 0.25, "square")
snd_explosion = make_sound(60, 0.4, 0.5, "noise")
snd_robot_hit = make_sound(220, 0.12, 0.3, "sine")
snd_spark = make_sound(880, 0.1, 0.2, "sine")
snd_hit_player = make_sound(150, 0.2, 0.4, "square")
snd_crumble = make_sound(40, 0.6, 0.45, "noise")
snd_electric = make_sound(1200, 0.18, 0.35, "square")
snd_oil = make_sound(90, 0.2, 0.2, "noise")
snd_fire = make_sound(200, 0.3, 0.4, "noise")
snd_atomic = make_sound(40, 1.2, 0.7, "noise")
snd_missile = make_sound(180, 0.2, 0.35, "sine")

def play(snd):
    ch = snd.play()
    if ch:
        ch.set_volume(VOLUME)

def load_highscores():
    if not os.path.exists("highscores.txt"):
        return [0] * 10
    try:
        with open("highscores.txt", "r") as f:
            scores = [int(line.strip()) for line in f if line.strip()]
            return (scores + [0] * 10)[:10]
    except:
        return [0] * 10

def save_highscores(scores):
    scores = sorted(scores, reverse=True)[:10]
    with open("highscores.txt", "w") as f:
        for s in scores:
            f.write(f"{s}\n")
    return scores

highscores = load_highscores()

STATE_TITLE = 0
STATE_PLAYING = 1
STATE_GAMEOVER = 2
STATE_STORE = 3

class Particle:
    def __init__(self, x, y, color, vx=0, vy=0, life=30, size=4, gravity=0):
        self.x = x
        self.y = y
        self.color = color
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.gravity = gravity

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.life -= 1
        return self.life > 0

    def draw(self, surface, cam_x):
        alpha = int(255 * (self.life / self.max_life))
        s = pygame.Surface((self.size*2, self.size*2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color[:3], alpha), (self.size, self.size), max(1, int(self.size * self.life / self.max_life)))
        surface.blit(s, (int(self.x - cam_x - self.size), int(self.y - self.size)))

class OilPuddle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.life = 300
        self.size = random.randint(8, 18)

    def update(self):
        self.life -= 1
        return self.life > 0

    def draw(self, surface, cam_x):
        alpha = int(180 * (self.life / 300))
        s = pygame.Surface((self.size*2, self.size), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (*OIL, alpha), (0, 0, self.size*2, self.size))
        surface.blit(s, (int(self.x - cam_x - self.size), int(self.y - self.size//2)))

class FirePatch:
    def __init__(self, x, y, life=180):
        self.x = x
        self.y = y
        self.life = life
        self.max_life = life

    def update(self, particles):
        self.life -= 1
        if random.random() < 0.4:
            particles.append(Particle(self.x + random.uniform(-15, 15), self.y,
                                      random.choice([FIRE, ORANGE, YELLOW]),
                                      random.uniform(-0.5, 0.5), random.uniform(-3, -1), 20, 5, -0.05))
        return self.life > 0

    def draw(self, surface, cam_x):
        alpha = int(200 * (self.life / self.max_life))
        s = pygame.Surface((40, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (*FIRE, alpha), (0, 0, 40, 20))
        surface.blit(s, (int(self.x - cam_x - 20), int(self.y - 10)))

class BodyPart:
    def __init__(self, x, y, part_type, color, vx=0, vy=0, ang_vel=0):
        self.x = x
        self.y = y
        self.part_type = part_type
        self.color = color
        self.vx = vx
        self.vy = vy
        self.angle = random.uniform(0, 360)
        self.ang_vel = ang_vel
        self.life = 220
        self.burning = part_type == "body"
        self.oil_timer = 0

    def update(self, particles, oil_puddles, ground_y):
        self.vy += 0.4
        self.x += self.vx
        self.y += self.vy
        self.angle += self.ang_vel
        self.ang_vel *= 0.985
        self.vx *= 0.98
        if self.y > ground_y - 10:
            self.y = ground_y - 10
            self.vy *= -0.4
            self.vx *= 0.6
            self.ang_vel *= 0.45
            if random.random() < 0.3:
                oil_puddles.append(OilPuddle(self.x, ground_y - 4))
        if self.burning and random.random() < 0.25:
            particles.append(Particle(self.x, self.y, random.choice([ORANGE, RED, YELLOW]),
                                      random.uniform(-1, 1), random.uniform(-2, 0), 15, 3, -0.05))
        self.oil_timer += 1
        if self.oil_timer % 8 == 0:
            particles.append(Particle(self.x, self.y, OIL, random.uniform(-0.5, 0.5), 1.5, 25, 3, 0.2))
        self.life -= 1
        return self.life > 0

    def draw(self, surface, cam_x):
        px = int(self.x - cam_x)
        py = int(self.y)
        if self.part_type == "head":
            surf = pygame.Surface((16, 16), pygame.SRCALPHA)
            pygame.draw.circle(surf, WHITE, (8, 8), 7)
            pygame.draw.circle(surf, BLACK, (6, 6), 2)
            pygame.draw.circle(surf, BLACK, (10, 6), 2)
            rot = pygame.transform.rotate(surf, self.angle)
            surface.blit(rot, (px - rot.get_width()//2, py - rot.get_height()//2))
        elif self.part_type == "body":
            surf = pygame.Surface((18, 22), pygame.SRCALPHA)
            pygame.draw.rect(surf, self.color, (2, 2, 14, 18))
            rot = pygame.transform.rotate(surf, self.angle)
            surface.blit(rot, (px - rot.get_width()//2, py - rot.get_height()//2))
        elif self.part_type == "arm":
            surf = pygame.Surface((20, 8), pygame.SRCALPHA)
            pygame.draw.line(surf, self.color, (2, 4), (18, 4), 4)
            rot = pygame.transform.rotate(surf, self.angle + math.sin(pygame.time.get_ticks() * 0.01) * 40)
            surface.blit(rot, (px - rot.get_width()//2, py - rot.get_height()//2))

class Explosion:
    def __init__(self, x, y, big=False, atomic=False):
        self.x = x
        self.y = y
        self.particles = []
        self.force = 30 if atomic else (16 if big else 9)
        count = 120 if atomic else (45 if big else 22)
        for _ in range(count):
            ang = random.uniform(0, math.pi * 2)
            spd = random.uniform(3, 15 if atomic else (9 if big else 5))
            col = random.choice([ORANGE, YELLOW, RED, WHITE, MAGENTA, CYAN])
            self.particles.append(Particle(x, y, col, math.cos(ang)*spd, math.sin(ang)*spd, random.randint(30, 70 if atomic else 45), random.randint(4, 12), 0.12))
        if atomic:
            play(snd_atomic)
        else:
            play(snd_explosion if big else snd_bomb)

    def apply_concussion(self, robots):
        for r in robots:
            if not r.alive:
                continue
            dx = r.x - self.x
            dy = r.y - self.y
            dist = max(30, math.hypot(dx, dy))
            if dist < (300 if self.force > 20 else 160):
                force = self.force * (1 - dist / 300) * 0.5
                r.vx += (dx / dist) * force
                r.vy += (dy / dist) * force - 6
                r.ragdoll = True
                r.ang_vel = random.uniform(-15, 15)

    def blow_apart_robot(self, robot, parts, oil_puddles):
        base_vx = random.uniform(-8, 8)
        base_vy = random.uniform(-10, -3)
        parts.append(BodyPart(robot.x, robot.y - 8, "head", robot.color, base_vx, base_vy - 2, random.uniform(-20, 20)))
        parts.append(BodyPart(robot.x, robot.y, "body", robot.color, base_vx * 0.7, base_vy, random.uniform(-10, 10)))
        parts.append(BodyPart(robot.x - 6, robot.y, "arm", robot.color, base_vx - 3, base_vy, random.uniform(-25, 25)))
        parts.append(BodyPart(robot.x + 6, robot.y, "arm", robot.color, base_vx + 3, base_vy, random.uniform(-25, 25)))
        oil_puddles.append(OilPuddle(robot.x, robot.y + 10))
        play(snd_oil)
        robot.alive = False
        robot.remove_me = True

    def update(self):
        self.particles = [p for p in self.particles if p.update()]
        return len(self.particles) > 0

    def draw(self, surface, cam_x):
        for p in self.particles:
            p.draw(surface, cam_x)

class Bomb:
    def __init__(self, x, y, vx, bomb_type="normal"):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = 1.5
        self.alive = True
        self.bomb_type = bomb_type

    def update(self, buildings, bridges, cars, carriers, bigboxes, explosions, robots, parts, oil_puddles, fires, ground_y):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.28
        exploded = False

        if self.y >= ground_y - 8:
            exploded = True

        for b in buildings:
            if b.alive and b.rect.collidepoint(self.x, self.y):
                if self.bomb_type == "napalm":
                    b.take_damage(40)
                    fires.append(FirePatch(self.x, ground_y - 5, 300))
                else:
                    b.take_damage(90)
                exploded = True
                break

        for br in bridges:
            if br.alive and br.rect.collidepoint(self.x, self.y):
                br.take_damage(100)
                exploded = True
                break

        for c in cars:
            if c.alive and abs(c.x - self.x) < 30 and abs(c.y - self.y) < 20:
                c.take_damage(120)
                exploded = True
                break

        for tc in carriers:
            if tc.alive and abs(tc.x - self.x) < 40 and abs(tc.y - self.y) < 25:
                tc.take_damage(150)
                exploded = True
                break

        for bb in bigboxes:
            if bb.alive and abs(bb.x - self.x) < 50 and abs(bb.y - self.y) < 30:
                bb.take_damage(200)
                exploded = True
                break

        if not exploded:
            for r in robots:
                if r.alive and abs(r.x - self.x) < 18 and abs(r.y - self.y) < 22:
                    exploded = True
                    break

        if exploded:
            if self.bomb_type == "atomic":
                exp = Explosion(self.x, self.y, atomic=True)
                for b in buildings[:]:
                    if abs(b.x - self.x) < 800:
                        b.alive = False
                for r in robots[:]:
                    if abs(r.x - self.x) < 600:
                        exp.blow_apart_robot(r, parts, oil_puddles)
                play(snd_atomic)
            elif self.bomb_type == "napalm":
                exp = Explosion(self.x, self.y, big=True)
                fires.append(FirePatch(self.x, ground_y - 5, 400))
                for _ in range(5):
                    fires.append(FirePatch(self.x + random.uniform(-40, 40), ground_y - 5, 250))
                play(snd_fire)
            else:
                exp = Explosion(self.x, self.y, big=True)
            for r in robots[:]:
                if r.alive and abs(r.x - self.x) < 35 and abs(r.y - self.y) < 35:
                    exp.blow_apart_robot(r, parts, oil_puddles)
            exp.apply_concussion(robots)
            explosions.append(exp)
            self.alive = False
        return exploded

    def draw(self, surface, cam_x):
        color = RED if self.bomb_type == "normal" else (ORANGE if self.bomb_type == "napalm" else MAGENTA)
        pygame.draw.circle(surface, (40, 40, 40), (int(self.x - cam_x), int(self.y)), 7)
        pygame.draw.circle(surface, color, (int(self.x - cam_x), int(self.y)), 4)

class Missile:
    def __init__(self, x, y, target=None):
        self.x = x
        self.y = y
        self.vx = 8
        self.vy = 0
        self.alive = True
        self.target = target

    def update(self, buildings, robots, explosions, parts, oil_puddles):
        if self.target and self.target.alive:
            dx = self.target.x - self.x
            dy = self.target.y - self.y
            dist = max(1, math.hypot(dx, dy))
            self.vx = dx / dist * 9
            self.vy = dy / dist * 9
        self.x += self.vx
        self.y += self.vy
        if self.y > HEIGHT or self.x < -100 or self.x > 10000:
            self.alive = False
            return
        for b in buildings:
            if b.alive and b.rect.collidepoint(self.x, self.y):
                b.take_damage(150)
                explosions.append(Explosion(self.x, self.y, big=True))
                self.alive = False
                return
        for r in robots:
            if r.alive and abs(r.x - self.x) < 20 and abs(r.y - self.y) < 20:
                explosions.append(Explosion(self.x, self.y))
                self.alive = False
                return

    def draw(self, surface, cam_x):
        pygame.draw.circle(surface, CYAN, (int(self.x - cam_x), int(self.y)), 5)
        pygame.draw.circle(surface, WHITE, (int(self.x - cam_x), int(self.y)), 2)

class SuicideRobot:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = random.choice([-3, 3])
        self.alive = True
        self.timer = 300

    def update(self, buildings, robots, explosions, parts, oil_puddles, ground_y):
        self.x += self.vx
        self.y = ground_y - 16
        self.timer -= 1
        if self.timer <= 0:
            self.explode(explosions, parts, oil_puddles)
            return False
        for b in buildings:
            if b.alive and abs(self.x - b.x) < 40 and abs(self.y - b.y) < 40:
                self.explode(explosions, parts, oil_puddles)
                b.take_damage(200)
                return False
        for r in robots:
            if r.alive and abs(self.x - r.x) < 20 and abs(self.y - r.y) < 20:
                self.explode(explosions, parts, oil_puddles)
                return False
        return True

    def explode(self, explosions, parts, oil_puddles):
        explosions.append(Explosion(self.x, self.y, big=True))
        self.alive = False
        play(snd_explosion)

    def draw(self, surface, cam_x):
        px = int(self.x - cam_x)
        py = int(self.y)
        pygame.draw.rect(surface, RED, (px - 10, py - 12, 20, 16))
        pygame.draw.circle(surface, YELLOW, (px, py - 16), 5)

class Bullet:
    def __init__(self, x, y, vx, vy, friendly=True, color=YELLOW):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.friendly = friendly
        self.color = color
        self.alive = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.y < -40 or self.y > HEIGHT + 40:
            self.alive = False

    def draw(self, surface, cam_x):
        pygame.draw.line(surface, self.color, (int(self.x - cam_x), int(self.y)),
                         (int(self.x - cam_x - self.vx * 2), int(self.y - self.vy * 2)), 3)

class Robot:
    def __init__(self, x, y, golfing=False):
        self.x = x
        self.y = y
        self.vx = random.choice([-2.2, -1.4, 1.4, 2.2])
        self.vy = 0
        self.alive = True
        self.ragdoll = False
        self.remove_me = False
        self.angle = 0
        self.ang_vel = 0
        self.shoot_timer = random.randint(50, 130)
        self.color = random.choice([RED, MAGENTA, ORANGE])
        self.on_bridge = False
        self.burning = False
        self.burn_time = 0
        self.frantic = False
        self.golfing = golfing
        self.swing_timer = random.randint(30, 80)
        self.golf_ball = None

    def update(self, player, bullets, ground_y, bridges, water_zones, fires, particles, golf_balls):
        if not self.alive:
            return False
        if self.burning:
            self.burn_time += 1
            self.frantic = True
            self.vx = random.choice([-4, -3, 3, 4]) if random.random() < 0.3 else self.vx
            if random.random() < 0.4:
                particles.append(Particle(self.x, self.y - 5, random.choice([FIRE, ORANGE]),
                                          random.uniform(-1, 1), random.uniform(-2, 0), 15, 3))
            if self.burn_time > 120:
                self.alive = False
                self.remove_me = True
                return False
        if self.ragdoll:
            self.vy += 0.4
            self.x += self.vx
            self.y += self.vy
            self.angle += self.ang_vel
            self.ang_vel *= 0.97
            self.vx *= 0.985
            for wz in water_zones:
                if wz[0] < self.x < wz[1] and self.y > ground_y - 20:
                    self.alive = False
                    self.remove_me = True
                    return False
            if self.y >= ground_y - 12:
                self.y = ground_y - 12
                self.vy *= -0.35
                self.vx *= 0.6
                self.ang_vel *= 0.5
                if abs(self.vy) < 1.2 and abs(self.vx) < 0.8:
                    self.ragdoll = False
                    self.angle = 0
            return True
        else:
            self.x += self.vx
            self.y = ground_y - 16
            supported = False
            for br in bridges:
                if br.alive and br.x < self.x < br.x + br.w:
                    self.y = br.y - 16
                    supported = True
                    self.on_bridge = True
                    break
            if not supported:
                self.on_bridge = False
                for wz in water_zones:
                    if wz[0] < self.x < wz[1]:
                        self.alive = False
                        self.remove_me = True
                        return False
            for f in fires:
                if abs(self.x - f.x) < 25 and abs(self.y - f.y) < 20:
                    self.burning = True
                    break
            if self.golfing:
                self.swing_timer -= 1
                if self.swing_timer <= 0:
                    ball = {"x": self.x + 20, "y": self.y - 5, "vx": random.uniform(4, 8), "vy": random.uniform(-6, -2), "alive": True}
                    golf_balls.append(ball)
                    self.swing_timer = random.randint(40, 90)
            else:
                if random.random() < 0.012 and not self.frantic:
                    self.vx = -self.vx
                self.shoot_timer -= 1
                if self.shoot_timer <= 0 and abs(self.x - player.x) < 550 and not self.burning:
                    dx = player.x - self.x
                    dy = player.y - self.y
                    dist = max(1, math.hypot(dx, dy))
                    bullets.append(Bullet(self.x, self.y - 8, dx / dist * 5.5, dy / dist * 5.5, False, RED))
                    self.shoot_timer = random.randint(70, 160)
            return True

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        px = int(self.x - cam_x)
        py = int(self.y)
        if self.ragdoll:
            body = pygame.Surface((20, 28), pygame.SRCALPHA)
            pygame.draw.rect(body, self.color, (2, 6, 16, 18))
            pygame.draw.circle(body, WHITE, (10, 6), 6)
            pygame.draw.circle(body, BLACK, (8, 5), 2)
            pygame.draw.circle(body, BLACK, (12, 5), 2)
            rot = pygame.transform.rotate(body, self.angle)
            surface.blit(rot, (px - rot.get_width() // 2, py - rot.get_height() // 2))
        else:
            col = self.color if not self.burning else FIRE
            pygame.draw.rect(surface, col, (px - 8, py - 16, 16, 20))
            pygame.draw.circle(surface, WHITE, (px, py - 20), 6)
            pygame.draw.circle(surface, BLACK, (px - 2, py - 21), 2)
            pygame.draw.circle(surface, BLACK, (px + 2, py - 21), 2)
            if self.golfing:
                pygame.draw.line(surface, BLACK, (px + 8, py - 8), (px + 20, py - 2), 2)
            else:
                pygame.draw.line(surface, col, (px - 8, py - 8), (px - 14, py - 2), 3)
                pygame.draw.line(surface, col, (px + 8, py - 8), (px + 14, py - 2), 3)

class FerrisWheel:
    def __init__(self, x, ground_y):
        self.x = x
        self.y = ground_y - 80
        self.angle = 0
        self.alive = True

    def update(self):
        self.angle += 0.8

    def draw(self, surface, cam_x):
        px = int(self.x - cam_x)
        py = int(self.y)
        pygame.draw.circle(surface, GOLD, (px, py), 60, 4)
        for i in range(8):
            ang = math.radians(self.angle + i * 45)
            gx = px + math.cos(ang) * 55
            gy = py + math.sin(ang) * 55
            pygame.draw.circle(surface, PINK, (int(gx), int(gy)), 8)
        pygame.draw.line(surface, DARK_GRAY, (px - 10, py + 60), (px + 10, py + 60), 6)

class Building:
    def __init__(self, x, ground_y, kind="normal", w=None, h=None):
        self.kind = kind
        if kind == "mall":
            self.w = w or random.randint(240, 360)
            self.h = h or random.randint(160, 240)
            self.robots_inside = random.randint(40, 70)
            self.color = (180, 140, 100)
        elif kind == "themepark":
            self.w = w or random.randint(200, 280)
            self.h = h or random.randint(100, 160)
            self.robots_inside = random.randint(15, 30)
            self.color = (100, 180, 220)
            self.ferris = FerrisWheel(x + self.w // 2, ground_y)
        elif kind == "zoo":
            self.w = w or random.randint(180, 260)
            self.h = h or random.randint(120, 180)
            self.robots_inside = random.randint(10, 25)
            self.color = (80, 160, 80)
        elif kind == "golf":
            self.w = w or random.randint(160, 220)
            self.h = h or random.randint(40, 80)
            self.robots_inside = random.randint(8, 16)
            self.color = (60, 140, 60)
        elif kind == "freeway":
            self.w = w or random.randint(300, 500)
            self.h = h or 30
            self.robots_inside = 0
            self.color = (70, 70, 70)
        else:
            self.w = w or random.randint(90, 170)
            self.h = h or random.randint(140, 300)
            self.robots_inside = random.randint(6, 15)
            self.color = random.choice(BUILDING_COLORS)
        self.x = x
        self.y = ground_y - self.h
        self.max_health = self.w * 2.2
        self.health = self.max_health
        self.alive = True
        self.damage_stage = 0
        self.spark_timer = 0
        self.rect = pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0 and self.alive:
            self.alive = False
            play(snd_crumble)
            return True
        self.damage_stage = max(0, 1 - (self.health / self.max_health))
        if random.random() < 0.25:
            self.spark_timer = 35
        return False

    def update(self, particles, robots, parts, oil_puddles):
        if hasattr(self, "ferris"):
            self.ferris.update()
        if self.spark_timer > 0:
            self.spark_timer -= 1
            if random.random() < 0.35:
                sx = self.x + random.randint(5, self.w - 5)
                sy = self.y + random.randint(10, max(20, self.h // 2))
                particles.append(Particle(sx, sy, YELLOW, random.uniform(-2.5, 2.5), random.uniform(-4, -1), 22, 4, 0.08))

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        shade = int(255 * (1 - self.damage_stage * 0.65))
        col = tuple(max(0, min(255, c * shade // 255)) for c in self.color)
        rect = pygame.Rect(int(self.x - cam_x), int(self.y), self.w, self.h)
        pygame.draw.rect(surface, col, rect)
        pygame.draw.rect(surface, BLACK, rect, 2)
        if self.kind == "mall":
            for i in range(3):
                ax = self.x + 30 + i * (self.w // 4)
                pygame.draw.arc(surface, GOLD, (int(ax - cam_x), int(self.y + 40), 60, 40), 0, math.pi, 3)
            label = small_font.render("FASHION", True, WHITE)
            surface.blit(label, (int(self.x - cam_x + self.w//2 - 30), int(self.y + 15)))
        elif self.kind == "themepark":
            if hasattr(self, "ferris"):
                self.ferris.draw(surface, cam_x)
            label = small_font.render("PARK", True, WHITE)
            surface.blit(label, (int(self.x - cam_x + 10), int(self.y + 10)))
        elif self.kind == "zoo":
            pygame.draw.rect(surface, (100, 200, 100), (int(self.x - cam_x + 20), int(self.y + 30), self.w - 40, 40))
            label = small_font.render("ZOO", True, WHITE)
            surface.blit(label, (int(self.x - cam_x + self.w//2 - 15), int(self.y + 10)))
        elif self.kind == "golf":
            pygame.draw.circle(surface, WHITE, (int(self.x - cam_x + self.w//2), int(self.y + self.h - 10)), 8)
            label = small_font.render("GOLF", True, WHITE)
            surface.blit(label, (int(self.x - cam_x + 10), int(self.y + 5)))
        elif self.kind == "freeway":
            pygame.draw.rect(surface, (50, 50, 50), rect)
            for lane in range(3):
                pygame.draw.line(surface, YELLOW, (int(self.x - cam_x), int(self.y + 8 + lane * 8)),
                                 (int(self.x + self.w - cam_x), int(self.y + 8 + lane * 8)), 2)
        else:
            for wy in range(self.y + 12, self.y + self.h - 8, 22):
                for wx in range(self.x + 8, self.x + self.w - 8, 18):
                    if random.random() > self.damage_stage * 0.75:
                        pygame.draw.rect(surface, YELLOW if random.random() > 0.65 else (170, 170, 90),
                                         (int(wx - cam_x), int(wy), 7, 10))
        if self.damage_stage > 0.45:
            pygame.draw.line(surface, BLACK, (int(self.x - cam_x + 8), int(self.y + 15)),
                             (int(self.x - cam_x + self.w - 8), int(self.y + self.h - 15)), 2)

class Bridge:
    def __init__(self, x, ground_y, w=280):
        self.x = x
        self.w = w
        self.y = ground_y - 8
        self.health = 400
        self.max_health = 400
        self.alive = True
        self.rect = pygame.Rect(self.x, self.y - 10, self.w, 20)
        self.water_start = x
        self.water_end = x + w

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0 and self.alive:
            self.alive = False
            play(snd_crumble)
            return True
        return False

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        shade = int(200 * (self.health / self.max_health))
        pygame.draw.rect(surface, (shade, shade, shade), (int(self.x - cam_x), int(self.y - 6), self.w, 12))
        pygame.draw.rect(surface, (80, 80, 80), (int(self.x - cam_x), int(self.y - 6), self.w, 12), 2)
        pygame.draw.line(surface, (60, 60, 60), (int(self.x - cam_x), int(self.y - 16)), (int(self.x + self.w - cam_x), int(self.y - 16)), 3)

class Car:
    def __init__(self, x, ground_y, freeway=False):
        self.x = x
        self.y = ground_y - 18
        self.vx = random.choice([-4.5, -3.5, 3.5, 4.5]) if not freeway else random.uniform(3, 6)
        self.alive = True
        self.health = 80
        self.robots = random.randint(1, 3)
        self.color = random.choice([(200, 50, 50), (50, 100, 200), (200, 200, 50), (100, 200, 100), (180, 100, 200)])
        self.freeway = freeway

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0:
            self.alive = False
            return True
        return False

    def update(self, ground_y):
        if not self.alive:
            return
        self.x += self.vx
        self.y = ground_y - 18

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        px = int(self.x - cam_x)
        py = int(self.y)
        pygame.draw.rect(surface, self.color, (px - 22, py - 10, 44, 16))
        pygame.draw.rect(surface, (180, 220, 255), (px - 12, py - 18, 24, 10))
        pygame.draw.circle(surface, BLACK, (px - 14, py + 8), 5)
        pygame.draw.circle(surface, BLACK, (px + 14, py + 8), 5)

class TroopCarrier:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = -2.5
        self.alive = True
        self.health = 250
        self.robots_left = random.randint(20, 30)
        self.drop_timer = 40
        self.color = (80, 80, 100)

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0 and self.alive:
            self.alive = False
            return True
        return False

    def update(self, robots, ground_y):
        if not self.alive:
            return
        self.x += self.vx
        self.drop_timer -= 1
        if self.drop_timer <= 0 and self.robots_left > 0:
            robots.append(Robot(self.x, ground_y - 16))
            self.robots_left -= 1
            self.drop_timer = random.randint(8, 18)
            if self.robots_left <= 0:
                self.alive = False

    def destroy(self, parts, oil_puddles, explosions):
        for _ in range(min(self.robots_left + 8, 40)):
            parts.append(BodyPart(self.x + random.uniform(-30, 30), self.y + random.uniform(-10, 10),
                                  random.choice(["head", "body", "arm"]), RED,
                                  random.uniform(-8, 8), random.uniform(-10, -2), random.uniform(-25, 25)))
        explosions.append(Explosion(self.x, self.y, big=True))
        oil_puddles.append(OilPuddle(self.x, self.y + 20))
        play(snd_oil)

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        px = int(self.x - cam_x)
        py = int(self.y)
        pygame.draw.rect(surface, self.color, (px - 40, py - 12, 80, 24))
        pygame.draw.rect(surface, (60, 60, 80), (px - 30, py - 20, 40, 10))
        pygame.draw.circle(surface, ORANGE, (px - 35, py + 4), 4)
        pygame.draw.circle(surface, ORANGE, (px + 35, py + 4), 4)

class BigBox:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = -1.8
        self.alive = True
        self.health = 800
        self.color = (120, 80, 40)
        self.shoot_timer = 20

    def take_damage(self, amount):
        self.health -= amount
        if self.health <= 0 and self.alive:
            self.alive = False
            return True
        return False

    def update(self, player, bullets):
        if not self.alive:
            return
        self.x += self.vx
        self.shoot_timer -= 1
        if self.shoot_timer <= 0 and abs(self.x - player.x) < 700:
            for _ in range(3):
                dx = player.x - self.x
                dy = player.y - self.y
                dist = max(1, math.hypot(dx, dy))
                bullets.append(Bullet(self.x, self.y, dx/dist * 7 + random.uniform(-1, 1), dy/dist * 7 + random.uniform(-1, 1), False, RED))
            self.shoot_timer = 15

    def destroy(self, robots, parts, oil_puddles, explosions, ground_y):
        total = random.randint(100, 180)
        for i in range(total):
            rx = self.x + random.uniform(-50, 50)
            ry = self.y + random.uniform(-30, 30)
            r = Robot(rx, ry)
            r.vy = random.uniform(2, 7)
            r.vx = random.uniform(-4, 4)
            r.ragdoll = True
            if random.random() > 0.3:
                r.alive = False
            robots.append(r)
        explosions.append(Explosion(self.x, self.y, big=True))
        for _ in range(25):
            oil_puddles.append(OilPuddle(self.x + random.uniform(-40, 40), ground_y - 4))
        play(snd_oil)

    def draw(self, surface, cam_x):
        if not self.alive:
            return
        px = int(self.x - cam_x)
        py = int(self.y)
        pygame.draw.rect(surface, self.color, (px - 55, py - 25, 110, 50))
        pygame.draw.rect(surface, (80, 50, 20), (px - 45, py - 35, 90, 15))
        pygame.draw.circle(surface, RED, (px - 35, py), 6)
        pygame.draw.circle(surface, RED, (px + 35, py), 6)

class Drone:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = random.uniform(-3, 3)
        self.alive = True
        self.shoot_timer = random.randint(40, 100)
        self.health = 30

    def update(self, player, bullets):
        if self.x < player.x - 80:
            self.vx += 0.12
        elif self.x > player.x + 80:
            self.vx -= 0.12
        self.vx = max(-4.5, min(4.5, self.vx))
        self.x += self.vx
        self.y += math.sin(pygame.time.get_ticks() * 0.004 + self.x * 0.01) * 1.2
        self.shoot_timer -= 1
        if self.shoot_timer <= 0 and abs(self.x - player.x) < 480:
            dx = player.x - self.x
            dy = player.y - self.y
            dist = max(1, math.hypot(dx, dy))
            bullets.append(Bullet(self.x, self.y, dx / dist * 6.5, dy / dist * 6.5, False, CYAN))
            self.shoot_timer = random.randint(55, 130)
        return self.alive

    def draw(self, surface, cam_x):
        pygame.draw.polygon(surface, CYAN, [
            (int(self.x - cam_x), int(self.y - 8)),
            (int(self.x - cam_x - 12), int(self.y + 6)),
            (int(self.x - cam_x + 12), int(self.y + 6))
        ])
        pygame.draw.circle(surface, RED, (int(self.x - cam_x), int(self.y)), 4)

class Player:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = 280.0
        self.y = 200.0
        self.vx = 0.0
        self.vy = 0.0
        self.health = 800
        self.max_health = 800
        self.lives = 10
        self.score = 20000
        self.invincible = 0
        self.strafe_timer = 0
        self.bomb_timer = 0
        self.strafing = False
        self.auto_bomb = False
        self.facing_right = True
        self.perma_shield = False
        self.wide_strafe = False
        self.napalm_unlocked = False
        self.atomic_unlocked = False
        self.missiles_unlocked = False
        self.suicide_bots = 0
        self.shield_active = False
        self.shield_timer = 0

    def update(self, keys, ground_y):
        accel = 0.55
        max_speed_x = 11
        max_speed_y = 7
        if keys[pygame.K_LEFT]:
            self.vx -= accel
        if keys[pygame.K_RIGHT]:
            self.vx += accel
        if keys[pygame.K_UP]:
            self.vy -= accel
        if keys[pygame.K_DOWN]:
            self.vy += accel
        self.vx *= 0.93
        self.vy *= 0.93
        self.vx = max(-max_speed_x, min(max_speed_x, self.vx))
        self.vy = max(-max_speed_y, min(max_speed_y, self.vy))
        self.x += self.vx
        self.y += self.vy
        self.y = max(50, min(ground_y - 50, self.y))

        if self.vx > 0.3:
            self.facing_right = True
        elif self.vx < -0.3:
            self.facing_right = False

        if self.invincible > 0:
            self.invincible -= 1
        if self.strafe_timer > 0:
            self.strafe_timer -= 1
        if self.bomb_timer > 0:
            self.bomb_timer -= 1
        if self.shield_timer > 0:
            self.shield_timer -= 1
            self.shield_active = True
        else:
            self.shield_active = False

    def take_damage(self, amount):
        if self.shield_active or self.perma_shield:
            amount = int(amount * 0.2)
        self.health -= amount
        return self.health

    def draw(self, surface, cam_x):
        if self.invincible > 0 and (self.invincible // 4) % 2 == 0:
            return
        px = int(self.x - cam_x)
        py = int(self.y)
        body = [(38, 0), (-18, -9), (-28, 0), (-18, 9)]
        wing_up = [(4, -4), (-8, -22), (14, -4)]
        wing_down = [(4, 4), (-8, 22), (14, 4)]
        nose = [(38, 0), (48, -3), (48, 3)]

        def transform(pts):
            result = []
            for x, y in pts:
                if not self.facing_right:
                    x = -x
                result.append((px + x, py + y))
            return result

        pygame.draw.polygon(surface, (55, 55, 75), transform(body))
        pygame.draw.polygon(surface, (75, 75, 115), transform(wing_up))
        pygame.draw.polygon(surface, (75, 75, 115), transform(wing_down))
        pygame.draw.circle(surface, CYAN, (px + (14 if self.facing_right else -14), py), 5)
        eng_x = px + (-24 if self.facing_right else 24)
        pygame.draw.circle(surface, ORANGE, (eng_x, py - 3), 3)
        pygame.draw.circle(surface, ORANGE, (eng_x, py + 3), 3)
        pygame.draw.polygon(surface, YELLOW, transform(nose))
        if self.shield_active or self.perma_shield:
            pygame.draw.circle(surface, (0, 200, 255, 80), (px, py), 28, 2)

STORE_ITEMS = [
    {"name": "Perma Shield", "cost": 800, "key": "", "desc": "Permanent damage reduction"},
    {"name": "Wide Strafe", "cost": 600, "key": "G", "desc": "5x bullets, wide spread"},
    {"name": "Napalm Bombs", "cost": 700, "key": "N", "desc": "Burn buildings & robots"},
    {"name": "Atomic Bombs", "cost": 1000, "key": "A", "desc": "Destroy all nearby buildings"},
    {"name": "Missiles", "cost": 750, "key": "M", "desc": "Homing missiles"},
    {"name": "Suicide Robots", "cost": 500, "key": "U", "desc": "Drop exploding runners"},
    {"name": "Extra Hull", "cost": 400, "key": "", "desc": "+1 plane"},
]

def draw_store(surface, player, selected):
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (0, 0))
    title = title_font.render("SCALP STORE", True, YELLOW)
    surface.blit(title, (WIDTH//2 - title.get_width()//2, 40))
    score_txt = ui_font.render(f"Scalps: {player.score}", True, WHITE)
    surface.blit(score_txt, (WIDTH//2 - score_txt.get_width()//2, 100))
    y = 160
    for i, item in enumerate(STORE_ITEMS):
        col = GREEN if i == selected else WHITE
        if player.score < item["cost"]:
            col = RED
        key_str = f" [{item['key']}]" if item["key"] else ""
        txt = store_font.render(f"{i+1}. {item['name']}{key_str} - {item['cost']}  ({item['desc']})", True, col)
        surface.blit(txt, (WIDTH//2 - 320, y))
        y += 48
    help_txt = small_font.render("UP/DOWN select  ENTER buy  S or ESC close   F5 save  F9 load", True, CYAN)
    surface.blit(help_txt, (WIDTH//2 - help_txt.get_width()//2, HEIGHT - 70))

CRAWL_TEXT = [
    "humans",
    "",
    "A long time ago in a neighborhood",
    "far, far too close...",
    "",
    "Malls, theme parks, zoos, golf courses,",
    "freeways, and buildings are filled with",
    "terrified human-killing robots.",
    "",
    "Your jet bomber is the last hope.",
    "",
    "Will Someone Please Stop This Already?",
    "",
    "Arrow keys: fly / hover",
    "SPACE: bombs    N: napalm    A: atomic",
    "M: missiles    U: suicide robots",
    "G: toggle strafing    B: auto-bomb",
    "S: store    F5: save    F9: load",
    "K / L: volume",
    "",
    "Start with 20,000 scalps.",
    "Press SPACE to begin.",
]

def draw_crawl(surface, offset):
    y = HEIGHT - offset
    for line in CRAWL_TEXT:
        if -40 < y < HEIGHT + 40:
            text = crawl_font.render(line, True, YELLOW)
            scale = max(0.65, 1.0 - (y / HEIGHT) * 0.35)
            if scale != 1.0:
                text = pygame.transform.scale(text, (int(text.get_width() * scale), int(text.get_height() * scale)))
            surface.blit(text, (WIDTH // 2 - text.get_width() // 2, y))
        y += 42
    return offset + 1.1

def draw_highscores(surface, x, y):
    title = ui_font.render("HIGH SCORES", True, YELLOW)
    surface.blit(title, (x, y))
    for i, score in enumerate(highscores[:8]):
        line = small_font.render(f"{i+1:2}. {score:8}", True, WHITE)
        surface.blit(line, (x, y + 36 + i * 26))

def save_game(player, cam_x):
    data = {
        "score": player.score,
        "lives": player.lives,
        "health": player.health,
        "x": player.x,
        "y": player.y,
        "perma_shield": player.perma_shield,
        "wide_strafe": player.wide_strafe,
        "napalm_unlocked": player.napalm_unlocked,
        "atomic_unlocked": player.atomic_unlocked,
        "missiles_unlocked": player.missiles_unlocked,
        "suicide_bots": player.suicide_bots,
        "cam_x": cam_x
    }
    try:
        with open(SAVE_FILE, "wb") as f:
            pickle.dump(data, f)
        return True
    except:
        return False

def load_game(player):
    if not os.path.exists(SAVE_FILE):
        return False, 0
    try:
        with open(SAVE_FILE, "rb") as f:
            data = pickle.load(f)
        player.score = data.get("score", 20000)
        player.lives = data.get("lives", 10)
        player.health = data.get("health", 800)
        player.x = data.get("x", 280)
        player.y = data.get("y", 200)
        player.perma_shield = data.get("perma_shield", False)
        player.wide_strafe = data.get("wide_strafe", False)
        player.napalm_unlocked = data.get("napalm_unlocked", False)
        player.atomic_unlocked = data.get("atomic_unlocked", False)
        player.missiles_unlocked = data.get("missiles_unlocked", False)
        player.suicide_bots = data.get("suicide_bots", 0)
        return True, data.get("cam_x", 0)
    except:
        return False, 0

def main():
    global WIDTH, HEIGHT, screen, highscores, VOLUME
    state = STATE_TITLE
    crawl_offset = 0
    player = Player()
    buildings = []
    bridges = []
    cars = []
    carriers = []
    bigboxes = []
    robots = []
    drones = []
    bombs = []
    bullets = []
    missiles = []
    suicide_bots = []
    explosions = []
    particles = []
    parts = []
    oil_puddles = []
    fires = []
    water_zones = []
    golf_balls = []
    next_building_x = 350
    next_feature_x = 800
    cam_x = 0
    store_selected = 0

    def get_ground_y():
        return HEIGHT - GROUND_OFFSET

    def spawn_world():
        nonlocal next_building_x, next_feature_x
        gy = get_ground_y()
        while next_building_x < cam_x + WIDTH + 600:
            kind_roll = random.random()
            if kind_roll < 0.08:
                kind = "mall"
            elif kind_roll < 0.14:
                kind = "themepark"
            elif kind_roll < 0.18:
                kind = "zoo"
            elif kind_roll < 0.22:
                kind = "golf"
            elif kind_roll < 0.28:
                kind = "freeway"
            else:
                kind = "normal"
            if next_feature_x < next_building_x and random.random() < 0.15:
                w = random.randint(220, 340)
                bridges.append(Bridge(next_feature_x, gy, w))
                water_zones.append((next_feature_x, next_feature_x + w))
                next_feature_x += w + random.randint(250, 450)
                next_building_x = max(next_building_x, next_feature_x)
            else:
                b = Building(next_building_x, gy, kind=kind)
                buildings.append(b)
                next_building_x += b.w + random.randint(30, 120)
                if kind == "freeway":
                    for i in range(8):
                        cars.append(Car(next_building_x - 200 + i * 40, gy, freeway=True))
                elif random.random() < 0.1:
                    cars.append(Car(next_building_x - 80, gy))
            if random.random() < 0.025 and len(carriers) < 2:
                carriers.append(TroopCarrier(cam_x + WIDTH + 120, random.randint(110, 200)))
            if random.random() < 0.012 and len(bigboxes) < 1:
                bigboxes.append(BigBox(cam_x + WIDTH + 180, random.randint(90, 160)))

    def start_game():
        nonlocal buildings, bridges, cars, carriers, bigboxes, robots, drones, bombs, bullets, missiles, suicide_bots, explosions, particles, parts, oil_puddles, fires, water_zones, golf_balls, next_building_x, next_feature_x, cam_x
        player.reset()
        buildings.clear()
        bridges.clear()
        cars.clear()
        carriers.clear()
        bigboxes.clear()
        robots.clear()
        drones.clear()
        bombs.clear()
        bullets.clear()
        missiles.clear()
        suicide_bots.clear()
        explosions.clear()
        particles.clear()
        parts.clear()
        oil_puddles.clear()
        fires.clear()
        water_zones.clear()
        golf_balls.clear()
        next_building_x = 180
        next_feature_x = 600
        cam_x = 0
        spawn_world()
        for _ in range(4):
            drones.append(Drone(random.randint(500, 1200), random.randint(80, 280)))

    running = True
    while running:
        clock.tick(FPS)
        keys = pygame.key.get_pressed()
        ground_y = get_ground_y()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = max(900, event.w), max(550, event.h)
                screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                if state == STATE_TITLE:
                    if event.key == pygame.K_SPACE:
                        start_game()
                        state = STATE_PLAYING
                    if event.key == pygame.K_F9:
                        ok, loaded_cam = load_game(player)
                        if ok:
                            start_game()
                            player.x = 280
                            cam_x = loaded_cam
                            state = STATE_PLAYING
                elif state == STATE_PLAYING:
                    if event.key == pygame.K_SPACE:
                        dir_x = 1 if player.facing_right else -1
                        bombs.append(Bomb(player.x + 28 * dir_x, player.y + 8, player.vx + 4.5 * dir_x, "normal"))
                        play(snd_bomb)
                    if event.key == pygame.K_n and player.napalm_unlocked:
                        dir_x = 1 if player.facing_right else -1
                        bombs.append(Bomb(player.x + 28 * dir_x, player.y + 8, player.vx + 4.5 * dir_x, "napalm"))
                        play(snd_bomb)
                    if event.key == pygame.K_a and player.atomic_unlocked:
                        dir_x = 1 if player.facing_right else -1
                        bombs.append(Bomb(player.x + 28 * dir_x, player.y + 8, player.vx + 4.5 * dir_x, "atomic"))
                        play(snd_bomb)
                    if event.key == pygame.K_m and player.missiles_unlocked:
                        target = None
                        closest = 9999
                        for r in robots:
                            if r.alive and abs(r.x - player.x) < closest:
                                closest = abs(r.x - player.x)
                                target = r
                        missiles.append(Missile(player.x + 30, player.y, target))
                        play(snd_missile)
                    if event.key == pygame.K_u and player.suicide_bots > 0:
                        suicide_bots.append(SuicideRobot(player.x, ground_y - 16))
                        player.suicide_bots -= 1
                    if event.key == pygame.K_g:
                        player.strafing = not player.strafing
                    if event.key == pygame.K_b:
                        player.auto_bomb = not player.auto_bomb
                    if event.key == pygame.K_s:
                        state = STATE_STORE
                        store_selected = 0
                    if event.key == pygame.K_k:
                        VOLUME = max(0.0, VOLUME - 0.1)
                    if event.key == pygame.K_l:
                        VOLUME = min(1.0, VOLUME + 0.1)
                    if event.key == pygame.K_F5:
                        save_game(player, cam_x)
                    if event.key == pygame.K_F9:
                        ok, loaded_cam = load_game(player)
                        if ok:
                            cam_x = loaded_cam
                elif state == STATE_STORE:
                    if event.key == pygame.K_s or event.key == pygame.K_ESCAPE:
                        state = STATE_PLAYING
                    elif event.key == pygame.K_UP:
                        store_selected = (store_selected - 1) % len(STORE_ITEMS)
                    elif event.key == pygame.K_DOWN:
                        store_selected = (store_selected + 1) % len(STORE_ITEMS)
                    elif event.key == pygame.K_RETURN:
                        item = STORE_ITEMS[store_selected]
                        if player.score >= item["cost"]:
                            player.score -= item["cost"]
                            if item["name"] == "Perma Shield":
                                player.perma_shield = True
                            elif item["name"] == "Wide Strafe":
                                player.wide_strafe = True
                            elif item["name"] == "Napalm Bombs":
                                player.napalm_unlocked = True
                            elif item["name"] == "Atomic Bombs":
                                player.atomic_unlocked = True
                            elif item["name"] == "Missiles":
                                player.missiles_unlocked = True
                            elif item["name"] == "Suicide Robots":
                                player.suicide_bots += 5
                            elif item["name"] == "Extra Hull":
                                player.lives += 1
                    if event.key == pygame.K_F5:
                        save_game(player, cam_x)
                    if event.key == pygame.K_F9:
                        ok, loaded_cam = load_game(player)
                        if ok:
                            cam_x = loaded_cam
                elif state == STATE_GAMEOVER:
                    if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        state = STATE_TITLE
                        crawl_offset = 0

        if state == STATE_TITLE:
            crawl_offset = draw_crawl(screen, crawl_offset)
            if crawl_offset > len(CRAWL_TEXT) * 48 + HEIGHT:
                crawl_offset = 0

        elif state == STATE_PLAYING or state == STATE_STORE:
            if state == STATE_PLAYING:
                player.update(keys, ground_y)
                cam_x = max(0, player.x - 320)

                if player.strafing and player.strafe_timer <= 0:
                    dir_x = 14 if player.facing_right else -14
                    ox = 36 if player.facing_right else -36
                    count = 5 if player.wide_strafe else 2
                    spread = 4 if player.wide_strafe else 1.2
                    for i in range(count):
                        vy = random.uniform(-spread, spread)
                        bullets.append(Bullet(player.x + ox, player.y + (i - count//2)*4, dir_x, vy, True, YELLOW))
                    play(snd_strafe)
                    player.strafe_timer = 5 if not player.wide_strafe else 3

                if player.auto_bomb and player.bomb_timer <= 0:
                    dir_x = 1 if player.facing_right else -1
                    bombs.append(Bomb(player.x + 28 * dir_x, player.y + 8, player.vx + 4.5 * dir_x))
                    play(snd_bomb)
                    player.bomb_timer = 18

                for bomb in bombs[:]:
                    if bomb.update(buildings, bridges, cars, carriers, bigboxes, explosions, robots, parts, oil_puddles, fires, ground_y):
                        bombs.remove(bomb)
                    elif not bomb.alive:
                        bombs.remove(bomb)

                for m in missiles[:]:
                    m.update(buildings, robots, explosions, parts, oil_puddles)
                    if not m.alive:
                        missiles.remove(m)

                for sb in suicide_bots[:]:
                    if not sb.update(buildings, robots, explosions, parts, oil_puddles, ground_y):
                        suicide_bots.remove(sb)

                for b in buildings[:]:
                    b.update(particles, robots, parts, oil_puddles)
                    if not b.alive:
                        count = b.robots_inside
                        golfing = b.kind == "golf"
                        for _ in range(count):
                            robots.append(Robot(b.x + random.randint(10, max(20, b.w - 10)), ground_y - 16, golfing=golfing))
                        for _ in range(20):
                            particles.append(Particle(b.x + random.randint(0, b.w), b.y + random.randint(0, b.h),
                                                      b.color, random.uniform(-3, 3), random.uniform(-5, 1), 35, 5, 0.18))
                        buildings.remove(b)
                        explosions.append(Explosion(b.x + b.w // 2, b.y + b.h // 2, big=True))

                for br in bridges[:]:
                    if not br.alive:
                        for r in robots[:]:
                            if r.alive and br.water_start - 20 < r.x < br.water_end + 20:
                                for _ in range(12):
                                    particles.append(Particle(r.x, r.y, CYAN, random.uniform(-6, 6), random.uniform(-8, -2), 20, 4))
                                parts.append(BodyPart(r.x, r.y - 8, "head", r.color, random.uniform(-4, 4), -6, random.uniform(-15, 15)))
                                parts.append(BodyPart(r.x, r.y, "body", r.color, random.uniform(-2, 2), -3, random.uniform(-8, 8)))
                                oil_puddles.append(OilPuddle(r.x, ground_y - 4))
                                r.alive = False
                                r.remove_me = True
                                play(snd_electric)
                                play(snd_oil)
                        bridges.remove(br)

                for c in cars[:]:
                    c.update(ground_y)
                    if not c.alive:
                        for _ in range(c.robots):
                            parts.append(BodyPart(c.x, c.y, "body", c.color, random.uniform(-5, 5), -4, random.uniform(-10, 10)))
                            parts.append(BodyPart(c.x, c.y - 8, "head", RED, random.uniform(-4, 4), -6, random.uniform(-12, 12)))
                        oil_puddles.append(OilPuddle(c.x, ground_y - 4))
                        explosions.append(Explosion(c.x, c.y, big=True))
                        play(snd_oil)
                        cars.remove(c)
                        player.score += 30

                for tc in carriers[:]:
                    if tc.alive:
                        tc.update(robots, ground_y)
                    else:
                        tc.destroy(parts, oil_puddles, explosions)
                        carriers.remove(tc)
                        player.score += 80

                for bb in bigboxes[:]:
                    if bb.alive:
                        bb.update(player, bullets)
                    else:
                        bb.destroy(robots, parts, oil_puddles, explosions, ground_y)
                        bigboxes.remove(bb)
                        player.score += 200

                robots = [r for r in robots if r.alive and not r.remove_me]

                for r in robots:
                    r.update(player, bullets, ground_y, bridges, water_zones, fires, particles, golf_balls)
                    for wz in water_zones:
                        if wz[0] < r.x < wz[1] and not r.on_bridge and r.y > ground_y - 30:
                            for _ in range(10):
                                particles.append(Particle(r.x, r.y, CYAN, random.uniform(-5, 5), random.uniform(-7, -1), 18, 4))
                            oil_puddles.append(OilPuddle(r.x, ground_y - 4))
                            r.alive = False
                            r.remove_me = True
                            play(snd_electric)
                            play(snd_oil)

                for ball in golf_balls[:]:
                    ball["x"] += ball["vx"]
                    ball["y"] += ball["vy"]
                    ball["vy"] += 0.2
                    if ball["y"] > ground_y:
                        golf_balls.remove(ball)

                for d in drones[:]:
                    if not d.update(player, bullets):
                        drones.remove(d)
                    for bul in bullets[:]:
                        if bul.friendly and abs(bul.x - d.x) < 14 and abs(bul.y - d.y) < 14:
                            d.health -= 12
                            bullets.remove(bul)
                            if d.health <= 0:
                                d.alive = False
                                player.score += 40
                                explosions.append(Explosion(d.x, d.y))

                for bul in bullets[:]:
                    bul.update()
                    if not bul.alive:
                        bullets.remove(bul)
                        continue
                    if bul.friendly:
                        for r in robots[:]:
                            if r.alive and abs(bul.x - r.x) < 15 and abs(bul.y - r.y) < 18:
                                parts.append(BodyPart(r.x, r.y - 8, "head", r.color, bul.vx * 0.15, -5, random.uniform(-16, 16)))
                                parts.append(BodyPart(r.x, r.y, "body", r.color, bul.vx * 0.1, -2, random.uniform(-8, 8)))
                                parts.append(BodyPart(r.x - 5, r.y, "arm", r.color, -2, -1, random.uniform(-20, 20)))
                                parts.append(BodyPart(r.x + 5, r.y, "arm", r.color, 2, -1, random.uniform(-20, 20)))
                                oil_puddles.append(OilPuddle(r.x, ground_y - 4))
                                r.alive = False
                                r.remove_me = True
                                bullets.remove(bul)
                                player.score += 100
                                explosions.append(Explosion(r.x, r.y))
                                play(snd_robot_hit)
                                play(snd_oil)
                                break
                    else:
                        if player.invincible <= 0 and abs(bul.x - player.x) < 22 and abs(bul.y - player.y) < 14:
                            player.take_damage(22)
                            bullets.remove(bul)
                            play(snd_hit_player)
                            player.invincible = 28
                            for _ in range(8):
                                particles.append(Particle(player.x, player.y, ORANGE, random.uniform(-4, 4), random.uniform(-4, 4), 14, 3))

                for d in drones:
                    if player.invincible <= 0 and abs(d.x - player.x) < 28 and abs(d.y - player.y) < 18:
                        player.take_damage(35)
                        d.alive = False
                        play(snd_hit_player)
                        player.invincible = 35

                if player.health <= 0:
                    player.lives -= 1
                    player.health = player.max_health
                    player.invincible = 80
                    explosions.append(Explosion(player.x, player.y, big=True))
                    if player.lives <= 0:
                        highscores.append(player.score)
                        highscores = save_highscores(highscores)
                        state = STATE_GAMEOVER

                spawn_world()
                if random.random() < 0.007 and len(drones) < 8:
                    drones.append(Drone(cam_x + WIDTH + 80, random.randint(70, 250)))

                buildings = [b for b in buildings if b.x > cam_x - 200]
                bridges = [br for br in bridges if br.x > cam_x - 200]
                cars = [c for c in cars if c.x > cam_x - 150 and c.alive]
                carriers = [tc for tc in carriers if tc.x > cam_x - 200]
                bigboxes = [bb for bb in bigboxes if bb.x > cam_x - 200]
                robots = [r for r in robots if r.x > cam_x - 120 and r.x < cam_x + WIDTH + 200 and r.alive]
                water_zones = [wz for wz in water_zones if wz[1] > cam_x - 100]

                particles = [p for p in particles if p.update()]
                explosions = [e for e in explosions if e.update()]
                parts = [p for p in parts if p.update(particles, oil_puddles, ground_y)]
                oil_puddles = [o for o in oil_puddles if o.update()]
                fires = [f for f in fires if f.update(particles)]

        # Draw
        screen.fill((18, 28, 48))

        if state == STATE_TITLE:
            for _ in range(70):
                pygame.draw.circle(screen, WHITE, (random.randint(0, WIDTH), random.randint(0, HEIGHT)), 1)
            crawl_offset = draw_crawl(screen, crawl_offset)
            draw_highscores(screen, 25, 30)
            prompt = ui_font.render("PRESS SPACE TO START   F9 LOAD", True, GREEN)
            screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT - 70))

        elif state == STATE_PLAYING or state == STATE_STORE or state == STATE_GAMEOVER:
            for wz in water_zones:
                wx1 = max(0, int(wz[0] - cam_x))
                wx2 = min(WIDTH, int(wz[1] - cam_x))
                if wx2 > wx1:
                    pygame.draw.rect(screen, WATER, (wx1, ground_y, wx2 - wx1, HEIGHT - ground_y))
                    for i in range(3):
                        pygame.draw.line(screen, (40, 90, 180), (wx1, ground_y + 8 + i*6), (wx2, ground_y + 8 + i*6), 1)

            pygame.draw.rect(screen, (28, 75, 28), (0, ground_y, WIDTH, HEIGHT - ground_y))
            pygame.draw.line(screen, (18, 55, 18), (0, ground_y), (WIDTH, ground_y), 4)

            for br in bridges:
                br.draw(screen, cam_x)
            for b in buildings:
                b.draw(screen, cam_x)
            for c in cars:
                c.draw(screen, cam_x)
            for tc in carriers:
                tc.draw(screen, cam_x)
            for bb in bigboxes:
                bb.draw(screen, cam_x)
            for r in robots:
                r.draw(screen, cam_x)
            for d in drones:
                d.draw(screen, cam_x)
            for bomb in bombs:
                bomb.draw(screen, cam_x)
            for m in missiles:
                m.draw(screen, cam_x)
            for sb in suicide_bots:
                sb.draw(screen, cam_x)
            for bul in bullets:
                bul.draw(screen, cam_x)
            for e in explosions:
                e.draw(screen, cam_x)
            for p in particles:
                p.draw(screen, cam_x)
            for part in parts:
                part.draw(screen, cam_x)
            for o in oil_puddles:
                o.draw(screen, cam_x)
            for f in fires:
                f.draw(screen, cam_x)
            for ball in golf_balls:
                pygame.draw.circle(screen, WHITE, (int(ball["x"] - cam_x), int(ball["y"])), 4)

            player.draw(screen, cam_x)

            pygame.draw.rect(screen, (10, 10, 10), (0, HEIGHT - UI_BAR_HEIGHT, WIDTH, UI_BAR_HEIGHT))
            info = (f"SCALP: {player.score:6}   PLANES: {player.lives}   HULL: {int(player.health / player.max_health * 100):3}%   "
                    f"STRAFE: {'ON ' if player.strafing else 'OFF'}   BOMB: {'ON ' if player.auto_bomb else 'OFF'}   BOTS: {player.suicide_bots}   VOL: {int(VOLUME * 100):3}%")
            text = ui_font.render(info, True, WHITE)
            screen.blit(text, (12, HEIGHT - UI_BAR_HEIGHT + 10))

            if state == STATE_STORE:
                draw_store(screen, player, store_selected)

            if state == STATE_GAMEOVER:
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 170))
                screen.blit(overlay, (0, 0))
                go = title_font.render("GAME OVER", True, RED)
                screen.blit(go, (WIDTH // 2 - go.get_width() // 2, HEIGHT // 2 - 110))
                sc = ui_font.render(f"Final Scalp Points: {player.score}", True, YELLOW)
                screen.blit(sc, (WIDTH // 2 - sc.get_width() // 2, HEIGHT // 2 - 45))
                if player.score >= (highscores[0] if highscores else 0):
                    new = ui_font.render("NEW HIGH SCORE!", True, GREEN)
                    screen.blit(new, (WIDTH // 2 - new.get_width() // 2, HEIGHT // 2 - 5))
                draw_highscores(screen, WIDTH // 2 - 110, HEIGHT // 2 + 30)
                prompt = small_font.render("Press SPACE or ENTER to return to title", True, WHITE)
                screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT - 50))

        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()