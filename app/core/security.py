import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hasher = PasswordHash.recommended()
DUMMY_HASH = password_hasher.hash("dummy-password-for-timing")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(user_id: int, session_id: str) -> str:
    now = utcnow()
    return jwt.encode(
        {"sub": str(user_id), "sid": session_id, "type": "access", "iat": now,
         "exp": now + timedelta(minutes=settings.access_token_minutes)},
        settings.jwt_secret_key.get_secret_value(), algorithm="HS256",
    )
