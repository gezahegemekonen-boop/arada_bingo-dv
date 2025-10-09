import os
import logging
import asyncio
import random
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo,
    InputFile, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from sqlalchemy import func
from database import db, init_db
from models import User, Transaction, Game, Lobby, ScheduledGame, GameParticipant
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from game_logic import BingoGame

# 🎯 Core game instance
game = BingoGame(game_id=1)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://bingo-pgil.onrender.com")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://bingo-pgil.onrender.com/cartela")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "364344971").split(",")]

# --- Flask setup ---
flask_app = Flask(__name__, template_folder="templates", static_folder="static")
flask_app.secret_key = os.getenv("FLASK_SECRET", "bot_secret")

try:
    init_db(flask_app)
except RuntimeError:
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)

# --- Telegram setup ---
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# -----------------------------
# Flask routes
# -----------------------------
@flask_app.route("/cartela", methods=["GET", "POST"])
def cartela():
    telegram_id = request.args.get("id")
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if request.method == "GET":
        return jsonify({
            "cartela": user.cartela,
            "bonus": [random.randint(1, 90) for _ in range(5)],
            "winner": str(user.telegram_id) if user.games_won > 0 else None
        })
    else:
        new_cartela = request.json.get("cartela")
        user.cartela = new_cartela
        db.session.commit()
        return jsonify({"status": "updated"})


@flask_app.route("/admin/dashboard")
def admin_dashboard():
    pending_deposits = Transaction.query.filter_by(type="deposit", status="pending").all()
    pending_withdrawals = Transaction.query.filter_by(type="withdraw", status="pending").all()
    games = Game.query.order_by(Game.created_at.desc()).limit(10).all()
    players = User.query.order_by(User.created_at.desc()).limit(10).all()
    leaderboard = game.get_leaderboard()
    summary = game.summary()
    users = {u.id: u for u in User.query.all()}
    return render_template(
        "admin_dashboard.html",
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        games=games,
        players=players,
        leaderboard=leaderboard,
        summary=summary,
        users=users
    )


@flask_app.route("/admin/approve_deposit", methods=["POST"])
def approve_deposit():
    tx_id = request.form.get("tx_id")
    amount = int(request.form.get("amount"))
    user_id = int(request.form.get("user_id"))
    tx = Transaction.query.get(tx_id)
    user = User.query.get(user_id)
    if tx and user:
        tx.status = "approved"
        tx.amount = amount
        user.balance += amount
        tx.approved_by = "admin"
        tx.approval_note = "manual approval"
        db.session.commit()
    return jsonify({"status": "approved"})


@flask_app.route("/admin/approve_withdrawal", methods=["POST"])
def approve_withdrawal():
    tx_id = request.form.get("tx_id")
    tx = Transaction.query.get(tx_id)
    if tx and tx.status == "pending":
        tx.status = "approved"
        tx.approved_by = "admin"
        tx.approval_note = request.form.get("note", "")
        db.session.commit()
    return jsonify({"status": "approved"})


@flask_app.route("/admin/payout_winner", methods=["POST"])
def payout_winner():
    winner_id = int(request.form.get("winner_id"))
    amount = float(request.form.get("amount"))
    user = User.query.get(winner_id)
    if user:
        user.balance += amount
        tx = Transaction(
            user_id=user.id,
            type="bingo_win",
            amount=amount,
            status="approved",
            reason="Manual payout from dashboard",
            approved_by="admin"
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"status": "paid"})
    return jsonify({"status": "error"})


# --- Language utils ---
LANGUAGE_MAP = { ... }  # keep full bilingual dictionary

def get_lang(context, fallback="en"):
    lang_code = context.chat_data.get("language", fallback)
    return LANGUAGE_MAP.get(lang_code, LANGUAGE_MAP["en"])

# -----------------------------
# Telegram command handlers
# -----------------------------

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
            db.session.add(user)
            db.session.commit()

            if referral_telegram_id and referral_telegram_id != telegram_id:
                referrer = User.query.filter_by(telegram_id=str(referral_telegram_id)).first()
                if referrer:
                    user.referrer_id = referrer.id
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
                        db.session.commit()
                        await context.bot.send_message(
                            chat_id=int(referrer.telegram_id),
                            text="🎉 You reached 10 active referrals! You've earned a 50 birr bonus!"
                        )
        else:
            db.session.commit()

        user_language = user.language

    context.chat_data["language"] = user_language
    lang = get_lang(context)
    keyboard = ReplyKeyboardMarkup([
        [lang["play"], lang["deposit"]],
        [lang["balance"], lang["withdraw"]],
        [lang["invite"], lang["language"]],
        [lang["summary"], lang["leaderboard"]],
        [lang["mycartela"], lang["mygames"]],
        [lang["referrals"], lang["toggle_sound"]],
        [lang["report_bug"], lang["call"]]
    ], resize_keyboard=True)

    await update.message.reply_text(lang["welcome"], reply_markup=keyboard)

    if user_language == "am":
        try:
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                voice=InputFile("audio/welcome_am.ogg")
            )
        except Exception:
            pass


# -----------------------------
# Financial & game commands
# -----------------------------
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    context.chat_data["deposit_method"] = "cbe_birr"
    await update.message.reply_text(lang["deposit"])


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(lang["withdraw"])


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        lang = get_lang(context)
        message = f"{lang['balance']}: {user.balance} birr"
        await update.message.reply_text(message)
    else:
        await update.message.reply_text("❌ You must start the bot first using /start.")


async def referral_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    telegram_id = str(update.effective_user.id)
    link = referral_link(telegram_id)
    await update.message.reply_text(f"{lang['referral_contest']}:\n{link}")


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    lang = get_lang(context)
    link = referral_link(telegram_id)
    await update.message.reply_text(f"{lang['invite']}: {link}")


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 Choose your language:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇬🇧 English", callback_data="toggle_lang:en")],
            [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="toggle_lang:am")]
        ])
    )


async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    lang = get_lang(context)
    await update.message.reply_text(
        f"{lang['play']}...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}?id={telegram_id}"))]
        ])
    )
    game.start_game(chat_id=update.effective_chat.id, context=context)


async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = game.call_number(chat_id=update.effective_chat.id, context=context)
    if result:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎱 {result['formatted']}")
        try:
            await context.bot.send_voice(chat_id=update.effective_chat.id, voice=InputFile("audio/number_call_am.ogg"))
        except Exception:
            pass
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Game finished!")

# -----------------------------
# Handle user input and errors
# -----------------------------

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

        # --- Edit cartela ---
        if text.startswith("edit:"):
            new_cartela = text.replace("edit:", "").strip()
            user.cartela = new_cartela
            db.session.commit()
            await update.message.reply_text("✅ Cartela updated.")
            return

        # --- Deposit process ---
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

        # --- Withdrawal process ---
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

            if user.language == "am":
                try:
                    await context.bot.send_voice(
                        chat_id=update.effective_chat.id,
                        voice=InputFile("audio/withdraw_am.ogg")
                    )
                except Exception:
                    pass

        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")


# -----------------------------
# Main async setup (Render-safe)
# -----------------------------
async def start_bot():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("deposit", deposit))
    telegram_app.add_handler(CommandHandler("withdraw", withdraw))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("referral_contest", referral_contest))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("language", language))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("call", call_number))
    telegram_app.add_handler(CommandHandler("leaderboard", leaderboard))
    telegram_app.add_handler(CommandHandler("summary", summary))
    telegram_app.add_handler(CommandHandler("mycartela", mycartela))
    telegram_app.add_handler(CommandHandler("mygames", mygames))
    telegram_app.add_handler(CommandHandler("referrals", referrals))
    telegram_app.add_handler(CommandHandler("toggle_sound", toggle_sound))
    telegram_app.add_handler(CommandHandler("report_bug", report_bug))
    telegram_app.add_handler(CommandHandler("schedule_game", schedule_game))
    telegram_app.add_handler(CommandHandler("broadcast", admin_broadcast))
    telegram_app.add_handler(CommandHandler("adminstats", admin_stats))
    telegram_app.add_handler(CommandHandler("cartela_preview", cartela_preview))

    telegram_app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))
    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    logging.info("✅ Arada Bingo Ethiopia bot is starting...")
    flask_app.app_context().push()

    # Render-safe webhook setup
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    await telegram_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=os.environ["WEBHOOK_URL"]
    )


# -----------------------------
# Render entrypoint (no double event loop)
# -----------------------------
if __name__ == "__main__":
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_bot())
    except RuntimeError:
        # Handles case when Render keeps a loop open
        asyncio.run(start_bot())
