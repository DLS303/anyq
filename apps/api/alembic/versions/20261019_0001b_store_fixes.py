"""Row versions, consent journal, and list indexes.

Revision ID: 20261019_0001b_store_fixes
Revises: 20261019_0001
Create Date: 2026-10-19

Sits between the baseline and later revisions such as 20261019_0002_pf0.
Those revisions should set down_revision to this id.

Downgrade copies consent_events back into records (collection consents)
before the journal is dropped. The copied rows use the earlier grant/revoke
shape, including a revoked_at value when a withdraw event exists.
"""

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

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

_PURPOSES = {"offer_pd", "cross_border", "ai"}

_TRIGGER_SQL = {
    "sqlite": (
        """
        CREATE TRIGGER IF NOT EXISTS consent_events_no_update
        BEFORE UPDATE ON consent_events
        BEGIN
            SELECT RAISE(ABORT, 'append-only');
        END
        """,
        """
        CREATE TRIGGER IF NOT EXISTS consent_events_no_delete
        BEFORE DELETE ON consent_events
        BEGIN
            SELECT RAISE(ABORT, 'append-only');
        END
        """,
    ),
    "postgresql": (
        """
        CREATE OR REPLACE FUNCTION consent_events_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'append-only';
        END;
        $$
        """,
        "DROP TRIGGER IF EXISTS consent_events_no_update ON consent_events",
        """
        CREATE TRIGGER consent_events_no_update
        BEFORE UPDATE ON consent_events
        FOR EACH ROW EXECUTE FUNCTION consent_events_append_only()
        """,
        "DROP TRIGGER IF EXISTS consent_events_no_delete ON consent_events",
        """
        CREATE TRIGGER consent_events_no_delete
        BEFORE DELETE ON consent_events
        FOR EACH ROW EXECUTE FUNCTION consent_events_append_only()
        """,
    ),
}


def _index_names(table: str) -> set[str]:
    bind = op.get_bind()
    return {row["name"] for row in sa.inspect(bind).get_indexes(table)}


def _drop_index(name: str, table: str) -> None:
    if name in _index_names(table):
        op.drop_index(name, table_name=table)


def _payload_expr(bind) -> str:
    if bind.dialect.name == "postgresql":
        return "CAST(:payload AS json)"
    return ":payload"


def _load_payload(value):
    if isinstance(value, str):
        return json.loads(value or "{}")
    return dict(value or {})


def _report_email_quarantine(bind, doc_ids: list[str]) -> None:
    unique = sorted(set(doc_ids))
    if not unique:
        return
    reported_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    for doc_id in unique:
        bind.execute(
            sa.text(
                "INSERT INTO email_quarantine (doc_id, reason, reported_at) "
                "VALUES (:doc_id, 'duplicate', :reported_at)"
            ),
            {"doc_id": doc_id, "reported_at": reported_at},
        )
    logging.getLogger("alembic.runtime.migration").warning(
        "email_quarantine count=%s doc_id=%s",
        len(unique),
        ",".join(unique),
    )


def _normalize_user_emails(bind) -> None:
    bind.execute(
        sa.text(
            "UPDATE records SET email = lower(email) "
            "WHERE collection = 'users' AND email IS NOT NULL AND email <> lower(email)"
        )
    )
    rows = list(
        bind.execute(
            sa.text(
                "SELECT doc_id, email, payload FROM records "
                "WHERE collection = 'users' AND email IS NOT NULL AND email <> '' "
                "ORDER BY seq, doc_id"
            )
        ).mappings()
    )
    seen: dict[str, str] = {}
    extras: list[str] = []
    for row in rows:
        email = str(row["email"])
        if email in seen:
            extras.append(str(row["doc_id"]))
        else:
            seen[email] = str(row["doc_id"])
    for doc_id in extras:
        bind.execute(
            sa.text("UPDATE records SET email = NULL WHERE collection = 'users' AND doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
    expr = _payload_expr(bind)
    for email, doc_id in seen.items():
        current = bind.execute(
            sa.text("SELECT payload FROM records WHERE collection = 'users' AND doc_id = :doc_id"),
            {"doc_id": doc_id},
        ).one()
        payload = _load_payload(current[0])
        stored = payload.get("email")
        if not isinstance(stored, str) or stored == email:
            continue
        payload["email"] = email
        bind.execute(
            sa.text(
                f"UPDATE records SET payload = {expr} WHERE collection = 'users' AND doc_id = :doc_id"
            ),
            {"payload": json.dumps(payload, ensure_ascii=False), "doc_id": doc_id},
        )
    empties = list(
        bind.execute(
            sa.text(
                "SELECT doc_id FROM records WHERE collection = 'users' AND email = '' ORDER BY seq, doc_id"
            )
        ).scalars()
    )
    for doc_id in empties[1:]:
        extras.append(str(doc_id))
        bind.execute(
            sa.text("UPDATE records SET email = NULL WHERE collection = 'users' AND doc_id = :doc_id"),
            {"doc_id": doc_id},
        )
    _report_email_quarantine(bind, extras)


def _text(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _consent_events(payload: dict, company_id: str | None) -> list[dict]:
    purpose = payload.get("type") if payload.get("type") in _PURPOSES else "offer_pd"
    action = payload.get("action") if payload.get("action") in {"grant", "revoke"} else "grant"
    granted = _text(payload.get("granted_at"))
    revoked = payload.get("revoked_at")
    base_id = _text(payload.get("id"))

    def one(legacy_id: str, stored: str, occurred: str) -> dict:
        return {
            "legacy_id": legacy_id,
            "event_uuid": str(uuid4()),
            "company_id": company_id,
            "subject_user_id": _text(payload.get("user_id")),
            "purpose": purpose,
            "text_version": _text(payload.get("text_version")),
            "text_sha256": _text(payload.get("text_sha256")),
            "action": "withdraw" if stored == "revoke" else "grant",
            "occurred_at": occurred or granted,
            "granted_at": granted or occurred,
            "ip": _text(payload.get("ip")),
            "user_agent": _text(payload.get("user_agent")),
            "login": _text(payload.get("login")),
            "provider": _text(payload.get("provider")),
            "country": _text(payload.get("country")),
            "privacy_version": _text(payload.get("privacy_version")),
            "privacy_sha256": _text(payload.get("privacy_sha256")),
            "evidence": json.dumps(
                {
                    "privacy_version": _text(payload.get("privacy_version")),
                    "privacy_sha256": _text(payload.get("privacy_sha256")),
                    "granted_at": granted,
                },
                ensure_ascii=False,
            ),
        }

    if action == "revoke" or revoked:
        return [
            one(base_id, "grant", granted),
            one(f"{base_id}:withdraw", "revoke", _text(revoked, granted)),
        ]
    return [one(base_id, "grant", granted)]


def _copy_consents(bind) -> None:
    # Consent rows move inside this revision. Pilot volume is small enough for that.
    legacy = bind.execute(
        sa.text("SELECT doc_id, company_key, user_id, payload FROM records WHERE collection = 'consents'")
    ).mappings()
    known: set[str] = set()
    seq = 0
    expr = "CAST(:evidence AS json)" if bind.dialect.name == "postgresql" else ":evidence"
    for row in legacy:
        payload = _load_payload(row["payload"])
        payload["id"] = _text(payload.get("id"), _text(row["doc_id"]))
        payload["user_id"] = _text(payload.get("user_id"), _text(row["user_id"]))
        for event in _consent_events(payload, row["company_key"]):
            if event["legacy_id"] in known:
                continue
            seq += 1
            event["seq"] = seq
            known.add(event["legacy_id"])
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO consent_events (
                        seq, legacy_id, event_uuid, company_id, subject_user_id, purpose,
                        text_version, text_sha256, action, occurred_at, granted_at, ip,
                        user_agent, login, provider, country, privacy_version,
                        privacy_sha256, evidence
                    ) VALUES (
                        :seq, :legacy_id, :event_uuid, :company_id, :subject_user_id, :purpose,
                        :text_version, :text_sha256, :action, :occurred_at, :granted_at, :ip,
                        :user_agent, :login, :provider, :country, :privacy_version,
                        :privacy_sha256, {expr}
                    )
                    """
                ),
                event,
            )
    if seq:
        bind.execute(
            sa.text(
                "INSERT INTO meta (id, revision) VALUES ('consents', :revision) "
                "ON CONFLICT (id) DO UPDATE SET revision = excluded.revision"
            ),
            {"revision": seq},
        )
    bind.execute(sa.text("DELETE FROM records WHERE collection = 'consents'"))


def _install_consent_triggers(bind) -> None:
    for statement in _TRIGGER_SQL.get(bind.dialect.name, ()):
        op.execute(statement)


def _base_legacy_id(legacy_id: str) -> str:
    suffix = ":withdraw"
    if legacy_id.endswith(suffix):
        return legacy_id[: -len(suffix)]
    return legacy_id


def _restore_consents(bind) -> None:
    rows = list(
        bind.execute(
            sa.text(
                """
                SELECT legacy_id, company_id, subject_user_id, purpose, text_version,
                       text_sha256, action, occurred_at, granted_at, ip, user_agent, login,
                       provider, country, privacy_version, privacy_sha256, seq
                FROM consent_events
                ORDER BY seq
                """
            )
        ).mappings()
    )
    groups: dict[str, dict] = {}
    for row in rows:
        base = _base_legacy_id(_text(row["legacy_id"]))
        slot = groups.setdefault(base, {"grant": None, "withdraw": None, "seq": 0})
        slot["seq"] = max(int(slot["seq"]), int(row["seq"] or 0))
        if row["action"] == "withdraw" or _text(row["legacy_id"]).endswith(":withdraw"):
            slot["withdraw"] = row
        else:
            slot["grant"] = row
    expr = _payload_expr(bind)
    for base, slot in groups.items():
        source = slot["grant"] or slot["withdraw"]
        if source is None:
            continue
        withdrawn = slot["withdraw"]
        granted_at = _text(source["granted_at"] or source["occurred_at"])
        purpose = source["purpose"] if source["purpose"] in _PURPOSES else "offer_pd"
        payload = {
            "id": base,
            "user_id": _text(source["subject_user_id"]),
            "type": purpose,
            "text_version": _text(source["text_version"]),
            "text_sha256": _text(source["text_sha256"]),
            "granted_at": granted_at,
            "action": "revoke" if withdrawn is not None else "grant",
            "revoked_at": _text(withdrawn["occurred_at"]) if withdrawn is not None else None,
            "ip": _text(source["ip"]),
            "user_agent": _text(source["user_agent"]),
            "login": _text(source["login"]),
            "provider": _text(source["provider"]),
            "country": _text(source["country"]),
            "privacy_version": _text(source["privacy_version"]),
            "privacy_sha256": _text(source["privacy_sha256"]),
        }
        bind.execute(
            sa.text(
                f"""
                INSERT INTO records (
                    collection, doc_id, company_key, user_id, created_at,
                    search_text, seq, row_version, payload
                ) VALUES (
                    'consents', :doc_id, :company_key, :user_id, :created_at,
                    '', :seq, 1, {expr}
                )
                """
            ),
            {
                "doc_id": base[:80],
                "company_key": source["company_id"],
                "user_id": _text(source["subject_user_id"]) or None,
                "created_at": granted_at,
                "seq": int(slot["seq"] or 0),
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )


def upgrade() -> None:
    op.add_column("records", sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"))
    for name, columns, unique in NEW_RECORD_INDEXES:
        op.create_index(name, "records", columns, unique=unique)
    op.create_index("ix_records_coll_created", "records", ["collection", "created_at"])
    op.create_table(
        "email_quarantine",
        sa.Column("doc_id", sa.String(length=80), primary_key=True),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("reported_at", sa.String(length=40), nullable=False),
    )
    _normalize_user_emails(op.get_bind())
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
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("legacy_id", sa.String(length=40), nullable=False),
        sa.Column("event_uuid", sa.String(length=36), nullable=False),
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
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("legacy_id", name="uq_consent_events_legacy_id"),
        sa.UniqueConstraint("event_uuid", name="uq_consent_events_event_uuid"),
    )
    op.create_index("ix_consent_events_seq", "consent_events", ["seq"], unique=True)
    op.create_index("ix_consents_subject", "consent_events", ["subject_user_id", "purpose", "occurred_at"])
    op.create_index("ix_consents_company", "consent_events", ["company_id", "occurred_at"])

    op.create_table(
        "record_tombstones",
        sa.Column("collection", sa.String(length=40), primary_key=True),
        sa.Column("doc_id", sa.String(length=80), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False),
    )
    op.create_index("ix_tombstones_coll_seq", "record_tombstones", ["collection", "seq"])

    op.create_table(
        "login_failures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )
    op.create_index("ix_login_failures_key_created", "login_failures", ["key_hash", "created_at"])

    bind = op.get_bind()
    _copy_consents(bind)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_records_search_trgm ON records USING gin (search_text gin_trgm_ops)"
        )
    _install_consent_triggers(bind)


def _drop_consent_triggers(bind) -> None:
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_update")
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_delete")
    elif bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_update ON consent_events")
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_delete ON consent_events")
        op.execute("DROP FUNCTION IF EXISTS consent_events_append_only()")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_records_search_trgm")
    _restore_consents(bind)
    _drop_consent_triggers(bind)
    op.drop_table("email_quarantine")
    op.drop_index("ix_login_failures_key_created", table_name="login_failures")
    op.drop_table("login_failures")
    op.drop_index("ix_tombstones_coll_seq", table_name="record_tombstones")
    op.drop_table("record_tombstones")
    op.drop_index("ix_consents_company", table_name="consent_events")
    op.drop_index("ix_consents_subject", table_name="consent_events")
    op.drop_index("ix_consent_events_seq", table_name="consent_events")
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
