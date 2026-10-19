"""Remember a successful create so the same key does not insert a second row.

The claim lives in `idempotency_keys` with a unique (user_id, key) constraint,
so more than one API worker can share it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
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
            select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
        )


def run_idempotent(user_id: str, key: str | None, fingerprint: str, create: Callable[[], T]) -> T:
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
            session.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == cleaned))
            session.commit()
        raise

    encoded = json.dumps(_encode(data), ensure_ascii=False)
    with store._sql.factory() as session:
        row = session.scalar(select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == cleaned))
        if row is not None:
            row.response_json = encoded
            session.commit()
    with _lock:
        _rows[token] = {"fp": fingerprint, "data": data}
    return data
