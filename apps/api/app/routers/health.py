"""Process liveness, dependency readiness, and build identity."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.config import settings
from app.paths import uploads_path
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


@router.get("/v1/version")
def version():
    return {
        "version": settings.version,
        "git_sha": os.getenv("GIT_SHA", "").strip(),
        "build_time": os.getenv("BUILD_TIME", "").strip(),
    }


def _script_directory() -> ScriptDirectory:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config()
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _probe_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"timeout": _PROBE_SECONDS, "check_same_thread": False}
    return {"connect_timeout": _PROBE_SECONDS, "options": "-c statement_timeout=2000"}


@contextmanager
def _probe_connection() -> Iterator:
    """Open one short-lived connection that does not use the application pool.

    Connecting and the statements that follow share a 2 second budget.
    """
    started = time.monotonic()
    engine = create_engine(
        store._sql.url,
        future=True,
        poolclass=NullPool,
        connect_args=_probe_connect_args(store._sql.url),
    )
    try:
        with engine.connect() as conn:
            remaining_ms = int((_PROBE_SECONDS - (time.monotonic() - started)) * 1000)
            if remaining_ms <= 0:
                raise TimeoutError("probe exceeded 2s")
            if conn.dialect.name == "postgresql":
                conn.execute(text(f"SET statement_timeout = {remaining_ms}"))
            elif conn.dialect.name == "sqlite":
                conn.exec_driver_sql(f"PRAGMA busy_timeout = {remaining_ms}")
            yield conn
    finally:
        engine.dispose()


def _known_revision(script: ScriptDirectory, revision: str) -> bool:
    try:
        return script.get_revision(revision) is not None
    except CommandError:
        return False


def _ancestor_ids(script: ScriptDirectory, heads: set[str]) -> set[str]:
    found: set[str] = set()
    for head in heads:
        for rev in script.walk_revisions(base="base", head=head):
            if rev.revision not in heads:
                found.add(rev.revision)
    return found


def _schema_matches(script: ScriptDirectory, current: set[str]) -> bool:
    """Head matches. An older known revision does not. An unknown revision does.

    An unknown revision means the database is newer than this code, which is
    what a rolled-back image sees.
    """
    heads = set(script.get_heads())
    if not heads:
        return False
    if current == heads:
        return True
    if not current:
        return False
    ancestors = _ancestor_ids(script, heads)
    saw_unknown = False
    for revision in current:
        if revision in ancestors:
            return False
        if _known_revision(script, revision):
            if revision not in heads:
                return False
            continue
        saw_unknown = True
    if saw_unknown and all(not _known_revision(script, revision) for revision in current):
        return True
    return current == heads


def _db_ok() -> bool:
    try:
        with _probe_connection() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


def _schema_ok() -> bool:
    try:
        script = _script_directory()
        with _probe_connection() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
        return _schema_matches(script, current)
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return False


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
def ready():
    failed: list[str] = []
    for name, probe in (
        (_CHECK_DB, _db_ok),
        (_CHECK_SCHEMA, _schema_ok),
        (_CHECK_UPLOADS, _uploads_ok),
    ):
        if not probe():
            logger.warning("readiness check failed: %s", name)
            failed.append(name)
    if failed:
        return JSONResponse(status_code=503, content={"ok": False, "checks": failed})
    return {"ok": True}
