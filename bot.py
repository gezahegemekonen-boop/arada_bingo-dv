import os
import logging
import asyncio
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from database import db, init_db
from models import User, Transaction
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from utils.build_main_keyboard import build_main_keyboard
from routes.admin import admin_bp

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://127.0.0.1:5000")

flask_app = Flask(__name__)
flask_app.secret_key = os.getenv("FLASK_SECRET", "bot_secret")

try:
    init_db(flask_app)
except RuntimeError:
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)

flask_app.register_blueprint(admin_bp)
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

LANGUAGE_MAP = {
    "en": {
        "welcome": "Welcome to Arada Bingo Ethiopia!",
        "deposit": "💰 Deposit Instructions:\nSend payment to 09XXXXXXXX and reply with the transaction ID.",
        "withdraw": "💸 Withdrawal Request:\nEnter the amount you want to withdraw.",
        "stats": "📊 Your Stats:\nBalance: {balance} birr\nGames Played: {played}\nGames Won: {won}\nReferrals: {ref_count}/10\nReferral Link: {link}",
        "invite": "🎁 Invite your friends!\nShare this link:\n{link}\nYou’ll earn 5 birr when they play their first game.\nBonus: 50 birr when you reach 10!",
        "language_set": "✅ Language set to English.",
    },
    "am": {
        "welcome": "እንኳን ደህና መጡ ወደ Arada Bingo Ethiopia!",
        "deposit": "💰 የተቀበሉትን ክፍያ ወደ 09XXXXXXXX ያስተላልፉ እና የግብይት መለያውን ያስገቡ።",
        "withdraw": "💸 የመነሻ ጥያቄ፡ የሚወስዱትን መጠን ያስገቡ።",
        "stats": "📊 የእርስዎ ሁኔታ፡ ቀሪ ባለቤት: {balance} ብር\nተጫዋች ጨዋታዎች: {played}\nየተሸነፉት: {won}\nማስተላለፊያዎች: {ref_count}/10\nአገናኝ: {link}",
        "invite": "🎁 ጓደኞችዎን ይጋብዙ!\nይህን አገናኝ ያጋሩ:\n{link}\nጓደኞችዎ መጀመሪያ ጨዋታ ከጫወቱ በኋላ 5 ብር ያገኛሉ።\n10 ጓደኞች ከጨመሩ በኋላ 50 ብር ያገኛሉ።",
        "language_set": "✅ ቋንቋ ወደ አማርኛ ተቀይሯል።",
    }
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    args = context.args
    referral_telegram_id = int(args[0]) if args and args[0].isdigit() else None
    telegram_id = update.effective_user.id
    username = update.effective_user.username

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=str(telegram_id)).first()

        if not user:
            user = User(
                telegram_id=str(telegram_id),
                username=username,
                balance=0,
                language="en"
            )

            if referral_telegram_id and referral_telegram_id != telegram_id:
                referrer = User.query.filter_by(telegram_id=str(referral_telegram_id)).first()
                if referrer:
                    user.referrer_id = referrer.id
                    db.session.add(user)
                    db.session.commit()

                    # ✅ Reward only if referrer has 10 active referrals
                    active_refs = [u for u in referrer.referred_users if u.games_played > 0]
                    if len(active_refs) + 1 == 10:
                        referrer.balance += 50
                        db.session.add(Transaction(
                            user_id=referrer.id,
                            type="referral_milestone",
                            amount=50,
                            status="approved",
                            reason="Milestone: 10 active referrals"
                        ))
                        db.session.add(referrer)

        else:
            db.session.commit()

        user_language = user.language

    context.chat_data["language"] = user_language
    lang = LANGUAGE_MAP.get(user_language, LANGUAGE_MAP["en"])
    keyboard = build_main_keyboard(lang, WEBAPP_URL)

    await update.message.reply_text(lang["welcome"], reply_markup=keyboard)

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
            link = referral_link(context.bot.username or "AradaBingoBot", user.telegram_id)
            active_refs = [u for u in user.referred_users if u.games_played > 0]
            ref_count = len(active_refs)
            text = lang["stats"].format(
                balance=user.balance,
                played=user.games_played,
                won=user.games_won,
                ref_count=ref_count,
                link=link
            )
            await update.callback_query.edit_message_text(text)

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query and update.effective_user:
        await update.callback_query.answer()
        telegram_id = str(update.effective_user.id)

        with flask_app.app_context():
            user = User.query.filter_by(telegram_id=telegram_id).first()
            if not user:
                return

            lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
            link = referral_link(context.bot.username or "AradaBingoBot", user.telegram_id)
            await update.callback_query.edit_message_text(lang["invite"].format(link=link))

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🎮 Launching Arada Bingo Ethiopia...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}"))]
            ])
        )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        with flask_app.app_context():
            top_winners = User.query.order_by(User.games_won.desc()).limit(5).all()
            most_active = User.query.order_by(User.games_played.desc()).limit(5).all()
            richest = User.query.order_by(User.balance.desc()).limit(5).all()

            lines = ["🏆 Top Winners:"]
            for u in top_winners:
                lines.append(f"@{u.username} – {u.games_won} wins")

            lines.append("\n🎯 Most Active:")
            for u in most_active:
                lines.append(f"@{u.username} – {u.games_played} games")

            lines.append("\n💰 Richest Players:")
            for u in richest:
                lines.append(f"@{u.username} – {u.balance} birr")

            await update.message.reply_text("\n".join(lines))

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)
    text = update.message.text.strip()

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

async def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("auto", toggle_auto_mode))
    telegram_app.add_handler(CommandHandler("sound", toggle_sound))
    telegram_app.add_handler(CommandHandler("help", start))
    telegram_app.add_handler(CommandHandler("stats", stats))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("lang", toggle_language))
    telegram_app.add_handler(CommandHandler("leaderboard", leaderboard))

    telegram_app.add_handler(CallbackQueryHandler(deposit_menu, pattern="deposit_menu"))
    telegram_app.add_handler(CallbackQueryHandler(deposit_method, pattern="^deposit_(cbe_birr|telebirr|cbe_bank)$"))
    telegram_app.add_handler(CallbackQueryHandler(withdraw, pattern="withdraw"))
    telegram_app.add_handler(CallbackQueryHandler(stats, pattern="stats"))
    telegram_app.add_handler(CallbackQueryHandler(invite, pattern="invite"))
    telegram_app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))

    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    logging.info("✅ Arada Bingo Ethiopia bot is starting...")

    await telegram_app.initialize()
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    flask_app.app_context().push()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    await telegram_app.updater.wait_until_closed()

if __name__ == "__main__":
    asyncio.run(main())
