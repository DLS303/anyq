"""SQL tables for designer questions.

Registered on the shared metadata so `alembic check` sees them. Revision 0001
skips these names; 0005 creates them with op.create_table.
"""

from __future__ import annotations

from sqlalchemy import Column, Index, Integer, String, Table, Text, text

from app.sql_backend import Base

metadata = Base.metadata

external_contacts = Table(
    "external_contacts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("company_id", String(180), nullable=False),
    Column("project_id", String(80), nullable=False),
    Column("author_id", String(80), nullable=False),
    Column("full_name", String(200)),
    Column("phone_e164", String(32)),
    Column("phone_hash", String(64)),
    Column("email", String(200)),
    Column("organization", String(200)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("row_version", Integer, nullable=False),
    Column("deleted_at", String(40)),
    Index("ix_external_contacts_company_updated", "company_id", "updated_at"),
)

rfis = Table(
    "rfis",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("company_id", String(180), nullable=False),
    Column("project_id", String(80), nullable=False),
    Column("number", String(32), nullable=False),
    Column("title", String(200), nullable=False),
    Column("question", Text, nullable=False),
    Column("answer", Text, nullable=False),
    Column("status", String(20), nullable=False),
    Column("assignee_user_id", String(80)),
    Column("assignee_contact_id", String(36)),
    Column("due_date", String(10)),
    Column("drawing_revision_id", String(80)),
    Column("attachments", Text, nullable=False),
    Column("author_id", String(80), nullable=False),
    Column("answered_at", String(40)),
    Column("answered_via_token_id", String(36)),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("row_version", Integer, nullable=False),
    Column("deleted_at", String(40)),
    Index("ix_rfis_company_updated", "company_id", "updated_at"),
    Index(
        "ix_rfis_project_status_due",
        "project_id",
        "status",
        "due_date",
        sqlite_where=text("deleted_at IS NULL"),
        postgresql_where=text("deleted_at IS NULL"),
    ),
)

access_tokens = Table(
    "access_tokens",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("company_id", String(180), nullable=False),
    Column("project_id", String(80), nullable=False),
    Column("purpose", String(32), nullable=False),
    Column("token_sha256", String(64), nullable=False),
    Column("entity_id", String(36), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("used_at", String(40)),
    Column("created_by", String(80), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("row_version", Integer, nullable=False),
    Column("deleted_at", String(40)),
    Index("ix_access_tokens_token_sha256", "token_sha256", unique=True),
    Index("ix_access_tokens_company_updated", "company_id", "updated_at"),
)


def ensure_rfi_tables(bind) -> None:
    metadata.create_all(bind)
