"""Insert 5000 synthetic catalog rows for a local performance check.

Not loaded at startup and not part of the demo fixture.

    ANYQ_MARKET_PERF=1 python -m scripts.seed_market_perf
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

PERF_COUNT = 5000
CATEGORIES = ("Металлопрокат", "Сэндвич-панели", "Крепёж", "Утеплитель")


def synthetic_rows(count: int = PERF_COUNT) -> list[dict]:
    rows = []
    for index in range(count):
        category = CATEGORIES[index % len(CATEGORIES)]
        rows.append(
            {
                "id": f"perf-{index}-{uuid4().hex[:8]}",
                "company_id": "msup-1",
                "category": category,
                "name": f"Синтетическая позиция {index}",
                "unit": "шт",
                "price_tiyn": 10000 + index,
                "city": "Алматы",
            }
        )
    return rows


def main() -> None:
    if os.getenv("ANYQ_MARKET_PERF") != "1":
        sys.exit("set ANYQ_MARKET_PERF=1 to load synthetic performance rows")
    from app.marketplace_models import CatalogItem
    from app.marketplace_service import search_text_of
    from app.store import store

    session = store._sql.factory()
    try:
        with session.begin():
            for row in synthetic_rows():
                session.add(
                    CatalogItem(
                        id=row["id"],
                        company_id=row["company_id"],
                        category=row["category"],
                        name=row["name"],
                        brand="",
                        unit=row["unit"],
                        price_tiyn=row["price_tiyn"],
                        vat_included=True,
                        vat_rate=16,
                        price_date="2026-10-20",
                        valid_days=7,
                        source="fixtures/synthetic-perf.pdf",
                        source_kind="file",
                        stock="in_stock",
                        lead_days=0,
                        city=row["city"],
                        min_qty=1,
                        hidden=False,
                        search_text=search_text_of(row["name"], row["category"]),
                        created_at="2026-10-21T00:00:00+00:00",
                        updated_at="2026-10-21T00:00:00+00:00",
                    )
                )
    finally:
        session.close()


if __name__ == "__main__":
    main()
