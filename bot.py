import os
import logging
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from database import db, init_db
from models import User, Transaction, Game, GameParticipant
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from utils.format_cartela import format_cartela
from utils.build_main_keyboard import build_main_keyboard
import requests

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://arada-bingo-dv-oxct.onrender.com")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

LANGUAGE_MAP = {
    "en": {
        "welcome": "Welcome to Arada Bingo Ethiopia!",
        "deposit": "💰 Deposit Instructions:\nSend payment to 09XXXXXXXX and reply with the transaction ID.",
        "withdraw": "💸 Withdrawal Request:\nEnter the amount you want to withdraw.",
        "stats": "📊 Your Stats:\nBalance: {balance} birr\nGames Played: {played}\nGames Won: {won}\nReferral Link: {link}",
        "invite": "🎁 Invite your friends!\nShare this link:\n{link}\nYou’ll earn 5 birr when they play their first game.",
        "language_set": "✅ Language set to English.",
    },
    "am": {
        "welcome": "እንኳን ደህና መጡ ወደ Arada Bingo Ethiopia!",
        "deposit": "💰 የተቀበሉትን ክፍያ ወደ 09XXXXXXXX ያስተላልፉ እና የግብይት መለያውን ያስገቡ።",
        "withdraw": "💸 የመነሻ ጥያቄ፡ የሚወስዱትን መጠን ያስገቡ።",
        "stats": "📊 የእርስዎ ሁኔታ፡ ቀሪ ባለቤት: {balance} ብር\nተጫዋች ጨዋታዎች: {played}\nየተሸነፉት: {won}\nየማስተላለፊያ አገናኝ: {link}",
        "invite": "🎁 ጓደኞችዎን ይጋብዙ!\nይህን አገናኝ ያጋሩ:\n{link}\nከመጀመሪያ ጨዋታ በኋላ 5 ብር ያገኛሉ።",
        "language_set": "✅ ቋንቋ ወደ አማርኛ ተቀይሯል።",
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("✅ /start command received")
    await update.message.reply_text("👋 Hello Mekonen! Your bot is alive and responding.")

# Optional: Keep your full Bingo logic here (start with user creation, referral, etc.)
# You can reintroduce it once the minimal bot is confirmed working.

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Use /start to begin. Tap buttons to deposit, withdraw, play, or invite friends.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"📩 Received message: {update.message.text}")
    await update.message.reply_text("✅ Bot received your message.")

def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT, echo))

    logging.info("✅ Arada Bingo Ethiopia bot is running via webhook...")

    telegram_app.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=f"{WEBAPP_URL}/webhook"
    )

if __name__ == "__main__":
    main()
