import os
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

def init_db(app):
    # ✅ Load database URI from environment
    db_uri = os.environ.get("DATABASE_URL")
    if not db_uri:
        raise RuntimeError("DATABASE_URL environment variable not set.")

    # ✅ Optional: Log connection for debugging
    print(f"Connecting to database: {db_uri}")

    # ✅ Configure SQLAlchemy
    app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

    # ✅ Initialize DB with app
    db.init_app(app)

    # ✅ Create tables inside app context
    with app.app_context():
        import models  # Avoid circular imports
        db.create_all()

# ✅ Expose for Alembic and other modules
__all__ = ["db", "Base"]
