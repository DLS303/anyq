"""Index material and specialist lists by category.

Revision ID: 20261021_0002_list_indexes
Revises: 20261019_0001b_store_fixes
Create Date: 2026-10-21

List queries filter records by collection and category, then order by seq.
The previous revision dropped the category index and did not replace it.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0002_list_indexes"
down_revision = "20261019_0001b_store_fixes"
branch_labels = None
depends_on = None

INDEX = "ix_records_coll_category_seq"
COLUMNS = ["collection", "category", "seq"]


def _names() -> set[str]:
    bind = op.get_bind()
    return {row["name"] for row in sa.inspect(bind).get_indexes("records")}


def upgrade() -> None:
    if INDEX not in _names():
        op.create_index(INDEX, "records", COLUMNS)


def downgrade() -> None:
    if INDEX in _names():
        op.drop_index(INDEX, table_name="records")
