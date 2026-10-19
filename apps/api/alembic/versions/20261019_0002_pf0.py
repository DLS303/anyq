"""Company feature flags and the audit log.

Revision ID: 20261019_0002_pf0
Revises: 20261019_0001b_store_fixes
Create Date: 2026-10-19

Downgrade drops company_features, companies, and audit_log, including their rows.
Do not run downgrade in production.

Tables are created with explicit DDL. This revision does not import application models.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0002_pf0"
down_revision = "20261019_0001b_store_fixes"
branch_labels = None
depends_on = None

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

_PG_PARTITIONS = """
CREATE TABLE audit_log_2026_10 PARTITION OF audit_log
  FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE audit_log_2026_11 PARTITION OF audit_log
  FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT
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

_PG_TRIGGERS = """
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
        sa.Column("changed_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("changed_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
        sa.UniqueConstraint("company_id", "key", name="uq_company_features_company_key"),
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
    op.create_index("ix_audit_entity", "audit_log", ["entity_type", "entity_id", "occurred_at"])
    op.create_index("ix_audit_actor", "audit_log", ["actor_user_id", "occurred_at"])
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'append-only'); END"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON audit_log "
        "BEGIN SELECT RAISE(ABORT, 'append-only'); END"
    )


def upgrade() -> None:
    _features()
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(_PG_AUDIT)
        op.execute(_PG_PARTITIONS)
        op.execute(_PG_INDEXES)
        op.execute(_PG_FUNCTION)
        op.execute(_PG_TRIGGERS)
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
