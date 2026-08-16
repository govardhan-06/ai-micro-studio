"""persist job observability and creator rejection reasons"""

from alembic import op
import sqlalchemy as sa


revision = "0005_task11_observability"
down_revision = "0004_task10_preview_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("story_versions", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("generation_jobs", sa.Column("latency_ms", sa.Float(), nullable=True))
    op.add_column("generation_jobs", sa.Column("outcome", sa.String(length=32), nullable=True))
    op.add_column("generation_jobs", sa.Column("usage_json", sa.JSON(), nullable=True))
    op.add_column("generation_jobs", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("generation_jobs", sa.Column("regeneration_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(
        "generation_jobs",
        sa.Column("timeline_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "timeline_json")
    op.drop_column("generation_jobs", "regeneration_count")
    op.drop_column("generation_jobs", "cost_usd")
    op.drop_column("generation_jobs", "usage_json")
    op.drop_column("generation_jobs", "outcome")
    op.drop_column("generation_jobs", "latency_ms")
    op.drop_column("story_versions", "rejection_reason")
