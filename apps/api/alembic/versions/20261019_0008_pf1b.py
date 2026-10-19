"""Sheet markups.

Revision ID: 20261019_0008_pf1b
Revises: 20261019_0003_pf1a
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0008_pf1b"
down_revision = "20261019_0003_pf1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "markups",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("drawing_revisions.id"), nullable=False),
        sa.Column("author_id", sa.String(length=80), nullable=False),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("shapes", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_markups_company_updated", "markups", ["company_id", "updated_at"])
    op.create_index("ix_markups_revision_created", "markups", ["revision_id", "created_at"])
    op.create_index("ix_markups_file_id", "markups", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_markups_file_id", table_name="markups")
    op.drop_index("ix_markups_revision_created", table_name="markups")
    op.drop_index("ix_markups_company_updated", table_name="markups")
    op.drop_table("markups")
