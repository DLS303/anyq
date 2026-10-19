"""Create the SQL store tables.

Revision ID: 20261019_0001
Revises:
Create Date: 2026-10-19
"""

from alembic import op
from app.sql_backend import Base

revision = "20261019_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # audit_log is created in 0002 with its original columns. 0005 expands it
    # and creates the designer-question tables.
    skip = {"audit_log", "external_contacts", "rfis", "access_tokens"}
    tables = [table for table in Base.metadata.sorted_tables if table.name not in skip]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
