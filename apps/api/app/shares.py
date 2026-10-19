"""Expiring public links for a daily photo report.

The raw token is returned once. Only its SHA-256 is stored.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime
from urllib.parse import quote

from app.site_models import DailyLog, Project

MIN_SHARE_DAYS = 14
MAX_SHARE_DAYS = 90
DEFAULT_SHARE_DAYS = 30
PUBLIC_ROBOTS = "noindex, nofollow"


def new_share_token() -> str:
    # 32 bytes → 256 bits, above the 128-bit minimum.
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hashes_match(stored: str | None, digest: str) -> bool:
    if not stored or len(stored) != len(digest):
        return False
    return hmac.compare_digest(stored, digest)


def parse_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def share_is_active(log: DailyLog, now: datetime | None = None) -> bool:
    if not log.share_token_sha256 or log.share_revoked:
        return False
    expires = parse_expiry(log.share_expires_at)
    if expires is None:
        return False
    return expires > (now or datetime.now(UTC))


def share_problem(log: DailyLog | None, digest: str, now: datetime | None = None) -> int | None:
    """None when the link can be read. 404 unknown/revoked, 410 expired."""
    if log is None or not hashes_match(log.share_token_sha256, digest) or log.share_revoked:
        return 404
    expires = parse_expiry(log.share_expires_at)
    if expires is None or expires <= (now or datetime.now(UTC)):
        return 410
    return None


def member_daily(log: DailyLog) -> dict:
    photos = [
        {
            "original_url": f"/v1/files/{photo.original_id}",
            "has_people": photo.has_people,
            "has_plates": photo.has_plates,
            "taken_at": photo.taken_at,
        }
        for photo in log.photos
    ]
    return {
        "id": log.id,
        "project_id": log.project_id,
        "day": log.day,
        "weather": log.weather,
        "temp_c": log.temp_c,
        "workers": log.workers,
        "notes": log.notes,
        "delays": log.delays,
        "delay_hours": log.delay_hours,
        "author_id": log.author_id,
        "author_role": log.author_role,
        "photos": photos,
        "share_active": share_is_active(log),
        "share_expires_at": log.share_expires_at if log.share_token_sha256 and not log.share_revoked else None,
    }


def author_role_of(log: DailyLog, lookup) -> str:
    if log.author_role:
        return log.author_role
    if not log.author_id:
        return ""
    user = lookup(log.author_id)
    if user is None:
        return ""
    return getattr(user, "role", "") or ""


def public_daily(log: DailyLog, project: Project, token: str, lookup) -> dict:
    quoted = quote(token, safe="")
    return {
        "day": log.day,
        "weather": log.weather,
        "temp_c": log.temp_c,
        "workers": log.workers,
        "notes": log.notes,
        "delays": log.delays,
        "delay_hours": log.delay_hours,
        "project_title": project.title,
        "author_role": author_role_of(log, lookup),
        "photos": [{"url": f"/v1/public/files/{photo.public_id}?t={quoted}"} for photo in log.photos],
    }
