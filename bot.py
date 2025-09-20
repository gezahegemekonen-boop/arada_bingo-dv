import os
import logging
import asyncio
import random
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from sqlalchemy import func
from database import db, init_db
from models import User, Transaction, Game, Lobby
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from utils.build_main_keyboard import build_main_keyboard
from routes.admin import admin_bp

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://arada-bingo.et")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "364344971").split(",")]

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

@app.route("/cartela", methods=["GET", "POST"])
def cartela():
    telegram_id = request.args.get("id")
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if request.method == "GET":
        return jsonify({"cartela": user.cartela})
    else:
        new_cartela = request.json.get("cartela")
        user.cartela = new_cartela
        db.session.commit()
        return jsonify({"status": "updated"})

@app.route("/admin/analytics")
def analytics():
    total_users = User.query.count()
    total_deposits = db.session.query(func.sum(Transaction.amount)).filter_by(type="deposit").scalar()
    total_withdrawals = db.session.query(func.sum(Transaction.amount)).filter_by(type="withdraw").scalar()
    top_referrers = User.query.order_by(User.referred_users.desc()).limit(5).all()

    return jsonify({
        "users": total_users,
        "deposits": total_deposits or 0,
        "withdrawals": total_withdrawals or 0,
        "top_referrers": [u.username for u in top_referrers]
    })

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
                        await context.bot.send_message(
                            chat_id=int(referrer.telegram_id),
                            text="🎉 You reached 10 active referrals! You've earned a 50 birr bonus!"
                        )

        else:
            db.session.commit()

        user_language = user.language

    context.chat_data["language"] = user_language
    lang = LANGUAGE_MAP.get(user_language, LANGUAGE_MAP["en"])
    keyboard = build_main_keyboard(lang, WEBAPP_URL)

    await update.message.reply_text(lang["welcome"], reply_markup=keyboard)
async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🎮 Launching Arada Bingo Ethiopia...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}?id={update.effective_user.id}"))]
            ])
        )

async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        cartela = user.cartela or [12, 34, 56, 78, 90]
        animated = "✨ " + " 🎯 ".join(str(n) for n in cartela) + " ✨"
        await update.message.reply_text(f"🎨 Your cartela:\n{animated}")

async def edit_cartela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    text = update.message.text.strip()
    try:
        numbers = [int(n) for n in text.split(",") if 1 <= int(n) <= 90]
        if len(numbers) != 5:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please enter 5 numbers between 1 and 90, separated by commas.")
        return

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        user.cartela = numbers
        db.session.add(user)
        db.session.commit()
        await update.message.reply_text(f"✅ Cartela updated: {numbers}")

async def join_lobby(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        lobby = Lobby.query.filter_by(status="waiting").first()
        if not lobby:
            lobby = Lobby(status="waiting", jackpot=0)
            db.session.add(lobby)
            db.session.commit()

        lobby.players.append(user)
        db.session.add(lobby)
        db.session.commit()
        await update.message.reply_text(f"🧩 Joined lobby #{lobby.id}. Waiting for others...")

async def start_jackpot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        lobby = Lobby.query.filter(Lobby.players.any(telegram_id=str(telegram_id)), Lobby.status=="waiting").first()
        if not lobby or len(lobby.players) < 2:
            await update.message.reply_text("❌ Need at least 2 players to start jackpot round.")
            return

        lobby.status = "active"
        lobby.jackpot = len(lobby.players) * 10
        db.session.add(lobby)
        db.session.commit()

        for player in lobby.players:
            await context.bot.send_message(chat_id=int(player.telegram_id), text=f"🎰 Jackpot Round Started!\nJackpot: {lobby.jackpot} birr")

        await update.message.reply_text(f"✅ Jackpot round started with {len(lobby.players)} players.")

async def end_jackpot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.effective_user.id in ADMIN_IDS:
        with flask_app.app_context():
            lobby = Lobby.query.filter_by(status="active").first()
            if not lobby or not lobby.players:
                await update.message.reply_text("❌ No active jackpot lobby.")
                return

            winner = random.choice(lobby.players)
            winner.balance += lobby.jackpot
            db.session.add(Transaction(
                user_id=winner.id,
                type="jackpot_win",
                amount=lobby.jackpot,
                status="approved",
                reason=f"Jackpot win in lobby #{lobby.id}"
            ))
            lobby.status = "completed"
            db.session.commit()

            for player in lobby.players:
                msg = "🎉 You won the jackpot!" if player.id == winner.id else "😢 You lost this round."
                await context.bot.send_message(chat_id=int(player.telegram_id), text=msg)

            await update.message.reply_text(f"✅ Jackpot paid to @{winner.username}")

async def jackpot_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        with flask_app.app_context():
            winners = db.session.query(User.username, func.sum(Transaction.amount))\
                .join(Transaction).filter(Transaction.type=="jackpot_win")\
                .group_by(User.username).order_by(func.sum(Transaction.amount).desc()).limit(5).all()

            lines = ["🏆 Jackpot Winners:"]
            for name, total in winners:
                lines.append(f"@{name} – {total} birr won")

            await update.message.reply_text("\n".join(lines))

async def referral_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        with flask_app.app_context():
            users = User.query.all()
            leaderboard = []

            for u in users:
                active_refs = [r for r in u.referred_users if r.games_played > 0]
                bonus = sum(tx.amount for tx in u.transactions if tx.type in ["referral_bonus", "referral_milestone"])
                if active_refs:
                    leaderboard.append((u.username, len(active_refs), bonus))

            leaderboard.sort(key=lambda x: x[1], reverse=True)
            lines = ["🎁 Referral Contest Leaderboard:"]
            for name, count, bonus in leaderboard[:10]:
                lines.append(f"@{name} – {count} active referrals, {bonus} birr earned")

            await update.message.reply_text("\n".join(lines))

async def replay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        last_game = Game.query.filter(Game.participants.any(user_id=user.id)).order_by(Game.created_at.desc()).first()
        if not last_game:
            await update.message.reply_text("📭 No games played yet.")
            return

        result = "🎉 You won!" if last_game.winner_id == user.id else "😢 You lost."
        sound = "🔊 Sound: ON" if context.chat_data.get("sound_enabled", True) else "🔇 Sound: OFF"
        await update.message.reply_text(f"🕹️ Last Game #{last_game.id}\n{result}\n{sound}")
async def remindme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("📅 Reminder set! We'll notify you before the next game starts.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        sender_id = update.effective_user.id
        if sender_id not in ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to broadcast.")
            return

        text = update.message.text.replace("/broadcast", "").strip()
        if not text:
            await update.message.reply_text("📢 Please include a message to broadcast.")
            return

        with flask_app.app_context():
            users = User.query.all()
            for user in users:
                try:
                    await context.bot.send_message(chat_id=int(user.telegram_id), text=f"📢 Announcement:\n{text}")
                except Exception as e:
                    logging.warning(f"Failed to send to {user.telegram_id}: {e}")

        await update.message.reply_text("✅ Broadcast sent to all users.")

async def toggle_auto_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = context.chat_data.get("auto_mode", False)
    context.chat_data["auto_mode"] = not current
    status = "ON" if not current else "OFF"
    await update.message.reply_text(f"🔁 Auto Mode is now {status}.")

async def toggle_sound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = context.chat_data.get("sound_enabled", True)
    context.chat_data["sound_enabled"] = not current
    status = "🔊 Sound ON" if not current else "🔇 Sound OFF"
    await update.message.reply_text(f"{status}")

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

        if text.startswith("edit:"):
            context.args = text.replace("edit:", "").strip()
            await edit_cartela(update, context)
            return

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

@app.route("/payment/confirm", methods=["POST"])
def confirm_payment():
    data = request.json
    tx_id = data.get("tx_id")
    telegram_id = data.get("telegram_id")
    amount = data.get("amount")

    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        user.balance += amount
        db.session.add(Transaction(
            user_id=user.id,
            type="deposit",
            amount=amount,
            status="approved",
            reference=tx_id,
            method="api"
        ))
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "user_not_found"})

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
    telegram_app.add_handler(CommandHandler("referral_leaderboard", referral_leaderboard))
    telegram_app.add_handler(CommandHandler("history", history))
    telegram_app.add_handler(CommandHandler("preview", preview))
    telegram_app.add_handler(CommandHandler("replay", replay))
    telegram_app.add_handler(CommandHandler("remindme", remindme))
    telegram_app.add_handler(CommandHandler("broadcast", broadcast))
    telegram_app.add_handler(CommandHandler("joinlobby", join_lobby))
    telegram_app.add_handler(CommandHandler("startjackpot", start_jackpot))
    telegram_app.add_handler(CommandHandler("endjackpot", end_jackpot))
    telegram_app.add_handler(CommandHandler("jackpot_leaderboard", jackpot_leaderboard))
    telegram_app.add_handler(CommandHandler("referral_contest", referral_contest))

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
