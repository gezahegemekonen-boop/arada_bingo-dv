import os
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from database import db, init_db
from models import User, Transaction, Game, GameParticipant
from datetime import datetime
from sqlalchemy import func

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-hosted-webapp.com")

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
            referred_by=referral_id,
            language="en",
            has_played=False
        )
        db.session.add(user)
        db.session.commit()

    # Referral bonus logic
    if referral_id and referral_id != user.id:
        referrer = User.query.get(referral_id)
        if referrer and not user.has_played:
            referrer.balance += 5
            db.session.add(Transaction(
                user_id=referrer.id,
                type="referral_bonus",
                amount=5,
                status="approved",
                created_at=datetime.utcnow()
            ))
            db.session.commit()

    # Set session defaults
    session = context.chat_data
    session['auto_mode'] = True
    session['sound_enabled'] = True
    session['language'] = user.language

    lang = LANGUAGE_MAP[user.language]
    keyboard = [
        [InlineKeyboardButton("🎮 Play Bingo", web_app=WebAppInfo(url=f"{WEBAPP_URL}"))],
        [InlineKeyboardButton("💰 Deposit", callback_data="deposit"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats"),
         InlineKeyboardButton("🎁 Invite Friends", callback_data="invite")],
        [InlineKeyboardButton("🌐 Language: English / አማርኛ", callback_data="toggle_lang")]
    ]
    await update.message.reply_text(
        lang["welcome"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def toggle_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        return

    user.language = "am" if user.language == "en" else "en"
    db.session.commit()

    context.chat_data['language'] = user.language
    lang = LANGUAGE_MAP[user.language]

    await update.callback_query.edit_message_text(lang["language_set"])

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    lang = LANGUAGE_MAP[context.chat_data.get("language", "en")]
    await update.callback_query.edit_message_text(lang["deposit"])

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    lang = LANGUAGE_MAP[context.chat_data.get("language", "en")]
    await update.callback_query.edit_message_text(lang["withdraw"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        await update.callback_query.edit_message_text("No stats found.")
        return

    lang = LANGUAGE_MAP[user.language]
    link = f"https://t.me/{context.bot.username}?start={user.id}"
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

    lang = LANGUAGE_MAP[user.language]
    link = f"https://t.me/{context.bot.username}?start={user.id}"
    await update.callback_query.edit_message_text(lang["invite"].format(link=link))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != os.getenv("ADMIN_TELEGRAM_ID"):
        await update.message.reply_text("🚫 You are not authorized.")
        return

    pending = Transaction.query.filter_by(type="withdraw", status="pending").all()
    if not pending:
        await update.message.reply_text("✅ No pending withdrawals.")
        return

    for tx in pending:
        user = User.query.get(tx.user_id)
        text = f"💸 Withdrawal Request\nUser: @{user.username}\nAmount: {tx.amount} birr\nTX ID: {tx.id}"
        buttons = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{tx.id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{tx.id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))

async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not str(update.effective_user.id) == os.getenv("ADMIN_TELEGRAM_ID"):
        await query.edit_message_text("🚫 Not authorized.")
        return

    if data.startswith("approve_"):
        tx_id = int(data.split("_")[1])
        tx = Transaction.query.get(tx_id)
        if tx and tx.status == "pending":
            tx.status = "approved"
            db.session.commit()
            await query.edit_message_text(f"✅ Withdrawal {tx.id} approved.")
    elif data.startswith("reject_"):
        tx_id = int(data.split("_")[1])
        tx = Transaction.query.get(tx_id)
        if tx and tx.status == "pending":
            tx.status = "rejected"
            db.session.commit()
            await query.edit_message_text(f"❌ Withdrawal {tx.id} rejected.")

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

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play_game))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("auto", toggle_auto_mode))
    app.add_handler(CommandHandler("sound", toggle_sound))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(deposit, pattern="deposit"))
    app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    app.add_handler(CallbackQueryHandler(invite, pattern="invite"))
    app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern="^(approve_|reject_).*"))

    logging.info("✅ Arada Bingo Ethiopia bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
