"""Baseline SQL store snapshot.

Revision ID: 20261019_0001
Revises:
Create Date: 2026-10-19
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "records",
        sa.Column("collection", sa.String(length=40), primary_key=True),
        sa.Column("doc_id", sa.String(length=80), primary_key=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("company_key", sa.String(length=180), nullable=True),
        sa.Column("owner_id", sa.String(length=80), nullable=True),
        sa.Column("user_id", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("district", sa.String(length=160), nullable=True),
        sa.Column("gas", sa.String(length=40), nullable=True),
        sa.Column("electricity", sa.String(length=40), nullable=True),
        sa.Column("water", sa.String(length=40), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=True),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_records_project_id", "records", ["project_id"])
    op.create_index("ix_records_company_key", "records", ["company_key"])
    op.create_index("ix_records_owner_id", "records", ["owner_id"])
    op.create_index("ix_records_user_id", "records", ["user_id"])
    op.create_index("ix_records_status", "records", ["status"])
    op.create_index("ix_records_created_at", "records", ["created_at"])
    op.create_index("ix_records_email", "records", ["email"])
    op.create_index("ix_records_category", "records", ["category"])
    op.create_index("ix_records_price", "records", ["price"])
    op.create_index("ix_records_seq", "records", ["seq"])
    op.create_index("ix_records_collection_status", "records", ["collection", "status"])
    op.create_index("ix_records_collection_project", "records", ["collection", "project_id"])
    op.create_index("ix_records_collection_company", "records", ["collection", "company_key"])
    op.create_index("ix_records_collection_created", "records", ["collection", "created_at"])
    op.create_index("ix_records_collection_owner", "records", ["collection", "owner_id"])
    op.create_index("ix_records_collection_user", "records", ["collection", "user_id"])
    op.create_index("ix_records_collection_category", "records", ["collection", "category"])
    op.create_index("ix_records_collection_email", "records", ["collection", "email"])

    op.create_table(
        "record_links",
        sa.Column("collection", sa.String(length=40), primary_key=True),
        sa.Column("doc_id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), primary_key=True),
        sa.ForeignKeyConstraint(
            ["collection", "doc_id"],
            ["records.collection", "records.doc_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_record_links_user", "record_links", ["user_id", "collection"])
    op.create_index("ix_record_links_doc", "record_links", ["collection", "doc_id"])

    op.create_table(
        "meta",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.execute("INSERT INTO meta (id, revision) VALUES ('rev', 0)")

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint("user_id", "key", name="uq_idempotency_user_key"),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])

    op.create_table(
        "invitations",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("company_key", sa.String(length=180), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("company_bin", sa.String(length=12), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("invited_by", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("used_at", sa.String(length=40), nullable=True),
        sa.Column("used_by", sa.String(length=80), nullable=True),
        sa.Column("revoked_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"], unique=True)
    op.create_index("ix_invitations_role", "invitations", ["role"])
    op.create_index("ix_invitations_company_key", "invitations", ["company_key"])
    op.create_index("ix_invitations_project_id", "invitations", ["project_id"])
    op.create_index("ix_invitations_invited_by", "invitations", ["invited_by"])
    op.create_index("ix_invitations_created_at", "invitations", ["created_at"])
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])

    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account", sa.String(length=200), nullable=False),
        sa.Column("ip", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index(
        "ix_login_failures_account_ip_created",
        "login_failures",
        ["account", "ip", "created_at"],
    )

    op.create_table(
        "photo_jobs",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.String(length=80), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("daily_log_id", sa.String(length=80), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("has_people", sa.Boolean(), nullable=True),
        sa.Column("has_plates", sa.Boolean(), nullable=True),
        sa.Column("taken_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("finished_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_photo_jobs_status", "photo_jobs", ["status"])
    op.create_index("ix_photo_jobs_owner_id", "photo_jobs", ["owner_id"])
    op.create_index("ix_photo_jobs_project_id", "photo_jobs", ["project_id"])
    op.create_index("ix_photo_jobs_daily_log_id", "photo_jobs", ["daily_log_id"])
    op.create_index("ix_photo_jobs_created_at", "photo_jobs", ["created_at"])


def downgrade() -> None:
    raise RuntimeError("baseline: downgrade not allowed")
