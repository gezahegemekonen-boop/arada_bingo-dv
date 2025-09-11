# --- Imports and Setup ---
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

# --- Environment and Logging ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
REPLIT_SLUG = os.getenv("REPLIT_SLUG")
WEBAPP_URL = f"https://{REPLIT_SLUG}.replit.app" if REPLIT_SLUG else "http://0.0.0.0:5000"

if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")

GAME_PRICES = [10, 20, 30, 50, 100]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Flask and Bot Setup ---
app = Flask(__name__)
init_db(app)

router = Router()
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
bot = Bot(token=TOKEN)

# --- Auto-Play Toggle ---
AUTO_PLAY = {}

# --- FSM States ---
class UserState(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdrawal = State()

@router.message(F.text == "💰 Deposit")
async def process_deposit_command(message: Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_deposit_amount)
    await message.answer(
        "💰 Enter the amount you want to deposit (in birr):\n"
        "Minimum: 10 birr\nMaximum: 1000 birr"
    )

@router.message(UserState.waiting_for_deposit_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
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
                    "Welcome to Arada Bingo Ethiopia! 🎉\nPlease share your phone number to complete registration.",
                    reply_markup=keyboard
                )
            else:
                await show_main_menu(message)
    except Exception as e:
        logger.error(f"Start error: {e}")
        await message.answer("Something went wrong. Try again later.")

@router.message(F.contact)
async def process_phone_number(message: Message):
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
                f"🎯 Main Menu — Arada Bingo Ethiopia\n\n"
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
    try:
        with app.app_context():
            user = User.query.filter_by(telegram_id=message.from_user.id).first()
            if not user:
