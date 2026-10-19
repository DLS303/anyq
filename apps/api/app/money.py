"""Tenge rounding shared by procurement savings and object budgets."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def as_decimal(value: Decimal | float | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_kzt(value: Decimal | float | str) -> int:
    return int(as_decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP))
