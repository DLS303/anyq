"""Live invoice identity, so a duplicate cannot be committed.

Revision ID: 20261020_0002_invoice_keys
Revises: 20261019_0001b_store_fixes
Create Date: 2026-10-20
"""

import sqlalchemy as sa

from alembic import op

revision = "20261020_0002_invoice_keys"
down_revision = "20261019_0001b_store_fixes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_identities",
        sa.Column("doc_id", sa.String(80), primary_key=True),
        sa.Column("company_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("supplier_id", sa.String(80), nullable=False, server_default=""),
        sa.Column("number", sa.String(80), nullable=False, server_default=""),
        sa.Column("doc_date", sa.String(40), nullable=False, server_default=""),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "uq_invoice_identity_live",
        "invoice_identities",
        ["company_id", "supplier_id", "number", "doc_date"],
        unique=True,
        sqlite_where=sa.text("deleted = 0"),
        postgresql_where=sa.text("deleted = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_invoice_identity_live", table_name="invoice_identities")
    op.drop_table("invoice_identities")
