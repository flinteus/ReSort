from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Float, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.sorting import SortingGuidance


class CollectionPoint(Base):
    __tablename__ = "collection_points"
    __table_args__ = (
        UniqueConstraint("source_code", "external_id", name="uq_collection_point_source"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_point_latitude"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_point_longitude"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_code: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100), index=True)
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[float] = mapped_column(Float, index=True)
    longitude: Mapped[float] = mapped_column(Float)
    opening_hours: Mapped[str] = mapped_column(String(1000))
    timezone: Mapped[str] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    notes: Mapped[str] = mapped_column(String(3000))
    is_active: Mapped[bool] = mapped_column(Boolean)
    source_url: Mapped[str] = mapped_column(String(2000))
    reviewed_at: Mapped[date] = mapped_column(Date)
    reviewed_by: Mapped[str] = mapped_column(String(200))
    materials: Mapped[list["CollectionPointMaterial"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="CollectionPointMaterial.material_code",
    )


class CollectionPointMaterial(Base):
    __tablename__ = "collection_point_materials"
    __table_args__ = (ForeignKeyConstraint(
        ["material_code", "region_code"], ["sorting_guidance.material_code", "sorting_guidance.region_code"],
        name="fk_point_material_guidance", ondelete="RESTRICT",
    ),)

    point_id: Mapped[str] = mapped_column(ForeignKey("collection_points.id", ondelete="CASCADE"), primary_key=True)
    material_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    region_code: Mapped[str] = mapped_column(String(50), primary_key=True)
    notes: Mapped[str] = mapped_column(String(2000))
    guidance: Mapped[SortingGuidance] = relationship(lazy="selectin")
