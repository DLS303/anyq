"""Rules for ANYQ_DEMO_PASSWORD.

Shell startup and the API call this function. Errors name the variable
and do not include its value.
"""

from __future__ import annotations

import os

_OBVIOUS = ("password", "demo", "change-me", "changeme", "change_me")


def _seeding_enabled() -> bool:
    """Same gate as the demo seed: demo mode, and demo or development."""
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    if env not in {"demo", "development"}:
        return False
    flag = os.getenv("ANYQ_DEMO_MODE", "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _class_count(password: str) -> int:
    return sum(
        (
            any(char.islower() for char in password),
            any(char.isupper() for char in password),
            any(char.isdigit() for char in password),
            any(not char.isalnum() for char in password),
        )
    )


def assert_demo_password_policy() -> None:
    """Production must leave the variable empty. A set demo password must be strong.

    An empty value still starts the demo and leaves login disabled.
    """
    password = os.getenv("ANYQ_DEMO_PASSWORD", "").strip()
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    if env == "production" and password:
        raise RuntimeError("ANYQ_DEMO_PASSWORD must be empty when ANYQ_ENV=production")
    if not password or not _seeding_enabled():
        return
    if len(password) < 16:
        raise RuntimeError("ANYQ_DEMO_PASSWORD must be at least 16 characters")
    if _class_count(password) < 3:
        raise RuntimeError(
            "ANYQ_DEMO_PASSWORD must use at least 3 of 4 classes: lower, upper, digit, symbol"
        )
    folded = password.casefold()
    if any(token in folded for token in _OBVIOUS):
        raise RuntimeError("ANYQ_DEMO_PASSWORD contains an obvious value")
