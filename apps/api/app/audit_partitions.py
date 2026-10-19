"""Monthly audit_log partitions for PostgreSQL.

The initial months are created by migration 0002. Run this once a month so the
next month exists before rows land in the default partition. Each new partition
gets the BEFORE TRUNCATE trigger and, when the role exists, the anyq_app REVOKE.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text


def _trigger(table: str) -> str:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261019_0002_pf0.py"
    spec = importlib.util.spec_from_file_location("pf0_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("audit migration is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit_truncate_trigger(table)


def _shift(year: int, month: int, step: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + step
    return index // 12, index % 12 + 1


def partition_statements(year: int, month: int) -> list[str]:
    """DDL for one month: partition, TRUNCATE guard, and REVOKE from anyq_app."""
    name = f"audit_log_{year:04d}_{month:02d}"
    start_year, start_month = year, month
    end_year, end_month = _shift(year, month, 1)
    start = f"{start_year:04d}-{start_month:02d}-01 00:00:00+00"
    end = f"{end_year:04d}-{end_month:02d}-01 00:00:00+00"
    revoke = f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anyq_app') THEN
    REVOKE UPDATE, DELETE, TRUNCATE ON {name} FROM anyq_app;
  END IF;
END $$
"""
    return [
        (
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF audit_log "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        ),
        _trigger(name),
        revoke,
    ]


def ensure_upcoming(connection, today: datetime | None = None) -> list[str]:
    """Create the current month and the next one. Returns the partition names."""
    moment = today or datetime.now(UTC)
    names = []
    for step in (0, 1):
        year, month = _shift(moment.year, moment.month, step)
        name = f"audit_log_{year:04d}_{month:02d}"
        for statement in partition_statements(year, month):
            if statement.lstrip().startswith("CREATE TRIGGER"):
                trigger = f"trg_{name}_no_truncate"
                exists = connection.execute(
                    text(
                        "SELECT 1 FROM pg_trigger t "
                        "JOIN pg_class c ON c.oid = t.tgrelid "
                        "WHERE t.tgname = :trigger AND c.relname = :table"
                    ),
                    {"trigger": trigger, "table": name},
                ).first()
                if exists:
                    continue
            connection.execute(text(statement))
        names.append(name)
    return names
