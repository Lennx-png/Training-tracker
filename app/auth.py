import hashlib
import os
from itsdangerous import URLSafeTimedSerializer
from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from app import models

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
SERIALIZER = URLSafeTimedSerializer(SECRET_KEY)
COOKIE_NAME = "session_user"
COOKIE_MAX_AGE = 86400 * 30


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def create_session(user_id: int) -> str:
    return SERIALIZER.dumps(str(user_id))


def get_session_user_id(request: Request) -> int | None:
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return None
    try:
        return int(SERIALIZER.loads(cookie, max_age=COOKIE_MAX_AGE))
    except Exception:
        return None


def register_user(db: Session, name: str, pin: str) -> models.User | None:
    existing = db.query(models.User).filter(models.User.name == name).first()
    if existing:
        return None
    user = models.User(name=name, pin_hash=hash_pin(pin))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, name: str, pin: str) -> models.User | None:
    user = db.query(models.User).filter(models.User.name == name).first()
    if not user:
        return None
    if user.pin_hash != hash_pin(pin):
        return None
    return user
