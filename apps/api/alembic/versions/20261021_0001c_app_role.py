"""API database role, one owner, and a truncate block on consent events.

Revision ID: 20261021_0001c_app_role
Revises: 20261019_0001b_store_fixes
Create Date: 2026-10-21

Downgrade removes the truncate trigger, the single-owner index, and this
database's grants for the login role. The role itself stays, because it is
cluster-wide and other databases may still use it. Consent rows are kept.

On PostgreSQL, lock_timeout is 5 seconds. The new index on the existing
records table is built with CONCURRENTLY. SQLite has no TRUNCATE and no roles.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0001c_app_role"
down_revision = "20261019_0001b_store_fixes"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _lock_timeout() -> None:
    if _postgres():
        op.execute("SET lock_timeout = '5s'")


def _mark_existing_owners() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        match = "payload->>'role' = 'owner'"
    else:
        match = "json_extract(payload, '$.role') = 'owner'"
    bind.execute(
        sa.text(f"UPDATE records SET status = 'owner' WHERE collection = 'users' AND {match}")
    )
    rows = list(
        bind.execute(
            sa.text(
                "SELECT doc_id FROM records "
                "WHERE collection = 'users' AND status = 'owner' "
                "ORDER BY seq, doc_id"
            )
        ).scalars()
    )
    for doc_id in rows[1:]:
        bind.execute(
            sa.text("UPDATE records SET status = NULL WHERE collection = 'users' AND doc_id = :doc_id"),
            {"doc_id": doc_id},
        )


def _create_owner_index() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.create_index(
                "ux_records_single_owner",
                "records",
                ["status"],
                unique=True,
                postgresql_where=sa.text("collection = 'users' AND status = 'owner'"),
                postgresql_concurrently=True,
            )
        return
    op.create_index(
        "ux_records_single_owner",
        "records",
        ["status"],
        unique=True,
        sqlite_where=sa.text("collection = 'users' AND status = 'owner'"),
    )


def _grant_app_role() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anyq_app') THEN
            CREATE ROLE anyq_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
          END IF;
        EXCEPTION
          WHEN duplicate_object THEN
            NULL;
        END
        $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          EXECUTE format('GRANT CONNECT ON DATABASE %I TO anyq_app', current_database());
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO anyq_app")
    op.execute("REVOKE CREATE ON SCHEMA public FROM anyq_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anyq_app"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anyq_app")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE consent_events FROM anyq_app"
    )
    op.execute("GRANT SELECT, INSERT ON TABLE consent_events TO anyq_app")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE alembic_version FROM anyq_app"
    )
    op.execute("GRANT SELECT ON TABLE alembic_version TO anyq_app")
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE email_quarantine FROM anyq_app"
    )
    op.execute("GRANT SELECT ON TABLE email_quarantine TO anyq_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO anyq_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO anyq_app"
    )


def _install_truncate_trigger() -> None:
    op.execute("DROP TRIGGER IF EXISTS consent_events_no_truncate ON consent_events")
    op.execute(
        """
        CREATE TRIGGER consent_events_no_truncate
        BEFORE TRUNCATE ON consent_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION consent_events_append_only()
        """
    )


def _revoke_app_role() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anyq_app') THEN
            RETURN;
          END IF;
          EXECUTE format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM anyq_app', current_database());
        END
        $$;
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM anyq_app")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM anyq_app")
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM anyq_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anyq_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anyq_app"
    )


def upgrade() -> None:
    _lock_timeout()
    _mark_existing_owners()
    _create_owner_index()
    if not _postgres():
        return
    _lock_timeout()
    _install_truncate_trigger()
    _grant_app_role()


def downgrade() -> None:
    _lock_timeout()
    if _postgres():
        op.execute("DROP TRIGGER IF EXISTS consent_events_no_truncate ON consent_events")
        _revoke_app_role()
    op.execute(
        "UPDATE records SET status = NULL WHERE collection = 'users' AND status = 'owner'"
    )
    op.drop_index("ux_records_single_owner", table_name="records")
