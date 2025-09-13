from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    username = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    balance = db.Column(db.Float, default=0.0)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    sound_enabled = db.Column(db.Boolean, default=True)  # 🔊 Mute/unmute toggle
    play_mode = db.Column(db.String(10), default="auto")  # "auto" or "manual"
    language = db.Column(db.String(10), default="en")
    referrer_id = db.Column(db.BigInteger, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='waiting')  # waiting, active, finished
    entry_price = db.Column(db.Float, nullable=False)
    pool = db.Column(db.Float, default=0.0)
    payout = db.Column(db.Float, default=0.0)  # 💰 Winner payout
    commission = db.Column(db.Float, default=0.0)  # 🧾 Admin commission
    called_numbers = db.Column(db.PickleType)  # ✅ Native Python list
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)

    # Relationships
    participants = db.relationship('GameParticipant', backref='game', lazy=True)
    winner = db.relationship('User', backref='won_games', lazy=True)

class GameParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cartela_number = db.Column(db.Integer, nullable=False)
    marked_numbers = db.Column(db.PickleType)  # ✅ Native Python list
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('game_id', 'cartela_number', name='unique_cartela_per_game'),
    )

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20))  # deposit, withdraw, win, game_entry, commission, manual_payout
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed
    method = db.Column(db.String(20))  # telebirr, cbe, manual
    reference = db.Column(db.String(100))  # payment ref or admin note
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    # For deposits
    deposit_phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))
    sms_text = db.Column(db.Text)

    # For withdrawals
    withdrawal_phone = db.Column(db.String(20))
    withdrawal_status = db.Column(db.String(20))  # pending, approved, rejected
    admin_note = db.Column(db.Text)

class ScheduledGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    start_time = db.Column(db.DateTime)
    entry_price = db.Column(db.Float, default=10.0)
    status = db.Column(db.String(20), default="pending")  # pending, active, finished
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
