"""Stored company key. Assigned at registration or invitation, never from a profile field."""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_BIN_KEY = re.compile(r"^bin:\d{12}$")
_USER_KEY = re.compile(r"^user:\S+$")

_COMPANIES = """
CREATE TABLE IF NOT EXISTS companies (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    legacy_key VARCHAR(180) NOT NULL,
    CONSTRAINT uq_companies_legacy_key UNIQUE (legacy_key)
)
"""


def company_key(user) -> str:
    """Tenant key already stored on the user. Empty storage falls back to user:<id>."""
    stored = str(getattr(user, "company_key", "") or "").strip()
    if _BIN_KEY.match(stored) or _USER_KEY.match(stored):
        return stored
    return f"user:{getattr(user, 'id', '')}"


def claim_company_key(engine, user_id: str, company_bin: str) -> tuple[str, bool]:
    """Reserve a BIN with INSERT into companies. A conflicting BIN becomes user:<id> plus review."""
    _ensure_companies(engine)
    digits = re.sub(r"\D", "", company_bin or "")
    if len(digits) == 12 and _insert_legacy_key(engine, f"bin:{digits}"):
        return f"bin:{digits}", False
    user_key = f"user:{user_id}"
    _insert_legacy_key(engine, user_key)
    return user_key, len(digits) == 12


def _ensure_companies(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(_COMPANIES))


def _insert_legacy_key(engine, key: str) -> bool:
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO companies (id, legacy_key) VALUES (:id, :key)"),
                {"id": str(uuid4()), "key": key},
            )
        return True
    except IntegrityError:
        return False
