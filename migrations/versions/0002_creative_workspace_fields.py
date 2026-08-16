"""retain idea selection and story critique metadata"""

from alembic import op
import sqlalchemy as sa


revision = "0002_creative_workspace_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("idea_candidates", sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("story_versions", sa.Column("critique", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("story_versions", "critique")
    op.drop_column("idea_candidates", "is_selected")
