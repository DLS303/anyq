"""Create this month and next month of audit_log. PostgreSQL only.

    python scripts/ensure_audit_partition.py
"""

from sqlalchemy import create_engine, text

from app.audit_partitions import ensure_upcoming
from app.sql_backend import resolve_database_url


def main() -> None:
    engine = create_engine(resolve_database_url(), future=True)
    with engine.begin() as connection:
        if connection.dialect.name != "postgresql":
            print("audit partitions are created on PostgreSQL only")
            return
        ready = connection.execute(text("SELECT to_regclass('public.audit_log')")).scalar()
        if ready is None:
            raise SystemExit("audit_log is missing; run alembic upgrade head first")
        names = ensure_upcoming(connection)
    print("audit partitions ready: " + ", ".join(names))


if __name__ == "__main__":
    main()
