"""Object budget totals. No store access.

Procurement fact is the chosen offer (price × qty, grossed up when VAT is
excluded). An invoice amount is used only when that request has no chosen
offer, so a header total is not added on top of the lines. Manual expenses
are added by category. Savings stay in procurement_calc and are not part of fact.

The forecast is fact divided by the elapsed share of the planned dates.
It is omitted before 20% of that span, and a result above twice the plan
is withheld from the card number (the raw figure stays available for the
explanation).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.budget_models import CATEGORIES
from app.money import as_decimal, round_kzt
from app.procurement_models import ProcDocument, ProcLine, ProcOffer

MIN_ELAPSED = Decimal("0.20")
SANE_MULTIPLE = 2


def _split() -> dict[str, int]:
    return {key: 0 for key in CATEGORIES}


def offer_spend(price: float, vat_included: bool | None, qty: float, vat_rate: float) -> Decimal:
    unit = as_decimal(price)
    if vat_included is False:
        unit = unit * (Decimal(1) + as_decimal(vat_rate))
    return unit * as_decimal(qty)


def procurement_actual(
    lines: list[ProcLine],
    offers: list[ProcOffer],
    documents: list[ProcDocument],
    vat_rate: float,
) -> dict[str, int]:
    by_id = {offer.id: offer for offer in offers}
    materials = Decimal(0)
    covered: set[str] = set()
    for line in lines:
        if not line.selected_offer_id:
            continue
        offer = by_id.get(line.selected_offer_id)
        if offer is None or offer.line_id != line.id:
            continue
        materials += offer_spend(offer.price_kzt, offer.vat_included, line.qty, vat_rate)
        covered.add(line.request_id)
    for doc in documents:
        if doc.duplicate_of or not doc.is_actual or doc.amount_kzt is None:
            continue
        if doc.request_id in covered:
            continue
        materials += as_decimal(doc.amount_kzt)
    totals = _split()
    totals["materials"] = round_kzt(materials)
    return totals


def manual_actual(expenses: list) -> dict[str, int]:
    totals = _split()
    for item in expenses:
        category = item.category if isinstance(item, object) and hasattr(item, "category") else item["category"]
        amount = item.amount_kzt if hasattr(item, "amount_kzt") else item["amount_kzt"]
        if category not in totals:
            continue
        totals[category] += int(amount)
    return totals


def merge_fact(procurement: dict[str, int], manual: dict[str, int]) -> dict[str, int]:
    return {key: int(procurement.get(key, 0)) + int(manual.get(key, 0)) for key in CATEGORIES}


def signal_for(fact: int, plan: int) -> tuple[str, float | None]:
    """Green under 80%, yellow from 80% through 100%, red above 100%."""
    if plan <= 0:
        return ("red" if fact > 0 else "green"), None
    pct = fact * 100 / plan
    if pct > 100:
        return "red", pct
    if pct >= 80:
        return "yellow", pct
    return "green", pct


def _parse_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def planned_window(project_start: str, project_finish: str, tasks: list[tuple[str, str]]) -> tuple[date, date] | None:
    """Object start/finish when both are set. Otherwise the schedule span."""
    start = _parse_date(project_start)
    finish = _parse_date(project_finish)
    if start and finish and finish > start:
        return start, finish
    begins: list[date] = []
    ends: list[date] = []
    for raw_start, raw_finish in tasks:
        task_start = _parse_date(raw_start)
        task_finish = _parse_date(raw_finish)
        if task_start and task_finish and task_finish > task_start:
            begins.append(task_start)
            ends.append(task_finish)
    if not begins:
        return None
    begin, end = min(begins), max(ends)
    if end <= begin:
        return None
    return begin, end


def _forecast_payload(**extra: object) -> dict:
    payload = {
        "forecast_kzt": None,
        "overrun_kzt": 0,
        "overrun_kind": "none",
        "elapsed_share": None,
        "elapsed_days": None,
        "span_days": None,
        "forecast_reason": "no_dates",
        "forecast_raw_kzt": None,
        "forecast_bound_kzt": None,
        "schedule_start": "",
        "schedule_finish": "",
    }
    payload.update(extra)
    return payload


def forecast_overrun(plan: int, fact: int, start: date | None, finish: date | None, today: date) -> dict:
    """Forecast = fact / elapsed share of the planned dates.

    No dates, or less than 20% of the span elapsed: no forecast.
    Fact already above the plan: the overrun is the current gap, not an extrapolation.
    A straight-line result above twice the plan is not shown as the card number.
    """
    bound = plan * SANE_MULTIPLE if plan > 0 else None
    elapsed_days = None
    span_days = None
    share: Decimal | None = None
    schedule_start = ""
    schedule_finish = ""
    if start and finish and finish > start:
        span_days = (finish - start).days
        gone = min(max((today - start).days, 0), span_days)
        elapsed_days = gone
        share = Decimal(gone) / Decimal(span_days) if span_days else Decimal(0)
        schedule_start = start.isoformat()
        schedule_finish = finish.isoformat()
    window = {
        "elapsed_share": float(share) if share is not None else None,
        "elapsed_days": elapsed_days,
        "span_days": span_days,
        "forecast_bound_kzt": bound,
        "schedule_start": schedule_start,
        "schedule_finish": schedule_finish,
    }
    if fact > plan > 0:
        return _forecast_payload(
            forecast_kzt=fact,
            overrun_kzt=fact - plan,
            overrun_kind="actual",
            forecast_reason="actual",
            **window,
        )
    if share is None:
        return _forecast_payload(**window, forecast_reason="no_dates")
    if share < MIN_ELAPSED:
        return _forecast_payload(**window, forecast_reason="early")
    if fact <= 0 or plan <= 0 or share >= 1:
        return _forecast_payload(**window, forecast_reason="ok", forecast_kzt=fact if share >= 1 else None)
    raw = round_kzt(Decimal(fact) / share)
    if bound is not None and raw > bound:
        return _forecast_payload(**window, forecast_reason="above_bound", forecast_raw_kzt=raw)
    overrun = raw - plan
    if overrun > 0:
        return _forecast_payload(
            **window,
            forecast_kzt=raw,
            overrun_kzt=overrun,
            overrun_kind="forecast",
            forecast_reason="ok",
            forecast_raw_kzt=raw,
        )
    return _forecast_payload(**window, forecast_kzt=raw, forecast_reason="ok", forecast_raw_kzt=raw)


def combine_savings(parts: list[dict]) -> dict:
    raw_saving = sum((as_decimal(part.get("savings_raw") or "0") for part in parts), Decimal(0))
    raw_base = sum((as_decimal(part.get("base_raw") or "0") for part in parts), Decimal(0))
    savings_kzt = round_kzt(raw_saving)
    base_kzt = round_kzt(raw_base)
    if any("lines" in part for part in parts):
        requests = sum(1 for part in parts if any(line.get("included") for line in part.get("lines") or []))
    else:
        requests = sum(int(part.get("requests") or 0) for part in parts)
    overprice_total = sum(
        (as_decimal(item.get("total") or 0) for part in parts for item in part.get("overprice") or []),
        Decimal(0),
    )
    return {
        "savings_kzt": savings_kzt,
        "base_kzt": base_kzt,
        "savings_pct": float(Decimal(savings_kzt) / Decimal(base_kzt)) if base_kzt else 0.0,
        "savings_raw": format(raw_saving, "f"),
        "base_raw": format(raw_base, "f"),
        "requests": requests,
        "overprice_count": sum(len(part.get("overprice") or []) for part in parts),
        "overprice_total": float(overprice_total),
    }
