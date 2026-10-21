"""The production rule for ANYQ_DEMO_PASSWORD.

Shell startup and the API call this function. The error names the variable
and does not include its value.
"""

from __future__ import annotations

import os


def assert_demo_password_policy() -> None:
    """Demo may set ANYQ_DEMO_PASSWORD. Production must leave it empty."""
    password = os.getenv("ANYQ_DEMO_PASSWORD", "").strip()
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    if env == "production" and password:
        raise RuntimeError("ANYQ_DEMO_PASSWORD must be empty when ANYQ_ENV=production")
