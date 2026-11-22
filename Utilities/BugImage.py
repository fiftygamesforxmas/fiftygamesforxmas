import pygame
import sys
import tempfile
import subprocess
import os
import math
import array
from PIL import Image, ImageDraw, ImageFont

# Dependencies: pygame, Pillow
# pip install pygame pillow

pygame.init()
pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)

screen = pygame.display.set_mode((400, 300))
pygame.display.set_caption("Image Rectangle Drawer  |  v: load  x: color  c: copy  z: undo  h: clear  b: blackout  +/-: zoom")
clock = pygame.time.Clock()

current_image = None          # Full-resolution PIL image (modified by blackouts)
surface = None                # Zoomed pygame surface for display
zoom_level = 1.0
MIN_ZOOM = 0.25
MAX_ZOOM = 4.0
ZOOM_STEP = 1.25

rectangles = []               # list of (pygame.Rect in original coords, color)
current_rect = None           # in original image coordinates
start_pos = None              # original coordinates
drawing = False
blackout_mode = False

colors = [
    (255, 255, 255),  # white
    (255, 255, 0),    # yellow
    (255, 0, 0),      # red
    (0, 0, 255),      # blue
    (0, 255, 0),      # green
]
color_idx = 0
border_color = colors[color_idx]
BORDER_THICKNESS = 5

def make_beep(frequency=440, duration=0.08, volume=0.18):
    sample_rate = 44100
    n_samples = int(sample_rate * duration)
    buf = array.array("h")
    for i in range(n_samples):
        sample = int(volume * 32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf)

sound_paste = make_beep(520, 0.07, 0.16)
sound_rect  = make_beep(400, 0.09, 0.15)
sound_undo  = make_beep(280, 0.10, 0.15)
sound_copy  = make_beep(480, 0.12, 0.17)
sound_blackout = make_beep(220, 0.15, 0.20)

def screen_to_original(pos):
    """Convert screen (zoomed) coordinates to original image coordinates."""
    if zoom_level <= 0:
        return (0, 0)
    return (pos[0] / zoom_level, pos[1] / zoom_level)

def original_to_screen(pos):
    """Convert original image coordinates to screen (zoomed) coordinates."""
    return (pos[0] * zoom_level, pos[1] * zoom_level)

def update_display():
    """Recreate the zoomed surface and resize the window."""
    global surface, screen
    if current_image is None:
        return
    w = max(1, int(current_image.width * zoom_level))
    h = max(1, int(current_image.height * zoom_level))
    scaled = current_image.resize((w, h), Image.Resampling.LANCZOS)
    surface = pygame.image.fromstring(scaled.tobytes(), scaled.size, "RGBA")
    screen = pygame.display.set_mode((w, h))

def load_from_clipboard():
    global current_image, zoom_level, rectangles, current_rect, blackout_mode

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    script = f'''
    try
        set imgData to the clipboard as «class PNGf»
        set f to open for access POSIX file "{tmp_path}" with write permission
        write imgData to f
        close access f
        return "ok"
    on error
        return "fail"
    end try
    '''

    try:
        p = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if (p.returncode != 0 or "fail" in p.stdout
                or not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0):
            print("No PNG image found on clipboard")
            return False

        img = Image.open(tmp_path)
        img.load()
    except Exception as e:
        print(f"Failed to load clipboard image: {e}")
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    current_image = img.convert("RGBA")
    zoom_level = 1.0
    rectangles.clear()
    current_rect = None
    blackout_mode = False
    update_display()
    sound_paste.play()
    print(f"Loaded image {current_image.width}x{current_image.height}")
    return True

def apply_blackout(rect):
    """Permanently black out a region (rect in original coordinates)."""
    global current_image
    if current_image is None or rect.width < 2 or rect.height < 2:
        return

    img = current_image.copy()
    draw = ImageDraw.Draw(img)

    x1 = max(0, int(rect.left))
    y1 = max(0, int(rect.top))
    x2 = min(img.width - 1, int(rect.right) - 1)
    y2 = min(img.height - 1, int(rect.bottom) - 1)

    draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 255))

    # Diagonal warning bars
    bar_spacing = 12
    width = x2 - x1
    height = y2 - y1
    for offset in range(-height, width + height, bar_spacing):
        pts = []
        for t in range(0, max(width, height) + 1, 2):
            px = x1 + offset + t
            py = y1 + t
            if x1 <= px <= x2 and y1 <= py <= y2:
                pts.append((px, py))
        if len(pts) >= 2:
            draw.line(pts, fill=(255, 255, 255, 255), width=2)

    # "hidden" text
    try:
        font_size = max(12, min(width, height) // 6)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except Exception:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    text = "hidden"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    tx = x1 + (width - text_w) // 2
    ty = y1 + (height - text_h) // 2
    draw.text((tx, ty), text, fill=(255, 255, 255, 255), font=font)

    current_image = img
    update_display()

def copy_to_clipboard():
    if current_image is None:
        print("Nothing to copy")
        return

    img_copy = current_image.copy()
    draw = ImageDraw.Draw(img_copy)

    for r, col in rectangles:
        if r.width > 0 and r.height > 0:
            x1 = int(r.left)
            y1 = int(r.top)
            x2 = int(r.right) - 1
            y2 = int(r.bottom) - 1
            draw.rectangle([x1, y1, x2, y2], outline=col, width=BORDER_THICKNESS)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img_copy.save(tmp.name, "PNG")
        tmp_path = tmp.name

    script = f'set the clipboard to (read (POSIX file "{tmp_path}") as «class PNGf»)'
    try:
        subprocess.run(["osascript", "-e", script], check=True)
        sound_copy.play()
        print("Copied modified PNG to clipboard")
    except Exception as e:
        print(f"Failed to copy to clipboard: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

def clear_window():
    global current_image, surface, screen, rectangles, current_rect, blackout_mode, zoom_level
    current_image = None
    surface = None
    rectangles.clear()
    current_rect = None
    blackout_mode = False
    zoom_level = 1.0
    screen = pygame.display.set_mode((400, 300))
    print("Window cleared")

def change_zoom(factor):
    global zoom_level
    if current_image is None:
        return
    new_zoom = zoom_level * factor
    new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
    if abs(new_zoom - zoom_level) > 0.01:
        zoom_level = new_zoom
        update_display()
        print(f"Zoom: {zoom_level:.2f}x")

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_v:
                load_from_clipboard()
            elif event.key == pygame.K_x:
                color_idx = (color_idx + 1) % len(colors)
                border_color = colors[color_idx]
                print(f"Border color → {border_color}")
            elif event.key == pygame.K_c:
                copy_to_clipboard()
            elif event.key == pygame.K_z:
                if rectangles and not blackout_mode:
                    rectangles.pop()
                    sound_undo.play()
                    print("Undo")
            elif event.key == pygame.K_h:
                clear_window()
            elif event.key == pygame.K_b and surface and not blackout_mode:
                blackout_mode = True
                current_rect = None
                print("Blackout mode: draw a rectangle to hide that region")
            elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                change_zoom(ZOOM_STEP)
            elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                change_zoom(1.0 / ZOOM_STEP)

        elif event.type == pygame.MOUSEBUTTONDOWN and surface and event.button == 1:
            orig = screen_to_original(event.pos)
            start_pos = orig
            drawing = True
            current_rect = pygame.Rect(orig[0], orig[1], 0, 0)

        elif event.type == pygame.MOUSEMOTION and drawing and start_pos:
            end = screen_to_original(event.pos)
            x = min(start_pos[0], end[0])
            y = min(start_pos[1], end[1])
            w = abs(end[0] - start_pos[0])
            h = abs(end[1] - start_pos[1])
            # Clamp to original image bounds
            x = max(0, min(x, current_image.width - 1))
            y = max(0, min(y, current_image.height - 1))
            w = min(w, current_image.width - x)
            h = min(h, current_image.height - y)
            current_rect = pygame.Rect(x, y, w, h)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and drawing:
            drawing = False
            if current_rect and current_rect.width > 5 and current_rect.height > 5:
                if blackout_mode:
                    apply_blackout(current_rect)
                    blackout_mode = False
                    sound_blackout.play()
                    print("Region blacked out — back to rectangle mode")
                else:
                    rectangles.append((current_rect.copy(), border_color))
                    sound_rect.play()
            current_rect = None

    # Draw
    screen.fill((30, 30, 30))
    if surface:
        screen.blit(surface, (0, 0))

    # Draw finished rectangles (scaled to current zoom)
    if not blackout_mode:
        for r, col in rectangles:
            if r.width > 0 and r.height > 0:
                sx = r.left * zoom_level
                sy = r.top * zoom_level
                sw = r.width * zoom_level
                sh = r.height * zoom_level
                pygame.draw.rect(screen, col, pygame.Rect(sx, sy, sw, sh), BORDER_THICKNESS)

    # Current rectangle preview
    if current_rect and current_rect.width > 0 and current_rect.height > 0:
        sx = current_rect.left * zoom_level
        sy = current_rect.top * zoom_level
        sw = current_rect.width * zoom_level
        sh = current_rect.height * zoom_level
        preview_color = (255, 80, 80) if blackout_mode else border_color
        pygame.draw.rect(screen, preview_color, pygame.Rect(sx, sy, sw, sh), BORDER_THICKNESS)

    # Mode / zoom indicator
    if surface:
        font = pygame.font.SysFont(None, 24)
        status = f"Zoom: {zoom_level:.2f}x"
        if blackout_mode:
            status = "BLACKOUT MODE — draw region to hide"
            color = (255, 80, 80)
        else:
            color = (200, 200, 200)
        label = font.render(status, True, color)
        screen.blit(label, (10, 10))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()