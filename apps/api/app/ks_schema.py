"""SQL tables for completed-work acts.

These models use their own metadata so store startup does not create them.
Revision 20261024_0001_ks_acts is the schema. Tests apply it with alembic upgrade head.

signed_file_id has no foreign key: the files table is not on this head.
The id is the existing upload record.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class KsBase(DeclarativeBase):
    pass


class CompanyKey(KsBase):
    """Existing companies row. Present so company_settings can reference legacy_key."""

    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_key: Mapped[str] = mapped_column(String(180), nullable=False)

    __table_args__ = (UniqueConstraint("legacy_key", name="uq_companies_legacy_key"),)


class VatRate(KsBase):
    __tablename__ = "vat_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="KZ", server_default="KZ")
    rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[str] = mapped_column(String(10), nullable=False)
    valid_to: Mapped[str | None] = mapped_column(String(10))
    basis: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_vat_rates_id"),
        CheckConstraint("rate_bp BETWEEN 0 AND 10000", name="ck_vat_rates_rate_bp"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="ck_vat_rates_valid_to"),
        UniqueConstraint("country", "valid_from", name="ux_vat_rates_country_from"),
    )


class CompanySettings(KsBase):
    __tablename__ = "company_settings"

    company_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        ForeignKeyConstraint(
            ["company_id"],
            ["companies.legacy_key"],
            name="fk_company_settings_company_id",
        ),
        Index("ix_company_settings_company_updated", "company_id", "updated_at"),
    )


class KsActCounter(KsBase):
    """Service table. No id and no row_version."""

    __tablename__ = "ks_act_counters"

    company_id: Mapped[str] = mapped_column(String(180), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    next_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (CheckConstraint("next_no > 0", name="ck_ks_act_counters_next_no"),)


class KsAct(KsBase):
    __tablename__ = "ks_acts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    contract_ref: Mapped[str | None] = mapped_column(String(120))
    contract_ref_key: Mapped[str] = mapped_column(String(120), nullable=False, default="", server_default="")
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    act_date: Mapped[str] = mapped_column(String(10), nullable=False)
    period_from: Mapped[str] = mapped_column(String(10), nullable=False)
    period_to: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft", server_default="draft")
    reject_reason_code: Mapped[str | None] = mapped_column(String(40))
    total_tiyn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    vat_tiyn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    total_with_vat_tiyn: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    vat_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_rate_id: Mapped[str | None] = mapped_column(String(36))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="KZT", server_default="KZT")
    signed_file_id: Mapped[str | None] = mapped_column(String(36))
    signed_at: Mapped[str | None] = mapped_column(String(40))
    submitted_at: Mapped[str | None] = mapped_column(String(40))
    budget_fact_written_at: Mapped[str | None] = mapped_column(String(40))
    esf_status: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_ks_acts_id"),
        CheckConstraint("number > 0", name="ck_ks_acts_number"),
        CheckConstraint("period_to >= period_from", name="ck_ks_acts_period"),
        CheckConstraint(
            "status IN ('draft','submitted','signed','rejected','cancelled')",
            name="ck_ks_acts_status",
        ),
        CheckConstraint("total_tiyn >= 0", name="ck_ks_acts_total_tiyn"),
        CheckConstraint("vat_tiyn >= 0", name="ck_ks_acts_vat_tiyn"),
        CheckConstraint("total_with_vat_tiyn >= 0", name="ck_ks_acts_total_with_vat_tiyn"),
        CheckConstraint(
            "total_with_vat_tiyn = total_tiyn + vat_tiyn",
            name="ck_ks_acts_total_with_vat_tiyn_sum",
        ),
        CheckConstraint("vat_rate_bp BETWEEN 0 AND 10000", name="ck_ks_acts_vat_rate_bp"),
        CheckConstraint("currency = 'KZT'", name="ck_ks_acts_currency"),
        ForeignKeyConstraint(["vat_rate_id"], ["vat_rates.id"], name="fk_ks_acts_vat_rate_id"),
        UniqueConstraint("project_id", "number", name="uq_ks_acts_project_number"),
        Index(
            "ux_ks_acts_period_open",
            "project_id",
            "period_from",
            "period_to",
            "contract_ref_key",
            unique=True,
            sqlite_where=sql_text("status <> 'cancelled' AND deleted_at IS NULL"),
            postgresql_where=sql_text("status <> 'cancelled' AND deleted_at IS NULL"),
        ),
        Index("ix_ks_acts_project_status_period", "project_id", "status", "period_to"),
        Index("ix_ks_acts_company_updated", "company_id", "updated_at"),
        Index("ix_ks_acts_signed_file_id", "signed_file_id"),
    )


class KsActLine(KsBase):
    __tablename__ = "ks_act_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    act_id: Mapped[str] = mapped_column(String(36), nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_line_id: Mapped[str | None] = mapped_column(String(80))
    change_order_line_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty_contract: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0, server_default="0")
    qty_prev: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0, server_default="0")
    qty_period: Mapped[float] = mapped_column(Numeric(18, 3), nullable=False, default=0, server_default="0")
    unit_price_tiyn: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount_tiyn: Mapped[int] = mapped_column(BigInteger, nullable=False)
    over_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("length(id) = 36", name="ck_ks_act_lines_id"),
        CheckConstraint("qty_contract >= 0", name="ck_ks_act_lines_qty_contract"),
        CheckConstraint("qty_prev >= 0", name="ck_ks_act_lines_qty_prev"),
        CheckConstraint("qty_period >= 0", name="ck_ks_act_lines_qty_period"),
        CheckConstraint("unit_price_tiyn >= 0", name="ck_ks_act_lines_unit_price_tiyn"),
        CheckConstraint("amount_tiyn >= 0", name="ck_ks_act_lines_amount_tiyn"),
        ForeignKeyConstraint(["act_id"], ["ks_acts.id"], name="fk_ks_act_lines_act_id"),
        UniqueConstraint("act_id", "line_no", name="uq_ks_act_lines_act_line"),
        Index("ix_ks_act_lines_act", "act_id"),
        Index("ix_ks_act_lines_estimate_line", "estimate_line_id"),
        Index("ix_ks_act_lines_company_updated", "company_id", "updated_at"),
    )
