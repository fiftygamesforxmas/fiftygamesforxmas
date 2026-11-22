import pygame
import chess
import random
import sys
import os
import urllib.request
import time

pygame.init()
pygame.display.set_caption("Resizable Chess")

LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
HIGHLIGHT = (186, 202, 68, 180)
SELECT = (246, 246, 105)
LINE_COLOR = (255, 50, 50)
TEXT_COLOR = (220, 220, 220)
BG = (40, 40, 40)
PANEL_BG = (50, 50, 50)

PIECE_URLS = {
    'wK': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wK.png',
    'wQ': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wQ.png',
    'wR': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wR.png',
    'wB': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wB.png',
    'wN': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wN.png',
    'wP': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/wP.png',
    'bK': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bK.png',
    'bQ': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bQ.png',
    'bR': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bR.png',
    'bB': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bB.png',
    'bN': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bN.png',
    'bP': 'https://cdn.jsdelivr.net/npm/chessboard-element@1.2.0/chesspieces/wikipedia/bP.png',
}

UNICODE_PIECES = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}

LEVEL_NAMES = [
    "0 - Stooge",
    "1 - Beginner",
    "2 - Novice",
    "3 - Intermediate",
    "4 - Club Player",
    "5 - Advanced",
    "6 - Expert",
    "7 - Master",
    "8 - Grandmaster",
    "9 - Best"
]

class ChessGame:
    def __init__(self):
        self.screen = pygame.display.set_mode((1100, 900), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 28)
        self.small_font = pygame.font.SysFont("arial", 20)
        self.piece_font = pygame.font.SysFont("dejavusans", 60)

        self.board = chess.Board()
        self.move_history = []          # list of SAN strings
        self.fen_history = [self.board.fen()]
        self.selected = None
        self.valid_moves = []
        self.vs_computer = True
        self.computer_level = 5
        self.computer_color = chess.BLACK
        self.saves = [None] * 9
        self.awaiting_slot = None
        self.status = ""
        self.last_move_text = ""
        self.advice_text = ""
        self.running = True

        # Move list panel
        self.panel_scroll = 0
        self.panel_width = 280
        self.last_click_time = 0
        self.last_click_index = -1

        # Anticipation mode (F8)
        self.anticipate_mode = False
        self.anticipate_moves = []
        self.anticipate_index = 0
        self.anticipate_start = 0
        self.anticipate_duration = 3.0

        self.piece_images = {}
        self.load_piece_images()
        self.update_layout()

        self.select_level()

    def select_level(self):
        selecting = True
        while selecting:
            self.screen.fill(BG)
            title = self.font.render("Select Computer Level", True, (255, 255, 255))
            self.screen.blit(title, (self.screen.get_width()//2 - title.get_width()//2, 80))

            for i, name in enumerate(LEVEL_NAMES):
                color = (255, 220, 100) if i == self.computer_level else (200, 200, 200)
                txt = self.small_font.render(name, True, color)
                y = 160 + i * 40
                self.screen.blit(txt, (self.screen.get_width()//2 - txt.get_width()//2, y))

            hint = self.small_font.render("Press 0-9 to select, then Enter to start", True, (180, 180, 180))
            self.screen.blit(hint, (self.screen.get_width()//2 - hint.get_width()//2, 600))

            pygame.display.flip()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN:
                    if pygame.K_0 <= event.key <= pygame.K_9:
                        self.computer_level = event.key - pygame.K_0
                    elif event.key == pygame.K_RETURN:
                        selecting = False
                    elif event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()

        self.update_status()

    def load_piece_images(self):
        pieces_dir = "pieces"
        os.makedirs(pieces_dir, exist_ok=True)
        for key, url in PIECE_URLS.items():
            path = os.path.join(pieces_dir, f"{key}.png")
            if not os.path.exists(path):
                try:
                    urllib.request.urlretrieve(url, path)
                except Exception:
                    pass
            if os.path.exists(path):
                try:
                    self.piece_images[key] = pygame.image.load(path).convert_alpha()
                except Exception:
                    pass

    def update_layout(self):
        w, h = self.screen.get_size()
        self.board_size = min(w - self.panel_width - 40, h - 160)
        self.sq_size = self.board_size // 8
        self.board_x = 20
        self.board_y = 20
        self.panel_x = self.board_x + self.board_size + 20
        self.panel_y = 20
        self.panel_height = h - 40

        self.scaled_pieces = {}
        for key, img in self.piece_images.items():
            self.scaled_pieces[key] = pygame.transform.smoothscale(img, (self.sq_size - 8, self.sq_size - 8))

    def square_at(self, pos):
        x, y = pos
        if not (self.board_x <= x < self.board_x + self.board_size and
                self.board_y <= y < self.board_y + self.board_size):
            return None
        col = (x - self.board_x) // self.sq_size
        row = 7 - (y - self.board_y) // self.sq_size
        return chess.square(col, row)

    def draw_board(self):
        for r in range(8):
            for c in range(8):
                color = LIGHT if (r + c) % 2 == 0 else DARK
                rect = pygame.Rect(
                    self.board_x + c * self.sq_size,
                    self.board_y + r * self.sq_size,
                    self.sq_size, self.sq_size
                )
                pygame.draw.rect(self.screen, color, rect)

        if self.selected is not None:
            self.draw_highlight(self.selected, SELECT)
            for mv in self.valid_moves:
                self.draw_highlight(mv.to_square, HIGHLIGHT)

        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece:
                self.draw_piece(sq, piece)

        # Anticipation lines
        if self.anticipate_mode and self.anticipate_moves:
            now = time.time()
            elapsed = now - self.anticipate_start
            current_idx = int(elapsed // self.anticipate_duration)
            if current_idx < len(self.anticipate_moves):
                mv = self.anticipate_moves[current_idx]
                self.draw_move_line(mv)
            elif elapsed > len(self.anticipate_moves) * self.anticipate_duration:
                self.anticipate_mode = False

    def draw_move_line(self, move):
        start = self.square_center(move.from_square)
        end = self.square_center(move.to_square)
        pygame.draw.line(self.screen, LINE_COLOR, start, end, 6)
        # Arrow head
        pygame.draw.circle(self.screen, LINE_COLOR, end, 10)

    def square_center(self, sq):
        col = chess.square_file(sq)
        row = 7 - chess.square_rank(sq)
        x = self.board_x + col * self.sq_size + self.sq_size // 2
        y = self.board_y + row * self.sq_size + self.sq_size // 2
        return (x, y)

    def draw_highlight(self, sq, color):
        col = chess.square_file(sq)
        row = 7 - chess.square_rank(sq)
        rect = pygame.Rect(
            self.board_x + col * self.sq_size,
            self.board_y + row * self.sq_size,
            self.sq_size, self.sq_size
        )
        s = pygame.Surface((self.sq_size, self.sq_size), pygame.SRCALPHA)
        s.fill(color)
        self.screen.blit(s, rect.topleft)

    def draw_piece(self, sq, piece):
        col = chess.square_file(sq)
        row = 7 - chess.square_rank(sq)
        key = ('w' if piece.color == chess.WHITE else 'b') + piece.symbol().upper()
        x = self.board_x + col * self.sq_size + 4
        y = self.board_y + row * self.sq_size + 4
        if key in self.scaled_pieces:
            self.screen.blit(self.scaled_pieces[key], (x, y))
        else:
            symbol = UNICODE_PIECES.get(piece.symbol(), '?')
            color = (255, 255, 255) if piece.color == chess.WHITE else (30, 30, 30)
            surf = self.piece_font.render(symbol, True, color)
            self.screen.blit(surf, (x, y))

    def draw_move_panel(self):
        panel_rect = pygame.Rect(self.panel_x, self.panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(self.screen, PANEL_BG, panel_rect)
        pygame.draw.rect(self.screen, (100, 100, 100), panel_rect, 2)

        title = self.small_font.render("Move History (double-click to revert)", True, (255, 255, 100))
        self.screen.blit(title, (self.panel_x + 10, self.panel_y + 10))

        y = self.panel_y + 50 - self.panel_scroll
        line_height = 28
        for i, san in enumerate(self.move_history):
            if y > self.panel_y + self.panel_height - 20:
                break
            if y > self.panel_y + 40:
                color = (255, 255, 255) if i % 2 == 0 else (200, 200, 200)
                text = self.small_font.render(f"{i+1}. {san}", True, color)
                self.screen.blit(text, (self.panel_x + 15, y))
            y += line_height

    def draw_status(self):
        y = self.board_y + self.board_size + 15
        lines = [
            self.status,
            self.last_move_text,
            self.advice_text,
            "F1: Mode | F2/F3: Level | F4/F5: Save/Load | F7: Advice | F8: Anticipate | R: New | ESC: Quit"
        ]
        for i, txt in enumerate(lines):
            surf = self.small_font.render(txt, True, TEXT_COLOR)
            self.screen.blit(surf, (20, y + i * 24))

    def draw(self):
        self.screen.fill(BG)
        self.draw_board()
        self.draw_move_panel()
        self.draw_status()
        pygame.display.flip()

    def make_move(self, move):
        san = self.board.san(move)
        self.board.push(move)
        self.move_history.append(san)
        self.fen_history.append(self.board.fen())
        self.last_move_text = f"Last: {san}"
        self.advice_text = ""
        self.selected = None
        self.valid_moves = []
        self.update_status()
        if self.vs_computer and self.board.turn == self.computer_color and not self.board.is_game_over():
            pygame.time.wait(300)
            self.computer_move()

    def computer_move(self):
        move = self.get_best_move(self.computer_level)
        if move:
            san = self.board.san(move)
            self.board.push(move)
            self.move_history.append(san)
            self.fen_history.append(self.board.fen())
            self.last_move_text = f"Computer: {san}"
            print(f"Computer plays: {san}")
            self.update_status()

    def get_best_move(self, level):
        legal = list(self.board.legal_moves)
        if not legal:
            return None
        if level == 0:
            return random.choice(legal)
        depth = max(1, level // 2 + 1)
        best_move = None
        best_score = -float('inf')
        for move in legal:
            self.board.push(move)
            score = -self.minimax(depth - 1, -float('inf'), float('inf'))
            self.board.pop()
            if score > best_score:
                best_score = score
                best_move = move
        return best_move or random.choice(legal)

    def minimax(self, depth, alpha, beta):
        if depth == 0 or self.board.is_game_over():
            return self.evaluate()
        max_eval = -float('inf')
        for move in self.board.legal_moves:
            self.board.push(move)
            eval_ = -self.minimax(depth - 1, -beta, -alpha)
            self.board.pop()
            max_eval = max(max_eval, eval_)
            alpha = max(alpha, eval_)
            if beta <= alpha:
                break
        return max_eval

    def evaluate(self):
        if self.board.is_checkmate():
            return -100000 if self.board.turn == chess.WHITE else 100000
        if self.board.is_stalemate() or self.board.is_insufficient_material():
            return 0
        values = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
                  chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 20000}
        score = 0
        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece:
                val = values[piece.piece_type]
                score += val if piece.color == chess.WHITE else -val
        return score if self.board.turn == chess.WHITE else -score

    def update_status(self):
        turn = "White" if self.board.turn == chess.WHITE else "Black"
        mode = "Vs Computer" if self.vs_computer else "Vs Human"
        lvl = LEVEL_NAMES[self.computer_level]
        self.status = f"{turn} to move | {mode} | {lvl}"
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self.status = f"Checkmate! {winner} wins"
        elif self.board.is_stalemate():
            self.status = "Stalemate"

    def give_advice(self):
        if self.board.is_game_over():
            self.advice_text = "Game over"
            return
        move = self.get_best_move(max(4, self.computer_level))
        if move:
            self.advice_text = f"Advice: {self.board.san(move)}"

    def start_anticipation(self):
        if self.board.is_game_over() or not self.vs_computer:
            return
        self.anticipate_moves = []
        temp_board = self.board.copy()
        for _ in range(2):
            if temp_board.is_game_over():
                break
            move = self.get_best_move_for_board(temp_board, self.computer_level)
            if not move:
                break
            self.anticipate_moves.append(move)
            temp_board.push(move)
        if self.anticipate_moves:
            self.anticipate_mode = True
            self.anticipate_start = time.time()
            self.last_move_text = "Anticipating next moves..."

    def get_best_move_for_board(self, board, level):
        # Temporary helper that works on a copy
        original = self.board
        self.board = board
        move = self.get_best_move(level)
        self.board = original
        return move

    def revert_to(self, index):
        """Revert to the position after `index` moves (0-based)."""
        if 0 <= index < len(self.fen_history):
            self.board = chess.Board(self.fen_history[index])
            self.move_history = self.move_history[:index]
            self.fen_history = self.fen_history[:index + 1]
            self.selected = None
            self.valid_moves = []
            self.anticipate_mode = False
            self.update_status()
            self.last_move_text = f"Reverted to move {index}"

    def run(self):
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.update_layout()
                elif event.type == pygame.MOUSEWHEEL:
                    # Scroll the move list
                    self.panel_scroll = max(0, self.panel_scroll - event.y * 30)
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.handle_click(event.pos)

            self.draw()
            self.clock.tick(60)
        pygame.quit()

    def handle_key(self, key):
        if self.awaiting_slot:
            if pygame.K_1 <= key <= pygame.K_9:
                slot = key - pygame.K_1
                if self.awaiting_slot == 'save':
                    self.saves[slot] = self.board.fen()
                    self.last_move_text = f"Saved to slot {slot + 1}"
                elif self.awaiting_slot == 'load' and self.saves[slot]:
                    self.board = chess.Board(self.saves[slot])
                    self.move_history = []
                    self.fen_history = [self.board.fen()]
                    self.last_move_text = f"Loaded slot {slot + 1}"
                    self.update_status()
                self.awaiting_slot = None
            elif key == pygame.K_ESCAPE:
                self.awaiting_slot = None
            return

        if key == pygame.K_F1:
            self.vs_computer = not self.vs_computer
            self.update_status()
        elif key == pygame.K_F2 and self.computer_level > 0:
            self.computer_level -= 1
            self.update_status()
        elif key == pygame.K_F3 and self.computer_level < 9:
            self.computer_level += 1
            self.update_status()
        elif key == pygame.K_F4:
            self.awaiting_slot = 'save'
            self.last_move_text = "Save: press 1-9"
        elif key == pygame.K_F5:
            self.awaiting_slot = 'load'
            self.last_move_text = "Load: press 1-9"
        elif key == pygame.K_F7:
            self.give_advice()
        elif key == pygame.K_F8:
            if self.anticipate_mode:
                self.anticipate_mode = False
                self.last_move_text = "Anticipation off"
            else:
                self.start_anticipation()
        elif key == pygame.K_r:
            self.board = chess.Board()
            self.move_history = []
            self.fen_history = [self.board.fen()]
            self.update_status()
            self.last_move_text = "New game"
            self.advice_text = ""
            self.anticipate_mode = False
        elif key == pygame.K_ESCAPE:
            self.running = False

    def handle_click(self, pos):
        # Check if click is on the move list
        if (self.panel_x <= pos[0] <= self.panel_x + self.panel_width and
            self.panel_y + 40 <= pos[1] <= self.panel_y + self.panel_height):
            relative_y = pos[1] - (self.panel_y + 50 - self.panel_scroll)
            index = relative_y // 28
            if 0 <= index < len(self.move_history):
                now = time.time()
                if index == self.last_click_index and (now - self.last_click_time) < 0.4:
                    # Double-click
                    self.revert_to(index)
                self.last_click_index = index
                self.last_click_time = now
            return

        # Board click
        if self.board.is_game_over() or self.awaiting_slot:
            return
        sq = self.square_at(pos)
        if sq is None:
            self.selected = None
            self.valid_moves = []
            return

        if self.selected is None:
            piece = self.board.piece_at(sq)
            if piece and piece.color == self.board.turn:
                if self.vs_computer and self.board.turn == self.computer_color:
                    return
                self.selected = sq
                self.valid_moves = [mv for mv in self.board.legal_moves if mv.from_square == sq]
        else:
            move = None
            for m in self.valid_moves:
                if m.to_square == sq:
                    move = m
                    break
            if move:
                self.make_move(move)
            else:
                piece = self.board.piece_at(sq)
                if piece and piece.color == self.board.turn:
                    self.selected = sq
                    self.valid_moves = [mv for mv in self.board.legal_moves if mv.from_square == sq]
                else:
                    self.selected = None
                    self.valid_moves = []

if __name__ == "__main__":
    game = ChessGame()
    game.run()