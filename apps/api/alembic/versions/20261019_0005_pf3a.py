"""Designer questions, external contacts, and reply links.

Revision ID: 20261019_0005_pf3a
Revises: 20261019_0002
Create Date: 2026-10-19

down_revision is PR #18 (20261019_0002). A later merge revision joins wave-1 heads.
"""

import sqlalchemy as sa

from alembic import op
from app.sql_backend import install_audit_guards

revision = "20261019_0005_pf3a"
down_revision = "20261019_0002"
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
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("drawing_revision_id", sa.String(length=80), nullable=True),
        sa.Column("attachments", sa.Text(), nullable=False),
        sa.Column("author_id", sa.String(length=80), nullable=False),
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
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("used_at", sa.String(length=40), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_access_tokens_token_sha256", "access_tokens", ["token_sha256"], unique=True)
    op.create_index("ix_access_tokens_company_updated", "access_tokens", ["company_id", "updated_at"])
    op.add_column("audit_log", sa.Column("entity_type", sa.String(length=64), nullable=True))
    op.add_column("audit_log", sa.Column("entity_id", sa.String(length=36), nullable=True))
    op.add_column("audit_log", sa.Column("project_id", sa.String(length=80), nullable=True))
    op.add_column("audit_log", sa.Column("changes", sa.Text(), nullable=True))
    install_audit_guards(op.get_bind())


def downgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("changes")
        batch.drop_column("project_id")
        batch.drop_column("entity_id")
        batch.drop_column("entity_type")
    install_audit_guards(op.get_bind())
    op.drop_index("ix_access_tokens_company_updated", table_name="access_tokens")
    op.drop_index("ix_access_tokens_token_sha256", table_name="access_tokens")
    op.drop_table("access_tokens")
    op.drop_index("ix_rfis_project_status_due", table_name="rfis")
    op.drop_index("ix_rfis_company_updated", table_name="rfis")
    op.drop_table("rfis")
    op.drop_index("ix_external_contacts_company_updated", table_name="external_contacts")
    op.drop_table("external_contacts")
