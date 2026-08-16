"""retain async asset-job request payloads"""

from alembic import op
import sqlalchemy as sa


revision = "0003_task7_asset_job_requests"
down_revision = "0002_creative_workspace_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("request_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "request_json")
