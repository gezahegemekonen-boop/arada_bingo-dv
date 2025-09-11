# bot_new.py — Arada Bingo (new logic version)

import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from pymongo import MongoClient

# 🔹 Load secrets from Replit Secrets
TOKEN = os.getenv("TOKEN")
MONGODB_URI = os.getenv("MONGODB_URI")
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() == "true"
ADMIN_ID = os.getenv("ADMIN_ID")
BOT_NAME = os.getenv("BOT_NAME", "Arada Bingo")
CBE_ACCOUNT = os.getenv("CBE_ACCOUNT")
CBE_BIRR = os.getenv("CBE_BIRR")
TELEBIRR = os.getenv("TELEBIRR")
PAYMENT_TIMEOUT = int(os.getenv("PAYMENT_TIMEOUT", "30"))

# 🔹 Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if DEBUG_MODE else logging.INFO
)

# 🔹 MongoDB connection
client = MongoClient(MONGODB_URI)
db = client["arada_bingo"]
users_collection = db["users"]
transactions_collection = db["transactions"]

# ---------------- COMMANDS ---------------- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🎮 Welcome to {BOT_NAME}!\n"
        f"💳 Deposit via:\n"
        f" - CBE Account: {CBE_ACCOUNT}\n"
        f" - CBE Birr: {CBE_BIRR}\n"
        f" - Telebirr: {TELEBIRR}\n"
        f"⌛ Payment timeout: {PAYMENT_TIMEOUT} minutes\n"
        f"Use /deposit <amount> to add funds.\n"
        f"Use /withdraw <amount> to request payout.\n"
        f"Use /join <room_amount> to join a game room."
    )

# 💰 Deposit
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("💰 Please enter the deposit amount. Example: /deposit 50")
        return

    if amount < 20:
        await update.message.reply_text("⚠️ Minimum deposit is 20 birr.")
        return

    user_id = update.effective_user.id
    transactions_collection.insert_one({
        "user_id": user_id,
        "type": "deposit",
        "amount": amount,
        "status": "confirmed"
    })

    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"balance": amount}},
        upsert=True
    )

    await update.message.reply_text(f"✅ Deposit of {amount} birr confirmed and added to your balance.")

# 🏧 Withdraw
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("🏧 Please enter the withdrawal amount. Example: /withdraw 300")
        return

    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id}) or {"balance": 0, "games_played": 0, "last_withdraw": None}

    if amount < 300:
        await update.message.reply_text("⚠️ Minimum withdrawal is 300 birr.")
        return

    if user["balance"] < amount:
        await update.message.reply_text("❌ Insufficient balance.")
        return

    if user.get("last_withdraw") and user["last_withdraw"] >= 300:
        if user["games_played"] < 5:
            await update.message.reply_text("⚠️ You must play at least 5 games before your next withdrawal.")
            return

    users_collection.update_one(
        {"user_id": user_id},
        {
            "$inc": {"balance": -amount},
            "$set": {"last_withdraw": amount, "games_played": 0}
        }
    )

    transactions_collection.insert_one({
        "user_id": user_id,
        "type": "withdraw",
        "amount": amount,
        "status": "pending"
    })

    await update.message.reply_text(f"✅ Withdrawal request for {amount} birr submitted. Admin will process it soon.")

# 🎯 Join Room
async def join_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        room_amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("🎯 Please choose a room: /join 10, /join 20, /join 30, /join 50, /join 100")
        return

    if room_amount not in [10, 20, 30, 50, 100]:
        await update.message.reply_text("⚠️ Invalid room. Choose 10, 20, 30, 50, or 100 birr.")
        return

    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id}) or {"balance": 0}

    if user["balance"] < room_amount:
        await update.message.reply_text("❌ Not enough balance to join this room.")
        return

    users_collection.update_one(
        {"user_id": user_id},
        {
            "$inc": {"balance": -room_amount, "games_played": 1}
        }
    )

    await update.message.reply_text(f"🎮 You joined the {room_amount} birr room. Good luck!")

# ---------------- MAIN ---------------- #

def main():
    if not TOKEN:
        raise ValueError("❌ TOKEN is missing. Add it in Replit Secrets.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deposit", deposit))
    app.add_handler(CommandHandler("withdraw", withdraw))
    app.add_handler(CommandHandler("join", join_room))

    app.run_polling()

if __name__ == "__main__":
    main()
