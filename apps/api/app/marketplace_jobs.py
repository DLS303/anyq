"""Daily recompute of supplier_ratings.

Run once a day after deals close:

    python -m app.marketplace_jobs

A new review or a closed deal also recomputes that supplier in the same
transaction. This job refreshes every supplier.
"""

from __future__ import annotations

from app.marketplace_price import market_today
from app.marketplace_service import recompute_all
from app.store import store


def main() -> None:
    session = store._sql.factory()
    try:
        with session.begin():
            count = recompute_all(session, market_today())
    finally:
        session.close()
    print(f"supplier_ratings {count}")


if __name__ == "__main__":
    main()
