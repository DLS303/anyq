"""Sign-up accounts, company owners, and supplier request recipients.

Revision ID: 20261021_0002_signup_accounts
Revises: 20261021_0001c_app_role
Create Date: 2026-10-21

Does not import application code. Downgrade drops only the tables added here.
Email duplicates stay in email_quarantine from the previous revision; this
revision does not copy those addresses back onto a unique index.

The migrator creates these tables. The application role anyq_app is not
changed here and is not asked to run DDL. There is no TRUNCATE. New tables
inherit the default DML grants from 20261021_0001c_app_role. Company
membership role owner is a company_members.role, not records.status owner.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0002_signup_accounts"
down_revision = "20261021_0001c_app_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("account_kind", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("bin", sa.String(length=12), nullable=True),
        sa.Column("iin", sa.String(length=12), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("categories", sa.String(length=400), nullable=True),
        sa.Column("vat_included", sa.Boolean(), nullable=True),
        sa.Column("e_invoice", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("role IN ('supplier', 'contractor', 'customer')", name="ck_companies_role"),
        sa.CheckConstraint("account_kind IN ('individual', 'company')", name="ck_companies_kind"),
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
    op.create_index(
        "ux_accounts_email",
        "accounts",
        ["email"],
        unique=True,
        sqlite_where=sa.text("email IS NOT NULL"),
        postgresql_where=sa.text("email IS NOT NULL"),
    )
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
    op.drop_table("signup_codes")
    op.drop_index("ix_company_members_company_role", table_name="company_members")
    op.drop_index("ix_company_members_user", table_name="company_members")
    op.drop_table("company_members")
    op.drop_index("ux_accounts_phone_verified", table_name="accounts")
    op.drop_index("ux_accounts_email", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("companies")
