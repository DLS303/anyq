"""Index material and specialist lists by category.

Revision ID: 20261023_0004_list_indexes
Revises: 20261019_0003_pf1a
Create Date: 2026-10-23

List queries filter records by collection and category, then order by seq.
The previous revision dropped the category index and did not replace it.

On PostgreSQL, lock_timeout is 5 seconds and the index is built with
CONCURRENTLY. SQLite uses a plain create_index.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261023_0004_list_indexes"
down_revision = "20261019_0003_pf1a"
branch_labels = None
depends_on = None

INDEX = "ix_records_coll_category_seq"
COLUMNS = ["collection", "category", "seq"]


def _names() -> set[str]:
    bind = op.get_bind()
    return {row["name"] for row in sa.inspect(bind).get_indexes("records")}


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if INDEX in _names():
        return
    if _postgres():
        op.execute("SET lock_timeout = '5s'")
        with op.get_context().autocommit_block():
            op.create_index(INDEX, "records", COLUMNS, postgresql_concurrently=True)
        return
    op.create_index(INDEX, "records", COLUMNS)


def downgrade() -> None:
    if INDEX in _names():
        op.drop_index(INDEX, table_name="records")
