# bot.py (Part 1)
import os
import logging
from datetime import datetime
from flask import Flask
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

# 🔧 Logging setup
logging.basicConfig(level=logging.INFO)

# 🔐 Environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://127.0.0.1:5000")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing in environment")

# 🌐 Flask app for DB context
flask_app = Flask(__name__)
flask_app.secret_key = os.getenv("FLASK_SECRET", "bot_secret")

try:
    init_db(flask_app)
    print("✅ Database initialized successfully")
except RuntimeError as e:
    print(f"⚠️ Database setup error: {e}")
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)

# 🤖 Telegram bot app
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# 🌍 Language map
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

# -------------------- COMMAND HANDLERS --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    logging.info("✅ /start command received")
    args = context.args
    referral_id = None
    if args:
        try:
            referral_id = int(args[0])
        except ValueError:
            pass

    telegram_id = update.effective_user.id
    username = update.effective_user.username

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=str(telegram_id)).first()

        if not user:
            user = User(
                telegram_id=str(telegram_id),
                username=username,
                balance=0,
                referrer_id=referral_id,
                language="en"
            )
            db.session.add(user)
            db.session.commit()

        if referral_id and referral_id != user.id:
            referrer = User.query.get(referral_id)
            if referrer:
                referrer.balance += 5
                db.session.add(Transaction(
                    user_id=referrer.id,
                    type="referral_bonus",
                    amount=5,
                    status="approved"
                ))
                db.session.commit()

        user_language = user.language

    context.chat_data.setdefault("auto_mode", True)
    context.chat_data.setdefault("sound_enabled", True)
    context.chat_data["language"] = user_language

    lang = LANGUAGE_MAP.get(user_language, LANGUAGE_MAP["en"])
    keyboard = build_main_keyboard(lang, WEBAPP_URL)

    await update.message.reply_text(
        lang["welcome"],
        reply_markup=keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "ℹ️ Use /start to begin. Tap buttons to deposit, withdraw, play, or invite friends."
        )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        logging.info(f"📩 Received message: {update.message.text}")
        await update.message.reply_text("✅ Bot received your message.")

# -------------------- DEPOSIT FLOW --------------------

async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        keyboard = [
            [InlineKeyboardButton("📲 CBE Birr", callback_data="deposit_cbe_birr")],
            [InlineKeyboardButton("📲 Telebirr", callback_data="deposit_telebirr")],
            [InlineKeyboardButton("🏦 CBE Bank", callback_data="deposit_cbe_bank")]
        ]
        await update.callback_query.edit_message_text(
            "💰 Choose your deposit method:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def deposit_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.callback_query.data:
        await update.callback_query.answer()
        method = update.callback_query.data.split("_")[1]
        context.chat_data["deposit_method"] = method

        msg = {
            "cbe_birr": "📲 CBE Birr Deposit:\nSend to 0920927761 and reply with your transaction ID.",
            "telebirr": "📲 Telebirr Deposit:\nSend to 0920927761 and reply with your transaction ID.",
            "cbe_bank": "🏦 CBE Bank Deposit:\nAccount Number: 1000316113347\nThen reply with your transaction ID."
        }.get(method, "❌ Unknown method.")

        await update.callback_query.edit_message_text(msg)

# -------------------- WITHDRAW & STATS --------------------

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        lang = LANGUAGE_MAP.get(
            context.chat_data.get("language", "en") if context.chat_data else "en",
            LANGUAGE_MAP["en"]
        )
        await update.callback_query.edit_message_text(lang["withdraw"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.effective_user:
        await update.callback_query.answer()
        telegram_id = str(update.effective_user.id)

        with flask_app.app_context():
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                await update.callback_query.edit_message_text("❌ No stats found.")
                return

            lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
            link = referral_link(context.bot.username or "AradaBingoBot", user.id)
text = lang["stats"].format(
    balance=user.balance,
    played=user.games_played,
    won=user.games_won,
    link=link
)
await update.callback_query.edit_message_text(text)

# -------------------- INVITE & GAME LAUNCH --------------------

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.effective_user:
        await update.callback_query.answer()
        telegram_id = str(update.effective_user.id)

        with flask_app.app_context():
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                return

            lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
            link = referral_link(context.bot.username or "AradaBingoBot", user.id)
            await update.callback_query.edit_message_text(lang["invite"].format(link=link))

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🎮 Launching Arada Bingo Ethiopia...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}"))]
            ])
        )

# -------------------- TOGGLE SETTINGS --------------------

async def toggle_auto_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        context.chat_data.setdefault("auto_mode", True)
        context.chat_data["auto_mode"] = not context.chat_data["auto_mode"]
        status = "ON" if context.chat_data["auto_mode"] else "OFF"
        await update.message.reply_text(f"🔁 Auto Mode: {status}")

async def toggle_sound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        context.chat_data.setdefault("sound_enabled", True)
        context.chat_data["sound_enabled"] = not context.chat_data["sound_enabled"]
        status = "ON" if context.chat_data["sound_enabled"] else "OFF"
        await update.message.reply_text(f"🔊 Sound: {status}")

# -------------------- USER INPUT HANDLER --------------------

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)
    text = update.message.text.strip() if update.message.text else ""

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must start the bot first using /start.")
            return

        # Deposit flow
        if context.chat_data and "deposit_method" in context.chat_data:
            method = context.chat_data["deposit_method"]
            if not is_valid_tx_id(text):
                await update.message.reply_text("❌ Invalid transaction ID. Please try again.")
                return

            tx = Transaction(
                user_id=user.id,
                type="deposit",
                amount=0,
                method=method,
                status="pending",
                reference=text
            )
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text("✅ Transaction received. Awaiting admin approval.")
            return

        # Withdrawal flow
        try:
            amount = int(text)
            if amount <= 0 or amount > user.balance:
                await update.message.reply_text("❌ Invalid amount or insufficient balance.")
                return

            tx = Transaction(
                user_id=user.id,
                type="withdraw",
                amount=amount,
                status="pending"
            )
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text(f"✅ Withdrawal request for {amount} birr submitted.")
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")

# -------------------- ERROR HANDLER --------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

# -------------------- BOT ENTRY POINT --------------------

def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("auto", toggle_auto_mode))
    telegram_app.add_handler(CommandHandler("sound", toggle_sound))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("stats", stats))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("lang", toggle_language))

    telegram_app.add_handler(CallbackQueryHandler(deposit_menu, pattern="deposit_menu"))
    telegram_app.add_handler(CallbackQueryHandler(deposit_method, pattern="^deposit_(cbe_birr|telebirr|cbe_bank)$"))
    telegram_app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    telegram_app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    telegram_app.add_handler(CallbackQueryHandler(invite, pattern="invite"))
    telegram_app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))

    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    logging.info("✅ Arada Bingo Ethiopia bot is running via polling...")

    # ✅ Fix: Push Flask context globally
    flask_app.app_context().push()

    telegram_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()

