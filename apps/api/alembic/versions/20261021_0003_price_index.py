"""Daily price index, and a locale-independent name for the observation source.

Revision ID: 20261021_0003_price_index
Revises: 20261021_0002_marketplace
Create Date: 2026-10-21

price_observations stays append-only. This revision renames source_kind to
source_type with ALTER RENAME, which does not rewrite rows and does not fire
the append-only trigger. price_index_daily is rebuilt by the daily job, so the
application role keeps ordinary row privileges on that table.

This file revises 20261021_0002_marketplace. That revision revises
20261021_0003_recipient_status. Drawing revision 20261019_0003_pf1a revises this one.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0003_price_index"
down_revision = "20261021_0002_marketplace"
branch_labels = None
depends_on = None


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _tech(length: int):
    if _postgres():
        return sa.String(length, collation="C")
    return sa.String(length)


def _lock_timeout() -> None:
    if _postgres():
        op.execute("SET lock_timeout = '5s'")


def upgrade() -> None:
    _lock_timeout()
    op.alter_column("price_observations", "source_kind", new_column_name="source_type")
    op.create_table(
        "price_index_daily",
        sa.Column("item_id", _tech(40), primary_key=True),
        sa.Column("city", sa.String(80), primary_key=True),
        sa.Column("day", sa.String(20), primary_key=True),
        sa.Column("median_tiyn", sa.Integer(), nullable=True),
        sa.Column("p25_tiyn", sa.Integer(), nullable=True),
        sa.Column("p75_tiyn", sa.Integer(), nullable=True),
        sa.Column("n_observations", sa.Integer(), nullable=False),
        sa.Column("n_suppliers", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_price_index_daily_item_city_day",
        "price_index_daily",
        ["item_id", "city", "day"],
    )
    if _postgres():
        op.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE price_index_daily TO anyq_app"
        )


def downgrade() -> None:
    _lock_timeout()
    op.drop_index("ix_price_index_daily_item_city_day", table_name="price_index_daily")
    op.drop_table("price_index_daily")
    op.alter_column("price_observations", "source_type", new_column_name="source_kind")
