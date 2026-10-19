"""VAT for KS-2 / KS-3 by the act date.

Kazakhstan Tax Code No. 214-VIII, article 503: 12% before 2026-01-01, 16% from that date.
Non-payers use a zero rate («без НДС»).
"""

from datetime import date

VAT_CHANGE = date(2026, 1, 1)
VAT_BASIS = "НК РК № 214-VIII, ст. 503"


def parse_act_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    raw = (value or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError("Дата акта в формате ГГГГ-ММ-ДД") from exc


def vat_rate(act_date: date | str, no_vat: bool = False) -> float:
    if no_vat:
        return 0.0
    day = parse_act_date(act_date)
    if day >= VAT_CHANGE:
        return 0.16
    return 0.12


def vat_quote(act_date: date | str, no_vat: bool = False) -> dict:
    day = parse_act_date(act_date)
    rate = vat_rate(day, no_vat=no_vat)
    percent = int(round(rate * 100))
    return {
        "act_date": day.isoformat(),
        "no_vat": bool(no_vat),
        "vat_rate": rate,
        "vat_percent": percent,
        "basis": "" if no_vat else VAT_BASIS,
    }
