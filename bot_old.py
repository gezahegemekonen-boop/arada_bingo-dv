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

# 🔄 Auto-play toggle (default: manual)
AUTO_PLAY = {}

@router.message(Command("toggle_auto"))
async def toggle_auto_play(message: Message):
    """Toggle auto-play mode for the user"""
    user_id = message.from_user.id
    AUTO_PLAY[user_id] = not AUTO_PLAY.get(user_id, False)

    mode = "Auto-Play ✅" if AUTO_PLAY[user_id] else "Manual Play ❌"
    await message.answer(f"🎮 Play mode switched to: {mode}")

@router.message(F.text == "🎮 Play Bingo")
async def process_play_command(message: Message):
    """Show game price options"""
    try:
        user_id = message.from_user.id
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if not user:
                await message.answer("Please register first using /start")
                return

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=f"{price} Birr",
                    callback_data=f"price_{price}"
                )] for price in GAME_PRICES
            ])

            await message.answer(
                "Choose your game entry price:",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error showing game prices: {e}")
        await message.answer("Sorry, there was an error. Please try again later.")

@router.callback_query(lambda c: c.data.startswith('price_'))
async def process_price_selection(callback_query: CallbackQuery):
    """Handle price selection and create game"""
    try:
        price = int(callback_query.data.split('_')[1])
        user_id = callback_query.from_user.id

        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if not user or user.balance < price:
                await callback_query.answer("Insufficient balance. Please deposit first.", show_alert=True)
                return

            # Deduct balance and increment games played
            user.balance -= price
            user.games_played += 1
            db.session.commit()

            # Create game via API
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{WEBAPP_URL}/game/create", json={
                    'entry_price': price,
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

                        if AUTO_PLAY.get(user_id, False):
                            await callback_query.message.edit_text(
                                f"🎮 Auto-Play enabled!\nGame created with {price} birr.\nCartela selected automatically."
                            )
                        else:
                            await callback_query.message.edit_text(
                                f"Game created! Entry price: {price} birr\nPlease select your cartela:",
                                reply_markup=keyboard
                            )
                    else:
                        await callback_query.answer("Failed to create game. Please try again.", show_alert=True)
    except Exception as e:
        logger.error(f"Error creating game: {e}")
        await callback_query.answer("Sorry, there was an error. Please try again.", show_alert=True)

class UserState(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdrawal = State()

@router.message(F.text == "💰 Deposit")
async def process_deposit_command(message: Message, state: FSMContext):
    """Ask user for deposit amount"""
    await state.set_state(UserState.waiting_for_deposit_amount)
    await message.answer(
        "💰 Enter the amount you want to deposit (in birr):\n"
        "Minimum: 10 birr\nMaximum: 1000 birr"
    )

@router.message(UserState.waiting_for_deposit_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    """Handle deposit amount input and auto-confirm"""
    try:
        amount = float(message.text)
        if amount < 10 or amount > 1000:
            await message.answer("⚠️ Deposit must be between 10 and 1000 birr.")
            return

        user_id = message.from_user.id
        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if not user:
                await message.answer("Please register first using /start")
                return

            # Save transaction and update balance
            transaction = Transaction(
                user_id=user.id,
                type='deposit',
                amount=amount,
                status='completed',
                completed_at=datetime.utcnow()
            )
            user.balance += amount
            db.session.add(transaction)
            db.session.commit()

            await message.answer(
                f"✅ Deposit of {amount:.2f} birr confirmed!\n"
                f"New Balance: {user.balance:.2f} birr"
            )
    except ValueError:
        await message.answer("⚠️ Please enter a valid number.")
    except Exception as e:
        logger.error(f"Deposit error: {e}")
        await message.answer("Sorry, something went wrong.")
    finally:
        await state.clear()

@router.message(F.text == "💳 Withdraw")
async def process_withdraw_command(message: Message, state: FSMContext):
    """Ask user for withdrawal amount"""
    user_id = message.from_user.id
    with app.app_context():
        user = User.query.filter_by(telegram_id=user_id).first()
        if not user:
            await message.answer("Please register first using /start")
            return

        if user.balance < 300:
            await message.answer("⚠️ Minimum withdrawal is 300 birr.")
            return

        if user.last_withdraw and user.last_withdraw >= 300 and user.games_played < 5:
            await message.answer("⚠️ You must play at least 5 games before your next withdrawal.")
            return

        await state.set_state(UserState.waiting_for_withdrawal)
        await message.answer("💳 Enter the amount you want to withdraw:")

@router.message(UserState.waiting_for_withdrawal)
async def process_withdrawal_request(message: Message, state: FSMContext):
    """Handle withdrawal request"""
    try:
        amount = float(message.text)
        user_id = message.from_user.id

        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if amount < 300:
                await message.answer("⚠️ Minimum withdrawal is 300 birr.")
                return
            if amount > user.balance:
                await message.answer("❌ Insufficient balance.")
                return

            transaction = Transaction(
                user_id=user.id,
                type='withdraw',
                amount=-amount,
                status='pending',
                withdrawal_phone=user.phone
            )
            user.balance -= amount
            user.last_withdraw = amount
            user.games_played = 0
            db.session.add(transaction)
            db.session.commit()

            await message.answer(
                f"✅ Withdrawal request for {amount:.2f} birr submitted.\n"
                "Admin will process it soon."
            )
    except ValueError:
        await message.answer("⚠️ Please enter a valid number.")
    except Exception as e:
        logger.error(f"Withdrawal error: {e}")
        await message.answer("Sorry, something went wrong.")
    finally:
        await state.clear()

@router.message(Command("start"))
async def cmd_start(message: Message):
    """Register user and show main menu"""
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        referrer_id = int(args[0]) if args else None

        with app.app_context():
            user = User.query.filter_by(telegram_id=user_id).first()
            if not user:
                user = User(
                    telegram_id=user_id,
                    username=username,
                    referrer_id=referrer_id
                )
                db.session.add(user)
                db.session.commit()

                keyboard = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Share Phone Number", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                await message.answer(
                    "Welcome to Arada Bingo! 🎉\nPlease share your phone number to complete registration.",
                    reply_markup=keyboard
                )
            else:
                await show_main_menu(message)
    except Exception as e:
        logger.error(f"Start error: {e}")
        await message.answer("Something went wrong. Try again later.")

@router.message(F.contact)
async def process_phone_number(message: Message):
    """Save user's phone number"""
    if not message.contact or message.contact.user_id != message.from_user.id:
        await message.answer("Please share your own contact.")
        return

    try:
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
    except Exception as e:
        logger.error(f"Phone error: {e}")
        await message.answer("Something went wrong. Try again later.")

async def show_main_menu(message: Message):
    """Display main menu"""
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=message.from_user.id).first()
            if not user:
                await message.answer("Please register first using /start")
                return

            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="🎮 Play Bingo")],
                    [KeyboardButton(text="💰 Deposit"), KeyboardButton(text="💳 Withdraw")],
                    [KeyboardButton(text="📊 My Stats"), KeyboardButton(text="/toggle_auto")]
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
    except Exception as e:
        logger.error(f"Menu error: {e}")
        await message.answer("Something went wrong. Try again later.")

@router.message(F.text == "📊 My Stats")
async def process_stats_command(message: Message):
    """Show user stats and recent transactions"""
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=message.from_user.id).first()
            if not user:
                await message.answer("Please register first using /start")
                return

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
