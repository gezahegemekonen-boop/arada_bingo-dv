import random
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class BingoGame:
    def __init__(self, game_id: int, entry_price: int = 10):
        self.game_id = game_id
        self.entry_price = entry_price
        self.pool = 0
        self.players: Dict[int, List[dict]] = {}  # user_id -> list of boards
        selfcalled_numbers: List[int] = []
        self.status = "waiting"
        self.winner_id = None
        self.created_at = datetime.utcnow()
        self.finished_at = None
        self.min_players = 1
        self.max_players = 100
        self.last_call_time = None
        self.auto_call_timer = None
        self.call_interval = 3.5  # seconds
        self.leaderboard: Dict[int, Dict[str, int]] = {}  # user_id -> {"wins": x, "earnings": y}

    def generate_board(self, cartela_number: int) -> List[int]:
        random.seed(cartela_number)
        b = random.sample(range(1, 16), 5)
        i = random.sample(range(16, 31), 5)
        n = random.sample(range(31, 46), 5)
        g = random.sample(range(46, 61), 5)
        o = random.sample(range(61, 76), 5)
        random.seed()

        board = []
        for row in range(5):
            board.extend([b[row], i[row], n[row], g[row], o[row]])
        return board

    def add_player(self, user_id: int, cartela_number: Optional[int] = None) -> List[int]:
        if user_id not in self.players:
            self.players[user_id] = []

        if len(self.players[user_id]) >= 5:
            return []  # Max 5 boards per player

        used_cartelas = {b['cartela_number'] for boards in self.players.values() for b in boards}
        available = [n for n in range(1, 101) if n not in used_cartelas]
        cartela_number = cartela_number or (random.choice(available) if available else 0)

        board = self.generate_board(cartela_number)
        self.players[user_id].append({
            'board': board,
            'marked': [board[12]],  # Center is free
            'cartela_number': cartela_number
        })
        self.pool += self.entry_price

        if self.status == "waiting" and self.total_players() >= self.min_players:
            self.start_game()

        return board

    def total_players(self) -> int:
        return sum(len(boards) for boards in self.players.values())

    def start_game(self) -> bool:
        self.status = "active"
        self.call_number()
        self.schedule_next_call()
        return True

    def schedule_next_call(self):
        if self.status != "active":
            return
        self.auto_call_timer = threading.Timer(self.call_interval, self.auto_call)
        self.auto_call_timer.start()

    def auto_call(self):
        if self.status != "active":
            return
        self.call_number()
        self.schedule_next_call()

    def call_number(self) -> Optional[str]:
        available = [n for n in range(1, 76) if n not in self.called_numbers]
        if not available:
            self.status = "finished"
            self.finished_at = datetime.utcnow()
            return None

        number = random.choice(available)
        self.called_numbers.append(number)
        self.last_call_time = datetime.utcnow()
        return self.format_number(number)

    @staticmethod
    def format_number(number: int) -> str:
        if 1 <= number <= 15:
            return f"B-{number}"
        elif 16 <= number <= 30:
            return f"I-{number}"
        elif 31 <= number <= 45:
            return f"N-{number}"
        elif 46 <= number <= 60:
            return f"G-{number}"
        else:
            return f"O-{number}"

    @staticmethod
    def audio_filename(number: int) -> str:
        return f"{BingoGame.format_number(number)}.mp3"

    def mark_number(self, user_id: int, number: int) -> bool:
        if user_id not in self.players:
            return False
        updated = False
        for board in self.players[user_id]:
            if number in board['board'] and number in self.called_numbers:
                if number not in board['marked']:
                    board['marked'].append(number)
                    board['marked'].sort()
                    updated = True
        return updated

    def check_winner(self, user_id: int) -> Tuple[bool, str]:
        if user_id not in self.players:
            return False, "Player not in game"

        for board in self.players[user_id]:
            marked = set(board['marked'])
            b = board['board']

            # Validate marked numbers
            for num in marked:
                if num not in b and num != b[12]:
                    continue
                if num not in self.called_numbers and num != b[12]:
                    continue

            # Check rows
            for i in range(0, 25, 5):
                if all(b[i + j] in marked for j in range(5)):
                    return True, "Winner - Row complete!"

            # Check columns
            for i in range(5):
                if all(b[i + j*5] in marked for j in range(5)):
                    return True, "Winner - Column complete!"

            # Check diagonals
            if all(b[i] in marked for i in [0, 6, 12, 18, 24]):
                return True, "Winner - Diagonal complete!"
            if all(b[i] in marked for i in [4, 8, 12, 16, 20]):
                return True, "Winner - Diagonal complete!"

        return False, "Keep playing"

    def end_game(self, winner_id: int):
        self.winner_id = winner_id
        self.status = "finished"
        self.finished_at = datetime.utcnow()
        if self.auto_call_timer:
            self.auto_call_timer.cancel()

        # Payout logic
        if winner_id not in self.leaderboard:
            self.leaderboard[winner_id] = {"wins": 0, "earnings": 0}
        self.leaderboard[winner_id]["wins"] += 1
        self.leaderboard[winner_id]["earnings"] += self.pool

    def get_leaderboard(self, top_n: int = 10) -> List[Tuple[int, int, int]]:
        sorted_lb = sorted(
            self.leaderboard.items(),
            key=lambda item: (item[1]["earnings"], item[1]["wins"]),
            reverse=True
        )
        return [(uid, data["wins"], data["earnings"]) for uid, data in sorted_lb[:top_n]]
