"""Temporary request_recipients model.

The registration branch owns this table. Drop this module when that revision
is on the chain and point offers at the registration model instead.
"""

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.sql_backend import Base, technical_string


class RequestRecipient(Base):
    __tablename__ = "request_recipients"

    id: Mapped[str] = mapped_column(technical_string(40), primary_key=True)
    request_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    company_id: Mapped[str] = mapped_column(technical_string(40), nullable=False)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)

    __table_args__ = (
        UniqueConstraint("request_id", "company_id", name="uq_request_recipients_pair"),
        Index("ix_request_recipients_company", "company_id"),
    )
