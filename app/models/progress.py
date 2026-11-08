from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SortingEvent(Base):
    __tablename__ = "sorting_events"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_sorting_event_idempotency"),
        UniqueConstraint("photo_reference", name="uq_sorting_event_photo"),
        ForeignKeyConstraint(["material_code", "region_code"],
                             ["sorting_guidance.material_code", "sorting_guidance.region_code"],
                             name="fk_sorting_event_material", ondelete="RESTRICT"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    photo_id: Mapped[str | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    # Immutable reference keeps duplicate protection after the photo is deleted.
    photo_reference: Mapped[str] = mapped_column(String(36))
    material_code: Mapped[str] = mapped_column(String(50))
    region_code: Mapped[str] = mapped_column(String(50))
    material_name: Mapped[str] = mapped_column(String(200))
    category_code: Mapped[str] = mapped_column(String(50))
    collection_point_id: Mapped[str | None] = mapped_column(ForeignKey("collection_points.id", ondelete="SET NULL"), nullable=True)
    collection_point_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Achievement(Base):
    __tablename__ = "achievements"
    __table_args__ = (
        CheckConstraint("target > 0", name="ck_achievement_target"),
        CheckConstraint("metric IN ('sorting_count', 'distinct_materials')", name="ck_achievement_metric"),
    )

    code: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(1000))
    metric: Mapped[str] = mapped_column(String(50))
    target: Mapped[int]


class UserAchievement(Base):
    __tablename__ = "user_achievements"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement_code: Mapped[str] = mapped_column(ForeignKey("achievements.code", ondelete="RESTRICT"), primary_key=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("sorting_events.id", ondelete="SET NULL"), nullable=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
