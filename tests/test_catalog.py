"""Structural checks do not assert that external sources have been editorially reviewed."""
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.sorting import GuidanceImport

CATALOG = Path(__file__).resolve().parents[1] / "catalog" / "waste-guidance.json"


def test_catalog_has_unique_materials_and_valid_structure():
    records = json.loads(CATALOG.read_text(encoding="utf-8"))
    assert len(records) == 13
    assert len({(r["material_code"], r["region_code"]) for r in records}) == len(records)
    checked = TypeAdapter(list[GuidanceImport]).validate_python(records)
    assert {r.category_code for r in checked} == {"paper", "glass", "metal", "plastic", "hazardous", "electronics", "organic"}
    assert all(r.region_code == "general" for r in checked)
    assert all(str(source.url).startswith("https://www.epa.gov/") for r in checked for source in r.sources)


def test_catalog_requires_review_metadata():
    records = json.loads(CATALOG.read_text(encoding="utf-8"))
    del records[0]["reviewed_at"]
    with pytest.raises(ValidationError):
        TypeAdapter(list[GuidanceImport]).validate_python(records)
