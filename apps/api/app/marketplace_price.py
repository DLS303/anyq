"""Price index and the suspicious-price check.

Medians use confirmed observations that have a source, in tiyn including VAT,
over the last 30 days. Fewer than three points is «мало данных».
A price more than 50% under that median is suspicious. If the window is too
thin, the last confirmed price is the fallback; otherwise the line needs a
manual review. Ranking does not use this as a paid signal.
"""

from __future__ import annotations

import os
import statistics
from datetime import date, timedelta

WINDOW_DAYS = 30
MIN_POINTS = 3
SUSPICIOUS_RATIO = 0.5
VAT_COMPARE = 16
LOW_DATA = "мало данных"
HAS_MEDIAN = "медиана"


def market_today() -> date:
    override = os.getenv("ANYQ_MARKET_TODAY", "").strip()
    if override:
        return date.fromisoformat(override)
    return date.today()


def incl_tiyn(price_tiyn: int, vat_included: bool, vat_rate: int) -> int:
    if vat_included:
        return int(price_tiyn)
    rate = vat_rate if vat_rate > 0 else VAT_COMPARE
    return int(round(price_tiyn * (100 + rate) / 100))


def median_tiyn(values: list[int]) -> int | None:
    if len(values) < MIN_POINTS:
        return None
    return int(round(statistics.median(values)))


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


def judge_price(price_incl: int, window_incl: list[int], last_incl: int | None) -> dict:
    """Suspicious when the price is under half the benchmark."""
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
