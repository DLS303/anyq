"""Feature-flag and audit tables. They are not on the store Base, so startup create_all skips them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Pf0Base(DeclarativeBase):
    pass


class CompanyFeature(Pf0Base):
    __tablename__ = "company_features"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(180), nullable=False)
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    changed_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    deleted_at: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (UniqueConstraint("company_id", "key", name="uq_company_features_company_key"),)


class AuditLog(Pf0Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    company_id: Mapped[str | None] = mapped_column(String(180))
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(80))
    actor_token_id: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80))
    project_id: Mapped[str | None] = mapped_column(String(80))
    request_id: Mapped[str | None] = mapped_column(String(80))
    ip: Mapped[str | None] = mapped_column(String(80))
    ua_hash: Mapped[str | None] = mapped_column(String(64))
    changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prev_hash: Mapped[bytes | None] = mapped_column(LargeBinary)
    row_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
