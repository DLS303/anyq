"""Company feature flags, audit log, and company-key backfill.

Revision ID: 20261019_0002_pf0
Revises: 20261019_0001b_store_fixes
Create Date: 2026-10-19

Existing users receive a stored company_key. A BIN that belongs to exactly one
company is written as bin:<digits> and reserved in companies.legacy_key.
Any other BIN is written as user:<id> and marked for moderator review.
Project, contact, and invitation keys are recomputed from that assignment.

Downgrade drops company_features, companies, and audit_log, including their rows.
It does not undo the company_key values written onto existing records.
Do not run downgrade in production.

Tables are created with explicit DDL. This revision does not import application models.
"""

import json
import re
from collections import defaultdict
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision = "20261019_0002_pf0"
down_revision = "20261019_0001b_store_fixes"
branch_labels = None
depends_on = None

_STORED_KEY = re.compile(r"^(?:bin:\d{12}|user:\S+)$")
_PARTITION_BOUNDS = (
    ("audit_log_2026_10", "2026-10-01 00:00:00+00", "2026-11-01 00:00:00+00"),
    ("audit_log_2026_11", "2026-11-01 00:00:00+00", "2026-12-01 00:00:00+00"),
)

_PG_AUDIT = """
CREATE TABLE audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY,
  occurred_at timestamptz NOT NULL,
  company_id varchar(180),
  actor_kind text NOT NULL CHECK (
    actor_kind IN ('user','token','system','platform_admin','migration')
  ),
  actor_user_id varchar(80),
  actor_token_id varchar(80),
  action text NOT NULL,
  entity_type text,
  entity_id text,
  project_id text,
  request_id text,
  ip text,
  ua_hash char(64),
  changes jsonb NOT NULL DEFAULT '{}',
  prev_hash bytea,
  row_hash bytea NOT NULL,
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at)
"""

_PG_INDEXES = """
CREATE INDEX ix_audit_company_time ON audit_log (company_id, occurred_at DESC);
CREATE INDEX ix_audit_entity ON audit_log (entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_audit_actor ON audit_log (actor_user_id, occurred_at DESC)
"""

_PG_FUNCTION = """
CREATE FUNCTION forbid_audit_log_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'append-only';
END $$
"""

_PG_PARENT_TRIGGERS = """
CREATE TRIGGER trg_audit_log_no_update
  BEFORE UPDATE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_audit_log_mutation();
CREATE TRIGGER trg_audit_log_no_delete
  BEFORE DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION forbid_audit_log_mutation();
CREATE TRIGGER trg_audit_log_no_truncate
  BEFORE TRUNCATE ON audit_log
  FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_log_mutation()
"""

_PG_REVOKE = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anyq_app') THEN
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM anyq_app;
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log_2026_10 FROM anyq_app;
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log_2026_11 FROM anyq_app;
    REVOKE UPDATE, DELETE, TRUNCATE ON audit_log_default FROM anyq_app;
  END IF;
END $$
"""


def audit_truncate_trigger(table: str) -> str:
    """BEFORE TRUNCATE guard. Apply this when creating a future monthly partition."""
    if not re.fullmatch(r"audit_log(_\d{4}_\d{2}|_default)?", table):
        raise ValueError(table)
    return (
        f"CREATE TRIGGER trg_{table}_no_truncate "
        f"BEFORE TRUNCATE ON {table} "
        "FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_log_mutation()"
    )


def _features() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("legacy_key", sa.String(length=180), nullable=False),
        sa.UniqueConstraint("legacy_key", name="uq_companies_legacy_key"),
    )
    op.create_table(
        "company_features",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "changed_by", sa.String(length=80), nullable=False, server_default=""
        ),
        sa.Column(
            "changed_at", sa.String(length=40), nullable=False, server_default=""
        ),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.String(length=40), nullable=False, server_default=""
        ),
        sa.Column(
            "updated_at", sa.String(length=40), nullable=False, server_default=""
        ),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
        sa.UniqueConstraint(
            "company_id", "key", name="uq_company_features_company_key"
        ),
    )


def _sqlite_audit() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=True),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", sa.String(length=80), nullable=True),
        sa.Column("actor_token_id", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=True),
        sa.Column("entity_id", sa.String(length=80), nullable=True),
        sa.Column("project_id", sa.String(length=80), nullable=True),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("ip", sa.String(length=80), nullable=True),
        sa.Column("ua_hash", sa.String(length=64), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("prev_hash", sa.LargeBinary(), nullable=True),
        sa.Column("row_hash", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "actor_kind IN ('user','token','system','platform_admin','migration')",
            name="ck_audit_log_actor_kind",
        ),
    )
    op.create_index("ix_audit_company_time", "audit_log", ["company_id", "occurred_at"])
    op.create_index(
        "ix_audit_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"]
    )
    op.create_index("ix_audit_actor", "audit_log", ["actor_user_id", "occurred_at"])
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'append-only'); END"
    )


def _pg_partitions() -> str:
    statements = []
    for name, start, end in _PARTITION_BOUNDS:
        statements.append(
            f"CREATE TABLE {name} PARTITION OF audit_log "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
    statements.append("CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT")
    return ";\n".join(statements)


def _install_pg_audit() -> None:
    op.execute(_PG_AUDIT)
    op.execute(_pg_partitions())
    op.execute(_PG_INDEXES)
    op.execute(_PG_FUNCTION)
    op.execute(_PG_PARENT_TRIGGERS)
    for name, _start, _end in _PARTITION_BOUNDS:
        op.execute(audit_truncate_trigger(name))
    op.execute(audit_truncate_trigger("audit_log_default"))
    op.execute(_PG_REVOKE)


def _json_load(value) -> dict:
    if value is None or value == "":
        return {}
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, dict):
        return dict(value)
    return dict(value)


def _digits(payload: dict) -> str:
    raw = re.sub(r"\D", "", str(payload.get("company_bin") or ""))
    return raw if len(raw) == 12 else ""


def _norm_company(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _same_company(user: dict, owner: dict, invite_company: dict[str, str]) -> bool:
    """True when the normalized names agree. A blank profile can inherit the invitation name."""
    own = _norm_company(user["payload"].get("company"))
    root = _norm_company(owner["payload"].get("company"))
    invited = _norm_company(invite_company.get(user["id"], ""))
    if own and root and own != root:
        return False
    if own and root:
        return True
    return bool(invited and root and invited == root)


def _assign(users: list[dict], invited_by: dict[str, str], invite_company: dict[str, str]) -> dict[str, dict]:
    """First company of a BIN keeps bin:X. A different name, or a later self-registration, is user:<id> plus review.

    An accepted invitation joins the inviter only when the company name matches.
    Legacy records.company_key is not an identity: every BIN owner was stored as bin:X.
    """
    assigned: dict[str, dict] = {}
    pending = []
    for user in users:
        stored = str(user["payload"].get("company_key") or "").strip()
        old = str(user["company_key"] or "")
        if _STORED_KEY.match(stored):
            assigned[user["id"]] = {"key": stored, "review": bool(user["payload"].get("company_review")), "old": old}
            continue
        pending.append(user)
    groups: dict[str, list] = defaultdict(list)
    for user in pending:
        digits = _digits(user["payload"])
        if not digits:
            assigned[user["id"]] = {
                "key": f"user:{user['id']}",
                "review": False,
                "old": str(user["company_key"] or ""),
            }
            continue
        groups[digits].append(user)
    for user in users:
        stored = assigned.get(user["id"], {}).get("key", "")
        if stored.startswith("bin:") and len(stored) == 16:
            groups[stored[4:]].append(user)
    for digits, members in groups.items():
        ordered = []
        seen: set[str] = set()
        for user in sorted(members, key=lambda item: (int(item.get("seq") or 0), item["id"])):
            if user["id"] in seen:
                continue
            seen.add(user["id"])
            ordered.append(user)
        holders = [item for item in ordered if assigned.get(item["id"], {}).get("key") == f"bin:{digits}"]
        owner = holders[0] if holders else ordered[0]
        accepted = {owner["id"]}
        progressed = True
        while progressed:
            progressed = False
            for user in ordered:
                if user["id"] in accepted:
                    continue
                inviter = invited_by.get(user["id"])
                if inviter in accepted and _same_company(user, owner, invite_company):
                    accepted.add(user["id"])
                    progressed = True
        for user in ordered:
            if user["id"] in assigned:
                continue
            if user["id"] in accepted:
                key, review = f"bin:{digits}", False
            else:
                key, review = f"user:{user['id']}", True
            assigned[user["id"]] = {
                "key": key,
                "review": review,
                "old": str(user["company_key"] or ""),
            }
    return assigned


def _backfill_company_keys(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT doc_id, company_key, payload, seq FROM records WHERE collection = 'users'"
        )
    ).mappings()
    users = [
        {
            "id": row["doc_id"],
            "company_key": row["company_key"],
            "payload": _json_load(row["payload"]),
            "seq": int(row["seq"] or 0),
        }
        for row in rows
    ]
    invited_by: dict[str, str] = {}
    invite_company: dict[str, str] = {}
    for row in bind.execute(sa.text("SELECT invited_by, used_by, company FROM invitations")).mappings():
        used_by = str(row["used_by"] or "").strip()
        if not used_by:
            continue
        invited_by[used_by] = str(row["invited_by"] or "").strip()
        invite_company[used_by] = str(row["company"] or "")
    assigned = _assign(users, invited_by, invite_company)
    if bind.dialect.name == "postgresql":
        user_sql = sa.text(
            "UPDATE records SET payload = CAST(:payload AS json), company_key = :key "
            "WHERE collection = 'users' AND doc_id = :id"
        )
    else:
        user_sql = sa.text(
            "UPDATE records SET payload = :payload, company_key = :key "
            "WHERE collection = 'users' AND doc_id = :id"
        )
    for user in users:
        info = assigned[user["id"]]
        payload = user["payload"]
        payload["company_key"] = info["key"]
        payload["company_review"] = info["review"]
        bind.execute(
            user_sql,
            {
                "payload": json.dumps(payload, ensure_ascii=False),
                "key": info["key"],
                "id": user["id"],
            },
        )
    old_to_new: dict[str, set[str]] = defaultdict(set)
    for info in assigned.values():
        if info["old"] and info["old"] != info["key"]:
            old_to_new[info["old"]].add(info["key"])
    unique_old = {
        old: next(iter(keys)) for old, keys in old_to_new.items() if len(keys) == 1
    }
    others = bind.execute(
        sa.text(
            "SELECT collection, doc_id, owner_id, company_key, payload "
            "FROM records WHERE collection != 'users'"
        )
    ).mappings()
    key_sql = sa.text(
        "UPDATE records SET company_key = :key WHERE collection = :collection AND doc_id = :id"
    )
    for row in others:
        payload = _json_load(row["payload"])
        owner_id = (
            row["owner_id"] or payload.get("owner_id") or payload.get("supplier_id")
        )
        new_key = None
        if owner_id and owner_id in assigned:
            new_key = assigned[owner_id]["key"]
        elif row["company_key"] and row["company_key"] in unique_old:
            new_key = unique_old[row["company_key"]]
        if new_key and new_key != row["company_key"]:
            bind.execute(
                key_sql,
                {"key": new_key, "collection": row["collection"], "id": row["doc_id"]},
            )
    invitations = bind.execute(
        sa.text("SELECT id, company_key, invited_by FROM invitations")
    ).mappings()
    invite_sql = sa.text("UPDATE invitations SET company_key = :key WHERE id = :id")
    for row in invitations:
        info = assigned.get(row["invited_by"])
        if info:
            new_key = info["key"]
        elif row["company_key"] in unique_old:
            new_key = unique_old[row["company_key"]]
        else:
            continue
        if new_key != row["company_key"]:
            bind.execute(invite_sql, {"key": new_key, "id": row["id"]})
    existing = {
        row[0]
        for row in bind.execute(sa.text("SELECT legacy_key FROM companies")).all()
    }
    insert_sql = sa.text("INSERT INTO companies (id, legacy_key) VALUES (:id, :key)")
    for key in {info["key"] for info in assigned.values()}:
        if key in existing:
            continue
        bind.execute(insert_sql, {"id": str(uuid4()), "key": key})
        existing.add(key)


def upgrade() -> None:
    _features()
    _backfill_company_keys(op.get_bind())
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _install_pg_audit()
        return
    _sqlite_audit()


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
        op.execute("DROP FUNCTION IF EXISTS forbid_audit_log_mutation()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_delete")
        op.drop_index("ix_audit_actor", table_name="audit_log")
        op.drop_index("ix_audit_entity", table_name="audit_log")
        op.drop_index("ix_audit_company_time", table_name="audit_log")
        op.drop_table("audit_log")
    op.drop_table("company_features")
    op.drop_table("companies")
