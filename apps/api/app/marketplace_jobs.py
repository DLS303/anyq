"""Daily recompute of supplier ratings and the price index.

Run once a day:

    python -m app.marketplace_jobs

A new review recomputes that supplier in the same transaction. A new
observation recomputes that day's price index in the same transaction.
This job refreshes every supplier and rewrites today's index.
"""

from __future__ import annotations

from app.marketplace_price import market_today
from app.marketplace_service import recompute_all, recompute_price_index
from app.store import store


def main() -> None:
    session = store._sql.factory()
    try:
        with session.begin():
            today = market_today()
            ratings = recompute_all(session, today)
            index_rows = recompute_price_index(session, today)
    finally:
        session.close()
    print(f"supplier_ratings {ratings}")
    print(f"price_index_daily {index_rows}")


if __name__ == "__main__":
    main()
