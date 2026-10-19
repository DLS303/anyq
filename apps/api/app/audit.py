"""Append-only audit log. write() participates in the caller's transaction and does not commit."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import text

from app.pf0_tables import AuditLog

_PII = {"phone", "email", "full_name", "name", "password", "company_bin", "token"}
_KINDS = {"user", "token", "system", "platform_admin", "migration"}


def _mask(value):
    if isinstance(value, dict):
        return {key: "***" if key in _PII else _mask(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_mask(item) for item in value]
    return value


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def write(
    action: str,
    entity_type: str | None,
    entity_id: str | None,
    project_id: str | None,
    changes: dict | None,
    *,
    session,
    company_id: str | None,
    actor_user_id: str | None,
    actor_kind: str = "user",
    request_id: str | None = None,
) -> None:
    """Insert one audit row. The caller commits."""
    if actor_kind not in _KINDS:
        actor_kind = "system"
    moment = datetime.now(UTC)
    masked = _mask(changes or {})
    body = {
        "action": action,
        "actor_kind": actor_kind,
        "actor_user_id": actor_user_id,
        "changes": masked,
        "company_id": company_id,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "occurred_at": _stamp(moment),
        "project_id": project_id,
        "request_id": request_id,
    }
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:company_id))"),
            {"company_id": company_id or ""},
        )
    prev = session.execute(
        text("SELECT row_hash FROM audit_log WHERE company_id = :company_id ORDER BY id DESC LIMIT 1"),
        {"company_id": company_id},
    ).scalar()
    prev_bytes = bytes(prev) if prev else b""
    digest = hashlib.sha256(prev_bytes + raw).digest()
    session.add(
        AuditLog(
            occurred_at=moment,
            company_id=company_id,
            actor_kind=actor_kind,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            request_id=request_id,
            changes=masked,
            prev_hash=prev_bytes or None,
            row_hash=digest,
        )
    )
    session.flush()
