"""Markup rows. The table is created by Alembic, not by metadata.create_all."""

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class MarkupBase(DeclarativeBase):
    pass


class MarkupRow(MarkupBase):
    __tablename__ = "markups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    revision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_id: Mapped[str] = mapped_column(String(80), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(36))
    shapes: Mapped[list] = mapped_column(JSON, nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_markups_company_updated", "company_id", "updated_at"),
        Index("ix_markups_revision_created", "revision_id", "created_at"),
        Index("ix_markups_file_id", "file_id"),
    )
