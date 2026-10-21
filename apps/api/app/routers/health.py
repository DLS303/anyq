"""Process liveness, dependency readiness, and build identity."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import settings
from app.paths import uploads_path
from app.sql_backend import database_revision_ready
from app.store import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_CHECK_DB = "db"
_CHECK_SCHEMA = "schema"
_CHECK_UPLOADS = "uploads"
_PROBE_SECONDS = 2


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/health")
def health():
    return {"ok": True, "version": settings.version}


def _short_git_sha(value: str) -> str:
    sha = value.strip()
    if sha and all(char in "0123456789abcdefABCDEF" for char in sha):
        return sha[:7].lower()
    return sha


@router.get("/v1/version")
def version():
    return {
        "version": settings.version,
        "git_sha": _short_git_sha(os.getenv("GIT_SHA", "")),
        "build_time": os.getenv("BUILD_TIME", "").strip(),
    }


def _probe_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"timeout": _PROBE_SECONDS, "check_same_thread": False}
    return {"connect_timeout": _PROBE_SECONDS, "options": "-c statement_timeout=2000"}


_probe_engine = create_engine(
    store._sql.url,
    future=True,
    poolclass=NullPool,
    connect_args=_probe_connect_args(store._sql.url),
)


@contextmanager
def _probe_connection() -> Iterator:
    """Open one short-lived connection that does not use the application pool.

    The engine is created once. Connecting and the statements that follow
    share a 2 second budget.
    """
    started = time.monotonic()
    with _probe_engine.connect() as conn:
        remaining_ms = int((_PROBE_SECONDS - (time.monotonic() - started)) * 1000)
        if remaining_ms <= 0:
            raise TimeoutError("probe exceeded 2s")
        if conn.dialect.name == "postgresql":
            conn.execute(text(f"SET statement_timeout = {remaining_ms}"))
        elif conn.dialect.name == "sqlite":
            conn.exec_driver_sql(f"PRAGMA busy_timeout = {remaining_ms}")
        yield conn


def _current_revision(conn) -> str:
    if conn.dialect.name == "sqlite":
        found = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'alembic_version'"
            )
        ).scalar()
    else:
        found = conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar()
    if not found:
        return ""
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return str(version or "")


def _database_checks() -> list[str]:
    """Read alembic_version once. A failed read is a database failure, not a schema failure."""
    try:
        with _probe_connection() as conn:
            version = _current_revision(conn)
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return [_CHECK_DB]
    if not database_revision_ready(version):
        return [_CHECK_SCHEMA]
    return []


def _uploads_ok() -> bool:
    try:
        root = uploads_path()
        if not root.is_dir() or not os.access(root, os.W_OK):
            return False
        with tempfile.NamedTemporaryFile(dir=root, prefix=".ready-", delete=True) as handle:
            handle.write(b"1")
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


@router.get("/v1/health/ready")
@router.get("/ready")
def ready():
    failed: list[str] = []
    for name in _database_checks():
        logger.warning("readiness check failed: %s", name)
        failed.append(name)
    if not _uploads_ok():
        logger.warning("readiness check failed: %s", _CHECK_UPLOADS)
        failed.append(_CHECK_UPLOADS)
    if failed:
        return JSONResponse(status_code=503, content={"ok": False, "checks": failed})
    return {"ok": True}
