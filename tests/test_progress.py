from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.security import utcnow
from app.db.database import engine
from app.models.collection_point import CollectionPoint, CollectionPointMaterial
from app.models.photo import Photo
from app.models.progress import SortingEvent, UserAchievement
from app.models.user import User
from test_auth import auth_client, headers, register_and_login  # noqa: F401
from test_photos import photo_client, upload  # noqa: F401


@pytest.fixture
def progress_client(photo_client):
    return photo_client


def confirm(client, photo_id, material="pet", key=None, **extra):
    return client.post("/api/v1/sorting-events", headers={"Idempotency-Key": key or str(uuid4())},
                       json={"photo_id": photo_id, "material_code": material, "confirmed": True, **extra})


def test_first_confirmation_and_replay(progress_client):
    client, _ = progress_client
    initial = client.get("/api/v1/users/me/tree").json()
    assert initial["stage"] == "seed" and initial["sorting_count"] == 0
    assert client.get("/api/v1/users/me/achievements").json() == []
    assert len(client.get("/api/v1/achievements").json()) == 4
    photo = upload(client).json()["id"]
    key = str(uuid4())
    response = confirm(client, photo, key=key)
    assert response.status_code == 201
    result = response.json()
    assert result["event"]["photo_id"] == photo
    assert result["tree"]["stage"] == "sprout"
    assert [a["code"] for a in result["awarded_achievements"]] == ["first_sort"]
    repeated = confirm(client, photo, key=key)
    assert repeated.status_code == 200 and repeated.json() == result
    assert confirm(client, photo).status_code == 409
    assert confirm(client, photo, material="paper", key=key).status_code == 409
    assert client.get("/api/v1/users/me/tree").json()["sorting_count"] == 1
    assert client.get("/api/v1/sorting-events").json()["total"] == 1
    assert client.get(f"/api/v1/sorting-events/{result['event']['id']}").json() == result["event"]


def test_milestones_and_tree_stages(progress_client):
    client, _ = progress_client
    expected = {1: "sprout", 2: "sprout", 3: "sapling", 5: "sapling", 6: "young_tree", 10: "young_tree", 11: "mature_tree"}
    awards = []
    for count in range(1, 12):
        photo = upload(client).json()["id"]
        response = confirm(client, photo, material=["pet", "paper", "glass_container"][(count - 1) % 3])
        assert response.status_code == 201
        result = response.json()
        assert result["tree"]["sorting_count"] == count
        if count in expected:
            assert result["tree"]["stage"] == expected[count]
        awards.extend(a["code"] for a in result["awarded_achievements"])
    assert sorted(awards) == ["first_sort", "materials_3", "sorting_10", "sorting_5"]
    tree = client.get("/api/v1/users/me/tree").json()
    assert tree["distinct_materials"] == 3 and tree["unlocked_achievements"] == 4
    assert tree["next_stage_at"] is None and tree["progress_percent"] == 100
    assert len(client.get("/api/v1/users/me/achievements").json()) == 4
    page = client.get("/api/v1/sorting-events?limit=2&offset=3").json()
    assert page["total"] == 11 and len(page["items"]) == 2


def test_photo_deletion_preserves_progress_and_idempotency(progress_client):
    client, _ = progress_client
    photo = upload(client).json()["id"]
    key = str(uuid4())
    event_id = confirm(client, photo, key=key).json()["event"]["id"]
    assert client.delete(f"/api/v1/photos/{photo}").status_code == 204
    assert client.get(f"/api/v1/sorting-events/{event_id}").json()["photo_id"] is None
    assert confirm(client, photo, key=key).status_code == 200
    assert client.get("/api/v1/users/me/tree").json()["sorting_count"] == 1


def test_private_history_and_photo_ownership(progress_client):
    client, _ = progress_client
    photo = upload(client).json()["id"]
    event_id = confirm(client, photo).json()["event"]["id"]
    _, _, other_tokens = register_and_login(client)
    client.headers.update(headers(other_tokens))
    assert confirm(client, photo).status_code == 404
    assert client.get(f"/api/v1/sorting-events/{event_id}").status_code == 404
    assert client.get("/api/v1/sorting-events").json()["total"] == 0
    assert client.get("/api/v1/users/me/tree").json()["sorting_count"] == 0
    del client.headers["Authorization"]
    assert confirm(client, photo).status_code == 401
    assert client.get("/api/v1/users/me/tree").status_code == 401
    assert client.get("/api/v1/users/me/achievements").status_code == 401


@pytest.mark.parametrize("changes", [{"confirmed": False}, {"confirmed": 1}, {"confirmed": "true"}, {"material_code": "INVALID"}, {"awarded_points": 100}])
def test_confirmation_contract(progress_client, changes):
    client, _ = progress_client
    photo = upload(client).json()["id"]
    assert confirm(client, photo, **changes).status_code == 422
    assert client.get("/api/v1/users/me/tree").json()["sorting_count"] == 0


def test_missing_key_and_material(progress_client):
    client, _ = progress_client
    photo = upload(client).json()["id"]
    assert client.post("/api/v1/sorting-events", json={"photo_id": photo, "material_code": "pet", "confirmed": True}).status_code == 422
    assert confirm(client, photo, material="unknown").status_code == 422
    assert confirm(client, photo, region_code="unknown").status_code == 422


def test_point_must_accept_material(progress_client):
    client, db = progress_client
    point = CollectionPoint(id=str(uuid4()), source_code="progress_test", external_id=str(uuid4()),
                            name="Test point", city="Test", address="Test", latitude=0, longitude=0,
                            opening_hours="Test", timezone="UTC", website=None, notes="", is_active=True,
                            source_url="https://example.com", reviewed_at=date(2026, 1, 1), reviewed_by="Test")
    point.materials = [CollectionPointMaterial(material_code="pet", region_code="general", notes="Test restriction")]
    db.add(point); db.commit()
    photo = upload(client).json()["id"]
    assert confirm(client, photo, material="paper", collection_point_id=point.id).status_code == 422
    result = confirm(client, photo, collection_point_id=point.id)
    assert result.status_code == 201
    assert result.json()["event"]["collection_point_name"] == "Test point"
    second_photo = upload(client).json()["id"]
    point.is_active = False; db.commit()
    assert confirm(client, second_photo, collection_point_id=point.id).status_code == 404


def test_transaction_failure_rolls_back_event_and_awards(progress_client, monkeypatch):
    client, db = progress_client
    photo = upload(client).json()["id"]
    user_id = db.get(Photo, photo).user_id
    def fail():
        raise RuntimeError("Simulated commit failure")
    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(RuntimeError, match="Simulated"):
        confirm(client, photo)
    assert db.scalar(select(func.count()).select_from(SortingEvent).where(SortingEvent.user_id == user_id)) == 0
    assert db.scalar(select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user_id)) == 0


def test_concurrent_confirmation_awards_once():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi.testclient import TestClient
    from app.main import app
    user_id = None
    try:
        with TestClient(app) as client:
            _, user, tokens = register_and_login(client)
            user_id = user["id"]
        photo_id = str(uuid4())
        with Session(engine) as db:
            db.add(Photo(id=photo_id, user_id=user_id, width=1, height=1, size_bytes=1, created_at=utcnow()))
            db.commit()
        barrier = Barrier(2)
        key = str(uuid4())
        def send():
            with TestClient(app) as client:
                client.headers.update(headers(tokens))
                barrier.wait(timeout=10)
                return confirm(client, photo_id, key=key)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: send(), range(2)))
        assert sorted(r.status_code for r in results) == [200, 201]
        assert len({r.json()["event"]["id"] for r in results}) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(SortingEvent).where(SortingEvent.user_id == user_id)) == 1
            assert db.scalar(select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user_id)) == 1
    finally:
        if user_id:
            with Session(engine) as db:
                db.execute(delete(User).where(User.id == user_id)); db.commit()
