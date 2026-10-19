"""Stored company key. Assigned at registration or invitation, never from a profile field."""

from __future__ import annotations

import re

_BIN_KEY = re.compile(r"^bin:\d{12}$")
_USER_KEY = re.compile(r"^user:\S+$")


def company_key(user) -> str:
    """Tenant key already stored on the user. Empty storage falls back to user:<id>."""
    stored = str(getattr(user, "company_key", "") or "").strip()
    if _BIN_KEY.match(stored) or _USER_KEY.match(stored):
        return stored
    return f"user:{getattr(user, 'id', '')}"


def assign_company_key(user_id: str, company_bin: str, taken_bin_keys: set[str]) -> tuple[str, bool]:
    """Return (key, needs_review). A BIN already used by another company does not join it."""
    digits = re.sub(r"\D", "", company_bin or "")
    if len(digits) == 12:
        key = f"bin:{digits}"
        if key in taken_bin_keys:
            return f"user:{user_id}", True
        return key, False
    return f"user:{user_id}", False
