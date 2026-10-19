"""Company feature flags and an append-only audit log.

Revision ID: 20261019_0002
Revises: 20261019_0001
Create Date: 2026-10-19

Works on SQLite and PostgreSQL 16. company_id is indexed. The logical key
(company_id, key) is unique. audit_log rejects UPDATE and DELETE.
"""

import sqlalchemy as sa

from alembic import op
from app.sql_backend import AuditLog, CompanyFeature, install_audit_guards

revision = "20261019_0002"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    CompanyFeature.__table__.create(bind, checkfirst=True)
    # Original columns only. 0005 adds entity_type, entity_id, project_id, changes.
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("at", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_audit_log_company_id", "audit_log", ["company_id"])
    install_audit_guards(bind)


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_audit_log_no_update")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_audit_log_no_delete")
    elif dialect == "postgresql":
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log")
        bind.exec_driver_sql("DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log")
        bind.exec_driver_sql("DROP FUNCTION IF EXISTS forbid_audit_log_mutation()")
    AuditLog.__table__.drop(bind, checkfirst=True)
    CompanyFeature.__table__.drop(bind, checkfirst=True)
