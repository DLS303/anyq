"""Completed-work acts, VAT rates, and company settings.

Revision ID: 20261024_0001_ks_acts
Revises: 20261019_0006_pf6
Create Date: 2026-10-24

down_revision is the single head on this branch. plots-drop is not present.
Expand only: new tables and nullable columns. No application models.

ks_act_counters is a service table: company_id + project_id, next_no, updated_at.
It has no id and no row_version.
"""

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from alembic import op

revision = "20261024_0001_ks_acts"
down_revision = "20261019_0006_pf6"
branch_labels = None
depends_on = None

_STAMP = "2026-10-24T00:00:00+00:00"
_BASIS = "НК РК № 214-VIII, ст. 503"


def _std() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    ]


def _vat_exclude() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    nested = bind.begin_nested()
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        bind.execute(
            sa.text(
                "ALTER TABLE vat_rates ADD CONSTRAINT ex_vat_rates_overlap "
                "EXCLUDE USING gist ("
                "country WITH =, "
                "daterange(valid_from::date, coalesce(valid_to::date, 'infinity'::date), '[]') WITH &&"
                ")"
            )
        )
        nested.commit()
    except SQLAlchemyError:
        nested.rollback()


def upgrade() -> None:
    op.create_table(
        "vat_rates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("country", sa.String(length=2), nullable=False, server_default="KZ"),
        sa.Column("rate_bp", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.String(length=10), nullable=False),
        sa.Column("valid_to", sa.String(length=10), nullable=True),
        sa.Column("basis", sa.String(length=120), nullable=False, server_default=""),
        *_std(),
        sa.CheckConstraint("length(id) = 36", name="ck_vat_rates_id"),
        sa.CheckConstraint("rate_bp BETWEEN 0 AND 10000", name="ck_vat_rates_rate_bp"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from",
            name="ck_vat_rates_valid_to",
        ),
        sa.UniqueConstraint("country", "valid_from", name="ux_vat_rates_country_from"),
    )
    vat = sa.table(
        "vat_rates",
        sa.column("id", sa.String),
        sa.column("country", sa.String),
        sa.column("rate_bp", sa.Integer),
        sa.column("valid_from", sa.String),
        sa.column("valid_to", sa.String),
        sa.column("basis", sa.String),
        sa.column("created_at", sa.String),
        sa.column("updated_at", sa.String),
        sa.column("created_by", sa.String),
        sa.column("updated_by", sa.String),
        sa.column("row_version", sa.Integer),
        sa.column("deleted_at", sa.String),
    )
    op.bulk_insert(
        vat,
        [
            {
                "id": "00000000-0000-4000-8000-000000000012",
                "country": "KZ",
                "rate_bp": 1200,
                "valid_from": "2009-01-01",
                "valid_to": "2025-12-31",
                "basis": _BASIS,
                "created_at": _STAMP,
                "updated_at": _STAMP,
                "created_by": "migration",
                "updated_by": "migration",
                "row_version": 1,
                "deleted_at": None,
            },
            {
                "id": "00000000-0000-4000-8000-000000000016",
                "country": "KZ",
                "rate_bp": 1600,
                "valid_from": "2026-01-01",
                "valid_to": None,
                "basis": _BASIS,
                "created_at": _STAMP,
                "updated_at": _STAMP,
                "created_by": "migration",
                "updated_by": "migration",
                "row_version": 1,
                "deleted_at": None,
            },
        ],
    )
    _vat_exclude()

    op.create_table(
        "company_settings",
        sa.Column("company_id", sa.String(length=180), primary_key=True),
        *_std(),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.legacy_key"],
            name="fk_company_settings_company_id",
        ),
    )
    op.create_index(
        "ix_company_settings_company_updated",
        "company_settings",
        ["company_id", "updated_at"],
    )

    with op.batch_alter_table("idempotency_keys") as batch:
        batch.add_column(sa.Column("company_id", sa.String(length=180), nullable=True))
        batch.add_column(sa.Column("scope", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("status", sa.String(length=12), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.String(length=40), nullable=True))
        batch.create_check_constraint(
            "ck_idempotency_keys_status",
            "status IS NULL OR status IN ('in_progress', 'done')",
        )
    op.create_index(
        "ux_idempotency_company_user_key",
        "idempotency_keys",
        ["company_id", "user_id", "key"],
        unique=True,
        sqlite_where=sa.text("company_id IS NOT NULL"),
        postgresql_where=sa.text("company_id IS NOT NULL"),
    )
    op.create_index(
        "ix_idempotency_company_updated",
        "idempotency_keys",
        ["company_id", "updated_at"],
    )
    op.create_index("ix_idempotency_expires", "idempotency_keys", ["expires_at"])

    op.create_table(
        "ks_act_counters",
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("next_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("next_no > 0", name="ck_ks_act_counters_next_no"),
        sa.PrimaryKeyConstraint("company_id", "project_id", name="pk_ks_act_counters"),
    )

    op.create_table(
        "ks_acts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("contract_ref", sa.String(length=120), nullable=True),
        sa.Column("contract_ref_key", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("act_date", sa.String(length=10), nullable=False),
        sa.Column("period_from", sa.String(length=10), nullable=False),
        sa.Column("period_to", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="draft"),
        sa.Column("reject_reason_code", sa.String(length=40), nullable=True),
        sa.Column("total_tiyn", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vat_tiyn", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_with_vat_tiyn", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("vat_rate_bp", sa.Integer(), nullable=False),
        sa.Column("vat_rate_id", sa.String(length=36), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="KZT"),
        sa.Column("signed_file_id", sa.String(length=36), nullable=True),
        sa.Column("signed_at", sa.String(length=40), nullable=True),
        sa.Column("submitted_at", sa.String(length=40), nullable=True),
        sa.Column("budget_fact_written_at", sa.String(length=40), nullable=True),
        sa.Column("esf_status", sa.String(length=12), nullable=True),
        *_std(),
        sa.CheckConstraint("length(id) = 36", name="ck_ks_acts_id"),
        sa.CheckConstraint("number > 0", name="ck_ks_acts_number"),
        sa.CheckConstraint("period_to >= period_from", name="ck_ks_acts_period"),
        sa.CheckConstraint(
            "status IN ('draft','submitted','signed','rejected','cancelled')",
            name="ck_ks_acts_status",
        ),
        sa.CheckConstraint("total_tiyn >= 0", name="ck_ks_acts_total_tiyn"),
        sa.CheckConstraint("vat_tiyn >= 0", name="ck_ks_acts_vat_tiyn"),
        sa.CheckConstraint("total_with_vat_tiyn >= 0", name="ck_ks_acts_total_with_vat_tiyn"),
        sa.CheckConstraint(
            "total_with_vat_tiyn = total_tiyn + vat_tiyn",
            name="ck_ks_acts_total_with_vat_tiyn_sum",
        ),
        sa.CheckConstraint("vat_rate_bp BETWEEN 0 AND 10000", name="ck_ks_acts_vat_rate_bp"),
        sa.CheckConstraint("currency = 'KZT'", name="ck_ks_acts_currency"),
        sa.ForeignKeyConstraint(["vat_rate_id"], ["vat_rates.id"], name="fk_ks_acts_vat_rate_id"),
        sa.UniqueConstraint("project_id", "number", name="uq_ks_acts_project_number"),
    )
    op.create_index(
        "ux_ks_acts_period_open",
        "ks_acts",
        ["project_id", "period_from", "period_to", "contract_ref_key"],
        unique=True,
        sqlite_where=sa.text("status <> 'cancelled' AND deleted_at IS NULL"),
        postgresql_where=sa.text("status <> 'cancelled' AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_ks_acts_project_status_period",
        "ks_acts",
        ["project_id", "status", "period_to"],
    )
    op.create_index("ix_ks_acts_company_updated", "ks_acts", ["company_id", "updated_at"])
    op.create_index("ix_ks_acts_signed_file_id", "ks_acts", ["signed_file_id"])

    op.create_table(
        "ks_act_lines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("act_id", sa.String(length=36), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("estimate_line_id", sa.String(length=80), nullable=True),
        sa.Column("change_order_line_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("qty_contract", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("qty_prev", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("qty_period", sa.Numeric(18, 3), nullable=False, server_default="0"),
        sa.Column("unit_price_tiyn", sa.BigInteger(), nullable=False),
        sa.Column("amount_tiyn", sa.BigInteger(), nullable=False),
        sa.Column("over_contract", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_std(),
        sa.CheckConstraint("length(id) = 36", name="ck_ks_act_lines_id"),
        sa.CheckConstraint("qty_contract >= 0", name="ck_ks_act_lines_qty_contract"),
        sa.CheckConstraint("qty_prev >= 0", name="ck_ks_act_lines_qty_prev"),
        sa.CheckConstraint("qty_period >= 0", name="ck_ks_act_lines_qty_period"),
        sa.CheckConstraint("unit_price_tiyn >= 0", name="ck_ks_act_lines_unit_price_tiyn"),
        sa.CheckConstraint("amount_tiyn >= 0", name="ck_ks_act_lines_amount_tiyn"),
        sa.ForeignKeyConstraint(["act_id"], ["ks_acts.id"], name="fk_ks_act_lines_act_id"),
        sa.UniqueConstraint("act_id", "line_no", name="uq_ks_act_lines_act_line"),
    )
    op.create_index("ix_ks_act_lines_act", "ks_act_lines", ["act_id"])
    op.create_index("ix_ks_act_lines_estimate_line", "ks_act_lines", ["estimate_line_id"])
    op.create_index(
        "ix_ks_act_lines_company_updated",
        "ks_act_lines",
        ["company_id", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ks_act_lines_company_updated", table_name="ks_act_lines")
    op.drop_index("ix_ks_act_lines_estimate_line", table_name="ks_act_lines")
    op.drop_index("ix_ks_act_lines_act", table_name="ks_act_lines")
    op.drop_table("ks_act_lines")
    op.drop_index("ix_ks_acts_signed_file_id", table_name="ks_acts")
    op.drop_index("ix_ks_acts_company_updated", table_name="ks_acts")
    op.drop_index("ix_ks_acts_project_status_period", table_name="ks_acts")
    op.drop_index("ux_ks_acts_period_open", table_name="ks_acts")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE vat_rates DROP CONSTRAINT IF EXISTS ex_vat_rates_overlap"))
    op.drop_table("ks_acts")
    op.drop_table("ks_act_counters")
    op.drop_index("ix_idempotency_expires", table_name="idempotency_keys")
    op.drop_index("ix_idempotency_company_updated", table_name="idempotency_keys")
    op.drop_index("ux_idempotency_company_user_key", table_name="idempotency_keys")
    with op.batch_alter_table("idempotency_keys") as batch:
        batch.drop_constraint("ck_idempotency_keys_status", type_="check")
        batch.drop_column("expires_at")
        batch.drop_column("updated_at")
        batch.drop_column("status")
        batch.drop_column("scope")
        batch.drop_column("company_id")
    op.drop_index("ix_company_settings_company_updated", table_name="company_settings")
    op.drop_table("company_settings")
    op.drop_table("vat_rates")
