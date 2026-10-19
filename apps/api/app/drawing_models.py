"""SQL rows for drawing sheets. Kept off the records metadata so migration 0001 does not create them."""

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DrawingBase(DeclarativeBase):
    pass


class StoredFile(DrawingBase):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(80))
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    mime: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    meta_stripped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("storage_key", name="ux_files_key"),
        Index("ix_files_company_updated", "company_id", "updated_at"),
    )


class DrawingSetRow(DrawingBase):
    __tablename__ = "drawing_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    discipline: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (Index("ix_drawing_sets_company_updated", "company_id", "updated_at"),)


class DrawingRow(DrawingBase):
    __tablename__ = "drawings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    set_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("drawing_sets.id"))
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_drawings_company_updated", "company_id", "updated_at"),
        Index("ix_drawings_set_id", "set_id"),
        Index(
            "ux_drawings_code",
            "project_id",
            "code",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class DrawingRevisionRow(DrawingBase):
    __tablename__ = "drawing_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    project_id: Mapped[str] = mapped_column(String(80), nullable=False)
    drawing_id: Mapped[str] = mapped_column(String(36), ForeignKey("drawings.id"), nullable=False)
    rev: Mapped[str] = mapped_column(String(16), nullable=False)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uploaded_by: Mapped[str] = mapped_column(String(80), nullable=False)
    uploaded_at: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index("ix_drawing_revisions_company_updated", "company_id", "updated_at"),
        Index("ix_drawing_revisions_file_id", "file_id"),
        Index(
            "ux_drawing_rev",
            "drawing_id",
            "rev",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ux_drawing_current",
            "drawing_id",
            unique=True,
            sqlite_where=text("is_current = 1 AND deleted_at IS NULL"),
            postgresql_where=text("is_current AND deleted_at IS NULL"),
        ),
    )
