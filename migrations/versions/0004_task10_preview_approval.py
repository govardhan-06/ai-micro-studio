"""persist explicit preview approval before final export"""

from alembic import op
import sqlalchemy as sa


revision = "0004_task10_preview_approval"
down_revision = "0003_task7_asset_job_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("renders", sa.Column("preview_approved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("renders", "preview_approved_at")
