from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, Transaction, User, Game
from telegram import Bot
from utils.notify_user import notify_user
import os
import asyncio

admin_bp = Blueprint("admin", __name__)
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

# ✅ Admin dashboard
@admin_bp.route("/admin/dashboard")
def admin_dashboard():
    pending_withdrawals = Transaction.query.filter_by(type="withdraw", status="pending").all()
    games = Game.query.order_by(Game.created_at.desc()).limit(10).all()
    players = User.query.order_by(User.created_at.desc()).limit(10).all()
    return render_template("admin_dashboard.html", pending_withdrawals=pending_withdrawals, games=games, players=players)

# ✅ Approve withdrawal
@admin_bp.route("/approve_withdrawal", methods=["POST"])
def approve_withdrawal():
    tx_id = request.form.get("tx_id")
    user_id = request.form.get("user_id")
    amount = float(request.form.get("amount"))

    tx = Transaction.query.get(tx_id)
    user = User.query.get(user_id)

    if tx and tx.status == "pending":
        tx.status = "approved"
        tx.completed_at = db.func.now()
        user.balance -= amount
        db.session.commit()
        asyncio.run(notify_user(bot, user.telegram_id, f"✅ Your withdrawal of {amount} birr has been approved."))

    return redirect(url_for("admin.admin_dashboard"))

# ✅ Start game manually
@admin_bp.route("/start_game", methods=["POST"])
def start_game():
    game_id = request.form.get("game_id")
    game = Game.query.get(game_id)
    if game and game.status == "waiting":
        game.status = "active"
        db.session.commit()
    return redirect(url_for("admin.admin_dashboard"))

# ✅ Logout route
@admin_bp.route("/logout")
def logout():
    session.clear()
    return "✅ Logged out"

# ✅ Login via Telegram
@admin_bp.route("/admin/login/<int:telegram_id>")
def login_via_telegram(telegram_id):
    user = User.query.filter_by(telegram_id=str(telegram_id)).first()
    if user and user.is_admin:
        session["admin_id"] = user.id
        return redirect(url_for("admin.admin_dashboard"))
    return "❌ Access denied", 403

# ✅ Protect dashboard routes
@admin_bp.before_request
def require_admin_login():
    protected_paths = ["/admin/dashboard", "/approve_withdrawal", "/start_game"]
    if request.path.startswith(tuple(protected_paths)):
        if "admin_id" not in session:
            return "🔒 You must be logged in as admin", 403
