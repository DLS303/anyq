"""Meetings and action items.

Revision ID: 20261019_0006_pf6
Revises: 20261019_0002_pf0
Create Date: 2026-10-19

down_revision is PR #18 (20261019_0002_pf0). Wave-1 heads are joined later by an
alembic merge revision. Intended order when that lands:
# merge chain: 0002_pf0 -> 0003_pf1a -> 0004_pf2a -> 0005_pf3a -> 0006_pf6

Expand only: new tables. No application models.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261019_0006_pf6"
down_revision = "20261019_0002_pf0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("meeting_date", sa.String(length=10), nullable=False),
        sa.Column("agenda", sa.Text(), nullable=False),
        sa.Column("decisions", sa.Text(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_meetings_company_updated", "meetings", ["company_id", "updated_at"])

    op.create_table(
        "meeting_participants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_meeting_participants_company_updated",
        "meeting_participants",
        ["company_id", "updated_at"],
    )

    op.create_table(
        "action_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("company_id", sa.String(length=180), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("meeting_id", sa.String(length=36), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("assignee_id", sa.String(length=80), nullable=True),
        sa.Column("due_date", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("carried_from_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String(length=40), nullable=True),
        sa.CheckConstraint("status IN ('open', 'done', 'cancelled')", name="ck_action_items_status"),
        sa.CheckConstraint("source IN ('meeting', 'punch', 'rfi')", name="ck_action_items_source"),
    )
    op.create_index("ix_action_items_company_updated", "action_items", ["company_id", "updated_at"])
    op.create_index(
        "ix_actions_assignee",
        "action_items",
        ["assignee_id", "status", "due_date"],
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_actions_assignee", table_name="action_items")
    op.drop_index("ix_action_items_company_updated", table_name="action_items")
    op.drop_table("action_items")
    op.drop_index("ix_meeting_participants_company_updated", table_name="meeting_participants")
    op.drop_table("meeting_participants")
    op.drop_index("ix_meetings_company_updated", table_name="meetings")
    op.drop_table("meetings")
