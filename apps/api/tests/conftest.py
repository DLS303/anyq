import os
import tempfile
from pathlib import Path

import pytest

_root = Path(tempfile.mkdtemp(prefix="anyq-test-"))
os.environ["ANYQ_ENV"] = "development"
os.environ["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
os.environ["LOGIN_HASH_SECRET"] = "test-only-login-hash-secret-value-32ch"


def _prepare_postgres() -> None:
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    from alembic import command

    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("ANYQ_TEST_POSTGRES requires DATABASE_URL")
    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    parsed = make_url(raw)
    dbname = f"{parsed.database}_{worker}"
    admin = create_engine(
        parsed.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": dbname},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
        connection.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin.dispose()
    os.environ["DATABASE_URL"] = parsed.set(database=dbname).render_as_string(hide_password=False)
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")


if os.environ.get("ANYQ_TEST_POSTGRES") == "1":
    _prepare_postgres()
else:
    os.environ.pop("DATABASE_URL", None)
os.environ["ANYQ_DB_PATH"] = str(_root / "db.json")
os.environ["ANYQ_UPLOADS_DIR"] = str(_root / "uploads")
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ANYQ_DEMO_PASSWORD"] = ""
os.environ["ANYQ_DEMO_MODE"] = "1"
if os.environ.get("ANYQ_TEST_POSTGRES") != "1":
    from alembic.config import Config

    from alembic import command

    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.ratelimit import login_limiter, signup_limiter

    login_limiter.reset()
    signup_limiter.reset()
    yield
    login_limiter.reset()
    signup_limiter.reset()
