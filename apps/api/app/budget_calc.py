"""Object budget totals. No store access.

Procurement fact is the chosen offer (price × qty, grossed up when VAT is
excluded). An invoice amount is used only when that request has no chosen
offer, so a header total is not added on top of the lines. Manual expenses
are added by category. Savings stay in procurement_calc and are not part of fact.
"""

from __future__ import annotations

from decimal import Decimal

from app.budget_models import CATEGORIES
from app.money import as_decimal, round_kzt
from app.procurement_models import ProcDocument, ProcLine, ProcOffer


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


def mean_progress(pcts: list[int]) -> float | None:
    if not pcts:
        return None
    return sum(pcts) / len(pcts)


def forecast_overrun(plan: int, fact: int, progress_pct: float | None) -> dict:
    """Project fact to 100% of the schedule. Overrun is how far that sits past the plan.

    When fact is already past the plan, the overrun is the current gap.
    """
    if fact > plan > 0:
        return {"forecast_kzt": fact, "overrun_kzt": fact - plan, "overrun_kind": "actual"}
    if plan <= 0 or fact <= 0 or progress_pct is None or progress_pct <= 0 or progress_pct >= 100:
        return {"forecast_kzt": None, "overrun_kzt": 0, "overrun_kind": "none"}
    forecast = round_kzt(Decimal(fact) / (as_decimal(progress_pct) / Decimal(100)))
    overrun = forecast - plan
    if overrun > 0:
        return {"forecast_kzt": forecast, "overrun_kzt": overrun, "overrun_kind": "forecast"}
    return {"forecast_kzt": forecast, "overrun_kzt": 0, "overrun_kind": "none"}


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
