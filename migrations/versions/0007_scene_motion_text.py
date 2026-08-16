"""store descriptive scene motion as text

Revision ID: 0007_scene_motion_text
Revises: 0006_shot_spec
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_scene_motion_text"
down_revision = "0006_shot_spec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "scenes",
        "motion",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "scenes",
        "motion",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
