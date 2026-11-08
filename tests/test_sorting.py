from contextlib import contextmanager
from datetime import date
import importlib
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.sorting import SortingGuidance
from test_auth import auth_client, headers, register_and_login  # noqa: F401


@pytest.fixture
def sorting_client(auth_client):
    client, db = auth_client
    _, _, tokens = register_and_login(client)
    client.headers.update(headers(tokens))
    record = {
        "material_code": "test_pet", "category_code": "plastic",
        "material_name": "Test material", "region_code": "general",
        "preparation_steps": ["Test reviewed instruction"],
        "restrictions": ["Test restriction"],
        "environmental_impact": "Test reviewed environmental description",
        "sources": [{"title": "Test source", "url": "https://example.com/reference"}],
        "reviewed_by": "Test editor", "reviewed_at": date(2026, 1, 1),
    }
    db.add(SortingGuidance(**record))
    db.commit()
    return client, db, record


def payload(**changes):
    recognition = {"item_name": "Бутылка", "category_code": "plastic", "material_code": "test_pet",
                   "needs_clarification": False}
    recognition.update(changes)
    return {"recognition": recognition}


def test_guidance_comes_from_directory(sorting_client):
    client, _, record = sorting_client
    response = client.post("/api/v1/sorting/recommendation", json=payload())
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ready"
    for key in ["preparation_steps", "restrictions", "environmental_impact", "sources"]:
        assert result["guidance"][key] == record[key]
    assert result["guidance"]["reviewed_at"] == "2026-01-01"
    assert "reviewed_by" not in result["guidance"]


def test_unknown_material_and_region(sorting_client):
    client, _, _ = sorting_client
    for body in [payload(material_code="unknown"), {**payload(), "region_code": "unknown_region"}]:
        response = client.post("/api/v1/sorting/recommendation", json=body)
        assert response.status_code == 200
        assert response.json()["status"] == "rules_not_available"
        assert response.json()["guidance"] is None


def test_clarification_prevents_guidance(sorting_client):
    client, _, _ = sorting_client
    for body in [payload(material_code=None), payload(needs_clarification=True,
                                                      clarification_question="Какая маркировка?")]:
        result = client.post("/api/v1/sorting/recommendation", json=body).json()
        assert result["status"] == "needs_clarification"
        assert result["clarification_question"]
        assert result["guidance"] is None


def test_category_mismatch(sorting_client):
    client, _, _ = sorting_client
    assert client.post("/api/v1/sorting/recommendation", json=payload(category_code="glass")).status_code == 422


@pytest.mark.parametrize("changes", [
    {"needs_clarification": True},
    {"needs_clarification": "false"},
    {"item_name": " "},
    {"material_code": "INVALID CODE"},
    {"preparation_steps": ["Untrusted AI instruction"]},
    {"clarification_question": "Question without clarification flag"},
])
def test_recognition_contract(sorting_client, changes):
    client, _, _ = sorting_client
    assert client.post("/api/v1/sorting/recommendation", json=payload(**changes)).status_code == 422


def test_materials_are_region_scoped(sorting_client):
    client, _, _ = sorting_client
    records = client.get("/api/v1/waste/materials").json()
    assert any(r["material_code"] == "test_pet" for r in records)
    assert client.get("/api/v1/waste/materials?region_code=unknown_region").json() == []


def test_sorting_requires_login(sorting_client):
    client, _, _ = sorting_client
    del client.headers["Authorization"]
    assert client.get("/api/v1/waste/materials").status_code == 401
    assert client.post("/api/v1/sorting/recommendation", json=payload()).status_code == 401


def test_import_is_repeatable_and_validated(sorting_client, tmp_path, monkeypatch):
    _, db, record = sorting_client
    importer = importlib.import_module("app.cli.import_guidance")

    class Transaction:
        @staticmethod
        @contextmanager
        def begin():
            yield db
            db.flush()

    monkeypatch.setattr(importer, "SessionLocal", Transaction)
    data = {**record, "reviewed_at": "2026-01-01", "material_code": "imported_test"}
    path = tmp_path / "guidance.json"
    path.write_text(json.dumps([data]))
    assert importer.import_guidance(path) == 1
    data["preparation_steps"] = ["Updated reviewed instruction"]
    path.write_text(json.dumps([data]))
    assert importer.import_guidance(path) == 1
    assert db.scalar(select(func.count()).select_from(SortingGuidance).where(
        SortingGuidance.material_code == "imported_test")) == 1
    assert db.scalar(select(SortingGuidance).where(
        SortingGuidance.material_code == "imported_test")).preparation_steps == data["preparation_steps"]
    path.write_text(json.dumps([data, data]))
    with pytest.raises(ValueError, match="Duplicate"):
        importer.import_guidance(path)
    path.write_text(json.dumps([{**data, "sources": []}]))
    with pytest.raises(ValidationError):
        importer.import_guidance(path)
