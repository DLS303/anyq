"""Row versions, consent journal, and list indexes.

Revision ID: 20261019_0001b_store_fixes
Revises: 20261019_0001
Create Date: 2026-10-19

Sits between the baseline and later revisions such as 20261019_0002_pf0.
Those revisions should set down_revision to this id.
"""

import json

import sqlalchemy as sa

from alembic import op
from app.sql_backend import install_consent_triggers

revision = "20261019_0001b_store_fixes"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None

OLD_RECORD_INDEXES = (
    "ix_records_project_id",
    "ix_records_company_key",
    "ix_records_owner_id",
    "ix_records_user_id",
    "ix_records_status",
    "ix_records_created_at",
    "ix_records_email",
    "ix_records_category",
    "ix_records_seq",
    "ix_records_collection_status",
    "ix_records_collection_project",
    "ix_records_collection_company",
    "ix_records_collection_created",
    "ix_records_collection_owner",
    "ix_records_collection_user",
    "ix_records_collection_category",
    "ix_records_collection_email",
)

NEW_RECORD_INDEXES = (
    ("ix_records_coll_seq", ["collection", "seq", "doc_id"], False),
    ("ix_records_coll_proj_seq", ["collection", "project_id", "seq"], False),
    ("ix_records_coll_comp_seq", ["collection", "company_key", "seq"], False),
    ("ix_records_coll_owner_seq", ["collection", "owner_id", "seq"], False),
    ("ix_records_coll_status_seq", ["collection", "status", "seq"], False),
)


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {row["name"] for row in sa.inspect(bind).get_indexes(table)}


def _drop_index(name: str, table: str) -> None:
    if name in _index_names(table):
        op.drop_index(name, table_name=table)


def upgrade() -> None:
    op.add_column("records", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"))
    for name, columns, unique in NEW_RECORD_INDEXES:
        op.create_index(name, "records", columns, unique=unique)
    op.create_index("ix_records_coll_created", "records", ["collection", sa.text("created_at DESC")])
    op.create_index(
        "ux_records_user_email",
        "records",
        ["email"],
        unique=True,
        sqlite_where=sa.text("collection = 'users'"),
        postgresql_where=sa.text("collection = 'users'"),
    )
    for name in OLD_RECORD_INDEXES:
        _drop_index(name, "records")
    _drop_index("ix_record_links_doc", "record_links")

    op.create_table(
        "consent_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("legacy_id", sa.String(length=40), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=True),
        sa.Column("subject_user_id", sa.String(length=80), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("text_version", sa.String(length=80), nullable=False),
        sa.Column("text_sha256", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.String(length=40), nullable=False),
        sa.Column("granted_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("user_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("login", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("provider", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("country", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("privacy_version", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("privacy_sha256", sa.String(length=64), nullable=False, server_default=""),
        sa.UniqueConstraint("legacy_id", name="uq_consent_events_legacy_id"),
    )
    op.create_index(
        "ix_consents_subject",
        "consent_events",
        ["subject_user_id", "purpose", sa.text("occurred_at DESC")],
    )
    op.create_index("ix_consents_company", "consent_events", ["company_id", sa.text("occurred_at DESC")])

    op.create_table(
        "record_tombstones",
        sa.Column("collection", sa.String(length=40), primary_key=True),
        sa.Column("doc_id", sa.String(length=80), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
    )
    op.create_index("ix_tombstones_coll_seq", "record_tombstones", ["collection", "seq"])

    bind = op.get_bind()
    legacy = bind.execute(
        sa.text("SELECT doc_id, company_key, user_id, payload FROM records WHERE collection = 'consents'")
    ).mappings()
    for row in legacy:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload or "{}")
        payload = payload or {}
        action = payload.get("action") or "grant"
        occurred = payload.get("granted_at") or ""
        if action == "revoke" and payload.get("revoked_at"):
            occurred = payload.get("revoked_at")
        bind.execute(
            sa.text(
                """
                INSERT INTO consent_events (
                    legacy_id, company_id, subject_user_id, purpose, text_version, text_sha256,
                    action, occurred_at, granted_at, ip, user_agent, login, provider, country,
                    privacy_version, privacy_sha256
                ) VALUES (
                    :legacy_id, :company_id, :subject_user_id, :purpose, :text_version, :text_sha256,
                    :action, :occurred_at, :granted_at, :ip, :user_agent, :login, :provider, :country,
                    :privacy_version, :privacy_sha256
                )
                """
            ),
            {
                "legacy_id": str(payload.get("id") or row["doc_id"]),
                "company_id": row["company_key"],
                "subject_user_id": str(payload.get("user_id") or row["user_id"] or ""),
                "purpose": str(payload.get("type") or "offer_pd"),
                "text_version": str(payload.get("text_version") or ""),
                "text_sha256": str(payload.get("text_sha256") or ""),
                "action": action,
                "occurred_at": str(occurred),
                "granted_at": str(payload.get("granted_at") or ""),
                "ip": str(payload.get("ip") or ""),
                "user_agent": str(payload.get("user_agent") or ""),
                "login": str(payload.get("login") or ""),
                "provider": str(payload.get("provider") or ""),
                "country": str(payload.get("country") or ""),
                "privacy_version": str(payload.get("privacy_version") or ""),
                "privacy_sha256": str(payload.get("privacy_sha256") or ""),
            },
        )
    bind.execute(sa.text("DELETE FROM records WHERE collection = 'consents'"))
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_records_search_trgm ON records USING gin (search_text gin_trgm_ops)"
        )
    install_consent_triggers(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_records_search_trgm")
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_update ON consent_events")
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_delete ON consent_events")
        op.execute("DROP FUNCTION IF EXISTS consent_events_append_only()")
    op.drop_index("ix_tombstones_coll_seq", table_name="record_tombstones")
    op.drop_table("record_tombstones")
    op.drop_index("ix_consents_company", table_name="consent_events")
    op.drop_index("ix_consents_subject", table_name="consent_events")
    op.drop_table("consent_events")
    _drop_index("ux_records_user_email", "records")
    _drop_index("ix_records_coll_created", "records")
    for name, _columns, _unique in NEW_RECORD_INDEXES:
        _drop_index(name, "records")
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("records") as batch:
            batch.drop_column("row_version")
    else:
        op.drop_column("records", "row_version")
    op.create_index("ix_records_project_id", "records", ["project_id"])
    op.create_index("ix_records_company_key", "records", ["company_key"])
    op.create_index("ix_records_owner_id", "records", ["owner_id"])
    op.create_index("ix_records_user_id", "records", ["user_id"])
    op.create_index("ix_records_status", "records", ["status"])
    op.create_index("ix_records_created_at", "records", ["created_at"])
    op.create_index("ix_records_email", "records", ["email"])
    op.create_index("ix_records_category", "records", ["category"])
    op.create_index("ix_records_seq", "records", ["seq"])
    op.create_index("ix_records_collection_status", "records", ["collection", "status"])
    op.create_index("ix_records_collection_project", "records", ["collection", "project_id"])
    op.create_index("ix_records_collection_company", "records", ["collection", "company_key"])
    op.create_index("ix_records_collection_created", "records", ["collection", "created_at"])
    op.create_index("ix_records_collection_owner", "records", ["collection", "owner_id"])
    op.create_index("ix_records_collection_user", "records", ["collection", "user_id"])
    op.create_index("ix_records_collection_category", "records", ["collection", "category"])
    op.create_index("ix_records_collection_email", "records", ["collection", "email"])
    op.create_index("ix_record_links_doc", "record_links", ["collection", "doc_id"])
