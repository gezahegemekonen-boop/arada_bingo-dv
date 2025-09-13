import os
import json
import time
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from database import db, init_db
from models import User, Game, GameParticipant, Transaction
from game_logic import (
    create_game, join_game, mark_number, check_win,
    call_next_number, get_game_state
)
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", "secret")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

init_db(app)

# -------------------------
# Player Routes
# -------------------------

@app.route('/')
def lobby():
    return render_template('game_lobby.html')

@app.route('/game/create', methods=['POST'])
def create_new_game():
    data = request.get_json()
    entry_price = data.get('entry_price')
    game = create_game(entry_price)
    return jsonify({"game_id": game.id})

@app.route('/game/list')
def list_games():
    games = Game.query.filter(Game.status.in_(["waiting", "countdown"])).all()
    return jsonify([{
        "id": g.id,
        "players": len(g.participants),
        "entry_price": g.entry_price
    } for g in games])

@app.route('/game/<int:game_id>/select')
def select_cartela(game_id):
    game = Game.query.get_or_404(game_id)
    used_cartelas = [p.cartela_number for p in game.participants]
    return render_template('cartela_selection.html',
                           game_id=game.id,
                           entry_price=game.entry_price,
                           used_cartelas=used_cartelas)

@app.route('/game/<int:game_id>/join', methods=['POST'])
def join_cartela(game_id):
    data = request.get_json()
    cartela_number = data.get('cartela_number')
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Not logged in"}), 403
    join_game(game_id, user_id, cartela_number)
    return jsonify({"game_id": game_id})

@app.route('/game/<int:game_id>')
def play_game(game_id):
    state = get_game_state(game_id, session.get('user_id'))
    return render_template('game.html', **state)

@app.route('/game/<int:game_id>/mark', methods=['POST'])
def mark_cell(game_id):
    data = request.get_json()
    user_id = session.get('user_id')
    if data.get('check_win'):
        return jsonify(check_win(game_id, user_id))
    else:
        return jsonify(mark_number(game_id, user_id, data.get('number')))

@app.route('/game/<int:game_id>/call', methods=['POST'])
def call_number(game_id):
    user_id = session.get('user_id')
    auto_mode = session.get('auto_mode', True)
    if auto_mode:
        return jsonify(call_next_number(game_id))
    else:
        return jsonify({"error": "Manual mode active"})

@app.route('/game/<int:game_id>/toggle_auto', methods=['POST'])
def toggle_auto(game_id):
    session['auto_mode'] = not session.get('auto_mode', True)
    return jsonify({"auto_mode": session['auto_mode']})

@app.route('/game/<int:game_id>/toggle_sound', methods=['POST'])
def toggle_sound(game_id):
    session['sound_enabled'] = not session.get('sound_enabled', True)
    return jsonify({"sound_enabled": session['sound_enabled']})

from flask import flash

# -------------------------
# Admin Routes
# -------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == os.getenv("ADMIN_USERNAME") and password == os.getenv("ADMIN_PASSWORD"):
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid credentials")
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    pending_tx = Transaction.query.filter_by(status="pending").all()
    recent_games = Game.query.order_by(Game.created_at.desc()).limit(10).all()
    return render_template('admin_dashboard.html',
                           transactions=pending_tx,
                           games=recent_games)

@app.route('/admin/approve/<int:tx_id>')
def approve_tx(tx_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    tx = Transaction.query.get_or_404(tx_id)
    tx.status = "approved"
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject/<int:tx_id>')
def reject_tx(tx_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    tx = Transaction.query.get_or_404(tx_id)
    tx.status = "rejected"
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# -------------------------
# App Runner
# -------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000)
