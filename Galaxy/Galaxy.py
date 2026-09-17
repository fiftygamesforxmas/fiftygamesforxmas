"""
Galaxy–galaxy collision in anaglyph 3D (Pygame).

Keys:
  T           cycle: red/cyan -> red/green -> red/blue -> normal
  Y           swap left/right eye colors
  P           ride an outer-halo particle; look at the star majority
  LEFT/RIGHT  yaw 360 deg (plane 1)
  UP/DOWN     pitch 360 deg (plane 2, perpendicular)
  Z           move point of view forward
  X           move point of view backward
  SPACE       pause
  R           reset
  ESC/Q       quit
"""

import json
import math
import os
import random
import sys
import numpy as np
import pygame

WIDTH, HEIGHT = 1280, 720
WIN_X, WIN_Y = 80, 60
N_PER_GALAXY = 90
N_GALAXIES = 3
SOFTENING = 18.0
G = 220.0
DT = 0.035
EYE_SEP = 7.5
FOCAL = 520.0
CAM_Z = 420.0
STAR_RADIUS = 2
Z_CONV_DEFAULT = CAM_Z
TURN_SPEED = 1.6
DOLLY_SPEED = 180.0

MODES = ("redcyan", "redgreen", "redblue", "normal")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "galaxy_window.json")


def load_window_config():
    global WIDTH, HEIGHT, WIN_X, WIN_Y
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        WIDTH = max(400, int(cfg.get("width", WIDTH)))
        HEIGHT = max(300, int(cfg.get("height", HEIGHT)))
        WIN_X = int(cfg.get("x", WIN_X))
        WIN_Y = int(cfg.get("y", WIN_Y))
    except (OSError, ValueError, TypeError):
        pass


def save_window_config():
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"width": WIDTH, "height": HEIGHT, "x": WIN_X, "y": WIN_Y}, f)
    except OSError:
        pass


def galaxy_positions(kind, n, scale):
    rng = np.random.default_rng()
    if kind == "spiral":
        arms = rng.integers(2, 5)
        r = scale * np.sqrt(rng.random(n))
        theta = r * (2.2 + rng.random() * 1.4) + rng.integers(0, arms, n) * (2 * np.pi / arms)
        theta += rng.normal(0, 0.18, n)
        z = rng.normal(0, scale * 0.06, n)
        p = np.column_stack((r * np.cos(theta), r * np.sin(theta), z))
    elif kind == "barred":
        bar = n // 3
        p = np.zeros((n, 3))
        p[:bar, 0] = rng.normal(0, scale * 0.55, bar)
        p[:bar, 1] = rng.normal(0, scale * 0.08, bar)
        p[:bar, 2] = rng.normal(0, scale * 0.05, bar)
        r = scale * np.sqrt(rng.random(n - bar))
        theta = r * 2.6 + rng.choice([0.0, np.pi], n - bar)
        theta += rng.normal(0, 0.2, n - bar)
        p[bar:, 0] = r * np.cos(theta)
        p[bar:, 1] = r * np.sin(theta)
        p[bar:, 2] = rng.normal(0, scale * 0.06, n - bar)
    elif kind == "elliptical":
        axes = np.array([1.0, 0.55 + rng.random() * 0.35, 0.28 + rng.random() * 0.2]) * scale
        p = rng.normal(0, 1, (n, 3))
        p /= np.linalg.norm(p, axis=1, keepdims=True) + 1e-9
        p *= rng.random(n)[:, None] ** (1 / 3) * axes
    elif kind == "ring":
        r = scale * (0.55 + 0.18 * rng.normal(0, 1, n))
        theta = rng.random(n) * 2 * np.pi
        p = np.column_stack((r * np.cos(theta), r * np.sin(theta), rng.normal(0, scale * 0.05, n)))
        core = n // 6
        p[:core] = rng.normal(0, scale * 0.12, (core, 3))
    elif kind == "lenticular":
        r = scale * np.sqrt(rng.random(n))
        theta = rng.random(n) * 2 * np.pi
        p = np.column_stack((r * np.cos(theta), r * np.sin(theta), rng.normal(0, scale * 0.04, n)))
    else:
        clumps = rng.integers(3, 7)
        centers = rng.normal(0, scale * 0.45, (clumps, 3))
        assign = rng.integers(0, clumps, n)
        p = centers[assign] + rng.normal(0, scale * 0.16, (n, 3))
        p[:, 2] *= 0.4

    ax = rng.normal(0, 1, 3)
    ax /= np.linalg.norm(ax)
    ang = rng.random() * 2 * np.pi
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    R = np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * (K @ K)
    return p @ R.T


def circular_vel(pos, mass_scale):
    x, y = pos[:, 0], pos[:, 1]
    r2 = x * x + y * y + 1e-6
    r = np.sqrt(r2 + pos[:, 2] ** 2)
    speed = np.sqrt(G * mass_scale / (r + SOFTENING)) * 0.55
    vx = -y / np.sqrt(r2) * speed
    vy = x / np.sqrt(r2) * speed
    return np.column_stack((vx, vy, np.random.normal(0, speed * 0.04, len(pos))))


def make_universe():
    kinds = ["spiral", "barred", "elliptical", "ring", "lenticular", "irregular"]
    palette = [
        (255, 220, 160),
        (180, 210, 255),
        (255, 170, 140),
        (200, 255, 190),
        (255, 200, 255),
        (230, 230, 210),
    ]
    merger = random.random() < (2.0 / 3.0)

    if merger:
        radius = random.uniform(95, 145)
        inbound = random.uniform(16, 26)
        miss = random.uniform(0.5, 3.5)
    else:
        radius = random.uniform(200, 280)
        inbound = random.uniform(22, 38)
        miss = random.uniform(10, 18)

    depth_roles = [-1, 1, random.choice([-1, 0, 1])]
    random.shuffle(depth_roles)
    near_z, far_z = -165.0, 175.0

    pos_list, vel_list, col_list, gid_list = [], [], [], []
    for i in range(N_GALAXIES):
        kind = random.choice(kinds)
        scale = random.uniform(50, 80) if merger else random.uniform(55, 95)
        p = galaxy_positions(kind, N_PER_GALAXY, scale)
        ang = 2 * np.pi * i / N_GALAXIES + random.uniform(-0.15, 0.15)
        role = depth_roles[i]
        if role < 0:
            zc = near_z + random.uniform(-20, 20)
        elif role > 0:
            zc = far_z + random.uniform(-20, 20)
        else:
            zc = random.uniform(-90, 90)
        center = np.array(
            [
                math.cos(ang) * radius,
                math.sin(ang) * radius * (0.55 if merger else 0.7),
                zc,
            ]
        )
        p = p + center
        v = circular_vel(p - center, N_PER_GALAXY)
        toward = -center / (np.linalg.norm(center) + 1e-6)
        miss_dir = np.cross(toward, np.array([0.0, 0.0, 1.0]))
        nrm = np.linalg.norm(miss_dir)
        miss_dir = miss_dir / nrm if nrm > 1e-8 else np.array([-toward[1], toward[0], 0.0])
        v += toward * inbound + miss_dir * miss
        pos_list.append(p)
        vel_list.append(v)
        col_list.append(np.tile(np.array(palette[i % len(palette)], dtype=np.float32), (N_PER_GALAXY, 1)))
        gid_list.append(np.full(N_PER_GALAXY, i, dtype=np.int32))

    pos = np.vstack(pos_list).astype(np.float64)
    vel = np.vstack(vel_list).astype(np.float64)
    col = np.vstack(col_list)
    gid = np.concatenate(gid_list)
    vel -= vel.mean(axis=0)
    pos -= pos.mean(axis=0)
    return pos, vel, col, gid, merger


def pick_outer_rider(pos, gid):
    centers = []
    for g in range(N_GALAXIES):
        sel = pos[gid == g]
        centers.append(sel.mean(axis=0) if len(sel) else pos.mean(axis=0))
    centers = np.array(centers)
    d = np.linalg.norm(pos[:, None, :] - centers[None, :, :], axis=2).min(axis=1)
    order = np.argsort(d)
    pool = order[-max(12, len(pos) // 5) :]
    return int(np.random.choice(pool))


def angles_from_forward(fwd):
    fwd = fwd / (np.linalg.norm(fwd) + 1e-9)
    pitch = math.asin(float(np.clip(fwd[1], -1.0, 1.0)))
    yaw = math.atan2(fwd[0], fwd[2])
    return yaw, pitch


def forward_from_angles(yaw, pitch):
    cp = math.cos(pitch)
    return np.array([cp * math.sin(yaw), math.sin(pitch), cp * math.cos(yaw)], dtype=np.float64)


def accelerate(pos):
    n = len(pos)
    acc = np.zeros_like(pos)
    for i in range(0, n, 64):
        sl = slice(i, min(i + 64, n))
        d = pos[None, :, :] - pos[sl, None, :]
        r2 = np.sum(d * d, axis=2) + SOFTENING * SOFTENING
        inv = 1.0 / (r2 * np.sqrt(r2))
        for k, idx in enumerate(range(sl.start, sl.stop)):
            inv[k, idx] = 0.0
        acc[sl] = G * np.sum(d * inv[:, :, None], axis=1)
    return acc


def look_basis(forward, up_hint):
    f = forward / (np.linalg.norm(forward) + 1e-9)
    r = np.cross(up_hint, f)
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(np.array([1.0, 0.0, 0.0]), f)
    r = r / (np.linalg.norm(r) + 1e-9)
    u = np.cross(f, r)
    u = u / (np.linalg.norm(u) + 1e-9)
    return r, u, f


def world_to_cam(pos, cam_pos, right, up, forward):
    rel = pos - cam_pos
    return np.column_stack((rel @ right, rel @ up, rel @ forward))


def project_stereo(cam_xyz, eye_sign, z_conv):
    z = np.maximum(cam_xyz[:, 2], 8.0)
    z_conv = max(float(z_conv), 8.0)
    px_shift = eye_sign * EYE_SEP * FOCAL * (1.0 / z - 1.0 / z_conv)
    sx = WIDTH * 0.5 + FOCAL * cam_xyz[:, 0] / z + px_shift
    sy = HEIGHT * 0.5 + FOCAL * cam_xyz[:, 1] / z
    return sx, sy, z


def draw_stars(surface, sx, sy, depth, colors, skip_idx=None):
    order = np.argsort(-depth)
    w, h = surface.get_size()
    for i in order:
        if skip_idx is not None and i == skip_idx:
            continue
        x, y = int(sx[i]), int(sy[i])
        if x < -4 or y < -4 or x > w + 4 or y > h + 4:
            continue
        c = colors[i]
        r = max(1, int(STAR_RADIUS * 420 / max(depth[i], 8.0)))
        pygame.draw.circle(surface, (int(c[0]), int(c[1]), int(c[2])), (x, y), r)


def composite_anaglyph(left_rgb, right_rgb, mode, swapped):
    if swapped:
        left_rgb, right_rgb = right_rgb, left_rgb
    out = np.zeros_like(left_rgb)
    if mode == "redcyan":
        out[:, :, 0] = left_rgb[:, :, 0]
        out[:, :, 1] = right_rgb[:, :, 1]
        out[:, :, 2] = right_rgb[:, :, 2]
    elif mode == "redgreen":
        out[:, :, 0] = left_rgb[:, :, 0]
        out[:, :, 1] = right_rgb[:, :, 1]
    elif mode == "redblue":
        out[:, :, 0] = left_rgb[:, :, 0]
        out[:, :, 2] = right_rgb[:, :, 2]
    else:
        out = left_rgb
    return out


def main():
    global WIDTH, HEIGHT, WIN_X, WIN_Y

    load_window_config()
    os.environ["SDL_VIDEO_WINDOW_POS"] = "%d,%d" % (WIN_X, WIN_Y)

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Galaxy collision — anaglyph 3D  [T Y P Z X arrows R]")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 16)

    pos, vel, colors, gid, merger = make_universe()
    rider = pick_outer_rider(pos, gid)
    mode_i = 0
    swapped = False
    paused = False
    ride = False
    yaw = 0.0
    pitch = 0.0
    dolly = 0.0
    look_up = np.array([0.0, 1.0, 0.0])

    left_surf = pygame.Surface((WIDTH, HEIGHT))
    right_surf = pygame.Surface((WIDTH, HEIGHT))

    running = True
    while running:
        dt_frame = clock.get_time() / 1000.0
        step = max(dt_frame, 1.0 / 120.0)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.WINDOWMOVED:
                WIN_X, WIN_Y = int(e.x), int(e.y)
            elif e.type in (pygame.VIDEORESIZE, getattr(pygame, "WINDOWRESIZED", pygame.VIDEORESIZE)):
                WIDTH = max(400, int(getattr(e, "w", getattr(e, "x", WIDTH))))
                HEIGHT = max(300, int(getattr(e, "h", getattr(e, "y", HEIGHT))))
                if e.type == pygame.VIDEORESIZE:
                    WIDTH, HEIGHT = max(400, e.w), max(300, e.h)
                screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                left_surf = pygame.Surface((WIDTH, HEIGHT))
                right_surf = pygame.Surface((WIDTH, HEIGHT))
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif e.key == pygame.K_t:
                    mode_i = (mode_i + 1) % len(MODES)
                elif e.key == pygame.K_y:
                    swapped = not swapped
                elif e.key == pygame.K_p:
                    ride = not ride
                    dolly = 0.0
                    if ride:
                        rider = pick_outer_rider(pos, gid)
                        others = np.delete(pos, rider, axis=0)
                        desired = others.mean(axis=0) - pos[rider]
                        yaw, pitch = angles_from_forward(desired)
                elif e.key == pygame.K_SPACE:
                    paused = not paused
                elif e.key == pygame.K_r:
                    pos, vel, colors, gid, merger = make_universe()
                    rider = pick_outer_rider(pos, gid)
                    yaw, pitch, dolly = 0.0, 0.0, 0.0

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            yaw -= TURN_SPEED * step
        if keys[pygame.K_RIGHT]:
            yaw += TURN_SPEED * step
        if keys[pygame.K_UP]:
            pitch += TURN_SPEED * step
        if keys[pygame.K_DOWN]:
            pitch -= TURN_SPEED * step
        if keys[pygame.K_z]:
            dolly += DOLLY_SPEED * step
        if keys[pygame.K_x]:
            dolly -= DOLLY_SPEED * step
        tau = 2.0 * math.pi
        yaw %= tau
        pitch %= tau

        if not paused:
            acc = accelerate(pos)
            vel += acc * DT
            vel *= 0.9992
            pos += vel * DT
            if not ride:
                pos -= pos.mean(axis=0)
                vel -= vel.mean(axis=0)

        look_fwd = forward_from_angles(yaw, pitch)
        skip = None
        if ride:
            cam_pos = pos[rider].copy() + look_fwd * dolly
            right, up, fwd = look_basis(look_fwd, look_up)
            cam_xyz = world_to_cam(pos, cam_pos, right, up, fwd)
            skip = rider
            z_conv = max(float(np.median(np.maximum(cam_xyz[:, 2], 8.0))), 80.0)
        else:
            cam_pos = -look_fwd * CAM_Z + look_fwd * dolly
            right, up, fwd = look_basis(look_fwd, look_up)
            cam_xyz = world_to_cam(pos, cam_pos, right, up, fwd)
            z_conv = Z_CONV_DEFAULT

        mode = MODES[mode_i]
        left_surf.fill((0, 0, 0))
        right_surf.fill((0, 0, 0))

        if mode == "normal":
            sx, sy, depth = project_stereo(cam_xyz, 0.0, z_conv)
            draw_stars(left_surf, sx, sy, depth, colors, skip)
            screen.blit(left_surf, (0, 0))
        else:
            lsx, lsy, ld = project_stereo(cam_xyz, -1.0, z_conv)
            rsx, rsy, rd = project_stereo(cam_xyz, +1.0, z_conv)
            draw_stars(left_surf, lsx, lsy, ld, colors, skip)
            draw_stars(right_surf, rsx, rsy, rd, colors, skip)
            la = pygame.surfarray.array3d(left_surf)
            ra = pygame.surfarray.array3d(right_surf)
            out = composite_anaglyph(la, ra, mode, swapped)
            pygame.surfarray.blit_array(screen, out)

        kind = "MERGER" if merger else "flyby"
        ride_s = "RIDE#%d" % rider if ride else "cam=orbit"
        label = "%s  %s  dolly=%.0f  %dx%d  mode=%s  [Z/X T/Y/P arrows]" % (
            kind,
            ride_s,
            dolly,
            WIDTH,
            HEIGHT,
            mode,
        )
        screen.blit(font.render(label, True, (180, 180, 180)), (12, 10))
        pygame.display.flip()
        clock.tick(60)

    save_window_config()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()