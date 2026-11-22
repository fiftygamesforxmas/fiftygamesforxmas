import pygame
import random
import sys

# Initialize Pygame
pygame.init()

# Constants
GRID_SIZE = 4
CARD_WIDTH = 150
CARD_HEIGHT = 120
MARGIN = 15
WINDOW_WIDTH = GRID_SIZE * (CARD_WIDTH + MARGIN) + MARGIN
WINDOW_HEIGHT = GRID_SIZE * (CARD_HEIGHT + MARGIN) + MARGIN + 60
FPS = 60
FLIP_DELAY = 1000  # milliseconds

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (34, 139, 34)
LIGHT_GREEN = (144, 238, 144)
RED = (220, 20, 60)
BLUE = (70, 130, 180)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)

# Kinds of lights
LIGHTS = [
    "Neon",
    "LED",
    "Arc",
    "Incandescent",
    "Fluorescent",
    "Halogen",
    "Xenon",
    "CFL",
    "OLED",
    "Laser",
    "Candle",
    "Lantern",
    "Spotlight",
    "Floodlight",
    "Streetlight",
    "Nightlight",
]

# Setup display
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Lights Memory Match - 4x4")
clock = pygame.time.Clock()
font_large = pygame.font.SysFont("arial", 26, bold=True)
font_title = pygame.font.SysFont("arial", 28, bold=True)

class Card:
    def __init__(self, x, y, light):
        self.rect = pygame.Rect(x, y, CARD_WIDTH, CARD_HEIGHT)
        self.light = light
        self.revealed = False
        self.matched = False

    def draw(self, surface):
        if self.matched:
            pygame.draw.rect(surface, LIGHT_GREEN, self.rect, border_radius=8)
            pygame.draw.rect(surface, GREEN, self.rect, 3, border_radius=8)
            name_surf = font_large.render(self.light, True, BLACK)
            name_rect = name_surf.get_rect(center=self.rect.center)
            surface.blit(name_surf, name_rect)
        elif self.revealed:
            pygame.draw.rect(surface, WHITE, self.rect, border_radius=8)
            pygame.draw.rect(surface, BLUE, self.rect, 3, border_radius=8)
            name_surf = font_large.render(self.light, True, BLACK)
            name_rect = name_surf.get_rect(center=self.rect.center)
            surface.blit(name_surf, name_rect)
        else:
            pygame.draw.rect(surface, GREEN, self.rect, border_radius=8)
            pygame.draw.rect(surface, DARK_GRAY, self.rect, 3, border_radius=8)
            back_text = font_large.render("?", True, WHITE)
            text_rect = back_text.get_rect(center=self.rect.center)
            surface.blit(back_text, text_rect)

def create_cards():
    # Select 8 lights and create pairs (perfect for 4x4 = 16 cards)
    selected = random.sample(LIGHTS, 8)
    all_data = selected * 2
    random.shuffle(all_data)

    cards = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            x = MARGIN + col * (CARD_WIDTH + MARGIN)
            y = MARGIN + row * (CARD_HEIGHT + MARGIN)
            idx = row * GRID_SIZE + col
            cards.append(Card(x, y, all_data[idx]))
    return cards

def main():
    cards = create_cards()
    selected = []
    moves = 0
    pairs_found = 0
    checking = False
    check_start_time = 0
    game_won = False

    running = True
    while running:
        screen.fill((240, 248, 255))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not checking and not game_won:
                pos = pygame.mouse.get_pos()
                for card in cards:
                    if card.rect.collidepoint(pos) and not card.revealed and not card.matched:
                        card.revealed = True
                        selected.append(card)
                        if len(selected) == 2:
                            moves += 1
                            checking = True
                            check_start_time = pygame.time.get_ticks()
                        break

        # Check for match after delay
        if checking and pygame.time.get_ticks() - check_start_time > FLIP_DELAY:
            c1, c2 = selected
            if c1.light == c2.light:
                c1.matched = True
                c2.matched = True
                pairs_found += 1
            else:
                c1.revealed = False
                c2.revealed = False
            selected = []
            checking = False
            if pairs_found == 8:
                game_won = True

        # Draw cards
        for card in cards:
            card.draw(screen)

        # Draw status
        status_y = WINDOW_HEIGHT - 45
        moves_text = font_title.render(f"Moves: {moves}", True, BLACK)
        pairs_text = font_title.render(f"Pairs: {pairs_found}/8", True, BLACK)
        screen.blit(moves_text, (20, status_y))
        screen.blit(pairs_text, (220, status_y))

        if game_won:
            win_text = font_title.render("You matched all pairs!", True, RED)
            win_rect = win_text.get_rect(center=(WINDOW_WIDTH // 2, status_y - 30))
            screen.blit(win_text, win_rect)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()