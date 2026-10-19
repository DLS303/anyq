"""Append-only audit rows in the shared audit_log table.

`write` only adds the INSERT. The caller commits it in the same transaction
as the change it describes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from app.sql_backend import AuditLog

_PLAIN = {
    "status",
    "row_version",
    "due_date",
    "drawing_revision_id",
    "assignee_user_id",
    "assignee_contact_id",
    "file_id",
    "expires_in_days",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def mask_changes(changes: dict | None) -> dict:
    """Drop names, phones, and free text. Status codes and ids stay."""
    if not changes:
        return {}
    masked: dict = {}
    for key, value in changes.items():
        if key in _PLAIN:
            masked[key] = value
        else:
            masked[key] = "***"
    return masked


def write(
    session,
    action: str,
    entity_type: str,
    entity_id: str,
    project_id: str,
    changes: dict | None,
    *,
    company_id: str,
    actor: str,
) -> None:
    session.add(
        AuditLog(
            event=action[:64],
            company_id=company_id,
            actor=(actor or "")[:80],
            at=_now(),
            key=entity_type[:64],
            entity_type=entity_type[:64],
            entity_id=entity_id[:36],
            project_id=(project_id or "")[:80],
            changes=json.dumps(mask_changes(changes), ensure_ascii=True, sort_keys=True),
        )
    )
