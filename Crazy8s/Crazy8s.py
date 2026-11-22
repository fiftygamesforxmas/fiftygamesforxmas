import pygame
import random
import sys

# Initialize
pygame.init()
WIDTH, HEIGHT = 1000, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Crazy Eights - Player vs Computer")
clock = pygame.time.Clock()

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (200, 0, 0)
BLUE = (0, 100, 200)
GREEN = (0, 150, 0)
GRAY = (180, 180, 180)
DARK_GRAY = (100, 100, 100)
GOLD = (255, 215, 0)
CARD_BACK = (0, 70, 140)

# Fonts
font = pygame.font.SysFont("arial", 28)
small_font = pygame.font.SysFont("arial", 20)
big_font = pygame.font.SysFont("arial", 40, bold=True)

# Suits and ranks
SUITS = ["Hearts", "Diamonds", "Clubs", "Spades"]
SUIT_SYMBOLS = {"Hearts": "♥", "Diamonds": "♦", "Clubs": "♣", "Spades": "♠"}
SUIT_COLORS = {"Hearts": RED, "Diamonds": RED, "Clubs": BLACK, "Spades": BLACK}
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

class Card:
    def __init__(self, rank, suit):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        return f"{self.rank}{SUIT_SYMBOLS[self.suit]}"

    def is_eight(self):
        return self.rank == "8"

    def can_play_on(self, top_card, current_suit):
        if self.is_eight():
            return True
        return self.suit == current_suit or self.rank == top_card.rank

class Button:
    def __init__(self, x, y, w, h, text, color=BLUE, text_color=WHITE):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.hover_color = tuple(min(c + 40, 255) for c in color)

    def draw(self, surface):
        color = self.hover_color if self.rect.collidepoint(pygame.mouse.get_pos()) else self.color
        pygame.draw.rect(surface, color, self.rect, border_radius=8)
        pygame.draw.rect(surface, BLACK, self.rect, 2, border_radius=8)
        txt = font.render(self.text, True, self.text_color)
        surface.blit(txt, (self.rect.centerx - txt.get_width()//2, self.rect.centery - txt.get_height()//2))

    def clicked(self, pos):
        return self.rect.collidepoint(pos)

class CrazyEights:
    def __init__(self):
        self.reset()

    def reset(self):
        self.deck = [Card(r, s) for s in SUITS for r in RANKS]
        random.shuffle(self.deck)

        self.player_hand = [self.deck.pop() for _ in range(7)]
        self.computer_hand = [self.deck.pop() for _ in range(7)]

        self.discard = [self.deck.pop()]
        while self.discard[-1].is_eight():
            self.deck.insert(0, self.discard.pop())
            self.discard.append(self.deck.pop())

        self.current_suit = self.discard[-1].suit
        self.player_turn = True
        self.message = "Your turn! Play a card or Draw."
        self.game_over = False
        self.winner = None
        self.choosing_suit = False
        self.pending_eight = None

        # Buttons
        self.draw_btn = Button(50, 620, 140, 50, "Draw")
        self.end_turn_btn = Button(210, 620, 160, 50, "End Turn")
        self.suit_buttons = [
            Button(400, 620, 120, 50, "♥ Hearts", RED),
            Button(530, 620, 140, 50, "♦ Diamonds", RED),
            Button(680, 620, 120, 50, "♣ Clubs", BLACK, WHITE),
            Button(810, 620, 140, 50, "♠ Spades", BLACK, WHITE),
        ]

    def top_card(self):
        return self.discard[-1]

    def valid_cards(self, hand):
        return [c for c in hand if c.can_play_on(self.top_card(), self.current_suit)]

    def draw_card(self, hand):
        if not self.deck:
            # Reshuffle discard (except top) into deck
            if len(self.discard) > 1:
                top = self.discard.pop()
                self.deck = self.discard[:]
                random.shuffle(self.deck)
                self.discard = [top]
        if self.deck:
            hand.append(self.deck.pop())
            return True
        return False

    def play_card(self, hand, card):
        hand.remove(card)
        self.discard.append(card)
        if card.is_eight():
            return True  # Need to choose suit
        else:
            self.current_suit = card.suit
            return False

    def computer_play(self):
        if self.game_over:
            return

        valid = self.valid_cards(self.computer_hand)
        if valid:
            # Prefer non-eights, then highest rank-ish
            non_eights = [c for c in valid if not c.is_eight()]
            if non_eights:
                card = max(non_eights, key=lambda c: RANKS.index(c.rank))
            else:
                card = valid[0]

            needs_suit = self.play_card(self.computer_hand, card)
            if needs_suit:
                # Computer chooses suit it has most of
                suit_count = {s: sum(1 for c in self.computer_hand if c.suit == s) for s in SUITS}
                self.current_suit = max(suit_count, key=suit_count.get)
                self.message = f"Computer played {card} and chose {self.current_suit}"
            else:
                self.message = f"Computer played {card}"

            if not self.computer_hand:
                self.game_over = True
                self.winner = "Computer"
                self.message = "Computer wins!"
                return
        else:
            self.draw_card(self.computer_hand)
            self.message = "Computer draws a card."

        self.player_turn = True
        if not self.game_over:
            self.message = "Your turn!"

    def check_win(self):
        if not self.player_hand:
            self.game_over = True
            self.winner = "You"
            self.message = "You win!"
        elif not self.computer_hand:
            self.game_over = True
            self.winner = "Computer"
            self.message = "Computer wins!"

    def draw_card_visual(self, card, x, y, face_up=True, highlight=False):
        rect = pygame.Rect(x, y, 70, 100)
        if face_up:
            pygame.draw.rect(screen, WHITE, rect, border_radius=6)
            pygame.draw.rect(screen, GOLD if highlight else BLACK, rect, 3, border_radius=6)
            rank_surf = small_font.render(card.rank, True, SUIT_COLORS[card.suit])
            suit_surf = small_font.render(SUIT_SYMBOLS[card.suit], True, SUIT_COLORS[card.suit])
            screen.blit(rank_surf, (x + 5, y + 5))
            screen.blit(suit_surf, (x + 25, y + 40))
            screen.blit(rank_surf, (x + 45, y + 70))
        else:
            pygame.draw.rect(screen, CARD_BACK, rect, border_radius=6)
            pygame.draw.rect(screen, BLACK, rect, 2, border_radius=6)
        return rect

    def draw(self):
        screen.fill((40, 80, 40))  # Table green

        # Title
        title = big_font.render("Crazy Eights", True, WHITE)
        screen.blit(title, (WIDTH//2 - title.get_width()//2, 10))

        # Current suit
        suit_text = font.render(f"Current Suit: {SUIT_SYMBOLS[self.current_suit]} {self.current_suit}", True, SUIT_COLORS[self.current_suit])
        screen.blit(suit_text, (WIDTH//2 - suit_text.get_width()//2, 60))

        # Discard pile
        if self.discard:
            self.draw_card_visual(self.discard[-1], WIDTH//2 - 35, 120)

        # Draw pile
        if self.deck:
            self.draw_card_visual(None, WIDTH//2 - 120, 120, face_up=False)

        # Computer hand (face down)
        cx = 50
        for i, _ in enumerate(self.computer_hand):
            self.draw_card_visual(None, cx + i * 35, 250, face_up=False)

        # Player hand
        px = 50
        valid = self.valid_cards(self.player_hand) if self.player_turn and not self.choosing_suit else []
        for i, card in enumerate(self.player_hand):
            highlight = card in valid
            self.draw_card_visual(card, px + i * 80, 480, face_up=True, highlight=highlight)

        # Message
        msg = font.render(self.message, True, WHITE)
        screen.blit(msg, (WIDTH//2 - msg.get_width()//2, 400))

        # Buttons
        if not self.game_over:
            if self.choosing_suit:
                for btn in self.suit_buttons:
                    btn.draw(screen)
            else:
                self.draw_btn.draw(screen)
                if not self.player_turn:
                    self.end_turn_btn.draw(screen)

        # Restart hint
        if self.game_over:
            restart = font.render("Press R to Restart", True, GOLD)
            screen.blit(restart, (WIDTH//2 - restart.get_width()//2, 650))

        pygame.display.flip()

    def run(self):
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and self.game_over:
                        self.reset()

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = event.pos

                    if self.game_over:
                        continue

                    if self.choosing_suit:
                        for i, btn in enumerate(self.suit_buttons):
                            if btn.clicked(pos):
                                self.current_suit = SUITS[i]
                                self.choosing_suit = False
                                self.pending_eight = None
                                self.message = f"You chose {self.current_suit}"
                                self.check_win()
                                if not self.game_over:
                                    self.player_turn = False
                                    self.computer_play()
                                break
                        continue

                    if self.player_turn:
                        # Click on player cards
                        px = 50
                        for i, card in enumerate(self.player_hand):
                            rect = pygame.Rect(px + i * 80, 480, 70, 100)
                            if rect.collidepoint(pos) and card.can_play_on(self.top_card(), self.current_suit):
                                needs_suit = self.play_card(self.player_hand, card)
                                if needs_suit:
                                    self.choosing_suit = True
                                    self.pending_eight = card
                                    self.message = "Choose a suit!"
                                else:
                                    self.message = f"You played {card}"
                                    self.check_win()
                                    if not self.game_over:
                                        self.player_turn = False
                                        self.computer_play()
                                break

                        # Draw button
                        if self.draw_btn.clicked(pos):
                            if self.draw_card(self.player_hand):
                                self.message = "You drew a card."
                                # Optional: allow playing the drawn card immediately
                                if self.player_hand[-1].can_play_on(self.top_card(), self.current_suit):
                                    self.message += " You can play it!"
                            else:
                                self.message = "No cards left to draw!"

                    # End turn (mainly after drawing)
                    if not self.player_turn and self.end_turn_btn.clicked(pos):
                        self.computer_play()

            self.draw()
            clock.tick(60)

if __name__ == "__main__":
    game = CrazyEights()
    game.run()