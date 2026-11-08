"""Import reviewed collection points from a UTF-8 JSON array."""
import argparse
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.collection_point import CollectionPoint, CollectionPointMaterial
from app.models.sorting import SortingGuidance
from app.schemas.collection_point import CollectionPointImport


def import_collection_points(path: Path, *, skip_existing: bool = False) -> int:
    records = TypeAdapter(list[CollectionPointImport]).validate_json(path.read_text(encoding="utf-8"))
    keys = [(r.source_code, r.external_id) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate source_code/external_id pairs")
    imported = 0
    with SessionLocal.begin() as db:
        known = set(db.execute(select(SortingGuidance.material_code, SortingGuidance.region_code)).all())
        missing = {(m.material_code, m.region_code) for r in records for m in r.accepted_materials} - known
        if missing:
            raise ValueError(f"Unknown material/region pairs: {sorted(missing)}")
        for record in records:
            point = db.scalar(select(CollectionPoint).where(
                CollectionPoint.source_code == record.source_code, CollectionPoint.external_id == record.external_id))
            if point is not None and skip_existing:
                continue
            data = record.model_dump(exclude={"accepted_materials"}, mode="json")
            data["reviewed_at"] = record.reviewed_at
            if point is None:
                point = CollectionPoint(id=str(uuid4()), **data)
                db.add(point)
            else:
                for name, value in data.items():
                    setattr(point, name, value)
                # Flush removal before inserting replacement association keys.
                point.materials.clear()
                db.flush()
            point.materials = [CollectionPointMaterial(**m.model_dump()) for m in record.accepted_materials]
            imported += 1
    return imported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()
    print(f"Imported {import_collection_points(args.path, skip_existing=args.skip_existing)} collection points")
