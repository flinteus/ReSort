"""Import an editorially reviewed JSON array: python -m app.cli.import_guidance path.json."""
import argparse
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.sorting import SortingGuidance
from app.schemas.sorting import GuidanceImport


def import_guidance(path: Path, *, skip_existing: bool = False) -> int:
    records = TypeAdapter(list[GuidanceImport]).validate_json(path.read_text(encoding="utf-8"))
    keys = [(r.material_code, r.region_code) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate material/region pairs in import")
    imported = 0
    with SessionLocal.begin() as db:
        for record in records:
            existing = db.scalar(select(SortingGuidance).where(
                SortingGuidance.material_code == record.material_code,
                SortingGuidance.region_code == record.region_code,
            ))
            if existing is not None and skip_existing:
                continue
            data = record.model_dump(mode="json")
            data["reviewed_at"] = record.reviewed_at
            if existing is None:
                db.add(SortingGuidance(**data))
            else:
                for key, value in data.items():
                    setattr(existing, key, value)
            imported += 1
    return imported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--skip-existing", action="store_true", help="Preserve existing material/region records")
    args = parser.parse_args()
    print(f"Imported {import_guidance(args.path, skip_existing=args.skip_existing)} guidance records")
