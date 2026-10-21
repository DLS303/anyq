"""Apply schema revisions once, under a PostgreSQL advisory lock.

The API process does not migrate on startup. Run this module before it:

    python -m app.migrate

The owner role in DATABASE_URL runs the revision. When ANYQ_APP_PASSWORD is
set, the same process gives that password to the anyq_app login. The password
is not written into the revision.
"""

from __future__ import annotations

import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command


def _set_app_password() -> None:
    password = os.getenv("ANYQ_APP_PASSWORD", "").strip()
    if not password:
        return
    from app.sql_backend import resolve_database_url

    url = resolve_database_url()
    if not url.startswith("postgresql"):
        return
    engine = create_engine(url, future=True)
    try:
        with engine.begin() as connection:
            exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'anyq_app'")).scalar()
            if not exists:
                return
            connection.execute(text("CREATE TEMP TABLE app_password_once (value text) ON COMMIT DROP"))
            connection.execute(
                text("INSERT INTO app_password_once (value) VALUES (:password)"),
                {"password": password},
            )
            connection.execute(
                text(
                    """
                    DO $$
                    DECLARE
                      secret text;
                    BEGIN
                      SELECT value INTO secret FROM app_password_once;
                      EXECUTE format('ALTER ROLE anyq_app WITH LOGIN PASSWORD %L', secret);
                    END
                    $$;
                    """
                )
            )
    finally:
        engine.dispose()


def main() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    _set_app_password()


if __name__ == "__main__":
    main()
