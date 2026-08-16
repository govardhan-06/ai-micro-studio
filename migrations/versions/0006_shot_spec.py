"""persist validated per-scene ShotSpec JSON"""

from alembic import op
import sqlalchemy as sa


revision = "0006_shot_spec"
down_revision = "0005_task11_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenes", sa.Column("shot_spec_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenes", "shot_spec_json")
