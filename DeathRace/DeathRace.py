import math
import random
import sys
import numpy as np
import pygame

# ---------- setup ----------
WIDTH, HEIGHT = 960, 640
FPS = 60
TILE = 48
CHUNK_TILES = 8
KEEP_CHUNKS = 2
ROAD_EVERY = 4
TARGET_ROBOTS = 18
CULL_DIST = 1400

pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
pygame.init()
pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Death Race — Infinite Town (Anaglyph)")
clock = pygame.time.Clock()
font = pygame.font.SysFont("consolas", 18)
big = pygame.font.SysFont("consolas", 42, bold=True)

# ---------- sounds ----------
def tone(freq, ms, vol=0.35, decay=True):
    sr = 22050
    n = int(sr * ms / 1000)
    t = np.arange(n, dtype=np.float32) / sr
    wave = np.sin(2 * np.pi * freq * t)
    if decay:
        wave *= np.linspace(1.0, 0.02, n, dtype=np.float32)
    mono = np.int16(np.clip(wave * vol, -1, 1) * 32767)
    return pygame.sndarray.make_sound(np.ascontiguousarray(np.column_stack((mono, mono))))

SND_COLLECT = tone(880, 90, 0.4)
SND_OIL = tone(140, 180, 0.45)
SND_START = tone(440, 200, 0.3)

def engine_loop():
    sr, n = 22050, 22050
    t = np.arange(n, dtype=np.float32) / sr
    wave = (
        0.25 * np.sin(2 * np.pi * 70 * t)
        + 0.12 * np.sin(2 * np.pi * 140 * t)
        + 0.05 * np.random.uniform(-1, 1, n).astype(np.float32)
    )
    mono = np.int16(np.clip(wave, -1, 1) * 32767)
    snd = pygame.sndarray.make_sound(np.ascontiguousarray(np.column_stack((mono, mono))))
    snd.set_volume(0.25)
    return snd

ENGINE = engine_loop()

# ---------- helpers ----------
ROAD, PARK, BUILDING = 0, 1, 2
APT, CHRYSLER, PYRAMID, OFFICE = "apt", "chrysler", "pyramid", "office"

def h32(x, y, salt=0):
    n = (int(x) * 374761393 + int(y) * 668265263 + salt * 1274126177) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return n

def h01(x, y, salt=0):
    return (h32(x, y, salt) & 0xFFFFFF) / float(0xFFFFFF)

def lerp(a, b, t):
    return a + (b - a) * t

def lerp_angle(a, b, t):
    d = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + d * t

def is_road_tile(tx, ty):
    return (tx % ROAD_EVERY == 0) or (ty % ROAD_EVERY == 0)

# ---------- world ----------
class World:
    def __init__(self):
        self.chunks = {}
        self.parks = set()

    def ensure(self, wx, wy):
        ccx = int(math.floor(wx / (CHUNK_TILES * TILE)))
        ccy = int(math.floor(wy / (CHUNK_TILES * TILE)))
        needed = set()
        for dy in range(-KEEP_CHUNKS, KEEP_CHUNKS + 1):
            for dx in range(-KEEP_CHUNKS, KEEP_CHUNKS + 1):
                needed.add((ccx + dx, ccy + dy))
        for key in list(self.chunks.keys()):
            if key not in needed:
                self._drop_chunk(key)
        for key in needed:
            if key not in self.chunks:
                self._gen_chunk(*key)

    def _drop_chunk(self, key):
        cx, cy = key
        ox, oy = cx * CHUNK_TILES, cy * CHUNK_TILES
        for ty in range(oy, oy + CHUNK_TILES):
            for tx in range(ox, ox + CHUNK_TILES):
                self.parks.discard((tx, ty))
        del self.chunks[key]

    def _gen_chunk(self, cx, cy):
        buildings = []
        ox, oy = cx * CHUNK_TILES, cy * CHUNK_TILES
        for ty in range(oy, oy + CHUNK_TILES):
            for tx in range(ox, ox + CHUNK_TILES):
                if is_road_tile(tx, ty):
                    continue
                bx, by = tx // ROAD_EVERY, ty // ROAD_EVERY
                if h01(bx, by, 9) < 0.28:
                    self.parks.add((tx, ty))
                    continue
                roll = h01(tx, ty, 3)
                if roll < 0.12:
                    kind = PYRAMID
                    height = 8.0 + h01(tx, ty, 4) * 4.0
                elif roll < 0.28:
                    kind = CHRYSLER
                    height = 6.5 + h01(tx, ty, 5) * 3.2
                elif roll < 0.55:
                    kind = OFFICE
                    height = 3.6 + h01(tx, ty, 6) * 2.4
                else:
                    kind = APT
                    height = 1.15 + h01(tx, ty, 7) * 1.5
                buildings.append(
                    {
                        "tx": tx,
                        "ty": ty,
                        "kind": kind,
                        "height": height,
                        "tint": 70 + int(h01(tx, ty, 11) * 50),
                    }
                )
        self.chunks[(cx, cy)] = buildings

    def tile(self, px, py):
        tx, ty = int(math.floor(px / TILE)), int(math.floor(py / TILE))
        if is_road_tile(tx, ty):
            return ROAD
        if (tx, ty) in self.parks:
            return PARK
        return BUILDING

    def blocked(self, px, py, radius=12):
        for ox, oy in ((0, 0), (radius, 0), (-radius, 0), (0, radius), (0, -radius)):
            if self.tile(px + ox, py + oy) == BUILDING:
                return True
        return False

WORLD = World()

# ---------- anaglyph ----------
# Larger z = closer to the viewer = sticks out of the page.
ANAGLYPH_SEP = 3.6
GROUND_Z = 0.04
MODE_CYAN, MODE_GREEN, MODE_BLUE = "cyan", "green", "blue"
anaglyph_mode = MODE_CYAN

def stereo_dx(eye_shift, z):
    return eye_shift * z

def combine_anaglyph(left, right, mode):
    l = pygame.surfarray.array3d(left)
    r = pygame.surfarray.array3d(right)
    out = np.zeros_like(l)
    out[:, :, 0] = l[:, :, 0]
    if mode == MODE_CYAN:
        out[:, :, 1] = r[:, :, 1]
        out[:, :, 2] = r[:, :, 2]
    elif mode == MODE_GREEN:
        out[:, :, 1] = r[:, :, 1]
        out[:, :, 2] = r[:, :, 1] // 4
    else:
        out[:, :, 2] = r[:, :, 2]
        out[:, :, 1] = r[:, :, 2] // 5
    return pygame.surfarray.make_surface(out)

# ---------- oil ----------
class OilDrop:
    def __init__(self, x, y):
        ang = random.uniform(0, math.tau)
        spd = random.uniform(1.2, 4.8)
        self.x, self.y = x, y
        self.vx = math.cos(ang) * spd
        self.vy = math.sin(ang) * spd
        self.r = random.uniform(3, 9)
        self.life = random.uniform(0.7, 1.6)
        self.max = self.life

    def update(self, dt):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.88
        self.vy *= 0.88
        self.life -= dt
        self.r += dt * 6

    def draw(self, surf, camx, camy, dx=0):
        if self.life <= 0:
            return
        a = max(0.0, self.life / self.max)
        col = (int(18 * a + 8), int(14 * a + 6), int(10 * a + 4))
        pygame.draw.circle(
            surf, col, (int(self.x - camx + dx), int(self.y - camy)), int(self.r)
        )

def burst_oil(x, y, drops):
    for _ in range(random.randint(14, 22)):
        drops.append(OilDrop(x, y))

# ---------- car ----------
class Car:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.angle = 0.0
        self.speed = 0.0
        self.max_speed = 6.0
        self.accel = 0.18
        self.friction = 0.05
        self.turn = 0.055
        self.w, self.h = 28, 16

    def update(self, keys):
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.speed += self.accel
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.speed -= self.accel * 0.65
        else:
            if self.speed > 0:
                self.speed = max(0, self.speed - self.friction)
            elif self.speed < 0:
                self.speed = min(0, self.speed + self.friction)
        self.speed = max(-self.max_speed * 0.35, min(self.max_speed, self.speed))

        if abs(self.speed) > 0.2:
            steer = 0
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                steer -= 1
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                steer += 1
            scale = 0.55 + 0.45 * min(1.0, abs(self.speed) / self.max_speed)
            self.angle += steer * self.turn * scale * (1 if self.speed > 0 else -1)

        nx = self.x + math.cos(self.angle) * self.speed
        ny = self.y + math.sin(self.angle) * self.speed
        if not WORLD.blocked(nx, self.y):
            self.x = nx
        else:
            self.speed *= 0.35
        if not WORLD.blocked(self.x, ny):
            self.y = ny
        else:
            self.speed *= 0.35
        self._lane_assist()
        ENGINE.set_volume(0.08 + min(0.32, abs(self.speed) / self.max_speed * 0.32))

    def _lane_assist(self):
        kind = WORLD.tile(self.x, self.y)
        if kind != ROAD:
            return
        tx, ty = int(math.floor(self.x / TILE)), int(math.floor(self.y / TILE))
        ns = tx % ROAD_EVERY == 0
        ew = ty % ROAD_EVERY == 0
        if ns and ew:
            return
        if ns:
            self.x = lerp(self.x, (tx + 0.5) * TILE, 0.12)
            desired = math.pi / 2 if math.sin(self.angle) >= 0 else -math.pi / 2
            if abs(self.speed) > 0.4:
                self.angle = lerp_angle(self.angle, desired, 0.08)
        elif ew:
            self.y = lerp(self.y, (ty + 0.5) * TILE, 0.12)
            desired = 0.0 if math.cos(self.angle) >= 0 else math.pi
            if abs(self.speed) > 0.4:
                self.angle = lerp_angle(self.angle, desired, 0.08)

    def draw(self, surf, camx, camy, dx=0):
        sx, sy = self.x - camx + dx, self.y - camy
        pts = [(self.w / 2, 0), (-self.w / 2, -self.h / 2), (-self.w / 3, 0), (-self.w / 2, self.h / 2)]
        rot = []
        for px, py in pts:
            rx = px * math.cos(self.angle) - py * math.sin(self.angle)
            ry = px * math.sin(self.angle) + py * math.cos(self.angle)
            rot.append((sx + rx, sy + ry))
        pygame.draw.polygon(surf, (235, 55, 50), rot)
        pygame.draw.polygon(surf, (255, 220, 80), rot, 2)
        hx = sx + math.cos(self.angle) * 14
        hy = sy + math.sin(self.angle) * 14
        pygame.draw.circle(surf, (255, 255, 200), (int(hx), int(hy)), 3)

    def rect(self):
        return pygame.Rect(self.x - 12, self.y - 12, 24, 24)

# ---------- robots ----------
class Robot:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.angle = random.uniform(0, math.tau)
        self.wobble = random.uniform(0, math.tau)
        self.kind = random.choice(["drone", "bot", "cube"])
        self.color = random.choice(
            [(80, 220, 255), (90, 255, 140), (255, 200, 70), (210, 150, 255)]
        )

    def update(self, car):
        in_park = WORLD.tile(self.x, self.y) == PARK
        walk = 1.05 if in_park else 2.55
        dx, dy = self.x - car.x, self.y - car.y
        dist = math.hypot(dx, dy) or 1
        self.wobble += 0.1
        if dist < 150 and not in_park:
            fx, fy = dx / dist, dy / dist
            nx = self.x + fx * walk + math.cos(self.wobble) * 0.3
            ny = self.y + fy * walk + math.sin(self.wobble) * 0.3
        else:
            self.angle += random.uniform(-0.12, 0.12) if in_park else random.uniform(-0.06, 0.06)
            spd = walk * (0.7 if in_park else 1.0)
            nx = self.x + math.cos(self.angle) * spd
            ny = self.y + math.sin(self.angle) * spd
        if not WORLD.blocked(nx, self.y, 8):
            self.x = nx
        else:
            self.angle += math.pi * 0.5
        if not WORLD.blocked(self.x, ny, 8):
            self.y = ny
        else:
            self.angle += math.pi * 0.5

    def draw(self, surf, camx, camy, dx=0):
        x, y = int(self.x - camx + dx), int(self.y - camy)
        if self.kind == "drone":
            pygame.draw.circle(surf, self.color, (x, y), 10)
            pygame.draw.circle(surf, (20, 20, 30), (x, y), 4)
            pygame.draw.line(surf, self.color, (x - 14, y), (x + 14, y), 2)
        elif self.kind == "bot":
            pygame.draw.rect(surf, self.color, (x - 8, y - 10, 16, 20), border_radius=3)
            pygame.draw.circle(surf, (20, 20, 30), (x - 3, y - 4), 2)
            pygame.draw.circle(surf, (20, 20, 30), (x + 3, y - 4), 2)
        else:
            pygame.draw.rect(surf, self.color, (x - 8, y - 8, 16, 16))
            pygame.draw.rect(surf, (20, 20, 30), (x - 3, y - 3, 6, 6))

    def rect(self):
        return pygame.Rect(self.x - 10, self.y - 10, 20, 20)

def random_open_near(wx, wy, spread=900):
    for _ in range(40):
        x = wx + random.uniform(-spread, spread)
        y = wy + random.uniform(-spread, spread)
        if WORLD.tile(x, y) != BUILDING:
            return x, y
    return wx + 80, wy

# ---------- extruded top-down buildings ----------
def offset_pts(pts, dx):
    return [(p[0] + dx, p[1]) for p in pts]

def draw_extrusion(surf, base_pts, top_pts, wall_col, top_col, outline):
    n = len(base_pts)
    for i in range(n):
        j = (i + 1) % n
        wall = [base_pts[i], base_pts[j], top_pts[j], top_pts[i]]
        pygame.draw.polygon(surf, wall_col, wall)
    pygame.draw.polygon(surf, top_col, top_pts)
    pygame.draw.polygon(surf, outline, top_pts, 1)
    pygame.draw.polygon(surf, outline, base_pts, 1)

def draw_building(surf, b, camx, camy, eye_shift):
    z = b["height"]
    base_dx = stereo_dx(eye_shift, GROUND_Z)
    top_dx = stereo_dx(eye_shift, z)
    rx = b["tx"] * TILE - camx
    ry = b["ty"] * TILE - camy
    t = b["tint"]
    kind = b["kind"]
    wall = (max(20, t - 25), max(18, t - 20), max(22, t - 10))
    roof = (min(255, t + 55), min(255, t + 45), min(255, t + 30))
    outline = (210, 205, 180)

    if kind == APT:
        inset = 5
        base = [
            (rx + inset + base_dx, ry + 12),
            (rx + TILE - inset + base_dx, ry + 12),
            (rx + TILE - inset + base_dx, ry + TILE - 6),
            (rx + inset + base_dx, ry + TILE - 6),
        ]
        top = [
            (rx + inset + 3 + top_dx, ry + 14),
            (rx + TILE - inset - 3 + top_dx, ry + 14),
            (rx + TILE - inset - 3 + top_dx, ry + TILE - 8),
            (rx + inset + 3 + top_dx, ry + TILE - 8),
        ]
        draw_extrusion(surf, base, top, wall, roof, outline)
        for i in range(2):
            for j in range(2):
                pygame.draw.rect(
                    surf, (230, 220, 120),
                    (rx + 12 + i * 14 + top_dx, ry + 18 + j * 12, 7, 7),
                )

    elif kind == OFFICE:
        inset = 7
        base = [
            (rx + inset + base_dx, ry + 5),
            (rx + TILE - inset + base_dx, ry + 5),
            (rx + TILE - inset + base_dx, ry + TILE - 5),
            (rx + inset + base_dx, ry + TILE - 5),
        ]
        top = [
            (rx + inset + 2 + top_dx, ry + 7),
            (rx + TILE - inset - 2 + top_dx, ry + 7),
            (rx + TILE - inset - 2 + top_dx, ry + TILE - 7),
            (rx + inset + 2 + top_dx, ry + TILE - 7),
        ]
        draw_extrusion(surf, base, top, (t, t + 8, t + 20), (t + 40, t + 50, t + 70), outline)
        for row in range(3):
            pygame.draw.rect(
                surf, (210, 230, 255),
                (rx + 14 + top_dx, ry + 10 + row * 11, TILE - 28, 6),
            )

    elif kind == CHRYSLER:
        # stacked setbacks: each higher slab pops out more
        slabs = [
            (8, 0.35, (t + 20, t + 18, t + 10)),
            (12, 0.62, (t + 35, t + 30, t + 16)),
            (16, 0.82, (220, 210, 160)),
            (20, 1.00, (230, 220, 170)),
        ]
        prev_z = GROUND_Z
        prev_pts = [
            (rx + 8 + stereo_dx(eye_shift, prev_z), ry + 8),
            (rx + TILE - 8 + stereo_dx(eye_shift, prev_z), ry + 8),
            (rx + TILE - 8 + stereo_dx(eye_shift, prev_z), ry + TILE - 6),
            (rx + 8 + stereo_dx(eye_shift, prev_z), ry + TILE - 6),
        ]
        for inset, frac, col in slabs:
            hz = max(GROUND_Z + 0.4, z * frac)
            pts = [
                (rx + inset + stereo_dx(eye_shift, hz), ry + inset),
                (rx + TILE - inset + stereo_dx(eye_shift, hz), ry + inset),
                (rx + TILE - inset + stereo_dx(eye_shift, hz), ry + TILE - inset),
                (rx + inset + stereo_dx(eye_shift, hz), ry + TILE - inset),
            ]
            draw_extrusion(surf, prev_pts, pts, wall, col, outline)
            prev_pts = pts
            prev_z = hz
        # needle
        tip_z = z + 2.2
        tip_dx = stereo_dx(eye_shift, tip_z)
        base_mid = (rx + TILE / 2 + stereo_dx(eye_shift, prev_z), ry + TILE / 2)
        pygame.draw.line(surf, (255, 240, 180), base_mid, (rx + TILE / 2 + tip_dx, ry + TILE / 2), 2)
        pygame.draw.circle(surf, (255, 230, 140), (int(rx + TILE / 2 + tip_dx), int(ry + TILE / 2)), 3)

    elif kind == PYRAMID:
        base = [
            (rx + 4 + base_dx, ry + TILE - 5),
            (rx + TILE - 4 + base_dx, ry + TILE - 5),
            (rx + TILE - 4 + base_dx, ry + 5),
            (rx + 4 + base_dx, ry + 5),
        ]
        apex_z = z + 1.5
        apex = (rx + TILE / 2 + stereo_dx(eye_shift, apex_z), ry + TILE / 2)
        # four triangular faces from ground square to raised tip
        faces = [
            [base[0], base[1], apex],
            [base[1], base[2], apex],
            [base[2], base[3], apex],
            [base[3], base[0], apex],
        ]
        cols = [
            (t + 20, t + 16, t + 8),
            (t + 40, t + 34, t + 18),
            (t + 28, t + 24, t + 12),
            (t + 50, t + 42, t + 22),
        ]
        for face, col in zip(faces, cols):
            pygame.draw.polygon(surf, col, face)
            pygame.draw.polygon(surf, outline, face, 1)
        pygame.draw.circle(surf, (255, 240, 180), (int(apex[0]), int(apex[1])), 3)

def visible_range(camx, camy, pad=3):
    min_tx = int(math.floor(camx / TILE)) - pad
    max_tx = int(math.floor((camx + WIDTH) / TILE)) + pad
    min_ty = int(math.floor(camy / TILE)) - pad
    max_ty = int(math.floor((camy + HEIGHT) / TILE)) + pad
    return min_tx, max_tx, min_ty, max_ty

def draw_ground(surf, camx, camy, eye_shift):
    min_tx, max_tx, min_ty, max_ty = visible_range(camx, camy)
    dx = stereo_dx(eye_shift, GROUND_Z)
    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            rx, ry = tx * TILE - camx + dx, ty * TILE - camy
            if is_road_tile(tx, ty):
                pygame.draw.rect(surf, (52, 54, 60), (rx, ry, TILE, TILE))
                if tx % ROAD_EVERY == 0 and ty % ROAD_EVERY != 0:
                    pygame.draw.line(
                        surf, (210, 195, 70),
                        (rx + TILE / 2, ry + 10), (rx + TILE / 2, ry + TILE - 10), 2,
                    )
                if ty % ROAD_EVERY == 0 and tx % ROAD_EVERY != 0:
                    pygame.draw.line(
                        surf, (210, 195, 70),
                        (rx + 10, ry + TILE / 2), (rx + TILE - 10, ry + TILE / 2), 2,
                    )
            elif (tx, ty) in WORLD.parks:
                pygame.draw.rect(surf, (26, 92, 40), (rx, ry, TILE, TILE))
                pygame.draw.circle(surf, (40, 140, 58), (int(rx + 16), int(ry + 18)), 7)
                pygame.draw.circle(surf, (34, 118, 50), (int(rx + 32), int(ry + 30)), 6)

def draw_buildings_layer(surf, camx, camy, eye_shift):
    min_tx, max_tx, min_ty, max_ty = visible_range(camx, camy)
    buildings = []
    for chunk in WORLD.chunks.values():
        for b in chunk:
            if min_tx <= b["tx"] <= max_tx and min_ty <= b["ty"] <= max_ty:
                buildings.append(b)
    buildings.sort(key=lambda b: b["height"])
    for b in buildings:
        draw_building(surf, b, camx, camy, eye_shift)

def draw_eye(camx, camy, eye_shift, car, robots, oil):
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((16, 20, 24))
    draw_ground(surf, camx, camy, eye_shift)
    for o in oil:
        o.draw(surf, camx, camy, dx=stereo_dx(eye_shift, 0.2))
    draw_buildings_layer(surf, camx, camy, eye_shift)
    for r in robots:
        r.draw(surf, camx, camy, dx=stereo_dx(eye_shift, 1.4))
    car.draw(surf, camx, camy, dx=stereo_dx(eye_shift, 1.7))
    return surf

# ---------- game ----------
def main():
    global anaglyph_mode
    start_x, start_y = 2.5 * TILE, 0.5 * TILE
    WORLD.ensure(start_x, start_y)
    car = Car(start_x, start_y)
    robots = []
    oil = []
    score = 0
    time_left = 90.0
    running = True
    started = False
    ENGINE.play(loops=-1)

    while running:
        dt = clock.tick(FPS) / 1000.0
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                if e.key == pygame.K_SPACE and not started:
                    started = True
                    SND_START.play()
                if e.key == pygame.K_r and time_left <= 0:
                    car = Car(start_x, start_y)
                    robots.clear()
                    oil.clear()
                    score = 0
                    time_left = 90.0
                    started = True
                    SND_START.play()
                if e.key == pygame.K_1:
                    anaglyph_mode = MODE_CYAN
                if e.key == pygame.K_2:
                    anaglyph_mode = MODE_GREEN
                if e.key == pygame.K_3:
                    anaglyph_mode = MODE_BLUE

        keys = pygame.key.get_pressed()
        WORLD.ensure(car.x, car.y)

        if started and time_left > 0:
            time_left -= dt
            car.update(keys)
            for r in robots:
                r.update(car)

            kept = []
            for r in robots:
                if car.rect().colliderect(r.rect()):
                    score += 10
                    SND_COLLECT.play()
                    SND_OIL.play()
                    burst_oil(r.x, r.y, oil)
                elif math.hypot(r.x - car.x, r.y - car.y) < CULL_DIST:
                    kept.append(r)
            robots = kept
            while len(robots) < TARGET_ROBOTS:
                x, y = random_open_near(car.x, car.y)
                if math.hypot(x - car.x, y - car.y) > 160:
                    robots.append(Robot(x, y))

            oil = [o for o in oil if o.life > 0]
            for o in oil:
                o.update(dt)

        camx = car.x - WIDTH / 2
        camy = car.y - HEIGHT / 2
        left = draw_eye(camx, camy, +ANAGLYPH_SEP, car, robots, oil)
        right = draw_eye(camx, camy, -ANAGLYPH_SEP, car, robots, oil)
        screen.blit(combine_anaglyph(left, right, anaglyph_mode), (0, 0))

        mode_name = {
            MODE_CYAN: "RED/CYAN",
            MODE_GREEN: "RED/GREEN",
            MODE_BLUE: "RED/BLUE",
        }[anaglyph_mode]
        hud = font.render(
            f"Collected: {score}   Time: {max(0, time_left):.1f}s   {mode_name}",
            True,
            (240, 240, 240),
        )
        screen.blit(hud, (12, 8))
        hint = font.render(
            "Arrows/WASD  SPACE  1 cyan  2 green  3 blue  R restart  ESC",
            True,
            (210, 210, 210),
        )
        screen.blit(hint, (12, HEIGHT - 26))

        if not started:
            msg = big.render("DEATH RACE", True, (255, 90, 80))
            sub = font.render(
                "Look down on the town. Buildings pop off the page. SPACE to start.",
                True,
                (230, 230, 230),
            )
            screen.blit(msg, msg.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 16)))
            screen.blit(sub, sub.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 22)))

        if time_left <= 0:
            over = big.render(f"TIME UP  —  SCORE {score}", True, (255, 220, 80))
            sub = font.render("Press R to drive again", True, (220, 220, 220))
            screen.blit(over, over.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 8)))
            screen.blit(sub, sub.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 26)))

        pygame.display.flip()

    ENGINE.stop()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()