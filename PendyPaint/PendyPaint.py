import pygame
import math
import sys
import colorsys
from pygame.locals import *

pygame.init()

# Screen
WIDTH, HEIGHT = 1400, 900
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Spirograph Paint Studio")
clock = pygame.time.Clock()

# Canvas
canvas = pygame.Surface((WIDTH - 320, HEIGHT), pygame.SRCALPHA)
canvas.fill((0, 0, 0, 0))
CANVAS_X = 320

background = pygame.Surface((WIDTH, HEIGHT))
background.fill((12, 12, 18))

# Colors
def make_palette(n=36):
    cols = []
    for i in range(n):
        h = i / n
        r, g, b = colorsys.hsv_to_rgb(h, 0.92, 1.0)
        cols.append((int(r*255), int(g*255), int(b*255)))
    return cols

PALETTE = make_palette()

# UI Colors
UI_BG = (25, 25, 35)
UI_PANEL = (35, 35, 50)
UI_ACCENT = (80, 140, 255)
UI_TEXT = (220, 220, 230)
UI_DIM = (140, 140, 160)

font = pygame.font.SysFont("consolas", 15)
small_font = pygame.font.SysFont("consolas", 13)
title_font = pygame.font.SysFont("consolas", 18, bold=True)

# --- Spirograph parameters ---
outer_teeth = 96          # Fixed ring teeth
inner_teeth = 48          # Moving gear teeth
pen_ratio = 0.7           # 0.0 = center, 1.0 = edge of inner gear
revolutions = 20          # How many times inner gear rolls
speed = 0.8               # Drawing speed multiplier

# Derived
def get_radii():
    R = 280                   # Outer radius (pixels)
    r = R * (inner_teeth / outer_teeth)
    d = r * pen_ratio
    return R, r, d

# Multiple pens
class Pen:
    def __init__(self, color_idx, alpha=200, pattern="line", phase=0.0, d_mult=1.0):
        self.color = PALETTE[color_idx % len(PALETTE)]
        self.alpha = alpha
        self.pattern = pattern
        self.phase = phase
        self.d_mult = d_mult
        self.prev = None

pens = [
    Pen(0,  210, "ribbon", 0.0, 1.0),
    Pen(6,  170, "line",   0.4, 0.85),
    Pen(12, 230, "dots",   1.1, 1.15),
    Pen(18, 150, "thick",  2.2, 0.7),
    Pen(24, 190, "ribbon", 3.0, 1.05),
    Pen(30, 120, "line",   0.8, 0.6),
]

# Simulation
t = 0.0
paused = False
spin = 0.0                 # Additional global rotation
spin_dir = 1

# UI state
dragging_slider = None
selected_pen = 0

# --- UI helpers ---
class Slider:
    def __init__(self, x, y, w, minv, maxv, value, label, step=1):
        self.rect = pygame.Rect(x, y, w, 22)
        self.minv = minv
        self.maxv = maxv
        self.value = value
        self.label = label
        self.step = step
        self.handle_w = 14

    def draw(self, surf):
        # Track
        pygame.draw.rect(surf, (50, 50, 65), self.rect, border_radius=4)
        # Fill
        ratio = (self.value - self.minv) / (self.maxv - self.minv)
        fill_w = int(self.rect.w * ratio)
        pygame.draw.rect(surf, UI_ACCENT, (self.rect.x, self.rect.y, fill_w, self.rect.h), border_radius=4)
        # Handle
        hx = self.rect.x + fill_w - self.handle_w//2
        hx = max(self.rect.x, min(hx, self.rect.right - self.handle_w))
        pygame.draw.rect(surf, (240, 240, 250), (hx, self.rect.y-2, self.handle_w, self.rect.h+4), border_radius=3)
        # Label
        txt = small_font.render(f"{self.label}: {self.value:.2f}" if isinstance(self.value, float) else f"{self.label}: {int(self.value)}", True, UI_TEXT)
        surf.blit(txt, (self.rect.x, self.rect.y - 16))

    def handle_event(self, event):
        if event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            return True
        if event.type == MOUSEMOTION and pygame.mouse.get_pressed()[0]:
            if self.rect.collidepoint(event.pos) or dragging_slider is self:
                rel = (event.pos[0] - self.rect.x) / self.rect.w
                rel = max(0, min(1, rel))
                raw = self.minv + rel * (self.maxv - self.minv)
                if self.step >= 1:
                    self.value = round(raw / self.step) * self.step
                else:
                    self.value = round(raw / self.step) * self.step
                return True
        return False

class Button:
    def __init__(self, x, y, w, h, text, callback):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.hover = False

    def draw(self, surf):
        col = (70, 110, 200) if self.hover else (55, 85, 160)
        pygame.draw.rect(surf, col, self.rect, border_radius=5)
        txt = small_font.render(self.text, True, (255, 255, 255))
        surf.blit(txt, txt.get_rect(center=self.rect.center))

    def handle(self, event):
        if event.type == MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.callback()
            return True
        return False

# Create controls
sliders = [
    Slider(20, 70,  280, 24, 144, outer_teeth, "Outer Gear", 1),
    Slider(20, 120, 280, 6,  72,  inner_teeth, "Inner Gear", 1),
    Slider(20, 170, 280, 0.05, 1.0, pen_ratio, "Pen Distance", 0.01),
    Slider(20, 220, 280, 1,  60,  revolutions, "Revolutions", 1),
    Slider(20, 270, 280, 0.1, 3.0, speed, "Speed", 0.05),
    Slider(20, 320, 280, -2.0, 2.0, spin, "Base Spin", 0.01),
]

def reset_canvas():
    global t, canvas
    canvas.fill((0, 0, 0, 0))
    t = 0.0
    for p in pens:
        p.prev = None

def save_image():
    final = pygame.Surface((canvas.get_width(), canvas.get_height()))
    final.fill((10, 10, 15))
    final.blit(canvas, (0, 0))
    pygame.image.save(final, "spirograph.jpg")
    print("Saved spirograph.jpg")

def cycle_pattern(idx):
    pats = ["line", "ribbon", "dots", "thick"]
    p = pens[idx]
    p.pattern = pats[(pats.index(p.pattern) + 1) % len(pats)]

def cycle_color(idx, dir=1):
    pens[idx].color = PALETTE[(PALETTE.index(pens[idx].color) + dir) % len(PALETTE)]

buttons = [
    Button(20, 380, 130, 32, "Reset Canvas", reset_canvas),
    Button(160, 380, 130, 32, "Save JPEG", save_image),
    Button(20, 420, 130, 32, "Pause/Resume", lambda: globals().update(paused=not paused)),
    Button(160, 420, 130, 32, "Spin CW", lambda: globals().update(spin_dir=1)),
    Button(20, 460, 130, 32, "Spin CCW", lambda: globals().update(spin_dir=-1)),
    Button(160, 460, 130, 32, "Clear Spin", lambda: globals().update(spin=0.0)),
]

# Pattern / color buttons for pens
pen_buttons = []
for i in range(len(pens)):
    y = 520 + i * 48
    pen_buttons.append(Button(20, y, 80, 28, f"Pat {i+1}", lambda i=i: cycle_pattern(i)))
    pen_buttons.append(Button(110, y, 80, 28, "Col+", lambda i=i: cycle_color(i, 1)))
    pen_buttons.append(Button(200, y, 80, 28, "Col-", lambda i=i: cycle_color(i, -1)))

def hypotrochoid(theta, R, r, d, phase=0):
    # Classic hypotrochoid (inner gear rolling inside outer)
    k = (R - r) / r
    x = (R - r) * math.cos(theta) + d * math.cos(k * theta + phase)
    y = (R - r) * math.sin(theta) - d * math.sin(k * theta + phase)
    return x, y

def draw_pen(surface, pen, pos):
    col = (*pen.color, pen.alpha)
    if pen.prev is None:
        pen.prev = pos
        return

    if pen.pattern == "line":
        pygame.draw.line(surface, col, pen.prev, pos, 1)
    elif pen.pattern == "ribbon":
        for i in range(5):
            a = max(15, pen.alpha - i * 35)
            c = (*pen.color, a)
            off = i * 1.8
            pygame.draw.line(surface, c, 
                             (pen.prev[0] + off, pen.prev[1]),
                             (pos[0] + off, pos[1]), 2)
    elif pen.pattern == "dots":
        if int(t * 30) % 3 == 0:
            pygame.draw.circle(surface, col, pos, 2)
    elif pen.pattern == "thick":
        pygame.draw.line(surface, col, pen.prev, pos, 3)
        pygame.draw.circle(surface, (*pen.color, min(255, pen.alpha+40)), pos, 2)

    pen.prev = pos

# Main loop
running = True
while running:
    mouse_pos = pygame.mouse.get_pos()

    for event in pygame.event.get():
        if event.type == QUIT:
            running = False

        # Sliders
        for s in sliders:
            if s.handle_event(event):
                dragging_slider = s
                # Update globals
                outer_teeth = int(sliders[0].value)
                inner_teeth = int(sliders[1].value)
                pen_ratio = sliders[2].value
                revolutions = int(sliders[3].value)
                speed = sliders[4].value
                spin = sliders[5].value

        if event.type == MOUSEBUTTONUP:
            dragging_slider = None

        # Buttons
        for b in buttons + pen_buttons:
            b.handle(event)

        # Keyboard shortcuts
        if event.type == KEYDOWN:
            if event.key == K_SPACE:
                paused = not paused
            elif event.key == K_r:
                reset_canvas()
            elif event.key == K_s:
                save_image()

    # Update simulation
    if not paused:
        R, r, d = get_radii()
        steps = max(1, int(speed * 4))
        for _ in range(steps):
            t += 0.012
            max_theta = revolutions * 2 * math.pi * (outer_teeth / inner_teeth)
            if t > max_theta:
                t = max_theta  # stop at end of set revolutions

            angle = t
            # Base spin
            base_rot = spin * t * spin_dir * 0.3

            for pen in pens:
                x, y = hypotrochoid(angle, R, r, d * pen.d_mult, pen.phase)
                # Apply base rotation
                rx = x * math.cos(base_rot) - y * math.sin(base_rot)
                ry = x * math.sin(base_rot) + y * math.cos(base_rot)
                pos = (int(CANVAS_X + canvas.get_width()/2 + rx),
                       int(HEIGHT/2 + ry))
                draw_pen(canvas, pen, pos)

    # Draw
    screen.blit(background, (0, 0))
    screen.blit(canvas, (CANVAS_X, 0))

    # UI Panel
    pygame.draw.rect(screen, UI_BG, (0, 0, 320, HEIGHT))
    pygame.draw.rect(screen, UI_PANEL, (8, 8, 304, HEIGHT-16), border_radius=8)

    title = title_font.render("SPIROGRAPH", True, UI_ACCENT)
    screen.blit(title, (20, 20))
    sub = small_font.render("Gear Controls", True, UI_DIM)
    screen.blit(sub, (20, 45))

    for s in sliders:
        s.draw(screen)

    for b in buttons:
        b.draw(screen)

    # Pens section
    pygame.draw.line(screen, (60, 60, 80), (20, 500), (300, 500), 1)
    pens_title = small_font.render("PENS  (Pattern / Color)", True, UI_TEXT)
    screen.blit(pens_title, (20, 508))

    for i, pen in enumerate(pens):
        y = 545 + i * 48
        # Color swatch
        pygame.draw.rect(screen, pen.color, (20, y-6, 18, 18), border_radius=3)
        info = small_font.render(f"α{pen.alpha}  {pen.pattern}", True, UI_DIM)
        screen.blit(info, (45, y-4))

    for b in pen_buttons:
        b.draw(screen)

    # Status
    R, r, d = get_radii()
    ratio = outer_teeth / inner_teeth if inner_teeth else 0
    status = small_font.render(
        f"Ratio {outer_teeth}:{inner_teeth}  ({ratio:.2f})   R={R:.0f} r={r:.0f} d={d:.0f}",
        True, (160, 180, 220)
    )
    screen.blit(status, (CANVAS_X + 15, 15))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()