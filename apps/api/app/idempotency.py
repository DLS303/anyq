"""Remember a successful create so the same key does not insert a second row.

The claim lives in `idempotency_keys` with a unique (user_id, key) constraint,
so more than one API worker can share it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

T = TypeVar("T")

_lock = threading.Lock()
_rows: dict[tuple[str, str], dict[str, Any]] = {}


class IdempotencyConflict(Exception):
    pass


def _encode(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _load_row(user_id: str, key: str):
    from app.sql_backend import IdempotencyKey
    from app.store import store

    with store._sql.factory() as session:
        return session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )


def run_idempotent(
    user_id: str,
    key: str | None,
    fingerprint: str,
    create: Callable[[], T],
    *,
    persist: Callable[[T], Any] | None = None,
) -> T:
    cleaned = (key or "").strip()
    if not cleaned:
        return create()
    if len(cleaned) > 80:
        raise ValueError("Некорректный ключ идемпотентности")
    token = (user_id, cleaned)
    with _lock:
        cached = _rows.get(token)
        if cached and cached.get("fp") == fingerprint and "data" in cached:
            return cached["data"]
        if cached and cached.get("fp") != fingerprint:
            raise IdempotencyConflict()

    from app.sql_backend import IdempotencyKey, utc_now
    from app.store import store

    session = store._sql.factory()
    try:
        session.add(
            IdempotencyKey(
                user_id=user_id,
                key=cleaned,
                fingerprint=fingerprint,
                response_json=None,
                created_at=utc_now(),
            )
        )
        session.commit()
        owner = True
    except IntegrityError:
        session.rollback()
        owner = False
    finally:
        session.close()

    if not owner:
        existing = _load_row(user_id, cleaned)
        if existing is None or existing.fingerprint != fingerprint:
            raise IdempotencyConflict()
        if existing.response_json:
            with _lock:
                cached = _rows.get(token)
                if cached and cached.get("fp") == fingerprint and "data" in cached:
                    return cached["data"]
            return json.loads(existing.response_json)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            time.sleep(0.05)
            existing = _load_row(user_id, cleaned)
            if existing is None or existing.fingerprint != fingerprint:
                raise IdempotencyConflict()
            if existing.response_json:
                return json.loads(existing.response_json)
            with _lock:
                cached = _rows.get(token)
                if cached and cached.get("fp") == fingerprint and "data" in cached:
                    return cached["data"]
        raise IdempotencyConflict()

    try:
        data = create()
    except Exception:
        with store._sql.factory() as session:
            session.execute(
                delete(IdempotencyKey).where(
                    IdempotencyKey.user_id == user_id, IdempotencyKey.key == cleaned
                )
            )
            session.commit()
        raise

    stored = data if persist is None else persist(data)
    encoded = json.dumps(_encode(stored), ensure_ascii=False)
    with store._sql.factory() as session:
        row = session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == cleaned
            )
        )
        if row is not None:
            row.response_json = encoded
            session.commit()
    with _lock:
        _rows[token] = {"fp": fingerprint, "data": stored}
    return data


def purge_idempotency_keys(older_than_hours: int = 24) -> int:
    """Delete idempotency rows whose created_at is older than the retention window."""
    cutoff = (datetime.now(UTC) - timedelta(hours=older_than_hours)).isoformat(
        timespec="seconds"
    )
    from app.sql_backend import IdempotencyKey
    from app.store import store

    with store._sql.factory() as session:
        stale = session.scalars(
            select(IdempotencyKey).where(IdempotencyKey.created_at < cutoff)
        ).all()
        tokens = [(row.user_id, row.key) for row in stale]
        if tokens:
            session.execute(
                delete(IdempotencyKey).where(IdempotencyKey.created_at < cutoff)
            )
            session.commit()
    with _lock:
        for item in tokens:
            _rows.pop(item, None)
    return len(tokens)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Delete idempotency keys older than 24 hours"
    )
    parser.add_argument("--older-than-hours", type=int, default=24)
    args = parser.parse_args()
    print(purge_idempotency_keys(args.older_than_hours))


if __name__ == "__main__":
    main()
