"""Stored company key. Assigned at registration or invitation, never from a profile field."""

from __future__ import annotations

import re
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_BIN_KEY = re.compile(r"^bin:\d{12}$")
_USER_KEY = re.compile(r"^user:\S+$")


def company_key(user) -> str:
    """Tenant key already stored on the user. Empty storage falls back to user:<id>."""
    stored = str(getattr(user, "company_key", "") or "").strip()
    if _BIN_KEY.match(stored) or _USER_KEY.match(stored):
        return stored
    return f"user:{getattr(user, 'id', '')}"


def claim_company_key(session, user_id: str, company_bin: str) -> tuple[str, bool]:
    """Reserve a BIN on the caller's open transaction. A conflict becomes user:<id> plus review.

    The caller commits this insert together with the new user. The companies table comes from
    migration 0002 only. A conflicting BIN rolls back only that insert, so earlier locks stay.
    """
    digits = re.sub(r"\D", "", company_bin or "")
    if len(digits) == 12 and _insert_legacy_key(session, f"bin:{digits}"):
        return f"bin:{digits}", False
    _insert_legacy_key(session, f"user:{user_id}")
    return f"user:{user_id}", len(digits) == 12


def _insert_legacy_key(session, key: str) -> bool:
    try:
        with session.begin_nested():
            session.execute(
                text("INSERT INTO companies (id, legacy_key) VALUES (:id, :key)"),
                {"id": str(uuid4()), "key": key},
            )
        return True
    except IntegrityError:
        return False
