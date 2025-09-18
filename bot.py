import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://arada-bingo-dv-oxct.onrender.com")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("✅ /start command received")
    await update.message.reply_text("👋 Hello Mekonen! Your bot is alive and responding.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))

    logging.info("✅ Minimal bot is running via webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=10000,
        webhook_url=f"{WEBAPP_URL}/webhook"
    )

if __name__ == "__main__":
    main()
