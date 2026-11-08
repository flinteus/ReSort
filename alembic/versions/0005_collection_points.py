"""Add reviewed collection points independently of optional AI integration."""
from alembic import op
import sqlalchemy as sa

revision = "0005_collection_points"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_points",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_code", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("opening_hours", sa.String(1000), nullable=False),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("website", sa.String(2000), nullable=True),
        sa.Column("notes", sa.String(3000), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("source_url", sa.String(2000), nullable=False),
        sa.Column("reviewed_at", sa.Date(), nullable=False),
        sa.Column("reviewed_by", sa.String(200), nullable=False),
        sa.UniqueConstraint("source_code", "external_id", name="uq_collection_point_source"),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name="ck_point_latitude"),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name="ck_point_longitude"),
    )
    op.create_index("ix_collection_points_city", "collection_points", ["city"])
    op.create_index("ix_collection_points_latitude", "collection_points", ["latitude"])
    op.create_table(
        "collection_point_materials",
        sa.Column("point_id", sa.String(36), sa.ForeignKey("collection_points.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("material_code", sa.String(50), primary_key=True),
        sa.Column("region_code", sa.String(50), primary_key=True),
        sa.Column("notes", sa.String(2000), nullable=False),
        sa.ForeignKeyConstraint(["material_code", "region_code"],
                                ["sorting_guidance.material_code", "sorting_guidance.region_code"],
                                name="fk_point_material_guidance", ondelete="RESTRICT"),
    )


def downgrade() -> None:
    op.drop_table("collection_point_materials")
    op.drop_table("collection_points")
