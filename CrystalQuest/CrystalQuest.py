"""
Crystal Quest — a single-file Pygame platformer
Controls: A/D or arrows move, Space/W/Up jump, J attack, R restart, Esc quit
Requires: pygame  (pip install pygame)
"""

import math
import random
import sys
from dataclasses import dataclass, field

import pygame

pygame.init()
pygame.mixer.init()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
W, H = 960, 540
FPS = 60
GRAVITY = 0.55
MAX_FALL = 14
TILE = 32

COL_BG = (18, 16, 28)
COL_BG2 = (28, 24, 42)
COL_PLAYER = (90, 210, 255)
COL_PLAYER_HIT = (255, 80, 80)
COL_PLATFORM = (70, 62, 95)
COL_PLATFORM_TOP = (120, 110, 160)
COL_SPIKE = (180, 50, 70)
COL_COIN = (255, 210, 70)
COL_HP = (80, 220, 120)
COL_SPEED = (80, 180, 255)
COL_DJUMP = (200, 120, 255)
COL_STAR = (255, 240, 160)
COL_ENEMY = (220, 80, 90)
COL_BOSS1 = (255, 90, 40)
COL_BOSS2 = (160, 60, 255)
COL_UI = (240, 236, 250)
COL_SHADOW = (0, 0, 0)

# ---------------------------------------------------------------------------
# Tiny sound helpers (no external files)
# ---------------------------------------------------------------------------
def tone(freq, ms, vol=0.15, wave="square"):
    sr = 22050
    n = int(sr * ms / 1000)
    buf = bytearray()
    for i in range(n):
        t = i / sr
        if wave == "square":
            s = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
        else:
            s = math.sin(2 * math.pi * freq * t)
        fade = min(i / 80, 1.0, (n - i) / 120)
        v = int(127 + 127 * s * vol * fade)
        buf.extend((v & 0xFF, v & 0xFF))
    try:
        snd = pygame.mixer.Sound(buffer=bytes(buf))
        snd.set_volume(vol)
        return snd
    except Exception:
        return None

SND_JUMP = tone(420, 80, 0.12)
SND_COIN = tone(880, 90, 0.12)
SND_HIT = tone(140, 160, 0.18)
SND_POWER = tone(660, 140, 0.14)
SND_SWING = tone(240, 60, 0.1)
SND_BOSS = tone(90, 280, 0.2, "sine")
SND_WIN = tone(523, 400, 0.16, "sine")

def play(s):
    if s:
        s.play()

# ---------------------------------------------------------------------------
# World layout (characters)
#   # solid  ^ spike  = moving platform  C coin  H health  S speed
#   D double-jump  * star (quest)  e walker  f flyer
#   1 boss1 spawn  2 boss2 spawn  P player
# ---------------------------------------------------------------------------
LEVEL = [
    "################################################################",
    "#                                                              #",
    "#                                                              #",
    "#                         C   C                                #",
    "#                       ######                                 #",
    "#                                              *               #",
    "#   P                         e           ##########           #",
    "#  ####              C                                         #",
    "#           ##                    C                            #",
    "#                    #####                                     #",
    "#    C                                   e                     #",
    "#  #####              e         ####               H           #",
    "#                                        ##      ####          #",
    "#                 C                                            #",
    "#          S                 ========                          #",
    "#      ######                               C        D         #",
    "#                         C          ##              ####      #",
    "#    e            #####                                        #",
    "#                                         f                    #",
    "#  ##########                 e      ##########                #",
    "#                                                              #",
    "#           C     ^^^^                                         #",
    "#        ###########              C                            #",
    "#                                    ####                      #",
    "#   1                                                          #",
    "# ##########                                    *              #",
    "#                                                              #",
    "#                     ========                                 #",
    "#                                          C                   #",
    "#              C                 e     #########               #",
    "#     ####                                                     #",
    "#                         f                                    #",
    "#  H                                                           #",
    "# #####            ##########                                  #",
    "#                                                              #",
    "#                         2                                    #",
    "#                      ##########                              #",
    "#                                                              #",
    "################################################################",
]

# ---------------------------------------------------------------------------
# Particles
# ---------------------------------------------------------------------------
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: tuple
    size: float
    g: float = 0.15

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.g
        self.life -= 1
        self.size = max(0, self.size - 0.05)

    def draw(self, surf, cam):
        if self.life <= 0 or self.size <= 0:
            return
        pygame.draw.circle(
            surf, self.color,
            (int(self.x - cam[0]), int(self.y - cam[1])),
            max(1, int(self.size)),
        )

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
class Platform:
    def __init__(self, x, y, w, h, moving=False, span=160):
        self.rect = pygame.Rect(x, y, w, h)
        self.moving = moving
        self.origin = x
        self.span = span
        self.dir = 1
        self.speed = 1.4

    def update(self):
        if not self.moving:
            return 0
        dx = self.dir * self.speed
        self.rect.x += dx
        if self.rect.x > self.origin + self.span:
            self.dir = -1
        elif self.rect.x < self.origin:
            self.dir = 1
        return dx

    def draw(self, surf, cam):
        r = self.rect.move(-cam[0], -cam[1])
        pygame.draw.rect(surf, COL_PLATFORM, r, border_radius=4)
        pygame.draw.rect(surf, COL_PLATFORM_TOP, (r.x, r.y, r.w, 6), border_radius=3)

class Spike:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y + TILE // 2, TILE, TILE // 2)

    def draw(self, surf, cam):
        r = self.rect.move(-cam[0], -cam[1])
        pts = [
            (r.left, r.bottom),
            (r.left + r.w // 2, r.top),
            (r.right, r.bottom),
        ]
        pygame.draw.polygon(surf, COL_SPIKE, pts)

class Pickup:
    def __init__(self, x, y, kind):
        self.kind = kind  # coin, health, speed, djump, star
        self.rect = pygame.Rect(x + 8, y + 8, 16, 16)
        self.t = random.random() * 6
        self.alive = True

    def update(self):
        self.t += 0.12

    def draw(self, surf, cam):
        if not self.alive:
            return
        bob = math.sin(self.t) * 4
        cx = int(self.rect.centerx - cam[0])
        cy = int(self.rect.centery - cam[1] + bob)
        color = {
            "coin": COL_COIN,
            "health": COL_HP,
            "speed": COL_SPEED,
            "djump": COL_DJUMP,
            "star": COL_STAR,
        }[self.kind]
        if self.kind == "star":
            pts = []
            for i in range(5):
                a = -math.pi / 2 + i * 2 * math.pi / 5
                pts.append((cx + math.cos(a) * 11, cy + math.sin(a) * 11))
                a2 = a + math.pi / 5
                pts.append((cx + math.cos(a2) * 5, cy + math.sin(a2) * 5))
            pygame.draw.polygon(surf, color, pts)
        else:
            pygame.draw.circle(surf, color, (cx, cy), 8)
            pygame.draw.circle(surf, (255, 255, 255), (cx - 2, cy - 2), 2)

class Enemy:
    def __init__(self, x, y, kind="walk"):
        self.kind = kind
        self.rect = pygame.Rect(x + 4, y + 8, 24, 24)
        self.dir = -1 if kind == "walk" else 1
        self.speed = 1.2 if kind == "walk" else 1.6
        self.hp = 2
        self.alive = True
        self.t = 0
        self.origin_y = y + 8

    def update(self, solids):
        if not self.alive:
            return
        self.t += 0.08
        if self.kind == "walk":
            self.rect.x += self.dir * self.speed
            probe = self.rect.move(self.dir * 8, 8)
            grounded = any(probe.colliderect(s.rect) for s in solids)
            blocked = any(self.rect.colliderect(s.rect) for s in solids)
            if blocked or not grounded:
                self.dir *= -1
                self.rect.x += self.dir * self.speed * 2
        else:
            self.rect.y = self.origin_y + math.sin(self.t) * 40
            self.rect.x += self.dir * self.speed
            if self.t % 8 < 0.1:
                self.dir *= -1

    def draw(self, surf, cam):
        if not self.alive:
            return
        r = self.rect.move(-cam[0], -cam[1])
        pygame.draw.rect(surf, COL_ENEMY, r, border_radius=6)
        eye = r.centerx + (4 if self.dir > 0 else -4)
        pygame.draw.circle(surf, (20, 10, 10), (eye, r.y + 8), 3)

class Projectile:
    def __init__(self, x, y, vx, vy, color, dmg=1, hostile=True):
        self.rect = pygame.Rect(x, y, 10, 10)
        self.vx, self.vy = vx, vy
        self.color = color
        self.dmg = dmg
        self.hostile = hostile
        self.life = 90
        self.alive = True

    def update(self):
        self.rect.x += self.vx
        self.rect.y += self.vy
        self.life -= 1
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, cam):
        r = self.rect.move(-cam[0], -cam[1])
        pygame.draw.circle(surf, self.color, r.center, 6)

class Boss:
    def __init__(self, x, y, kind=1):
        self.kind = kind
        self.rect = pygame.Rect(x, y - 40, 64, 64)
        self.max_hp = 18 if kind == 1 else 26
        self.hp = self.max_hp
        self.alive = True
        self.t = 0
        self.dir = 1
        self.phase = 1
        self.cd = 0
        self.name = "Ember Golem" if kind == 1 else "Void Seraph"

    def update(self, player, projectiles):
        if not self.alive:
            return
        self.t += 1
        self.cd = max(0, self.cd - 1)
        self.phase = 2 if self.hp < self.max_hp * 0.45 else 1
        px = player.rect.centerx
        if self.kind == 1:
            if abs(px - self.rect.centerx) > 20:
                self.dir = 1 if px > self.rect.centerx else -1
                self.rect.x += self.dir * (1.4 if self.phase == 1 else 2.2)
            if self.cd == 0:
                self.cd = 70 if self.phase == 1 else 40
                vx = 5 if px > self.rect.centerx else -5
                projectiles.append(
                    Projectile(self.rect.centerx, self.rect.centery, vx, -1, COL_BOSS1, 1)
                )
                if self.phase == 2:
                    projectiles.append(
                        Projectile(self.rect.centerx, self.rect.centery, vx * 0.6, -3, COL_BOSS1, 1)
                    )
        else:
            self.rect.y += math.sin(self.t * 0.05) * 1.2
            self.rect.x += math.cos(self.t * 0.02) * 1.6
            if self.cd == 0:
                self.cd = 50 if self.phase == 1 else 28
                for a in range(0, 360, 45 if self.phase == 1 else 30):
                    rad = math.radians(a + self.t)
                    projectiles.append(
                        Projectile(
                            self.rect.centerx, self.rect.centery,
                            math.cos(rad) * 3.2, math.sin(rad) * 3.2,
                            COL_BOSS2, 1,
                        )
                    )

    def draw(self, surf, cam):
        if not self.alive:
            return
        r = self.rect.move(-cam[0], -cam[1])
        col = COL_BOSS1 if self.kind == 1 else COL_BOSS2
        pygame.draw.rect(surf, col, r, border_radius=10)
        pygame.draw.rect(surf, (255, 255, 255), r.inflate(-18, -28), border_radius=6)
        # HP bar
        bw = 80
        bx, by = r.centerx - bw // 2, r.y - 14
        pygame.draw.rect(surf, (30, 20, 20), (bx, by, bw, 7))
        pygame.draw.rect(surf, col, (bx, by, int(bw * self.hp / self.max_hp), 7))

class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 22, 30)
        self.vx = 0
        self.vy = 0
        self.on_ground = False
        self.jumps = 0
        self.max_jumps = 1
        self.speed = 4.2
        self.hp = 6
        self.max_hp = 6
        self.inv = 0
        self.atk_cd = 0
        self.facing = 1
        self.stars = 0
        self.coins = 0
        self.alive = True
        self.speed_timer = 0
        self.star_timer = 0  # invuln power
        self.shake = 0

    def attack_box(self):
        if self.atk_cd > 12:
            w = 28
            x = self.rect.right if self.facing > 0 else self.rect.left - w
            return pygame.Rect(x, self.rect.y + 6, w, 18)
        return None

    def hit(self, dmg=1):
        if self.inv > 0 or self.star_timer > 0:
            return
        self.hp -= dmg
        self.inv = 50
        self.shake = 10
        play(SND_HIT)
        if self.hp <= 0:
            self.alive = False

    def update(self, keys, solids, movers_dx):
        if not self.alive:
            return
        self.inv = max(0, self.inv - 1)
        self.atk_cd = max(0, self.atk_cd - 1)
        self.speed_timer = max(0, self.speed_timer - 1)
        self.star_timer = max(0, self.star_timer - 1)
        self.shake = max(0, self.shake - 1)

        spd = self.speed + (2.2 if self.speed_timer else 0)
        ax = 0
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            ax = -1
            self.facing = -1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            ax = 1
            self.facing = 1
        self.vx = ax * spd
        self.vy = min(MAX_FALL, self.vy + GRAVITY)

        # move X
        self.rect.x += int(self.vx) + movers_dx
        for s in solids:
            if self.rect.colliderect(s.rect):
                if self.vx + movers_dx > 0:
                    self.rect.right = s.rect.left
                elif self.vx + movers_dx < 0:
                    self.rect.left = s.rect.right
                self.vx = 0

        # move Y
        self.rect.y += int(self.vy)
        self.on_ground = False
        for s in solids:
            if self.rect.colliderect(s.rect):
                if self.vy > 0:
                    self.rect.bottom = s.rect.top
                    self.vy = 0
                    self.on_ground = True
                    self.jumps = 0
                elif self.vy < 0:
                    self.rect.top = s.rect.bottom
                    self.vy = 0

    def jump(self):
        cap = self.max_jumps
        if self.jumps < cap and (self.on_ground or self.jumps > 0 or cap >= 2):
            if self.on_ground or self.jumps < cap:
                self.vy = -11.2
                self.jumps += 1
                self.on_ground = False
                play(SND_JUMP)

    def attack(self):
        if self.atk_cd == 0:
            self.atk_cd = 20
            play(SND_SWING)

    def draw(self, surf, cam):
        if not self.alive:
            return
        r = self.rect.move(-cam[0], -cam[1])
        col = COL_PLAYER
        if self.inv and (self.inv // 3) % 2 == 0:
            col = COL_PLAYER_HIT
        if self.star_timer:
            col = (
                200 + int(55 * math.sin(pygame.time.get_ticks() * 0.02)),
                220,
                80,
            )
        pygame.draw.rect(surf, col, r, border_radius=5)
        eye_x = r.centerx + (5 if self.facing > 0 else -5)
        pygame.draw.circle(surf, (10, 20, 30), (eye_x, r.y + 10), 3)
        box = self.attack_box()
        if box:
            br = box.move(-cam[0], -cam[1])
            pygame.draw.rect(surf, (220, 240, 255), br, border_radius=4)

# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Crystal Quest")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big = pygame.font.SysFont("consolas", 36, bold=True)
        self.state = "title"
        self.reset()

    def reset(self):
        self.platforms = []
        self.spikes = []
        self.pickups = []
        self.enemies = []
        self.bosses = []
        self.projectiles = []
        self.particles = []
        self.player = None
        self.cam = [0, 0]
        self.quest = {
            "stars": 0,
            "stars_needed": 2,
            "bosses": 0,
            "bosses_needed": 2,
        }
        self.msg = "Collect both crystals. Defeat both bosses."
        self.msg_t = 240
        self.won = False
        self.parse_level()

    def parse_level(self):
        rows = len(LEVEL)
        cols = len(LEVEL[0])
        self.world_w = cols * TILE
        self.world_h = rows * TILE
        for j, row in enumerate(LEVEL):
            for i, ch in enumerate(row):
                x, y = i * TILE, j * TILE
                if ch == "#":
                    self.platforms.append(Platform(x, y, TILE, TILE))
                elif ch == "=":
                    if i == 0 or LEVEL[j][i - 1] != "=":
                        k = i
                        while k < cols and LEVEL[j][k] == "=":
                            k += 1
                        self.platforms.append(Platform(x, y, (k - i) * TILE, TILE, True, 140))
                elif ch == "^":
                    self.spikes.append(Spike(x, y))
                elif ch == "P":
                    self.player = Player(x, y)
                elif ch == "C":
                    self.pickups.append(Pickup(x, y, "coin"))
                elif ch == "H":
                    self.pickups.append(Pickup(x, y, "health"))
                elif ch == "S":
                    self.pickups.append(Pickup(x, y, "speed"))
                elif ch == "D":
                    self.pickups.append(Pickup(x, y, "djump"))
                elif ch == "*":
                    self.pickups.append(Pickup(x, y, "star"))
                elif ch == "e":
                    self.enemies.append(Enemy(x, y, "walk"))
                elif ch == "f":
                    self.enemies.append(Enemy(x, y, "fly"))
                elif ch == "1":
                    self.bosses.append(Boss(x, y, 1))
                elif ch == "2":
                    self.bosses.append(Boss(x, y, 2))
        if self.player is None:
            self.player = Player(64, 64)

    def burst(self, x, y, color, n=12):
        for _ in range(n):
            self.particles.append(
                Particle(
                    x, y,
                    random.uniform(-3, 3), random.uniform(-5, -1),
                    random.randint(18, 36), color, random.uniform(2, 5),
                )
            )

    def set_msg(self, text, t=180):
        self.msg = text
        self.msg_t = t

    def update(self):
        keys = pygame.key.get_pressed()
        p = self.player
        movers_dx = 0
        for plat in self.platforms:
            dx = plat.update()
            if dx and p.rect.move(0, 2).colliderect(plat.rect):
                movers_dx = int(dx)

        solids = self.platforms
        p.update(keys, solids, movers_dx)

        for pk in self.pickups:
            pk.update()
            if pk.alive and p.rect.colliderect(pk.rect):
                pk.alive = False
                if pk.kind == "coin":
                    p.coins += 1
                    play(SND_COIN)
                    self.burst(pk.rect.centerx, pk.rect.centery, COL_COIN)
                    if p.coins >= 8 and p.max_hp < 8:
                        p.max_hp += 1
                        p.hp = min(p.max_hp, p.hp + 1)
                        self.set_msg("Coin hoard: max HP up!")
                elif pk.kind == "health":
                    p.hp = min(p.max_hp, p.hp + 2)
                    play(SND_POWER)
                    self.set_msg("Restored vitality.")
                elif pk.kind == "speed":
                    p.speed_timer = 420
                    play(SND_POWER)
                    self.set_msg("Swift wind — speed up!")
                elif pk.kind == "djump":
                    p.max_jumps = 2
                    play(SND_POWER)
                    self.set_msg("Sky step — double jump unlocked!")
                elif pk.kind == "star":
                    self.quest["stars"] += 1
                    p.stars += 1
                    p.star_timer = 180
                    play(SND_POWER)
                    self.set_msg(f"Crystal {self.quest['stars']}/{self.quest['stars_needed']} secured.")
                    self.burst(pk.rect.centerx, pk.rect.centery, COL_STAR, 20)

        for e in self.enemies:
            e.update(solids)
            if e.alive and p.rect.colliderect(e.rect):
                p.hit(1)
            box = p.attack_box()
            if e.alive and box and box.colliderect(e.rect):
                e.hp -= 1
                e.rect.x += p.facing * 12
                self.burst(e.rect.centerx, e.rect.centery, COL_ENEMY, 8)
                if e.hp <= 0:
                    e.alive = False
                    p.coins += 1

        for b in self.bosses:
            b.update(p, self.projectiles)
            if b.alive and p.rect.colliderect(b.rect):
                p.hit(1)
            box = p.attack_box()
            if b.alive and box and box.colliderect(b.rect):
                b.hp -= 1
                b.rect.x += p.facing * 8
                self.burst(b.rect.centerx, b.rect.centery, COL_BOSS1 if b.kind == 1 else COL_BOSS2)
                if b.hp <= 0:
                    b.alive = False
                    self.quest["bosses"] += 1
                    play(SND_BOSS)
                    self.set_msg(f"{b.name} falls! {self.quest['bosses']}/{self.quest['bosses_needed']}")
                    self.burst(b.rect.centerx, b.rect.centery, COL_STAR, 40)

        for pr in self.projectiles:
            pr.update()
            if not pr.alive:
                continue
            if pr.hostile and p.rect.colliderect(pr.rect):
                p.hit(pr.dmg)
                pr.alive = False
            box = p.attack_box()
            if box and box.colliderect(pr.rect):
                pr.alive = False
            for plat in self.platforms:
                if pr.rect.colliderect(plat.rect):
                    pr.alive = False
                    break

        self.projectiles = [pr for pr in self.projectiles if pr.alive]
        for sp in self.spikes:
            if p.rect.colliderect(sp.rect):
                p.hit(1)
                p.vy = -8

        for part in self.particles:
            part.update()
        self.particles = [pt for pt in self.particles if pt.life > 0]

        # camera
        tx = p.rect.centerx - W // 2
        ty = p.rect.centery - H // 2 - 40
        self.cam[0] += (tx - self.cam[0]) * 0.12
        self.cam[1] += (ty - self.cam[1]) * 0.12
        if p.shake:
            self.cam[0] += random.randint(-4, 4)
            self.cam[1] += random.randint(-4, 4)
        self.cam[0] = max(0, min(self.world_w - W, self.cam[0]))
        self.cam[1] = max(0, min(self.world_h - H, self.cam[1]))

        self.msg_t = max(0, self.msg_t - 1)

        if (
            self.quest["stars"] >= self.quest["stars_needed"]
            and self.quest["bosses"] >= self.quest["bosses_needed"]
            and not self.won
        ):
            self.won = True
            self.state = "win"
            play(SND_WIN)

        if not p.alive:
            self.state = "dead"

    def draw_bg(self):
        self.screen.fill(COL_BG)
        camx, camy = self.cam
        for i in range(18):
            x = (i * 140 - camx * 0.2) % (W + 140) - 70
            y = 40 + (i * 37) % 180
            pygame.draw.circle(self.screen, COL_BG2, (int(x), int(y)), 40)

    def draw_ui(self):
        p = self.player
        for i in range(p.max_hp):
            r = pygame.Rect(16 + i * 22, 14, 18, 14)
            col = COL_HP if i < p.hp else (50, 40, 50)
            pygame.draw.rect(self.screen, col, r, border_radius=3)
        q = f"Crystals {self.quest['stars']}/{self.quest['stars_needed']}   Bosses {self.quest['bosses']}/{self.quest['bosses_needed']}   Coins {p.coins}"
        self.screen.blit(self.font.render(q, True, COL_UI), (16, 36))
        buffs = []
        if p.max_jumps >= 2:
            buffs.append("Double Jump")
        if p.speed_timer:
            buffs.append("Speed")
        if p.star_timer:
            buffs.append("Aegis")
        if buffs:
            self.screen.blit(self.font.render("  ".join(buffs), True, COL_STAR), (16, 56))
        if self.msg_t:
            txt = self.font.render(self.msg, True, COL_UI)
            self.screen.blit(txt, (W // 2 - txt.get_width() // 2, H - 36))

    def draw_world(self):
        cam = self.cam
        for plat in self.platforms:
            r = plat.rect.move(-cam[0], -cam[1])
            if r.right < 0 or r.left > W or r.bottom < 0 or r.top > H:
                continue
            plat.draw(self.screen, cam)
        for sp in self.spikes:
            sp.draw(self.screen, cam)
        for pk in self.pickups:
            pk.draw(self.screen, cam)
        for e in self.enemies:
            e.draw(self.screen, cam)
        for b in self.bosses:
            b.draw(self.screen, cam)
        for pr in self.projectiles:
            pr.draw(self.screen, cam)
        for pt in self.particles:
            pt.draw(self.screen, cam)
        self.player.draw(self.screen, cam)

    def draw_title(self):
        self.screen.fill(COL_BG)
        title = self.big.render("CRYSTAL QUEST", True, COL_PLAYER)
        self.screen.blit(title, (W // 2 - title.get_width() // 2, 140))
        lines = [
            "Quest: gather both crystals and slay Ember Golem + Void Seraph.",
            "Move A/D or Arrows   Jump Space/W   Attack J",
            "Powerups: green heart, blue speed, purple double jump, gold coins.",
            "Press ENTER to begin.",
        ]
        for i, line in enumerate(lines):
            t = self.font.render(line, True, COL_UI)
            self.screen.blit(t, (W // 2 - t.get_width() // 2, 230 + i * 28))

    def draw_end(self, win):
        self.draw_bg()
        self.draw_world()
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((10, 8, 16, 180))
        self.screen.blit(overlay, (0, 0))
        text = "THE REALM IS SAVED" if win else "YOU FELL"
        t = self.big.render(text, True, COL_STAR if win else COL_ENEMY)
        self.screen.blit(t, (W // 2 - t.get_width() // 2, H // 2 - 40))
        s = self.font.render("Press R to play again", True, COL_UI)
        self.screen.blit(s, (W // 2 - s.get_width() // 2, H // 2 + 16))

    def run(self):
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if self.state == "title" and ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.state = "play"
                    if self.state == "play":
                        if ev.key in (pygame.K_SPACE, pygame.K_w, pygame.K_UP):
                            self.player.jump()
                        if ev.key == pygame.K_j:
                            self.player.attack()
                    if ev.key == pygame.K_r and self.state in ("dead", "win", "play"):
                        self.reset()
                        self.state = "play"

            if self.state == "play":
                self.update()
                self.draw_bg()
                self.draw_world()
                self.draw_ui()
            elif self.state == "title":
                self.draw_title()
            elif self.state == "dead":
                self.draw_end(False)
            elif self.state == "win":
                self.draw_end(True)

            pygame.display.flip()
            self.clock.tick(FPS)

if __name__ == "__main__":
    Game().run()