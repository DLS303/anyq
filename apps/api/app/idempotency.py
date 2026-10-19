"""Remember a successful create so the same key does not insert a second row."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_rows: dict[tuple[str, str], dict[str, Any]] = {}


class IdempotencyConflict(Exception):
    pass


def run_idempotent(user_id: str, key: str | None, fingerprint: str, create: Callable[[], T]) -> T:
    cleaned = (key or "").strip()
    if not cleaned:
        return create()
    if len(cleaned) > 80:
        raise ValueError("Некорректный ключ идемпотентности")
    token = (user_id, cleaned)
    with _lock:
        row = _rows.get(token)
        if row is None:
            event = threading.Event()
            _rows[token] = {"fp": fingerprint, "event": event}
            owner = True
        else:
            owner = False
            event = row["event"]
            if row["fp"] != fingerprint:
                raise IdempotencyConflict()
            if "data" in row:
                return row["data"]
    if not owner:
        if not event.wait(8):
            raise IdempotencyConflict()
        with _lock:
            done = _rows.get(token)
            if done and done.get("fp") == fingerprint and "data" in done:
                return done["data"]
        raise IdempotencyConflict()
    try:
        data = create()
    except Exception:
        with _lock:
            _rows.pop(token, None)
        event.set()
        raise
    with _lock:
        current = _rows.get(token)
        if current is not None:
            current["data"] = data
    event.set()
    return data
