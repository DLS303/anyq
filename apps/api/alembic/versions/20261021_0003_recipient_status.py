"""Status and timestamps on supplier request recipients.

Revision ID: 20261021_0003_recipient_status
Revises: 20261021_0002_signup_accounts
Create Date: 2026-10-21

Does not import application code. The migrator adds columns. There is no
TRUNCATE and no role change. Downgrade drops only the columns added here.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261021_0003_recipient_status"
down_revision = "20261021_0002_signup_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("request_recipients") as batch:
        batch.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="sent"))
        batch.add_column(sa.Column("created_at", sa.String(length=40), nullable=False, server_default=""))
        batch.add_column(sa.Column("updated_at", sa.String(length=40), nullable=False, server_default=""))
        batch.create_check_constraint(
            "ck_request_recipients_status",
            "status IN ('sent', 'closed')",
        )
    op.execute(
        "UPDATE request_recipients SET created_at = sent_at, updated_at = sent_at "
        "WHERE created_at = ''"
    )


def downgrade() -> None:
    with op.batch_alter_table("request_recipients") as batch:
        batch.drop_constraint("ck_request_recipients_status", type_="check")
        batch.drop_column("updated_at")
        batch.drop_column("created_at")
        batch.drop_column("status")
