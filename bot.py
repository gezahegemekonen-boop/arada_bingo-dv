# bot.py

import os
import logging
import asyncio
from datetime import datetime
from flask import Flask
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db, init_db
from models import User, Transaction
import aiohttp

# 🔐 Environment Variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REPLIT_SLUG = os.getenv("REPLIT_SLUG")
WEBAPP_URL = f"https://{REPLIT_SLUG}.replit.app" if REPLIT_SLUG else "http://0.0.0.0:5000"

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")

# 🧠 Game Settings
GAME_PRICES = [10, 20, 30, 50, 100]
LANGUAGES = {"en": "English", "am": "አማርኛ"}
AUTO_PLAY = {}
USER_LANG = {}

# 🧪 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 🧠 Flask App + DB
app = Flask(__name__)
init_db(app)

# 🤖 Aiogram Setup
router = Router()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=TOKEN)

class UserState(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdrawal = State()
    waiting_for_language = State()

# 🟢 Start & Registration
@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    referrer_id = int(args[0]) if args else None

    with app.app_context():
        user = User.query.filter_by(telegram_id=user_id).first()
        if not user:
            user = User(telegram_id=user_id, username=username, referrer_id=referrer_id)
            db.session.add(user)
            db.session.commit()

            if referrer_id:
                referrer = User.query.filter_by(telegram_id=referrer_id).first()
                if referrer:
                    referrer.balance += 5
                    db.session.commit()

            keyboard = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Share Phone Number", request_contact=True)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
            await message.answer("Welcome to Arada Bingo! 🎉\nPlease share your phone number to complete registration.", reply_markup=keyboard)
        else:
            await show_main_menu(message)

@router.message(F.contact)
async def process_phone_number(message: Message):
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("Please share your own contact.")
        return

    with app.app_context():
        user = User.query.filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Please use /start first.")
            return

        user.phone = message.contact.phone_number
        db.session.commit()

        bot_info = await bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

        await message.answer(
            f"✅ Registration complete!\nYour referral link:\n{referral_link}\n\n"
            "Share it with friends to earn bonuses!",
            reply_markup=ReplyKeyboardRemove()
        )
        await show_main_menu(message)

async def show_main_menu(message: Message):
    with app.app_context():
        user = User.query.filter_by(telegram_id=message.from_user.id).first()
        if not user:
            await message.answer("Please register first using /start")
            return

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🎮 Play Bingo"), KeyboardButton(text="🧪 Demo Mode")],
                [KeyboardButton(text="💰 Deposit"), KeyboardButton(text="💳 Withdraw")],
                [KeyboardButton(text="📊 My Stats"), KeyboardButton(text="📈 Leaderboard")],
                [KeyboardButton(text="🌐 Language"), KeyboardButton(text="🧾 Transactions")],
                [KeyboardButton(text="📋 Instructions"), KeyboardButton(text="📨 Invite Friends")],
                [KeyboardButton(text="💱 Convert Coins"), KeyboardButton(text="💼 Game History")],
                [KeyboardButton(text="💸 Check Balance")]
            ],
            resize_keyboard=True
        )

        await message.answer(
            f"🎯 Main Menu\n\n"
            f"💰 Balance: {user.balance:.2f} birr\n"
            f"🎮 Games played: {user.games_played}\n"
            f"🏆 Games won: {user.games_won}",
            reply_markup=keyboard
        )

# 💰 Deposit Flow
@router.message(F.text == "💰 Deposit")
async def process_deposit_command(message: Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_deposit_amount)
    await message.answer(
        "💰 Choose your deposit method:\n"
        "1. CBE: 1000316113347\n"
        "2. Telebirr: 0920927761\n"
        "3. CBE Birr: 0920927761\n\n"
        "Then enter the amount you deposited (min 30 birr):"
    )

@router.message(UserState.waiting_for_deposit_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        if amount < 30 or amount > 1000:
            await message.answer("⚠️ Deposit must be between 30 and 1000 birr.")
            return

        user_id = message.from_user.id
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            transaction = Transaction(user_id=user.id, type='deposit', amount=amount, status='completed', completed_at=datetime.utcnow())
            user.balance += amount
            db.session.add(transaction)
            db.session.commit()

            await message.answer(f"✅ Deposit of {amount:.2f} birr confirmed!\nNew Balance: {user.balance:.2f} birr")
    except Exception as e:
        logger.error(f"Deposit error: {e}")
        await message.answer("Something went wrong.")
    finally:
        await state.clear()

# 💳 Withdrawal Flow
@router.message(F.text == "💳 Withdraw")
async def process_withdraw_command(message: Message, state: FSMContext):
    user_id = message.from_user.id
    with app.app_context():
        user = User.query.filter_by(telegram_id=user_id).first()
        if user.balance < 50:
            await message.answer("⚠️ Minimum withdrawal is 50 birr.")
            return
        if user.last_withdraw == 500 and user.games_played < 5:
            await message.answer("⚠️ You must play 5 games before withdrawing again.")
            return
        await state.set_state(UserState.waiting_for_withdrawal)
        await message.answer("💳 Enter the amount you want to withdraw (max 500 birr):")

@router.message(UserState.waiting_for_withdrawal)
async def process_withdrawal_request(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
        user_id = message.from_user.id
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if amount < 50 or amount > 500:
                await message.answer("⚠️ Withdrawal must be between 50 and 500 birr.")
                return
            if amount > user.balance:
                await message.answer("❌ Insufficient balance.")
                return

            transaction = Transaction(user_id=user.id, type='withdraw', amount=-amount, status='pending', withdrawal_phone=user.phone)
            user.balance -= amount
            user.last_withdraw = amount
            user.games_played = 0
            db.session.add(transaction)
            db.session.commit()

            await message.answer(f"✅ Withdrawal request for {amount:.2f} birr submitted.\nAdmin will process it soon.")
    except Exception as e:
        logger.error(f"Withdrawal error: {e}")
        await message.answer("Something went wrong.")
    finally:
        await state.clear()

# 🎮 Game Room Selection
@router.message(F.text == "🎮 Play Bingo")
async def process_play_command(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{price} Birr Room", callback_data=f"room_{price}")] for price in GAME_PRICES
    ])

        await message.answer("Choose your Bingo room:", reply_markup=keyboard)

@router.callback_query(lambda c: c.data.startswith('room_'))
async def process_room_selection(callback_query: CallbackQuery):
    try:
        price = int(callback_query.data.split('_')[1])
        user_id = callback_query.from_user.id

        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if not user or user.balance < price:
                await callback_query.answer("Insufficient balance. Please deposit first.", show_alert=True)
                return

            total_price = price
            commission = total_price * 0.2
            net_entry = total_price - commission

            user.balance -= total_price
            user.games_played += 1
            db.session.commit()

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{WEBAPP_URL}/game/create", json={
                    'entry_price': net_entry,
                    'user_id': user.id
                }) as response:
                    if response.status == 200:
                        data = await response.json()
                        game_id = data['game_id']
                        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(
                                text="Select Your Cartela",
                                web_app=WebAppInfo(url=f"{WEBAPP_URL}/game/{game_id}/select_cartela")
                            )
                        ]])
                        await callback_query.message.edit_text(
                            f"Game created! Entry price: {price} birr\nPlease select your cartela:",
                            reply_markup=keyboard
                        )
                    else:
                        await callback_query.answer("Failed to create game. Please try again.", show_alert=True)
    except Exception as e:
        logger.error(f"Error creating game: {e}")
        await callback_query.answer("Sorry, there was an error. Please try again.", show_alert=True)

# 🧪 Demo Mode
@router.message(F.text == "🧪 Demo Mode")
async def demo_mode(message: Message):
    await message.answer("🎮 Demo Mode activated!\nYou can play without spending real money.\nEnjoy testing the game!")

# 📊 My Stats
@router.message(F.text == "📊 My Stats")
async def process_stats_command(message: Message):
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=message.from_user.id).first()
            transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).limit(5).all()
            stats = (
                f"📊 Your Stats\n\n"
                f"💰 Balance: {user.balance:.2f} birr\n"
                f"🎮 Games Played: {user.games_played}\n"
                f"🏆 Games Won: {user.games_won}\n\n"
                f"Recent Transactions:\n"
            )
            for tx in transactions:
                stats += f"{'➕' if tx.amount > 0 else '➖'} {abs(tx.amount)} birr - {tx.type} ({tx.status})\n"

            await message.answer(stats)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await message.answer("Something went wrong. Try again later.")

# 📈 Leaderboard
@router.message(F.text == "📈 Leaderboard")
async def leaderboard(message: Message):
    with app.app_context():
        top_users = User.query.order_by(User.games_won.desc()).limit(5).all()
        board = "🏆 Top Players:\n\n"
        for i, user in enumerate(top_users, start=1):
            board += f"{i}. @{user.username or 'Anonymous'} - {user.games_won} wins\n"
        await message.answer(board)

# 🌐 Language
@router.message(F.text == "🌐 Language")
async def language_toggle(message: Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_language)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=lang)] for lang in LANGUAGES.values()],
        resize_keyboard=True
    )
    await message.answer("Choose your language:", reply_markup=keyboard)

@router.message(UserState.waiting_for_language)
async def set_language(message: Message, state: FSMContext):
    lang = message.text
    user_id = message.from_user.id
    for code, name in LANGUAGES.items():
        if lang == name:
            USER_LANG[user_id] = code
            await message.answer(f"✅ Language set to {name}")
            await state.clear()
            return
    await message.answer("Invalid choice. Please try again.")

# 🧾 Transactions
@router.message(F.text == "🧾 Transactions")
async def transaction_history(message: Message):
    with app.app_context():
        user = User.query.filter_by(telegram_id=message.from_user.id).first()
        transactions = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).limit(10).all()
        history = "🧾 Your Last 10 Transactions:\n\n"
        for tx in transactions:
            history += f"{tx.created_at.strftime('%Y-%m-%d')} - {tx.type} - {tx.amount} birr ({tx.status})\n"
        await message.answer(history)

# ✅ New Commands You Requested

@router.message(F.text == "💸 Check Balance")
async def check_balance(message: Message):
    with app.app_context():
        user = User.query.filter_by(telegram_id=message.from_user.id).first()
        await message.answer(f"💰 Your current balance is: {user.balance:.2f} birr")

@router.message(F.text == "💱 Convert Coins")
async def convert_coins(message: Message):
    await message.answer("🔄 Coin conversion feature is coming soon!")

@router.message(F.text == "💼 Game History")
async def game_history(message: Message):
    await message.answer("📋 Game history feature is under development. Stay tuned!")

@router.message(F.text == "📋 Instructions")
async def game_instructions(message: Message):
    await message.answer(
        "📋 How to Play Arada Bingo:\n\n"
        "1. Deposit funds to join a room.\n"
        "2. Choose a Bingo room based on entry price.\n"
        "3. Select your cartela and wait for numbers to be called.\n"
        "4. Win by matching patterns!\n\n"
        "🎯 Demo Mode is available for free testing."
    )

@router.message(F.text == "📨 Invite Friends")
async def invite_friends(message: Message):
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(f"📨 Share this link to invite friends:\n{referral_link}")

# 🚀 Bot Startup
async def main():
    try:
        dp.include_router(router)
        logger.info("Bot is starting...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
