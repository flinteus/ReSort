from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_refresh, utcnow
from app.db.database import engine
from app.db.dependecy import get_db
from app.main import app
from app.models.user import AuthSession, User


@pytest.fixture
def auth_client():
    # Each request commits normally into a savepoint; outer rollback leaves no test users.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            app.dependency_overrides[get_db] = lambda: db
            try:
                with TestClient(app) as client:
                    yield client, db
            finally:
                app.dependency_overrides.pop(get_db, None)
                transaction.rollback()


def register_and_login(client):
    creds = {"username": "User_" + uuid4().hex[:12], "password": "correct-password"}
    registered = client.post("/api/v1/auth/register", json=creds)
    assert registered.status_code == 201
    assert set(registered.json()) == {"id", "username"}
    login = client.post("/api/v1/auth/login", json=creds)
    assert login.status_code == 200
    assert login.headers["cache-control"] == "no-store"
    return creds, registered.json(), login.json()


def headers(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def test_full_auth_flow(auth_client):
    client, db = auth_client
    creds, user, tokens = register_and_login(client)
    stored = db.get(User, user["id"])
    assert stored.password_hash.startswith("$argon2")
    assert stored.password_hash != creds["password"]
    assert client.get("/api/v1/users/me", headers=headers(tokens)).json() == user
    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user["id"]))
    assert session.refresh_hash == hash_refresh(tokens["refresh_token"])
    assert session.refresh_hash != tokens["refresh_token"]
    renewed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert renewed.status_code == 200
    new_tokens = renewed.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=headers(new_tokens)).status_code == 204
    assert client.get("/api/v1/users/me", headers=headers(tokens)).status_code == 401
    assert client.get("/api/v1/users/me", headers=headers(new_tokens)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": new_tokens["refresh_token"]}).status_code == 401


def test_duplicate_username_and_bad_password(auth_client):
    client, _ = auth_client
    creds, _, _ = register_and_login(client)
    assert client.post("/api/v1/auth/register", json={**creds, "username": creds["username"].upper()}).status_code == 409
    assert client.post("/api/v1/auth/login", json={**creds, "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={**creds, "username": "missing_" + uuid4().hex}).status_code == 401


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": "long-password"},
    {"username": "with space", "password": "long-password"},
    {"username": "valid_name", "password": "short"},
    {"username": "valid_name", "password": "x" * 129},
])
def test_registration_validation(auth_client, body):
    client, _ = auth_client
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_invalid_and_expired_access(auth_client):
    client, _ = auth_client
    _, _, tokens = register_and_login(client)
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    payload = jwt.decode(tokens["access_token"], settings.jwt_secret_key.get_secret_value(), algorithms=["HS256"])
    payload["exp"] = utcnow() - timedelta(seconds=1)
    expired = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + expired}).status_code == 401
    payload["exp"] = utcnow() + timedelta(minutes=1)
    forged = jwt.encode(payload, "different-key-that-is-at-least-32-bytes", algorithm="HS256")
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + forged}).status_code == 401


def test_expired_refresh_and_session_isolation(auth_client):
    client, db = auth_client
    _, _, tokens = register_and_login(client)
    _, other_user, other_tokens = register_and_login(client)
    session = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == hash_refresh(tokens["refresh_token"])))
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/users/me", headers=headers(tokens)).status_code == 401
    assert client.get("/api/v1/users/me", headers=headers(other_tokens)).json() == other_user


def test_legacy_user_has_no_password(auth_client):
    client, db = auth_client
    username = "legacy_" + uuid4().hex[:12]
    db.add(User(username=username))
    db.commit()
    assert client.post("/api/v1/auth/login", json={"username": username, "password": "anything"}).status_code == 401


def test_logout_preserves_other_login(auth_client):
    client, _ = auth_client
    creds, user, first = register_and_login(client)
    second = client.post("/api/v1/auth/login", json=creds).json()
    assert client.post("/api/v1/auth/logout", headers=headers(first)).status_code == 204
    assert client.get("/api/v1/users/me", headers=headers(second)).json() == user


def test_concurrent_refresh_uses_token_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import delete

    # Independent committed sessions are required to exercise PostgreSQL row locks.
    user_id = None
    try:
        with TestClient(app) as client:
            _, user, tokens = register_and_login(client)
            user_id = user["id"]
        barrier = Barrier(2)

        def refresh():
            with TestClient(app) as client:
                barrier.wait(timeout=10)
                return client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: refresh(), range(2))) == [200, 401]
    finally:
        if user_id is not None:
            with Session(engine) as db:
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
