"""SQL tables for meetings and action items.

These models use their own metadata so store startup does not create them.
Revision 20261019_0006_pf6 is the schema. Tests apply it with alembic upgrade head.
"""

from sqlalchemy import CheckConstraint, Index, Integer, String, Text
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class MeetingBase(DeclarativeBase):
    pass


class MeetingRow(MeetingBase):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    meeting_date: Mapped[str] = mapped_column(String(10), nullable=False)
    agenda: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decisions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    participants: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (Index("ix_meetings_company_updated", "company_id", "updated_at"),)


class MeetingParticipantRow(MeetingBase):
    __tablename__ = "meeting_participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    meeting_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (Index("ix_meeting_participants_company_updated", "company_id", "updated_at"),)


class ActionItemRow(MeetingBase):
    __tablename__ = "action_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    meeting_id: Mapped[str | None] = mapped_column(String(36))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(80))
    due_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80))
    carried_from_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("status IN ('open', 'done', 'cancelled')", name="ck_action_items_status"),
        CheckConstraint("source IN ('meeting', 'punch', 'rfi')", name="ck_action_items_source"),
        Index("ix_action_items_company_updated", "company_id", "updated_at"),
        Index(
            "ix_actions_assignee",
            "assignee_id",
            "status",
            "due_date",
            sqlite_where=sql_text("deleted_at IS NULL"),
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
    )
