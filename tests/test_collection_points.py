from contextlib import contextmanager
from datetime import date
import importlib
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.collection_point import CollectionPoint, CollectionPointMaterial
from app.models.sorting import SortingGuidance
from test_auth import auth_client  # noqa: F401


@pytest.fixture
def points_client(auth_client):
    client, db = auth_client
    for code, category in [("test_point_paper", "paper"), ("test_point_pet", "plastic"), ("test_point_glass", "glass")]:
        db.add(SortingGuidance(material_code=code, category_code=category, material_name=code,
                              region_code="general", preparation_steps=["Test"], restrictions=[],
                              environmental_impact="Test", sources=[{"title": "Test", "url": "https://example.com"}],
                              reviewed_at=date(2026, 1, 1), reviewed_by="Test"))
    db.flush()
    def point(name, lat, lon, materials, active=True, city="Тестовый город"):
        p = CollectionPoint(id=str(uuid4()), source_code="test", external_id=str(uuid4()), name=name,
                            city=city, address="Тестовый адрес", latitude=lat, longitude=lon,
                            opening_hours="Пн–Пт 10:00–18:00", timezone="Europe/Moscow", website=None,
                            notes="Тестовая запись", is_active=active, source_url="https://example.com/points",
                            reviewed_at=date(2026, 1, 1), reviewed_by="Test")
        p.materials = [CollectionPointMaterial(material_code=code, region_code="general", notes="Только чистые изделия") for code in materials]
        db.add(p)
        return p
    near = point("A nearby", 55.75, 37.61, ["test_point_paper", "test_point_pet"])
    farther = point("B farther", 55.76, 37.61, ["test_point_paper"])
    far = point("C far away", 56.75, 37.61, ["test_point_glass"], city="Другой город")
    inactive = point("D closed", 55.75, 37.61, ["test_point_pet"], active=False)
    db.commit()
    return client, db, point, near, farther, far, inactive


def test_nearby_sorted_by_distance(points_client):
    client, _, _, near, farther, _, _ = points_client
    response = client.get("/api/v1/collection-points?lat=55.75&lon=37.61&radius_m=2000")
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 2
    assert [p["id"] for p in result["items"]] == [near.id, farther.id]
    assert result["items"][0]["distance_m"] == 0
    assert 1100 < result["items"][1]["distance_m"] < 1120
    assert "reviewed_by" not in result["items"][0]
    assert result["items"][0]["accepted_materials"][0]["category_code"]


def test_filters_and_pagination(points_client):
    client, _, _, near, _, _, _ = points_client
    response = client.get("/api/v1/collection-points", params={"material_code": "test_point_pet", "category_code": "plastic"}).json()
    assert response["total"] == 1 and response["items"][0]["id"] == near.id
    assert client.get("/api/v1/collection-points", params={"material_code": "test_point_pet", "category_code": "paper"}).json()["total"] == 0
    assert client.get("/api/v1/collection-points?region_code=unknown").json()["total"] == 0
    response = client.get("/api/v1/collection-points", params={"city": "тестовый город", "limit": 1, "offset": 1}).json()
    assert response["total"] == 2 and len(response["items"]) == 1
    assert response["items"][0]["distance_m"] is None
    assert client.get("/api/v1/collection-points?material_code=unknown").json() == {"items": [], "total": 0}


def test_detail_and_inactive(points_client):
    client, _, _, near, _, _, inactive = points_client
    assert client.get(f"/api/v1/collection-points/{near.id}").status_code == 200
    assert client.get(f"/api/v1/collection-points/{inactive.id}").status_code == 404
    assert client.get(f"/api/v1/collection-points/{uuid4()}").status_code == 404
    assert client.get("/api/v1/collection-points/not-a-uuid").status_code == 422


@pytest.mark.parametrize("query", ["lat=55", "lon=37", "lat=91&lon=37", "lat=55&lon=181", "lat=nan&lon=0",
                                    "lat=0&lon=inf", "radius_m=0", "radius_m=100001", "limit=101", "offset=-1"])
def test_invalid_search(points_client, query):
    client, *_ = points_client
    assert client.get("/api/v1/collection-points?" + query).status_code == 422


def test_dateline_and_poles(points_client):
    client, db, point, *_ = points_client
    dateline = point("Dateline", 0, -179.999, ["test_point_pet"])
    pole = point("Pole", 89.999, -150, ["test_point_pet"])
    db.commit()
    response = client.get("/api/v1/collection-points?lat=0&lon=179.999&radius_m=500").json()
    assert [p["id"] for p in response["items"]] == [dateline.id]
    assert 220 < response["items"][0]["distance_m"] < 225
    response = client.get("/api/v1/collection-points?lat=90&lon=0&radius_m=500").json()
    assert [p["id"] for p in response["items"]] == [pole.id]


def test_import_is_atomic_repeatable_and_preserves_id(points_client, tmp_path, monkeypatch):
    _, db, *_ = points_client
    importer = importlib.import_module("app.cli.import_collection_points")
    class Transaction:
        @staticmethod
        @contextmanager
        def begin():
            yield db
            db.flush()
    monkeypatch.setattr(importer, "SessionLocal", Transaction)
    data = dict(source_code="test", external_id="stable", name="Imported test point", city="Test",
                address="Test address", latitude=0, longitude=0, opening_hours="Check with operator",
                timezone="UTC", source_url="https://example.com", reviewed_at="2026-01-01", reviewed_by="Test",
                accepted_materials=[{"material_code": "test_point_paper"}])
    path = tmp_path / "points.json"
    path.write_text(json.dumps([data]))
    assert importer.import_collection_points(path) == 1
    first = db.scalar(select(CollectionPoint).where(CollectionPoint.external_id == "stable"))
    saved_id = first.id
    data["accepted_materials"] = [{"material_code": "test_point_pet", "notes": "New restriction"}]
    data["name"] = "Updated test point"
    path.write_text(json.dumps([data]))
    assert importer.import_collection_points(path) == 1
    assert first.id == saved_id and first.name == data["name"]
    assert [m.material_code for m in first.materials] == ["test_point_pet"]
    assert db.scalar(select(func.count()).select_from(CollectionPointMaterial).where(CollectionPointMaterial.point_id == saved_id)) == 1
    data["name"] = "Should not replace"
    path.write_text(json.dumps([data]))
    assert importer.import_collection_points(path, skip_existing=True) == 0
    assert first.name == "Updated test point"
    path.write_text(json.dumps([data, data]))
    with pytest.raises(ValueError, match="Duplicate"):
        importer.import_collection_points(path)
    good = {**data, "external_id": "must_not_insert"}
    bad = {**data, "external_id": "unknown", "accepted_materials": [{"material_code": "missing_material"}]}
    path.write_text(json.dumps([good, bad]))
    with pytest.raises(ValueError, match="Unknown"):
        importer.import_collection_points(path)
    assert db.scalar(select(CollectionPoint.id).where(CollectionPoint.external_id == "must_not_insert")) is None
    path.write_text(json.dumps([{**data, "latitude": 95}]))
    with pytest.raises(ValidationError):
        importer.import_collection_points(path)
