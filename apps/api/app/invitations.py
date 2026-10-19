"""One-time company and project invitations.

The raw token is returned once. Only its SHA-256 hash is stored. A link expires
after 7 days, works once, and can be revoked. Nothing is sent by phone or email.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.sql_backend import InvitationRow, utc_now

INVITE_ROLES = frozenset({"supervisor", "foreman", "procurement", "customer", "specialist", "moderator"})
INVITE_DAYS = 7


class InvitationClosed(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session():
    from app.store import store

    return store._sql.factory()


def _row_by_hash(token: str) -> InvitationRow | None:
    digest = _hash(token.strip())
    with _session() as session:
        row = session.scalar(select(InvitationRow).where(InvitationRow.token_hash == digest))
        if row is None:
            return None
        session.expunge(row)
        return row


def _status(row: InvitationRow, now: datetime | None = None) -> str:
    if row.revoked_at:
        return "revoked"
    if row.used_at:
        return "used"
    current = now or datetime.now(UTC)
    expires = datetime.fromisoformat(row.expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= current:
        return "expired"
    return "open"


def _require_inviter(actor, project_id: str | None):
    from app.store import store

    if actor.role not in ("owner", "admin"):
        raise PermissionError("Приглашать может владелец или администратор")
    if not project_id:
        return None
    project = store.get_project(project_id)
    if project is None:
        raise LookupError("Проект не найден")
    if actor.role == "admin":
        return project
    if project.owner_id == actor.id or store.same_company(actor, project.owner_id):
        return project
    raise PermissionError("Недостаточно прав")


def create_invitation(actor, role: str, project_id: str | None = None) -> dict:
    if role not in INVITE_ROLES:
        raise ValueError("Роль приглашения недоступна")
    project = _require_inviter(actor, project_id)
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    expires = now + timedelta(days=INVITE_DAYS)
    row = InvitationRow(
        id=f"inv-{secrets.token_hex(6)}",
        token_hash=_hash(token),
        role=role,
        company_key="",
        company=actor.company or "",
        company_bin=actor.company_bin or "",
        project_id=project.id if project else None,
        invited_by=actor.id,
        created_at=utc_now(),
        expires_at=expires.isoformat(timespec="seconds"),
    )
    from app.store import company_key

    row.company_key = company_key(actor)
    with _session() as session:
        session.add(row)
        session.commit()
    return {
        "id": row.id,
        "token": token,
        "path": f"/invite/{token}",
        "role": row.role,
        "project_id": row.project_id,
        "expires_at": row.expires_at,
        "company": row.company,
    }


def list_invitations(actor, project_id: str | None = None) -> list[dict]:
    _require_inviter(actor, project_id)
    from app.store import company_key

    key = company_key(actor)
    with _session() as session:
        stmt = select(InvitationRow).order_by(InvitationRow.created_at.desc())
        if actor.role != "admin":
            stmt = stmt.where(InvitationRow.company_key == key)
        if project_id:
            stmt = stmt.where(InvitationRow.project_id == project_id)
        rows = session.scalars(stmt).all()
    return [_public(row) for row in rows]


def _public(row: InvitationRow) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "project_id": row.project_id,
        "company": row.company,
        "expires_at": row.expires_at,
        "created_at": row.created_at,
        "status": _status(row),
    }


def preview(token: str) -> dict:
    row = _row_by_hash(token)
    if row is None:
        raise LookupError("Приглашение не найдено")
    from app.store import store

    project_title = ""
    if row.project_id:
        project = store.get_project(row.project_id)
        project_title = project.title if project else ""
    view = _public(row)
    view["project_title"] = project_title
    return view


def revoke(actor, invitation_id: str) -> dict:
    if actor.role not in ("owner", "admin"):
        raise PermissionError("Недостаточно прав")
    from app.store import company_key

    with _session() as session:
        row = session.get(InvitationRow, invitation_id)
        if row is None:
            raise LookupError("Приглашение не найдено")
        if actor.role != "admin" and row.company_key != company_key(actor) and row.invited_by != actor.id:
            raise PermissionError("Недостаточно прав")
        if row.used_at:
            raise ValueError("Приглашение уже принято")
        row.revoked_at = utc_now()
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return _public(row)


def accept(token: str, body, *, ip: str = "", user_agent: str = "") -> tuple:
    row = _row_by_hash(token)
    if row is None:
        raise LookupError("Приглашение не найдено")
    state = _status(row)
    if state == "revoked":
        raise InvitationClosed("revoked", "Приглашение отозвано")
    if state == "used":
        raise InvitationClosed("used", "Приглашение уже использовано")
    if state == "expired":
        raise InvitationClosed("expired", "Срок приглашения истёк")
    if not getattr(body, "consent_offer_pd", False):
        raise ValueError("Нужно согласие на обработку персональных данных")
    from app.store import store

    user, auth = store.create_invited_account(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        phone=body.phone,
        role=row.role,
        company=row.company,
        company_bin=row.company_bin,
        project_id=row.project_id,
        ip=ip,
        user_agent=user_agent,
    )
    with _session() as session:
        current = session.get(InvitationRow, row.id)
        if current is None or current.used_at or current.revoked_at:
            raise InvitationClosed("used", "Приглашение уже использовано")
        current.used_at = utc_now()
        current.used_by = user.id
        session.commit()
    return user, auth
