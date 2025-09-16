from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps
from datetime import datetime
import logging
from config import (
    ADMIN_USERNAME, ADMIN_PASSWORD, SECRET_KEY,
    FLASK_HOST, FLASK_PORT
)
from models import db, User, Game, Transaction

app = Flask(__name__)
app.secret_key = SECRET_KEY

# 🔐 Admin login protection
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 🔑 Login page
@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials')
            
    return render_template('admin/login.html')

# 📊 Admin dashboard
@app.route('/admin/dashboard')
@admin_required
def dashboard():
    players = User.query.all()
    games = Game.query.all()
    pending_withdrawals = Transaction.query.filter_by(type="withdraw", status="pending").all()

    return render_template(
        'admin/dashboard.html',
        players=players,
        games=games,
        pending_withdrawals=pending_withdrawals,
        active_games=Game.query.filter_by(status="active").count(),
        total_players=User.query.count()
    )

# 🎮 Start a game manually
@app.route('/admin/game/start', methods=['POST'])
@admin_required
def start_game():
    game_id = request.form.get('game_id')
    game = Game.query.get(game_id)

    if game and game.status == "waiting":
        game.status = "active"
        game.called_numbers = []
        game.created_at = datetime.utcnow()
        db.session.commit()
        flash('Game started successfully')
    else:
        flash('Could not start game')
    return redirect(url_for('dashboard'))

# 🏁 Finish a game manually (optional)
@app.route('/admin/game/finish', methods=['POST'])
@admin_required
def finish_game():
    game_id = request.form.get('game_id')
    game = Game.query.get(game_id)

    if game and game.status == "active":
        game.status = "finished"
        game.finished_at = datetime.utcnow()
        db.session.commit()
        flash('Game marked as finished')
    else:
        flash('Game not active or not found')
    return redirect(url_for('dashboard'))

# 💸 Approve withdrawal
@app.route('/admin/withdrawal/approve', methods=['POST'])
@admin_required
def approve_withdrawal():
    user_id = request.form.get('user_id')
    tx_id = request.form.get('tx_id')
    amount = float(request.form.get('amount'))

    user = User.query.get(user_id)
    tx = Transaction.query.get(tx_id)

    if not user or not tx:
        flash('User or transaction not found')
        return redirect(url_for('dashboard'))

    if user.balance >= amount:
        user.balance -= amount
        tx.status = "approved"
        tx.completed_at = datetime.utcnow()
        db.session.commit()
        logging.info(f"✅ Admin approved withdrawal TX {tx_id} for user {user_id}")
        flash('Withdrawal approved')
    else:
        flash('Insufficient balance')
    return redirect(url_for('dashboard'))

# ❌ Reject withdrawal
@app.route('/admin/withdrawal/reject', methods=['POST'])
@admin_required
def reject_withdrawal():
    tx_id = request.form.get('tx_id')
    reason = request.form.get('reason', 'No reason provided')

    tx = Transaction.query.get(tx_id)
    if not tx:
        flash('Transaction not found')
        return redirect(url_for('dashboard'))

    tx.status = "rejected"
    tx.admin_note = reason
    tx.completed_at = datetime.utcnow()
    db.session.commit()
    logging.info(f"❌ Admin rejected withdrawal TX {tx_id} with reason: {reason}")
    flash('Withdrawal rejected')
    return redirect(url_for('dashboard'))

# 🚪 Logout
@app.route('/admin/logout')
@admin_required
def logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully')
    return redirect(url_for('login'))

# 🚀 Run the app
if __name__ == '__main__':
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=True)
