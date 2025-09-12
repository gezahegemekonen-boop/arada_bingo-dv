import os
import random
import asyncio
import logging
from flask import Flask, jsonify, request, session, render_template, redirect, url_for
from datetime import datetime
from database import db, init_db
from game_logic import BingoGame

# 🔧 Logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 🚀 Flask App
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key")
init_db(app)

# 📦 Models
from models import User, Game, GameParticipant, Transaction

# 🎮 Active Games (temporary)
active_games = {}

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = random.randint(1, 1000000)
    return render_template('game_lobby.html')

# 💰 Deposit Webhook
@app.route('/webhook/deposit', methods=['POST'])
def deposit_webhook():
    try:
        data = request.get_json()
        logger.info(f"Received deposit webhook: {data}")

        if not data or 'amount' not in data or 'phone' not in data:
            return jsonify({'error': 'Invalid webhook data'}), 400

        try:
            amount = float(data['amount'])
            if amount <= 0:
                return jsonify({'error': 'Amount must be positive'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid amount format'}), 400

        from bot import process_deposit_confirmation
        asyncio.run(process_deposit_confirmation(data))

        return jsonify({'status': 'success', 'message': 'Deposit processed successfully'})
    except Exception as e:
        logger.exception(f"Webhook error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# 🧪 Webhook Test
@app.route('/webhook/test', methods=['POST'])
def test_webhook():
    try:
        data = request.get_json()
        logger.info(f"Test webhook received: {data}")
        logger.debug(f"Request headers: {dict(request.headers)}")

        validation = {
            "format_check": [],
            "data_validation": [],
            "received_data": data,
            "headers": dict(request.headers)
        }

        amount = None
        phone = None

        if 'amount' in data and 'phone' in data:
            amount = data.get('amount')
            phone = data.get('phone')
        elif 'issue' in data:
            title = data['issue']['title']
            if 'Deposit:' in title:
                try:
                    parts = title.split('Deposit:')[1].strip().split('-')
                    amount = float(parts[0].strip())
                    phone = parts[1].strip()
                except (IndexError, ValueError):
                    pass

        for field in [('amount', amount), ('phone', phone)]:
            if not field[1]:
                validation["format_check"].append(f"❌ Missing: {field[0]}")
            else:
                validation["format_check"].append(f"✅ Found: {field[0]}")

        try:
            amount = float(amount) if amount else 0
            if amount <= 0:
                validation["data_validation"].append("❌ Amount must be positive")
            else:
                validation["data_validation"].append(f"✅ Valid amount: {amount}")
        except (ValueError, TypeError):
            validation["data_validation"].append("❌ Invalid amount format")

        if phone:
            phone = str(phone)
            if not phone.isdigit() or len(phone) < 10:
                validation["data_validation"].append("❌ Invalid phone format")
            else:
                validation["data_validation"].append(f"✅ Valid phone: {phone}")

        validation["status"] = "valid" if all("❌" not in check for check in validation["format_check"] + validation["data_validation"]) else "invalid"
        logger.info(f"Validation result: {validation}")
        return jsonify(validation)
    except Exception as e:
        logger.error(f"Webhook test error: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "help": "Send a POST request with Content-Type: application/json"
        }), 500

# 🎮 Create Game
@app.route('/game/create', methods=['POST'])
def create_game():
    try:
        data = request.get_json()
        entry_price = int(data.get('entry_price', 10))
        user_id = data.get('user_id')

        if entry_price not in [10, 20, 30, 50, 100]:
            return jsonify({'error': 'Invalid entry price'}), 400

        game_id = len(active_games) + 1
        active_games[game_id] = BingoGame(game_id, entry_price)
        session['user_id'] = user_id

        return jsonify({'game_id': game_id, 'entry_price': entry_price})
    except Exception as e:
        logger.exception(f"Create game error: {str(e)}")
        return jsonify({'error': 'Failed to create game'}), 500

# 🎯 Cartela Selection
@app.route('/game/<int:game_id>/select_cartela')
def select_cartela(game_id):
    if game_id not in active_games:
        return redirect(url_for('index'))

    game = active_games[game_id]
    used_cartelas = {player.get('cartela_number', 0) for player in game.players.values()}

    return render_template('cartela_selection.html',
                           game_id=game_id,
                           entry_price=game.entry_price,
                           used_cartelas=used_cartelas)

# 🎮 Play Game
@app.route('/game/<int:game_id>')
def play_game(game_id):
    if game_id not in active_games:
        return redirect(url_for('index'))

    game = active_games[game_id]
    user_id = session['user_id']

    if user_id not in game.players:
        board = game.add_player(user_id)
        if not board:
            return redirect(url_for('index'))

    player = game.players[user_id]

    if game.status == "waiting" and len(game.players) >= game.min_players:
        game.start_game()
        if game.status == "active":
            game.call_number()

    current_number = None
    if game.status == "active" and game.called_numbers:
        current_number = game.format_number(game.called_numbers[-1])

    return render_template('game.html',
                           game_id=game_id,
                           game=game,
                           board=player['board'],
                           marked=player['marked'],
                           called_numbers=game.called_numbers,
                           current_number=current_number,
                           active_players=len(game.players),
                           game_status=game.status,
                           entry_price=game.entry_price)

# 🔢 Call Number
@app.route('/game/<int:game_id>/call', methods=['POST'])
def call_number(game_id):
    if game_id not in active_games:
        return jsonify({'error': 'Game not found'}), 404

    game = active_games[game_id]
    if game.status != "active":
        return jsonify({'error': 'Game not active'}), 400

    number = game.call_number()
    if number:
        return jsonify({'number': number, 'called_numbers': game.called_numbers})
    return jsonify({'error': 'No more numbers'}), 400

# ✅ Mark Number
@app.route('/game/<int:game_id>/mark', methods=['POST'])
def mark_number(game_id):
    if game_id not in active_games:
        return jsonify({'error': 'Game not found'}), 404

    game = active_games[game_id]
    user_id = session['user_id']

    if user_id not in game.players:
        return jsonify({'error': 'Player not in game'}), 400

    number = request.json.get('number')
    if not number:
        return jsonify({'error': 'Number required'}), 400

    success = game.mark_number(user_id, number)
    if not success:
        return jsonify({'error': 'Could not mark number'}), 400

    winner, message = game.check_winner(user_id)
    if winner:
        game.end_game(user_id)

    return jsonify({
        'marked': game.players[user_id]['marked'],
        'winner': winner,
        'message': message
    })

# 🔐 Admin Login
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == os.getenv("ADMIN_USERNAME") and password == os.getenv("ADMIN_PASSWORD"):
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        return "Invalid credentials", 403
    return render_template("admin_login.html")

# 🧭 Admin Dashboard
@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html")

# 🟢 Flask Startup
if __name__ == "__main__":
    app.run(host="0.0.
