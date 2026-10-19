"""Process liveness, dependency readiness, and build identity."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.paths import uploads_dir
from app.store import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_CHECK_DB = "db"
_CHECK_ALEMBIC = "alembic"
_CHECK_UPLOADS = "uploads"
_heads: set[str] | None = None


@router.get("/healthz")
def healthz():
    return {"ok": True}


@router.get("/health")
def health():
    return {"ok": True, "version": settings.version}


@router.get("/v1/version")
def version():
    return {
        "version": settings.version,
        "git_sha": os.getenv("GIT_SHA", "").strip(),
        "build_time": os.getenv("BUILD_TIME", "").strip(),
    }


def _alembic_heads() -> set[str]:
    global _heads
    if _heads is None:
        api_root = Path(__file__).resolve().parents[2]
        cfg = Config()
        cfg.set_main_option("script_location", str(api_root / "alembic"))
        found = set(ScriptDirectory.from_config(cfg).get_heads())
        if found:
            _heads = found
        return found
    return set(_heads)


@contextmanager
def _probe_connection() -> Iterator:
    """Borrow a pooled connection for one readiness probe.

    PostgreSQL ``statement_timeout`` is transaction-local and ends on rollback,
    so later requests on the same connection keep their previous timeout.
    """
    with store._sql.engine.connect() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
        elif dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA busy_timeout = 2000")
        try:
            yield conn
        finally:
            if dialect == "sqlite":
                conn.exec_driver_sql("PRAGMA busy_timeout = 5000")
            conn.rollback()


def _db_ok() -> bool:
    try:
        with _probe_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


def _alembic_ok() -> bool:
    try:
        heads = _alembic_heads()
        if not heads:
            return False
        with _probe_connection() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
        return current == heads
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


def _uploads_ok() -> bool:
    try:
        root = uploads_dir()
        with tempfile.NamedTemporaryFile(dir=root, prefix=".ready-", delete=True) as handle:
            handle.write(b"1")
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


@router.get("/v1/health/ready")
def ready():
    failed: list[str] = []
    for name, probe in (
        (_CHECK_DB, _db_ok),
        (_CHECK_ALEMBIC, _alembic_ok),
        (_CHECK_UPLOADS, _uploads_ok),
    ):
        if not probe():
            logger.warning("readiness check failed: %s", name)
            failed.append(name)
    if failed:
        return JSONResponse(status_code=503, content={"ok": False, "checks": failed})
    return {"ok": True}
