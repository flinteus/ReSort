import secrets
from datetime import timedelta
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import DUMMY_HASH, create_access_token, hash_refresh, password_hasher, utcnow
from app.db.dependecy import get_db
from app.models.user import AuthSession, User
from app.schemas.auth import RefreshRequest, TokenResponse, UserLoginSchema, UserRegisterSchema, UserResponse

router = APIRouter(tags=["auth"])
bearer = HTTPBearer(auto_error=False)
Database = Annotated[Session, Depends(get_db)]


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid credentials or expired session",
                         headers={"WWW-Authenticate": "Bearer"})


def token_response(user_id: int, session_id: str, refresh: str, response: Response) -> TokenResponse:
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=create_access_token(user_id, session_id),
                         refresh_token=refresh, expires_in=settings.access_token_minutes * 60)


def current_session(
    db: Database,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AuthSession:
    if credentials is None:
        raise unauthorized()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key.get_secret_value(),
                             algorithms=["HS256"], options={"require": ["sub", "sid", "exp", "iat", "type"]})
        if payload["type"] != "access" or not isinstance(payload["sid"], str):
            raise unauthorized()
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise unauthorized() from None
    session = db.scalar(select(AuthSession).where(AuthSession.id == payload["sid"],
                                                AuthSession.user_id == user_id,
                                                AuthSession.expires_at > utcnow()))
    if session is None:
        raise unauthorized()
    return session


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(creds: UserRegisterSchema, db: Database):
    user = User(username=creds.username.lower(), password_hash=password_hasher.hash(creds.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already registered") from None
    db.refresh(user)
    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(creds: UserLoginSchema, response: Response, db: Database):
    user = db.scalar(select(User).where(User.username == creds.username.lower()))
    stored_hash = user.password_hash if user and user.password_hash else DUMMY_HASH
    valid = password_hasher.verify(creds.password, stored_hash)
    if not valid or user is None or user.password_hash is None:
        raise unauthorized()
    refresh = secrets.token_urlsafe(48)
    session = AuthSession(id=str(uuid4()), user_id=user.id, refresh_hash=hash_refresh(refresh),
                          expires_at=utcnow() + timedelta(days=settings.refresh_token_days))
    db.add(session)
    db.commit()
    return token_response(user.id, session.id, refresh, response)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(creds: RefreshRequest, response: Response, db: Database):
    # A row lock serializes concurrent refreshes: an old token is usable only once.
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == hash_refresh(creds.refresh_token),
                                                AuthSession.expires_at > utcnow()).with_for_update())
    if session is None:
        raise unauthorized()
    refresh = secrets.token_urlsafe(48)
    session.refresh_hash = hash_refresh(refresh)
    db.commit()
    return token_response(session.user_id, session.id, refresh, response)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_user(db: Database, session: Annotated[AuthSession, Depends(current_session)]):
    db.execute(delete(AuthSession).where(AuthSession.id == session.id))
    db.commit()
    return Response(status_code=204)


@router.get("/users/me", response_model=UserResponse)
def current_user(db: Database, session: Annotated[AuthSession, Depends(current_session)]):
    user = db.get(User, session.user_id)
    if user is None:
        raise unauthorized()
    return user
