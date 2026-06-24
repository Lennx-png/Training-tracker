from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./training.db")

if DATABASE_URL.startswith("postgres"):
    engine = create_engine(DATABASE_URL)
else:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def run_migrations():
    from app import models

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "users" not in tables:
        Base.metadata.create_all(bind=engine)
        return

    existing_cols = {c["name"] for c in inspector.get_columns("workouts")}
    if "user_id" not in existing_cols:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE workouts ADD COLUMN user_id INTEGER"))
            conn.commit()

    if "timer_started_at" not in existing_cols:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE workouts ADD COLUMN timer_started_at TIMESTAMP"))
            conn.commit()

    existing_cols_we = {c["name"] for c in inspector.get_columns("weight_entries")}
    if "user_id" not in existing_cols_we:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE weight_entries ADD COLUMN user_id INTEGER"))
            conn.commit()

    db = SessionLocal()
    try:
        default_user = db.query(models.User).filter(models.User.name == "Admin").first()
        if not default_user:
            from app.auth import hash_pin
            default_user = models.User(name="Admin", pin_hash=hash_pin("1234"))
            db.add(default_user)
            db.commit()
            db.refresh(default_user)
        for table, model_cls in [("workouts", models.Workout), ("weight_entries", models.WeightEntry)]:
            null_records = db.query(model_cls).filter(model_cls.user_id.is_(None)).all()
            for rec in null_records:
                rec.user_id = default_user.id
            if null_records:
                db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
