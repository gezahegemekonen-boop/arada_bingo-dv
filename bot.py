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
from utils import (
    is_valid_tx_id,
    referral_link,
    toggle_language,
    format_cartela,
    build_main_keyboard,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-hosted-webapp.com")
ADMIN_ID = os.getenv("ADMIN_TELEGRAM_ID")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN not set in environment.")

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
    args = context.args
    referral_id = None
    if args:
        try:
            referral_id = int(args[0])
        except ValueError:
            pass

    telegram_id = str(update.effective_user.id)
    username = update.effective_user.username
    user = User.query.filter_by(telegram_id=telegram_id).first()

    if not user:
        user = User(
            telegram_id=telegram_id,
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
                status="approved",
                created_at=datetime.utcnow()
            ))
            db.session.commit()

    session = context.chat_data
    session['auto_mode'] = True
    session['sound_enabled'] = True
    session['language'] = user.language

    lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
    keyboard = build_main_keyboard(lang, WEBAPP_URL)

    await update.message.reply_text(
        lang["welcome"],
        reply_markup=keyboard
    )

async def toggle_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return

    user.language = toggle_language(user.language)
    db.session.commit()

    context.chat_data['language'] = user.language
    lang = LANGUAGE_MAP[user.language]
    await update.callback_query.edit_message_text(lang["language_set"])

async def deposit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.callback_query.answer()
    method = update.callback_query.data.split("_")[1]
    context.chat_data["deposit_method"] = method

    msg = {
        "cbe_birr": "📲 CBE Birr Deposit:\nSend to 0920927761 and reply with your transaction ID.",
        "telebirr": "📲 Telebirr Deposit:\nSend to 0920927761 and reply with your transaction ID.",
        "cbe_bank": "🏦 CBE Bank Deposit:\nAccount Number: 1000316113347\nThen reply with your transaction ID."
    }.get(method, "❌ Unknown method.")
    
    await update.callback_query.edit_message_text(msg)

async def handle_transaction_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    method = context.chat_data.get("deposit_method", "unknown")
    tx_id = update.message.text.strip()

    if not user:
        await update.message.reply_text("❌ You must start the bot first using /start.")
        return

    if not is_valid_tx_id(tx_id):
        await update.message.reply_text("❌ Invalid transaction ID. Please try again.")
        return

    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=0,
        method=method,
        status="pending",
        reference=tx_id,
        created_at=datetime.utcnow()
    )
    db.session.add(tx)
    db.session.commit()

    logging.info(f"User {telegram_id} submitted deposit via {method}: {tx_id}")
    await update.message.reply_text("✅ Transaction received. Awaiting admin approval.")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    lang = LANGUAGE_MAP.get(context.chat_data.get("language", "en"), LANGUAGE_MAP["en"])
    await update.callback_query.edit_message_text(lang["withdraw"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
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

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
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

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return

    lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
    link = referral_link(context.bot.username or "AradaBingoBot", user.id)
    await update.callback_query.edit_message_text(lang["invite"].format(link=link))

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Launching Arada Bingo Ethiopia...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}"))]
        ])
    )

async def toggle_auto_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = context.chat_data
    session['auto_mode'] = not session.get('auto_mode', True)
    status = "ON" if session['auto_mode'] else "OFF"
    await update.message.reply_text(f"🔁 Auto Mode: {status}")

async def toggle_sound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = context.chat_data
    session['sound_enabled'] = not session.get('sound_enabled', True)
    status = "ON" if session['sound_enabled'] else "OFF"
    await update.message.reply_text(f"🔊 Sound: {status}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Use /start to begin. Tap buttons to deposit, play, or invite friends.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play_game))
    app.add_handler(CommandHandler("auto", toggle_auto_mode))
    app.add_handler(CommandHandler("sound", toggle_sound))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("lang", toggle_language))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(deposit_menu, pattern="deposit_menu"))
    app.add_handler(CallbackQueryHandler(deposit_method, pattern="^deposit_(cbe_birr|telebirr|cbe_bank)$"))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    app.add_handler(CallbackQueryHandler(invite, pattern="invite"))
    app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))

    # Message handler for transaction ID
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transaction_id))

    logging.info("✅ Arada Bingo Ethiopia bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
