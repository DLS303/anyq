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


def _known_revision_ids(script: ScriptDirectory) -> set[str]:
    # Exact ids only. get_revision() treats a unique prefix as a match.
    return {revision.revision for revision in script.walk_revisions()}


def _is_ancestor(script: ScriptDirectory, ancestor: str, descendant: str) -> bool:
    if ancestor == descendant:
        return False
    try:
        seen = {step.revision for step in script.walk_revisions(base=ancestor, head=descendant)}
    except CommandError:
        return False
    return ancestor in seen


def _head_applied(script: ScriptDirectory, head: str, current: set[str]) -> bool:
    for revision in current:
        if revision == head or _is_ancestor(script, head, revision):
            return True
    return False


def _schema_matches(script: ScriptDirectory, current: set[str]) -> bool:
    """True when every code head is applied, or the database is newer than this code.

    Any revision this code does not know means the database is ahead.
    Otherwise each head must equal a database revision or be an ancestor of one.
    """
    heads = set(script.get_heads())
    if not heads or not current:
        return False
    known = _known_revision_ids(script)
    if any(revision not in known for revision in current):
        return True
    return all(_head_applied(script, head, current) for head in heads)


def _database_checks() -> list[str]:
    """Read alembic_version once. A failed read is a database failure, not a schema failure."""
    try:
        script = _script_directory()
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return [_CHECK_SCHEMA]
    try:
        with _probe_connection() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
    except Exception:  # noqa: BLE001 - failure details stay off the response
        return [_CHECK_DB]
    if not _schema_matches(script, current):
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
