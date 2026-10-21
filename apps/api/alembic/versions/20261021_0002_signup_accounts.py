"""Sign-up accounts on the company row from 20261019_0002_pf0.

Revision ID: 20261021_0002_signup_accounts
Revises: 20261019_0002_pf0
Create Date: 2026-10-21

Does not import application code. Downgrade drops the tables and columns
added here and leaves the company registry from 20261019_0002_pf0 in place.
Email duplicates stay in email_quarantine. This revision does not copy those
addresses back onto a unique index.

The migrator alters the schema. The application role is not changed and is
not asked to run DDL. There is no TRUNCATE. New tables inherit the default
DML grants from 20261021_0001c_app_role. Company membership role owner is a
company_members.role, not records.status owner.

Email uniqueness is lower(email), so it does not follow a locale. On
PostgreSQL, email, phone, and the sign-up code hash use COLLATE "C".
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0002_signup_accounts"
down_revision = "20261019_0002_pf0"
branch_labels = None
depends_on = None

_COMPANY_COLUMNS = (
    ("role", 40),
    ("account_kind", 20),
    ("name", 200),
    ("bin", 12),
    ("iin", 12),
    ("city", 120),
    ("categories", 400),
    ("e_invoice", 120),
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _collate(table: str, column: str, length: int, enabled: bool) -> None:
    if not _postgres():
        return
    suffix = ' COLLATE "C"' if enabled else ""
    op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar({length}){suffix}")


def _email_index(table: str, name: str, where: str) -> None:
    op.create_index(
        name,
        table,
        [sa.text("lower(email)")],
        unique=True,
        sqlite_where=sa.text(where),
        postgresql_where=sa.text(where),
    )


def upgrade() -> None:
    op.drop_index("ux_records_user_email", table_name="records")
    _collate("records", "email", 200, True)
    _email_index("records", "ux_records_user_email", "collection = 'users'")
    with op.batch_alter_table("companies") as batch:
        for name, length in _COMPANY_COLUMNS:
            batch.add_column(sa.Column(name, sa.String(length=length), nullable=True))
        batch.add_column(sa.Column("vat_included", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("created_at", sa.String(length=40), nullable=True))
        batch.create_check_constraint(
            "ck_companies_role",
            "role IS NULL OR role IN ('supplier', 'contractor', 'customer')",
        )
        batch.create_check_constraint(
            "ck_companies_kind",
            "account_kind IS NULL OR account_kind IN ('individual', 'company')",
        )
    op.create_table(
        "accounts",
        sa.Column("user_id", sa.String(length=80), primary_key=True),
        sa.Column("company_id", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("account_kind", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("phone_verified_at", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("bin", sa.String(length=12), nullable=True),
        sa.Column("iin", sa.String(length=12), nullable=True),
        sa.CheckConstraint("phone IS NOT NULL OR email IS NOT NULL", name="ck_accounts_contact"),
        sa.CheckConstraint("role IN ('supplier', 'contractor', 'customer')", name="ck_accounts_role"),
        sa.CheckConstraint("account_kind IN ('individual', 'company')", name="ck_accounts_kind"),
        sa.CheckConstraint("status IN ('pending', 'active')", name="ck_accounts_status"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_accounts_company_id"),
    )
    _collate("accounts", "email", 200, True)
    _collate("accounts", "phone", 20, True)
    _email_index("accounts", "ux_accounts_email", "email IS NOT NULL")
    op.create_index(
        "ux_accounts_phone_verified",
        "accounts",
        ["phone"],
        unique=True,
        sqlite_where=sa.text("phone_verified_at IS NOT NULL"),
        postgresql_where=sa.text("phone_verified_at IS NOT NULL"),
    )
    op.create_table(
        "company_members",
        sa.Column("company_id", sa.String(length=80), primary_key=True),
        sa.Column("user_id", sa.String(length=80), primary_key=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'supplier')", name="ck_company_members_role"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="fk_company_members_company_id"),
    )
    op.create_index("ix_company_members_user", "company_members", ["user_id"])
    op.create_index("ix_company_members_company_role", "company_members", ["company_id", "role"])
    op.create_table(
        "signup_codes",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["accounts.user_id"],
            name="fk_signup_codes_user_id",
            ondelete="CASCADE",
        ),
    )
    _collate("signup_codes", "code_hash", 64, True)
    op.create_index("ix_signup_codes_user", "signup_codes", ["user_id"])
    op.create_table(
        "request_recipients",
        sa.Column("request_id", sa.String(length=80), primary_key=True),
        sa.Column("supplier_company_id", sa.String(length=80), primary_key=True),
        sa.Column("sent_at", sa.String(length=40), nullable=False),
    )
    op.create_index("ix_request_recipients_request", "request_recipients", ["request_id"])
    op.create_index("ix_request_recipients_company", "request_recipients", ["supplier_company_id"])


def downgrade() -> None:
    op.drop_index("ix_request_recipients_company", table_name="request_recipients")
    op.drop_index("ix_request_recipients_request", table_name="request_recipients")
    op.drop_table("request_recipients")
    op.drop_index("ix_signup_codes_user", table_name="signup_codes")
    _collate("signup_codes", "code_hash", 64, False)
    op.drop_table("signup_codes")
    op.drop_index("ix_company_members_company_role", table_name="company_members")
    op.drop_index("ix_company_members_user", table_name="company_members")
    op.drop_table("company_members")
    op.drop_index("ux_accounts_phone_verified", table_name="accounts")
    op.drop_index("ux_accounts_email", table_name="accounts")
    _collate("accounts", "phone", 20, False)
    _collate("accounts", "email", 200, False)
    op.drop_table("accounts")
    with op.batch_alter_table("companies") as batch:
        batch.drop_constraint("ck_companies_kind", type_="check")
        batch.drop_constraint("ck_companies_role", type_="check")
        batch.drop_column("created_at")
        batch.drop_column("vat_included")
        for name, _length in reversed(_COMPANY_COLUMNS):
            batch.drop_column(name)
    op.drop_index("ux_records_user_email", table_name="records")
    _collate("records", "email", 200, False)
    op.create_index(
        "ux_records_user_email",
        "records",
        ["email"],
        unique=True,
        sqlite_where=sa.text("collection = 'users'"),
        postgresql_where=sa.text("collection = 'users'"),
    )
