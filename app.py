from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Game, GameParticipant, Transaction
from game_logic import generate_cartela, check_win, call_next_number
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "arada_secret_key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///arada.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

@app.route("/game/create", methods=["POST"])
def create_game():
    data = request.json
    host_id = data.get("host_id")
    cartela = generate_cartela()
    game = Game(host_id=host_id, status="waiting", called_numbers=[], created_at=datetime.utcnow())
    db.session.add(game)
    db.session.commit()

    participant = GameParticipant(game_id=game.id, user_id=host_id, cartela=cartela)
    db.session.add(participant)
    db.session.commit()

    return jsonify({"game_id": game.id, "cartela": cartela})

@app.route("/game/join", methods=["POST"])
def join_game():
    data = request.json
    game_id = data.get("game_id")
    user_id = data.get("user_id")

    game = Game.query.get(game_id)
    if not game or game.status != "waiting":
        return jsonify({"error": "Game not available"}), 400

    cartela = generate_cartela()
    participant = GameParticipant(game_id=game.id, user_id=user_id, cartela=cartela)
    db.session.add(participant)
    db.session.commit()

    return jsonify({"cartela": cartela})

@app.route("/game/play/<int:game_id>", methods=["GET"])
def play_game(game_id):
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    participants = GameParticipant.query.filter_by(game_id=game_id).all()
    data = {
        "called_numbers": game.called_numbers,
        "players": [
            {"user_id": p.user_id, "cartela": p.cartela, "marked": p.marked_numbers}
            for p in participants
        ]
    }
    return jsonify(data)

@app.route("/game/mark", methods=["POST"])
def mark_number():
    data = request.json
    game_id = data.get("game_id")
    user_id = data.get("user_id")
    number = data.get("number")

    participant = GameParticipant.query.filter_by(game_id=game_id, user_id=user_id).first()
    if not participant:
        return jsonify({"error": "Participant not found"}), 404

    if number not in participant.marked_numbers:
        participant.marked_numbers.append(number)
        db.session.commit()

    win = check_win(participant.cartela, participant.marked_numbers)
    return jsonify({"marked": participant.marked_numbers, "win": win})

@app.route("/game/call/<int:game_id>", methods=["POST"])
def call_number(game_id):
    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    next_number = call_next_number(game.called_numbers)
    game.called_numbers.append(next_number)
    db.session.commit()

    return jsonify({"next_number": next_number})

@app.route("/deposit", methods=["POST"])
def deposit():
    data = request.json
    user_id = data.get("user_id")
    method = data.get("method")
    reference = data.get("reference")

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=0,  # Admin will update manually
        method=method,
        reference=reference,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({"message": "Deposit logged. Awaiting admin approval."})

@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = data.get("amount")

    user = User.query.get(user_id)
    if not user or user.balance < amount:
        return jsonify({"error": "Insufficient balance"}), 400

    tx = Transaction(
        user_id=user.id,
        type="withdraw",
        amount=amount,
        status="pending",
        created_at=datetime.utcnow()
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({"message": "Withdrawal request submitted."})

@app.route("/admin/transactions", methods=["GET"])
def admin_transactions():
    txs = Transaction.query.order_by(Transaction.created_at.desc()).limit(50).all()
    data = []
    for tx in txs:
        user = User.query.get(tx.user_id)
        data.append({
            "id": tx.id,
            "user": user.username if user else "unknown",
            "type": tx.type,
            "amount": tx.amount,
            "method": tx.method,
            "reference": tx.reference,
            "status": tx.status,
            "created_at": tx.created_at.isoformat()
        })
    return jsonify(data)

@app.route("/admin/approve/<int:tx_id>", methods=["POST"])
def approve_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Transaction not found or already processed"}), 400

    tx.status = "approved"
    if tx.type == "deposit":
        user = User.query.get(tx.user_id)
        user.balance += tx.amount
    elif tx.type == "withdraw":
        user = User.query.get(tx.user_id)
        user.balance -= tx.amount

    db.session.commit()
    return jsonify({"message": "Transaction approved."})

@app.route("/admin/reject/<int:tx_id>", methods=["POST"])
def reject_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Transaction not found or already processed"}), 400

    tx.status = "rejected"
    db.session.commit()
    return jsonify({"message": "Transaction rejected."})

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
