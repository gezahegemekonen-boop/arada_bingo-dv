import os
import logging
import asyncio
import random
import threading
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from sqlalchemy import func
from database import db, init_db
from models import User, Transaction, Game, Lobby, ScheduledGame, GameParticipant
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from game_logic import BingoGame
game = BingoGame(game_id=1)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://arada-bingo-dv-oxct.onrender.com")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "364344971").split(",")]

flask_app = Flask(__name__, template_folder="templates", static_folder="static")
flask_app.secret_key = os.getenv("FLASK_SECRET", "bot_secret")

try:
    init_db(flask_app)
except RuntimeError:
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

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
    return render_template("admin_dashboard.html",
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

LANGUAGE_MAP = {
    "en": {
        "welcome": "🎉 Welcome to Arada Bingo Ethiopia!",
        "play": "🎮 Play",
        "deposit": "💰 Deposit",
        "withdraw": "🏧 Withdraw",
        "balance": "💳 Balance",
        "invite": "📨 Invite Friends",
        "language": "🌐 Language",
        "convert": "🔄 Convert Coins",
        "transactions": "📜 Transactions",
        "history": "📂 Game History",
        "instruction": "📘 Instructions",
        "support": "🛠️ Support",
        "referral_contest": "🏆 Referral Contest",
        "leaderboard": "📊 Leaderboard",
        "summary": "🧾 Summary",
        "mycartela": "🧩 My Cartela",
        "mygames": "🎲 My Games",
        "referrals": "👥 My Referrals",
        "toggle_sound": "🔈 Toggle Sound",
        "report_bug": "🐞 Report Bug",
        "schedule_game": "🗓️ Schedule Game",
        "broadcast": "📢 Admin Broadcast",
        "adminstats": "📈 Admin Stats",
        "cartela_preview": "👀 Cartela Preview",
        "call": "📞 Call Admin"
    },
    "am": {
        "welcome": "🎉 እንኳን ደህና መጣህ ወደ አራዳ ቢንጎ ኢትዮጵያ!",
        "play": "🎮 መጫወት",
        "deposit": "💰 ተቀማጭ",
        "withdraw": "🏧 መውጣት",
        "balance": "💳 ቀሪ ሂሳብ",
        "invite": "📨 ጓደኞችን መጋበዝ",
        "language": "🌐 ቋንቋ",
        "convert": "🔄 ኮይኖችን መቀየር",
        "transactions": "📜 ግብይቶች",
        "history": "📂 የጨዋታ ታሪክ",
        "instruction": "📘 መመሪያዎች",
        "support": "🛠️ ድጋፍ",
        "referral_contest": "🏆 የምስክር ውድድር",
        "leaderboard": "📊 የአሸናፊዎች ዝርዝር",
        "summary": "🧾 ዝርዝር መግለጫ",
        "mycartela": "🧩 የእኔ ካርተላ",
        "mygames": "🎲 የእኔ ጨዋታዎች",
        "referrals": "👥 የእኔ ምስክሮች",
        "toggle_sound": "🔈 ድምፅ መቀየር",
        "report_bug": "🐞 ችግር ማመልከት",
        "schedule_game": "🗓️ ጨዋታ መመደብ",
        "broadcast": "📢 የአስተዳዳሪ መልዕክት",
        "adminstats": "📈 የአስተዳዳሪ ቁጥሮች",
        "cartela_preview": "👀 ካርተላ ቅድመ እይታ",
        "call": "📞 አስተዳዳሪን ማግኘት"
    }
}

def get_lang(context, fallback="en"):
    return LANGUAGE_MAP.get(context.chat_data.get("language", fallback), LANGUAGE_MAP["en"])

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
                db.session.add(user)
                db.session.commit()

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
        except:
            pass

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
    user = User.query.filter_by(telegram_id=telegram_id).first()
    lang = get_lang(context)
    link = referral_link(telegram_id)
    await update.message.reply_text(lang["invite"].format(link=link))

async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 Choose your language:", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🇬🇧 English", callback_data="toggle_lang:en")],
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="toggle_lang:am")]
    ]))

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
        except:
            pass
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Game finished!")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    lb = game.get_leaderboard()
    if not lb:
        await update.message.reply_text(f"{lang['leaderboard']}: No winners yet.")
        return
    lines = [lang["leaderboard"]]
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, wins, earnings) in enumerate(lb):
        user = User.query.get(uid)
        medal = medals[i] if i < 3 else "🔹"
        lines.append(f"{medal} @{user.username} – {wins} wins, {earnings} birr")
    await update.message.reply_text("\n".join(lines))

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    s = game.summary()
    lines = [
        f"{lang['summary']}:",
        f"Game #{s['game_id']}",
        f"Status: {s['status']}",
        f"Players: {s['players']}",
        f"Pool: {s['pool']} birr",
        f"Called Numbers: {s['called']}",
        f"Winner: @{User.query.get(s['winner']).username}" if s['winner'] else "Winner: —",
        f"Admin Earnings: {s['admin_earnings']} birr"
    ]
    await update.message.reply_text("\n".join(lines))

async def mycartela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    summary = game.get_player_summary(user.id)
    if not summary:
        await update.message.reply_text("🧩 You have no active cartelas.")
        return
    lines = ["🧩 Your Cartelas:"]
    for c in summary:
        lines.append(f"Cartela #{c['cartela_number']}: marked {len(c['marked'])} numbers")
        lines.append(f"🔢 {sorted(c['marked'])}")
    await update.message.reply_text("\n".join(lines))

async def mygames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    games = GameParticipant.query.filter_by(user_id=user.id).order_by(GameParticipant.id.desc()).limit(5).all()
    lines = ["📜 Your Recent Games:"]
    for g in games:
        lines.append(f"Game #{g.game_id} – Cartela #{g.cartela_number} – Marked: {len(g.marked_numbers)}")
    await update.message.reply_text("\n".join(lines))

async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    active_refs = [u for u in user.referred_users if u.games_played > 0]
    link = referral_link(telegram_id)
    lang = get_lang(context)
    await update.message.reply_text(f"{lang['referrals']}: {len(active_refs)} active\nLink: {link}")

async def toggle_sound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    user.sound_enabled = not user.sound_enabled
    db.session.commit()
    lang = get_lang(context)
    status = lang["toggle_sound"] + (" ✅ ON" if user.sound_enabled else " ❌ OFF")
    await update.message.reply_text(status)

async def report_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(lang["report_bug"])

async def schedule_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can schedule games.")
        return
    sg = ScheduledGame(entry_price=10.0, status="pending")
    db.session.add(sg)
    db.session.commit()
    lang = get_lang(context)
    await update.message.reply_text(f"{lang['schedule_game']}: Game #{sg.id} created.")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Only admins can broadcast.")
        return
    message = " ".join(context.args)
    users = User.query.all()
    for u in users:
        try:
            await context.bot.send_message(chat_id=int(u.telegram_id), text=message)
        except:
            continue
    lang = get_lang(context)
    await update.message.reply_text(f"{lang['broadcast']}: Sent.")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = User.query.count()
    total_games = Game.query.count()
    total_balance = db.session.query(func.sum(User.balance)).scalar() or 0
    lang = get_lang(context)
    await update.message.reply_text(
        f"{lang['adminstats']}:\nUsers: {total_users}\nGames: {total_games}\nTotal Balance: {total_balance} birr"
    )

async def cartela_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(f"{lang['cartela_preview']}: Coming soon.")

async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = game.call_number(chat_id=update.effective_chat.id, context=context)
    if result:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎱 {result['formatted']}")
        try:
            await context.bot.send_voice(chat_id=update.effective_chat.id, voice=InputFile("audio/number_call_am.ogg"))
        except:
            pass
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Game finished!")

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
            user.cartela = context.args
            db.session.commit()
            await update.message.reply_text("✅ Cartela updated.")
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

            if user.language == "am":
                try:
                    await context.bot.send_voice(
                        chat_id=update.effective_chat.id,
                        voice=InputFile("audio/withdraw_am.ogg")
                    )
                except:
                    pass

        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

async def main():
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
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    await telegram_app.run_polling()

if __name__ == "__main__":
    threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))),
        daemon=True
    ).start()

    asyncio.run(main())

