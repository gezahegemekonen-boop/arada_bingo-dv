# routes/admin.py
from flask import Blueprint, jsonify
from models import db, Transaction, User
from telegram import Bot
from utils.notify_user import notify_user
import os
import asyncio

admin_bp = Blueprint("admin", __name__)
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

@admin_bp.route("/admin/approve/<int:tx_id>", methods=["POST"])
def approve_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Invalid transaction"}), 400

    tx.status = "approved"
    tx.completed_at = db.func.now()

    user = User.query.get(tx.user_id)
    if tx.type == "withdraw":
        user.balance -= tx.amount

    db.session.commit()
    asyncio.run(notify_user(bot, user.telegram_id, f"✅ Your withdrawal of {tx.amount} birr has been approved."))
    return jsonify({"message": "Transaction approved"})

@admin_bp.route("/admin/reject/<int:tx_id>", methods=["POST"])
def reject_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Invalid transaction"}), 400

    tx.status = "rejected"
    tx.completed_at = db.func.now()

    user = User.query.get(tx.user_id)
    db.session.commit()
    asyncio.run(notify_user(bot, user.telegram_id, f"❌ Your withdrawal request was rejected."))
    return jsonify({"message": "Transaction rejected"})
