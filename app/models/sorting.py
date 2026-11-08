from datetime import date

from sqlalchemy import JSON, Date, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SortingGuidance(Base):
    __tablename__ = "sorting_guidance"
    __table_args__ = (UniqueConstraint("material_code", "region_code", name="uq_guidance_material_region"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    material_code: Mapped[str] = mapped_column(String(50))
    category_code: Mapped[str] = mapped_column(String(50))
    material_name: Mapped[str] = mapped_column(String(200))
    region_code: Mapped[str] = mapped_column(String(50))
    preparation_steps: Mapped[list[str]] = mapped_column(JSON)
    restrictions: Mapped[list[str]] = mapped_column(JSON)
    environmental_impact: Mapped[str]
    sources: Mapped[list[dict]] = mapped_column(JSON)
    reviewed_by: Mapped[str] = mapped_column(String(200))
    reviewed_at: Mapped[date] = mapped_column(Date)
