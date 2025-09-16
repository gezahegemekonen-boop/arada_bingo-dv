from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False, index=True)
    username = db.Column(db.String(64))
    phone = db.Column(db.String(20))
    balance = db.Column(db.Float, default=0.0)
    games_played = db.Column(db.Integer, default=0)
    games_won = db.Column(db.Integer, default=0)
    sound_enabled = db.Column(db.Boolean, default=True)
    play_mode = db.Column(db.String(10), default="auto")
    language = db.Column(db.String(10), default="en")
    referrer_id = db.Column(db.BigInteger, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)  # ✅ Admin role support
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='user', lazy=True)
    game_entries = db.relationship('GameParticipant', backref='user', lazy=True)
    won_games = db.relationship('Game', backref='winner', lazy=True)
    scheduled_games = db.relationship('ScheduledGame', backref='creator', lazy=True)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), default='waiting', index=True)
    entry_price = db.Column(db.Float, nullable=False)
    pool = db.Column(db.Float, default=0.0)
    payout = db.Column(db.Float, default=0.0)
    commission = db.Column(db.Float, default=0.0)
    called_numbers = db.Column(db.PickleType)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants = db.relationship('GameParticipant', backref='game', lazy=True)

class GameParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    cartela_number = db.Column(db.Integer, nullable=False)
    cartela_count = db.Column(db.Integer, default=1)  # ✅ Multi-cartela support
    marked_numbers = db.Column(db.PickleType)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('game_id', 'cartela_number', name='unique_cartela_per_game'),
    )

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(20), index=True)  # deposit, withdrawal, payout
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    method = db.Column(db.String(20))  # e.g. Telebirr, CBE, manual
    reference = db.Column(db.String(100))
    reason = db.Column(db.String(200))  # ✅ Admin rejection reason
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deposit_phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))
    sms_text = db.Column(db.Text)

    withdrawal_phone = db.Column(db.String(20))
    withdrawal_status = db.Column(db.String(20))
    admin_note = db.Column(db.Text)

class ScheduledGame(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # ✅ Track who scheduled it
    start_time = db.Column(db.DateTime)
    entry_price = db.Column(db.Float, default=10.0)
    status = db.Column(db.String(20), default="pending", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ✅ Indexes for performance
db.Index('ix_game_created_at', Game.created_at)
db.Index('ix_transaction_created_at', Transaction.created_at)
