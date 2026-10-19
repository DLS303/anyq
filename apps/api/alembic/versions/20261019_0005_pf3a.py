"""Designer questions, external contacts, and reply links.

Revision ID: 20261019_0005_pf3a
Revises: 20261019_0002_pf0
Create Date: 2026-10-19

down_revision is the company feature-flag revision. A later merge joins wave-1 heads.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0005_pf3a"
down_revision = "20261019_0002_pf0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_contacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("author_id", sa.String(length=80), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("phone_e164", sa.String(length=32), nullable=True),
        sa.Column("phone_hash", sa.String(length=64), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("organization", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_external_contacts_company_updated",
        "external_contacts",
        ["company_id", "updated_at"],
    )
    op.create_table(
        "rfis",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_user_id", sa.String(length=80), nullable=True),
        sa.Column("assignee_contact_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignee_contact_id"],
            ["external_contacts.id"],
            name="fk_rfis_assignee_contact",
        ),
        sa.UniqueConstraint("project_id", "number", name="uq_rfis_project_number"),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("drawing_revision_id", sa.String(length=80), nullable=True),
        sa.Column("attachments", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(length=80), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("answered_at", sa.String(length=40), nullable=True),
        sa.Column("answered_via_token_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_rfis_company_updated", "rfis", ["company_id", "updated_at"])
    op.create_index(
        "ix_rfis_project_status_due",
        "rfis",
        ["project_id", "status", "due_date"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "access_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["rfis.id"], name="fk_access_tokens_entity"),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("used_at", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_access_tokens_token_sha256", "access_tokens", ["token_sha256"], unique=True)
    op.create_index("ix_access_tokens_company_updated", "access_tokens", ["company_id", "updated_at"])
    op.create_index("ix_access_tokens_entity_id", "access_tokens", ["entity_id"])
    op.create_table(
        "rfi_files",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("rfi_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["rfi_id"], ["rfis.id"], name="fk_rfi_files_rfi"),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "uq_rfi_files_rfi_file",
        "rfi_files",
        ["rfi_id", "file_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_rfi_files_company_updated", "rfi_files", ["company_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_rfi_files_company_updated", table_name="rfi_files")
    op.drop_index("uq_rfi_files_rfi_file", table_name="rfi_files")
    op.drop_table("rfi_files")
    op.drop_index("ix_access_tokens_entity_id", table_name="access_tokens")
    op.drop_index("ix_access_tokens_company_updated", table_name="access_tokens")
    op.drop_index("ix_access_tokens_token_sha256", table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_index("ix_rfis_project_status_due", table_name="rfis")
    op.drop_index("ix_rfis_company_updated", table_name="rfis")
    op.drop_table("rfis")
    op.drop_index("ix_external_contacts_company_updated", table_name="external_contacts")
    op.drop_table("external_contacts")
