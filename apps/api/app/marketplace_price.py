"""Daily price index and the suspicious-price check.

Observations store tiyn excluding VAT. The daily index stores the inclusive
median, p25, and p75 for one item, city, and day. A price more than 50% under
the inclusive median is suspicious and stays out of the index. The index is
shown only when at least three distinct suppliers remain. A thinner city falls
back to the last confirmed price, then to a manual review.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

WINDOW_DAYS = 30
MIN_POINTS = 3
MIN_SUPPLIERS = 3
SUSPICIOUS_RATIO = 0.5
VAT_COMPARE = 16
LOW_DATA = "мало данных"
HAS_MEDIAN = "медиана"
SOURCE_TYPES = frozenset({"offer", "invoice"})


def market_today() -> date:
    override = os.getenv("ANYQ_MARKET_TODAY", "").strip()
    if override:
        return date.fromisoformat(override)
    return date.today()


def incl_tiyn(price_tiyn: int, vat_included: bool, vat_rate: int) -> int:
    if vat_included:
        return int(price_tiyn)
    rate = vat_rate if vat_rate > 0 else VAT_COMPARE
    return round(price_tiyn * (100 + rate) / 100)


def excl_tiyn(price_tiyn: int, vat_included: bool, vat_rate: int) -> int:
    """Store observations without VAT. An inclusive price is ungrossed."""

    if not vat_included:
        return int(price_tiyn)
    rate = vat_rate if vat_rate > 0 else VAT_COMPARE
    return round(price_tiyn * 100 / (100 + rate))


def median_tiyn(values: list[int]) -> int | None:
    if len(values) < MIN_POINTS:
        return None
    return round(statistics.median(values))


def in_window(observed_on: str, as_of: date) -> bool:
    try:
        day = date.fromisoformat(observed_on[:10])
    except ValueError:
        return False
    return as_of - timedelta(days=WINDOW_DAYS) <= day <= as_of


def has_source(source_kind: str | None, source_id: str | None) -> bool:
    return bool((source_kind or "").strip()) and bool((source_id or "").strip())


def index_for(values_incl: list[int]) -> dict:
    median = median_tiyn(values_incl)
    if median is None:
        return {"median_tiyn": None, "median_label": LOW_DATA, "points": len(values_incl)}
    return {"median_tiyn": median, "median_label": HAS_MEDIAN, "points": len(values_incl)}


def judge_price(
    price_incl: int,
    window_incl: list[int],
    last_incl: int | None,
    index_median: int | None = None,
    index_suppliers: int = 0,
) -> dict:
    """Suspicious when the price is under half the benchmark.

    The daily index is the benchmark when it has enough distinct suppliers.
    The raw window remains for a direct check. Otherwise the last confirmed
    price is the fallback, and a missing benchmark needs a manual review.
    """

    if index_median is not None and index_suppliers >= MIN_SUPPLIERS:
        suspicious = price_incl < index_median * SUSPICIOUS_RATIO
        return {"suspicious": suspicious, "manual_review": False, "benchmark_tiyn": index_median, "basis": "index"}
    median = median_tiyn(window_incl)
    if median is not None:
        suspicious = price_incl < median * SUSPICIOUS_RATIO
        return {"suspicious": suspicious, "manual_review": False, "benchmark_tiyn": median, "basis": "median"}
    if last_incl is not None:
        suspicious = price_incl < last_incl * SUSPICIOUS_RATIO
        return {
            "suspicious": suspicious,
            "manual_review": False,
            "benchmark_tiyn": last_incl,
            "basis": "last",
        }
    return {"suspicious": False, "manual_review": True, "benchmark_tiyn": None, "basis": "manual"}


@dataclass(frozen=True)
class PricePoint:
    supplier_id: str
    price_tiyn: int
    vat_included: bool
    vat_rate: int


@dataclass(frozen=True)
class IndexSnapshot:
    median_tiyn: int | None
    p25_tiyn: int | None
    p75_tiyn: int | None
    n_observations: int
    n_suppliers: int


def _percentile(values: list[int], pct: float) -> int:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight)


def _point_incl(point: PricePoint) -> int:
    return incl_tiyn(point.price_tiyn, point.vat_included, point.vat_rate)


def without_suspicious(points: list[PricePoint]) -> list[PricePoint]:
    """Drop prices more than 50% under the inclusive median of this set."""

    if len(points) < MIN_POINTS:
        return list(points)
    values = [_point_incl(point) for point in points]
    median = round(statistics.median(values))
    return [point for point, value in zip(points, values) if value >= median * SUSPICIOUS_RATIO]


def summarize(points: list[PricePoint]) -> IndexSnapshot:
    """Inclusive percentiles of the prices that remain after the suspicious cut.

    Fewer than three distinct suppliers leaves the percentiles empty. The
    counts still record what remained, so a thin city reads as «мало данных».
    """

    kept = without_suspicious(points)
    suppliers = {point.supplier_id for point in kept if point.supplier_id}
    if len(suppliers) < MIN_SUPPLIERS:
        return IndexSnapshot(None, None, None, len(kept), len(suppliers))
    values = [_point_incl(point) for point in kept]
    median = round(statistics.median(values))
    low = min(_percentile(values, 0.25), median)
    high = max(_percentile(values, 0.75), median)
    return IndexSnapshot(median, low, high, len(kept), len(suppliers))


def overpay_parts(price_incl: int, market_incl: int | None) -> tuple[int | None, str]:
    if market_incl is None or market_incl <= 0:
        return None, ""
    pct = round((price_incl - market_incl) * 100 / market_incl)
    if pct > 0:
        return pct, f"дороже рынка на {pct}%"
    if pct < 0:
        return pct, f"дешевле рынка на {-pct}%"
    return 0, "как на рынке"


def market_label(city: str) -> str:
    name = city.strip()
    if not name:
        return "Рыночная цена"
    return f"Рыночная цена в {name}"
