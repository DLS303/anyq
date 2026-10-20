"""Apply schema revisions once, under a PostgreSQL advisory lock.

The API process does not migrate on startup. Run this module before it:

    python -m app.migrate
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

from alembic import command


def main() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")


if __name__ == "__main__":
    main()
