"""Add reviewed sorting guidance directory."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sorting_guidance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_code", sa.String(50), nullable=False),
        sa.Column("category_code", sa.String(50), nullable=False),
        sa.Column("material_name", sa.String(200), nullable=False),
        sa.Column("region_code", sa.String(50), nullable=False),
        sa.Column("preparation_steps", sa.JSON(), nullable=False),
        sa.Column("restrictions", sa.JSON(), nullable=False),
        sa.Column("environmental_impact", sa.String(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("reviewed_by", sa.String(200), nullable=False),
        sa.Column("reviewed_at", sa.Date(), nullable=False),
        sa.UniqueConstraint("material_code", "region_code", name="uq_guidance_material_region"),
    )


def downgrade() -> None:
    op.drop_table("sorting_guidance")
