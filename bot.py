import os
import logging
import asyncio
import random
import threading
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile
)
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
from game_logic import BingoGame  # ✅ Added
game = BingoGame(game_id=1)       # ✅ Added

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
    return render_template("admin_dashboard.html", pending_deposits=pending_deposits, pending_withdrawals=pending_withdrawals, games=games, players=players)

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
        db.session.commit()
    return jsonify({"status": "approved"})

@flask_app.route("/admin/approve_withdrawal", methods=["POST"])
def approve_withdrawal():
    tx_id = request.form.get("tx_id")
    tx = Transaction.query.get(tx_id)
    if tx and tx.status == "pending":
        tx.status = "approved"
        db.session.commit()
    return jsonify({"status": "approved"})

LANGUAGE_MAP = {
    "en": {
        "welcome": "Welcome to Arada Bingo Ethiopia!",
        "deposit": "💰 Deposit Instructions:\nSend to:\n- CBE Birr: 0920927761\n- Telebirr: 0920927761\n- CBE Bank: 1000316113347\nThen reply with your transaction ID.",
        "withdraw": "💸 Withdrawal Request:\nEnter the amount you want to withdraw.\nWe will send to your preferred account.",
        "stats": "📊 Your Stats:\nBalance: {balance} birr\nGames Played: {played}\nGames Won: {won}\nReferrals: {ref_count}/10\nReferral Link: {link}",
        "invite": "🎁 Invite your friends!\nShare this link:\n{link}\nYou’ll earn 5 birr when they play their first game.\nBonus: 50 birr when you reach 10!",
        "language_set": "✅ Language set to English.",
    },
    "am": {
        "welcome": "እንኳን ደህና መጡ ወደ Arada Bingo Ethiopia!",
        "deposit": "💰 የተቀበሉትን ክፍያ ወደ:\n- CBE Birr: 0920927761\n- Telebirr: 0920927761\n- CBE Bank: 1000316113347\nያስተላልፉ እና የግብይት መለያውን ያስገቡ።",
        "withdraw": "💸 የመነሻ ጥያቄ፡ የሚወስዱትን መጠን ያስገቡ። ክፍያው ወደ ተመረጠው መለያ ይሄዳል።",
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

    if user_language == "am":
        try:
            await context.bot.send_voice(
                chat_id=update.effective_chat.id,
                voice=InputFile("audio/welcome_am.ogg")
            )
        except:
            pass

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    await update.message.reply_text(
        "🎮 Launching Arada Bingo Ethiopia...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🧩 Open Game WebApp", web_app=WebAppInfo(url=f"{WEBAPP_URL}?id={telegram_id}"))]
        ])
    )

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

                if player.id == winner.id:
                    try:
                        await context.bot.send_voice(
                            chat_id=int(player.telegram_id),
                            voice=InputFile("audio/jackpot_win_am.ogg")
                        )
                    except:
                        pass

            await update.message.reply_text(f"✅ Jackpot paid to @{winner.username}")

async def referral_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, count, bonus) in enumerate(leaderboard[:10]):
            medal = medals[i] if i < 3 else "🔹"
            lines.append(f"{medal} @{name} – {count} active referrals, {bonus} birr earned")

        await update.message.reply_text("\n".join(lines))

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = LANGUAGE_MAP.get(context.chat_data.get("language", "en"))
    keyboard = [
        [InlineKeyboardButton("CBE Birr", callback_data="deposit_cbe_birr")],
        [InlineKeyboardButton("Telebirr", callback_data="deposit_telebirr")],
        [InlineKeyboardButton("CBE Bank", callback_data="deposit_cbe_bank")]
    ]
    await update.message.reply_text(lang["deposit"], reply_markup=InlineKeyboardMarkup(keyboard))
    context.chat_data["deposit_method"] = "manual"

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = LANGUAGE_MAP.get(context.chat_data.get("language", "en"))
    await update.message.reply_text(lang["withdraw"])

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must start the bot first using /start.")
            return
        lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
        link = referral_link(user.telegram_id)
        await update.message.reply_text(lang["stats"].format(
            balance=user.balance,
            played=user.games_played,
            won=user.games_won,
            ref_count=len(user.referred_users),
            link=link
        ))

async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="toggle_lang_en")],
        [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="toggle_lang_am")]
    ]
    await update.message.reply_text("🌐 Choose your language:", reply_markup=InlineKeyboardMarkup(keyboard))

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        lang = LANGUAGE_MAP.get(user.language, LANGUAGE_MAP["en"])
        link = referral_link(user.telegram_id)
        await update.message.reply_text(lang["invite"].format(link=link))

        if user.language == "am":
            try:
                await context.bot.send_voice(
                    chat_id=update.effective_chat.id,
                    voice=InputFile("audio/invite_am.ogg")
                )
            except:
                pass

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

async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = game.call_number(chat_id=update.effective_chat.id, context=context)
    if result:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎱 {result['formatted']}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Game finished!")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

async def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("edit", edit_cartela))
    telegram_app.add_handler(CommandHandler("endjackpot", end_jackpot))
    telegram_app.add_handler(CommandHandler("referral_contest", referral_contest))
    telegram_app.add_handler(CommandHandler("deposit", deposit))
    telegram_app.add_handler(CommandHandler("withdraw", withdraw))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("language", language))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("call", call_number))  # ✅ Added

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
    threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))),
        daemon=True
    ).start()

    asyncio.run(main())
