import pygame
import sys
import json
import os
import random
import math
from pygame._sdl2.video import Window

# Constants
ROWS = 6
COLS = 7
CONFIG_FILE = "connect4_config.json"
ANIM_STEP_TIME = 0.22
AI_MOVE_DELAY = 0.1
DEFAULT_WIDTH = 700
DEFAULT_HEIGHT = 650

# Colors
BLUE = (0, 0, 200)
BLACK = (0, 0, 0)
RED = (220, 50, 50)
YELLOW = (240, 220, 50)
WHITE = (255, 255, 255)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return (data.get("width", DEFAULT_WIDTH),
                        data.get("height", DEFAULT_HEIGHT),
                        data.get("x", 100),
                        data.get("y", 100))
        except Exception:
            pass
    return DEFAULT_WIDTH, DEFAULT_HEIGHT, 100, 100

def save_config(width, height, x, y):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump({"width": width, "height": height, "x": x, "y": y}, f)
    except Exception:
        pass

def create_board():
    return [[0 for _ in range(COLS)] for _ in range(ROWS)]

def get_next_open_row(board, col):
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == 0:
            return r
    return None

def is_valid_location(board, col):
    return board[0][col] == 0

def drop_piece(board, row, col, piece):
    board[row][col] = piece

def winning_move(board, piece):
    for r in range(ROWS):
        for c in range(COLS - 3):
            if all(board[r][c + i] == piece for i in range(4)):
                return True
    for c in range(COLS):
        for r in range(ROWS - 3):
            if all(board[r + i][c] == piece for i in range(4)):
                return True
    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            if all(board[r + i][c + i] == piece for i in range(4)):
                return True
    for r in range(3, ROWS):
        for c in range(COLS - 3):
            if all(board[r - i][c + i] == piece for i in range(4)):
                return True
    return False

def get_valid_locations(board):
    return [c for c in range(COLS) if is_valid_location(board, c)]

def is_terminal(board):
    return (winning_move(board, 1) or
            winning_move(board, 2) or
            len(get_valid_locations(board)) == 0)

def evaluate_window(window, piece):
    score = 0
    opp = 3 - piece
    if window.count(piece) == 4:
        score += 100
    elif window.count(piece) == 3 and window.count(0) == 1:
        score += 10
    elif window.count(piece) == 2 and window.count(0) == 2:
        score += 4
    if window.count(opp) == 3 and window.count(0) == 1:
        score -= 80
    return score

def score_position(board, piece):
    score = 0
    center_col = [board[r][COLS // 2] for r in range(ROWS)]
    score += center_col.count(piece) * 6

    for r in range(ROWS):
        row_array = board[r]
        for c in range(COLS - 3):
            window = row_array[c:c + 4]
            score += evaluate_window(window, piece)

    for c in range(COLS):
        col_array = [board[r][c] for r in range(ROWS)]
        for r in range(ROWS - 3):
            window = col_array[r:r + 4]
            score += evaluate_window(window, piece)

    for r in range(ROWS - 3):
        for c in range(COLS - 3):
            window = [board[r + i][c + i] for i in range(4)]
            score += evaluate_window(window, piece)

    for r in range(3, ROWS):
        for c in range(COLS - 3):
            window = [board[r - i][c + i] for i in range(4)]
            score += evaluate_window(window, piece)

    return score

def get_search_depth(level, board):
    pieces = sum(row.count(1) + row.count(2) for row in board)
    remaining = 42 - pieces
    base = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 9}.get(level, 5)
    # High levels search to the end in the late game (no more dumb endgame mistakes)
    if level >= 7 and remaining <= 16:
        base = max(base, remaining)
    return min(base, remaining)

def minimax(board, depth, alpha, beta, maximizing):
    valid = get_valid_locations(board)
    # Center-first ordering greatly improves strength and speed
    valid.sort(key=lambda c: abs(c - 3))
    terminal = is_terminal(board)
    if depth == 0 or terminal:
        if terminal:
            if winning_move(board, 2):
                return (None, 100000)
            elif winning_move(board, 1):
                return (None, -100000)
            else:
                return (None, 0)
        else:
            return (None, score_position(board, 2))

    if maximizing:
        value = -math.inf
        best_col = valid[0] if valid else 0
        for col in valid:
            row = get_next_open_row(board, col)
            if row is None:
                continue
            temp = [r[:] for r in board]
            drop_piece(temp, row, col, 2)
            new_score = minimax(temp, depth - 1, alpha, beta, False)[1]
            if new_score > value:
                value = new_score
                best_col = col
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return best_col, value
    else:
        value = math.inf
        best_col = valid[0] if valid else 0
        for col in valid:
            row = get_next_open_row(board, col)
            if row is None:
                continue
            temp = [r[:] for r in board]
            drop_piece(temp, row, col, 1)
            new_score = minimax(temp, depth - 1, alpha, beta, True)[1]
            if new_score < value:
                value = new_score
                best_col = col
            beta = min(beta, value)
            if alpha >= beta:
                break
        return best_col, value

def ai_move(board, piece, level):
    valid = get_valid_locations(board)
    if not valid:
        return None
    opp = 3 - piece

    # Always take immediate win
    for col in valid:
        temp = [r[:] for r in board]
        row = get_next_open_row(temp, col)
        if row is not None:
            drop_piece(temp, row, col, piece)
            if winning_move(temp, piece):
                return col

    # Always block immediate threat
    for col in valid:
        temp = [r[:] for r in board]
        row = get_next_open_row(temp, col)
        if row is not None:
            drop_piece(temp, row, col, opp)
            if winning_move(temp, opp):
                return col

    # Minimax
    depth = get_search_depth(level, board)
    maximizing = (piece == 2)
    col, _ = minimax(board, depth, -math.inf, math.inf, maximizing)

    # Occasional blunders below level 9
    if level < 9 and random.random() < (9 - level) * 0.08:
        return random.choice(valid)

    return col if col in valid else random.choice(valid)

def draw_board(screen, board, width, height, anim=None):
    screen.fill(BLUE)
    margin = 20
    usable_w = max(width - 2 * margin, COLS * 20)
    usable_h = max(height - 2 * margin - 70, ROWS * 20)
    cell_size = min(usable_w // COLS, usable_h // ROWS)
    board_width = cell_size * COLS
    board_height = cell_size * ROWS
    offset_x = (width - board_width) // 2
    offset_y = (height - board_height) // 2 + 10

    for r in range(ROWS):
        for c in range(COLS):
            x = offset_x + c * cell_size + cell_size // 2
            y = offset_y + r * cell_size + cell_size // 2
            pygame.draw.circle(screen, BLACK, (x, y), cell_size // 2 - 4)
            piece = board[r][c]
            if piece == 1:
                pygame.draw.circle(screen, RED, (x, y), cell_size // 2 - 8)
            elif piece == 2:
                pygame.draw.circle(screen, YELLOW, (x, y), cell_size // 2 - 8)

    if anim:
        col, vis_row, piece = anim
        if 0 <= vis_row < ROWS:
            x = offset_x + col * cell_size + cell_size // 2
            y = offset_y + vis_row * cell_size + cell_size // 2
            color = RED if piece == 1 else YELLOW
            pygame.draw.circle(screen, color, (x, int(y)), cell_size // 2 - 8)

    return cell_size, offset_x, offset_y

def main():
    width, height, win_x, win_y = load_config()
    os.environ["SDL_VIDEO_WINDOW_POS"] = f"{win_x},{win_y}"

    pygame.init()
    screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
    pygame.display.set_caption("Connect 4")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 28, bold=True)

    window = Window.from_display_module()

    board = create_board()
    game_over = False
    turn = 1
    mode = None
    selecting_level = False
    ai_level = 5
    anim = None
    last_anim_time = 0
    target_row = None
    pending_ai = False
    ai_start_time = 0
    winner = None

    running = True
    while running:
        current_time = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pos = window.position
                size = window.size
                save_config(size[0], size[1], pos[0], pos[1])
                running = False
            elif event.type == pygame.VIDEORESIZE:
                width, height = event.size
                screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if selecting_level:
                        selecting_level = False
                    else:
                        pos = window.position
                        size = window.size
                        save_config(size[0], size[1], pos[0], pos[1])
                        running = False
                elif event.key == pygame.K_r and game_over:
                    board = create_board()
                    game_over = False
                    turn = 1
                    winner = None
                    anim = None
                    pending_ai = False
                    if mode == 3:
                        pending_ai = True
                        ai_start_time = current_time
                elif mode is None and not selecting_level:
                    if event.key == pygame.K_1:
                        mode = 1
                    elif event.key == pygame.K_2:
                        selecting_level = True
                    elif event.key == pygame.K_3:
                        mode = 3
                        pending_ai = True
                        ai_start_time = current_time
                elif selecting_level and pygame.K_1 <= event.key <= pygame.K_9:
                    ai_level = event.key - pygame.K_0
                    mode = 2
                    selecting_level = False
            elif (event.type == pygame.MOUSEBUTTONDOWN and not game_over
                  and anim is None and mode is not None and not selecting_level):
                if mode == 3 or (mode == 2 and turn == 2):
                    continue
                mouse_x = event.pos[0]
                margin = 20
                usable_w = max(width - 2 * margin, COLS * 20)
                usable_h = max(height - 2 * margin - 70, ROWS * 20)
                cell_size = min(usable_w // COLS, usable_h // ROWS)
                board_width = cell_size * COLS
                offset_x = (width - board_width) // 2
                if offset_x <= mouse_x < offset_x + board_width:
                    col = (mouse_x - offset_x) // cell_size
                    if 0 <= col < COLS and is_valid_location(board, col):
                        target_row = get_next_open_row(board, col)
                        if target_row is not None:
                            anim = [col, 0.0, turn]
                            last_anim_time = current_time

        # Animation
        if anim is not None:
            col, vis_row, piece = anim
            if current_time - last_anim_time >= ANIM_STEP_TIME:
                last_anim_time = current_time
                next_vis = vis_row + 1
                if next_vis > target_row:
                    drop_piece(board, target_row, col, piece)
                    anim = None
                    if winning_move(board, piece):
                        game_over = True
                        winner = piece
                    elif not get_valid_locations(board):
                        game_over = True
                        winner = 0
                    else:
                        turn = 3 - turn
                        if not game_over:
                            if mode == 2 and turn == 2:
                                pending_ai = True
                                ai_start_time = current_time
                            elif mode == 3:
                                pending_ai = True
                                ai_start_time = current_time
                else:
                    anim[1] = next_vis

        # AI
        if pending_ai and anim is None and not game_over:
            if current_time - ai_start_time >= AI_MOVE_DELAY:
                pending_ai = False
                piece = turn
                level = ai_level if mode == 2 else 9
                col = ai_move(board, piece, level)
                if col is not None and is_valid_location(board, col):
                    target_row = get_next_open_row(board, col)
                    if target_row is not None:
                        anim = [col, 0.0, piece]
                        last_anim_time = current_time

        # Draw
        draw_board(screen, board, width, height, anim)

        # UI
        if mode is None:
            if selecting_level:
                text = font.render("Select AI skill 1-9  (9 = perfect)", True, WHITE)
            else:
                text = font.render("1: Two Players    2: vs Computer    3: AI vs AI (perfect)", True, WHITE)
            screen.blit(text, (width // 2 - text.get_width() // 2, 15))
        else:
            if game_over:
                if winner == 0:
                    msg = "Draw! Press R to restart"
                else:
                    p = "Red" if winner == 1 else "Yellow"
                    msg = f"{p} wins! Press R to restart"
                text = font.render(msg, True, WHITE)
            else:
                p = "Red" if turn == 1 else "Yellow"
                if mode == 1:
                    mode_str = "2 Players"
                elif mode == 2:
                    mode_str = f"vs AI (lvl {ai_level})"
                else:
                    mode_str = "AI vs AI (perfect)"
                msg = f"{mode_str} - {p}'s turn"
                text = font.render(msg, True, WHITE)
            screen.blit(text, (width // 2 - text.get_width() // 2, height - 45))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()