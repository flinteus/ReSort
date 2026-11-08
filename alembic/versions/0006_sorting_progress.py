"""Add sorting confirmations, achievements and persisted awards."""
from alembic import op
import sqlalchemy as sa

revision = "0006_sorting_progress"
down_revision = "0005_collection_points"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sorting_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("photo_id", sa.String(36), sa.ForeignKey("photos.id", ondelete="SET NULL"), nullable=True),
        sa.Column("photo_reference", sa.String(36), nullable=False),
        sa.Column("material_code", sa.String(50), nullable=False),
        sa.Column("region_code", sa.String(50), nullable=False),
        sa.Column("material_name", sa.String(200), nullable=False),
        sa.Column("category_code", sa.String(50), nullable=False),
        sa.Column("collection_point_id", sa.String(36), sa.ForeignKey("collection_points.id", ondelete="SET NULL"), nullable=True),
        sa.Column("collection_point_name", sa.String(200), nullable=True),
        sa.Column("idempotency_key", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_sorting_event_idempotency"),
        sa.UniqueConstraint("photo_reference", name="uq_sorting_event_photo"),
        sa.ForeignKeyConstraint(["material_code", "region_code"],
                                ["sorting_guidance.material_code", "sorting_guidance.region_code"],
                                name="fk_sorting_event_material", ondelete="RESTRICT"),
    )
    op.create_index("ix_sorting_events_user_id", "sorting_events", ["user_id"])
    definitions = op.create_table(
        "achievements",
        sa.Column("code", sa.String(50), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.CheckConstraint("target > 0", name="ck_achievement_target"),
        sa.CheckConstraint("metric IN ('sorting_count', 'distinct_materials')", name="ck_achievement_metric"),
    )
    op.bulk_insert(definitions, [
        {"code": "first_sort", "name": "Первый шаг", "description": "Подтвердить первую сортировку", "metric": "sorting_count", "target": 1},
        {"code": "sorting_5", "name": "Полезная привычка", "description": "Подтвердить пять сортировок", "metric": "sorting_count", "target": 5},
        {"code": "sorting_10", "name": "Забота о природе", "description": "Подтвердить десять сортировок", "metric": "sorting_count", "target": 10},
        {"code": "materials_3", "name": "Знаток материалов", "description": "Отсортировать три разных материала", "metric": "distinct_materials", "target": 3},
    ])
    op.create_table(
        "user_achievements",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("achievement_code", sa.String(50), sa.ForeignKey("achievements.code", ondelete="RESTRICT"), primary_key=True),
        sa.Column("event_id", sa.String(36), sa.ForeignKey("sorting_events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("sorting_events")
