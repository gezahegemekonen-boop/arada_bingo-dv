import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def is_valid_tx_id(tx_id: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9]{6,}$", tx_id.strip()))

def referral_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start={user_id}"

def toggle_language(current: str) -> str:
    return "am" if current == "en" else "en"

def format_cartela(board: list, marked: list) -> str:
    output = ""
    for i in range(5):
        row = board[i*5:(i+1)*5]
        formatted = [
            f"[{n}]" if n in marked else f" {n} "
            for n in row
        ]
        output += " ".join(formatted) + "\n"
    return output.strip()

def build_main_keyboard(lang: dict, webapp_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 Play Bingo", web_app={"url": webapp_url})],
        [InlineKeyboardButton("💰 Deposit", callback_data="deposit_menu"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
         InlineKeyboardButton("🎁 Invite Friends", callback_data="invite")],
        [InlineKeyboardButton("🌐 Language: English / አማርኛ", callback_data="toggle_lang")]
    ])
