"""Punch items, punch photos, and file rows.

Revision ID: 20261019_0004_pf2a
Revises: 20261019_0002_pf0
Create Date: 2026-10-19

down_revision is PR #18's revision 20261019_0002_pf0.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261019_0004_pf2a"
down_revision = "20261019_0002_pf0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(180), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=True),
        sa.Column("storage", sa.String(10), nullable=False, server_default="disk"),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("mime", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
        sa.Column("meta_stripped", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.CheckConstraint("storage IN ('disk','s3')", name="ck_files_storage"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_files_size"),
    )
    op.create_index("ix_files_company_updated", "files", ["company_id", "updated_at"])
    op.create_index("ix_files_company_sha", "files", ["company_id", "sha256"])

    op.create_table(
        "punch_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(180), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False, server_default=""),
        sa.Column("trade", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assignee_id", sa.String(80), nullable=True),
        sa.Column("due_date", sa.String(10), nullable=True),
        sa.Column("author_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("closed_by", sa.String(80), nullable=True),
        sa.Column("closed_at", sa.String(40), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.CheckConstraint("status IN ('open','fixed','accepted','returned')", name="ck_punch_items_status"),
    )
    op.create_index("ix_punch_items_company_updated", "punch_items", ["company_id", "updated_at"])
    op.create_index(
        "ix_punch_items_project_status_due",
        "punch_items",
        ["project_id", "status", "due_date"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_punch_items_assignee_status",
        "punch_items",
        ["assignee_id", "status"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "punch_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(180), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("punch_id", sa.String(36), nullable=False),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("sort_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(40), nullable=True),
        sa.CheckConstraint("phase IN ('before','after')", name="ck_punch_photos_phase"),
    )
    op.create_index("ix_punch_photos_company_updated", "punch_photos", ["company_id", "updated_at"])
    op.create_index(
        "ix_punch_photos_punch_phase",
        "punch_photos",
        ["punch_id", "phase"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("punch_photos")
    op.drop_table("punch_items")
    op.drop_table("files")
