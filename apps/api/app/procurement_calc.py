"""Pure comparison for a procurement request. No store access."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from app.money import as_decimal, round_kzt
from app.procurement_models import ProcDocument, ProcLine, ProcOffer

STATUS_TEXT = {
    "no_price": "нет цены",
    "one_offer": "одно предложение",
    "no_compare": "нет сравнения",
    "compared": "сравнено",
}

_PHONE = re.compile(r"(?:\+\s*)?(?:\d[\s\-()]*){10,}\d")
_EMAIL = re.compile(r"\S+@\S+")


def norm_supplier(name: str) -> str:
    return " ".join((name or "").casefold().split())


def strip_contacts(text: str) -> tuple[str, bool]:
    """Drop phone numbers and email addresses. Returns cleaned text and whether any were removed."""
    raw = text or ""
    cleaned = _EMAIL.sub("", _PHONE.sub("", raw))
    cleaned = " ".join(cleaned.split())
    return cleaned, cleaned != " ".join(raw.split())


def assert_org_name(name: str) -> str:
    text, removed = strip_contacts(name)
    if removed or not text:
        raise ValueError("Укажите название организации, без телефона и почты")
    if len(text) > 200:
        raise ValueError("Название организации длиннее 200 символов")
    return text


def clean_note(text: str, limit: int = 500) -> str:
    cleaned, _removed = strip_contacts(text or "")
    return cleaned[:limit]


def pos_key(pos: str) -> tuple:
    parts = re.split(r"(\d+)", pos or "")
    key: list[tuple] = []
    for part in parts:
        if part.isdigit():
            key.append((0, int(part)))
        elif part:
            key.append((1, part.casefold()))
    return tuple(key)


def _offer_view(offer: ProcOffer, line: ProcLine, best_id: str | None, selected_id: str | None) -> dict:
    short = offer.qty_available is not None and offer.qty_available < line.qty
    return {
        "id": offer.id,
        "line_id": offer.line_id,
        "supplier_name": offer.supplier_name,
        "price_kzt": offer.price_kzt,
        "vat_included": offer.vat_included,
        "qty_available": offer.qty_available,
        "source_doc_id": offer.source_doc_id,
        "source_label": offer.source_label,
        "offer_date": offer.offer_date,
        "confirmed": offer.confirmed,
        "note": offer.note,
        "delivery_term": offer.delivery_term,
        "is_best": offer.id == best_id,
        "is_selected": offer.id == selected_id,
        "short": short,
    }


def _classify(offers: list[ProcOffer]) -> tuple[str, bool, ProcOffer | None]:
    if not offers:
        return "no_price", False, None
    confirmed = [offer for offer in offers if offer.confirmed]
    if len(offers) == 1:
        only = offers[0]
        if only.confirmed and only.vat_included is not None:
            return "one_offer", True, only
        return "one_offer", False, None
    if not confirmed:
        return "no_compare", False, None
    bases = {offer.vat_included for offer in confirmed}
    if None in bases or len(bases) != 1:
        return "no_compare", False, None
    same = [offer for offer in confirmed if offer.vat_included is not None]
    if len(same) == 1:
        return "one_offer", True, same[0]
    best = min(same, key=lambda offer: (offer.price_kzt, offer.id))
    return "compared", True, best


def _display_offer(group: list[ProcOffer]) -> ProcOffer:
    confirmed = [offer for offer in group if offer.confirmed]
    pool = confirmed or group
    return min(pool, key=lambda offer: (offer.price_kzt, offer.id))


def build_sheet(lines: list[ProcLine], offers: list[ProcOffer]) -> dict:
    ordered = sorted(lines, key=lambda line: (pos_key(line.pos_no), line.id))
    by_line: dict[str, list[ProcOffer]] = defaultdict(list)
    for offer in offers:
        by_line[offer.line_id].append(offer)

    supplier_names: list[str] = []
    seen: set[str] = set()
    for line in ordered:
        for offer in by_line.get(line.id, []):
            if offer.supplier_name not in seen:
                seen.add(offer.supplier_name)
                supplier_names.append(offer.supplier_name)

    totals = {name: 0.0 for name in supplier_names}
    priced = {name: 0 for name in supplier_names}
    vat_sets: dict[str, set] = {name: set() for name in supplier_names}
    out_lines = []
    for line in ordered:
        group = by_line.get(line.id, [])
        status, comparable, best = _classify(group)
        best_id = best.id if best else None
        views = [_offer_view(offer, line, best_id, line.selected_offer_id) for offer in group]
        by_supplier: dict[str, list[ProcOffer]] = defaultdict(list)
        for offer in group:
            by_supplier[offer.supplier_name].append(offer)
        cells = {}
        for name in supplier_names:
            bucket = by_supplier.get(name) or []
            if not bucket:
                cells[name] = None
                continue
            chosen = _display_offer(bucket)
            cells[name] = _offer_view(chosen, line, best_id, line.selected_offer_id)
            totals[name] += chosen.price_kzt * line.qty
            priced[name] += 1
            vat_sets[name].add(chosen.vat_included)
        focus = None
        if line.selected_offer_id:
            focus = next((offer for offer in group if offer.id == line.selected_offer_id), None)
        if focus is None:
            focus = best
        short = bool(focus and focus.qty_available is not None and focus.qty_available < line.qty)
        out_lines.append(
            {
                "id": line.id,
                "pos_no": line.pos_no,
                "title": line.title,
                "unit": line.unit,
                "qty": line.qty,
                "note": line.note,
                "selected_offer_id": line.selected_offer_id,
                "reference_price_kzt": line.reference_price_kzt,
                "reference_vat_included": line.reference_vat_included,
                "reference_source": line.reference_source,
                "status": STATUS_TEXT[status],
                "status_code": status,
                "comparable": comparable,
                "best_offer_id": best_id,
                "short_qty": short,
                "short_available": focus.qty_available if short and focus else None,
                "short_need": line.qty if short else None,
                "offers": views,
                "cells": cells,
            }
        )

    suppliers = [
        {
            "name": name,
            "total_kzt": round(totals[name], 2),
            "priced_lines": priced[name],
            "vat_mixed": len(vat_sets[name]) > 1,
        }
        for name in supplier_names
    ]
    summary = {
        "lines": len(ordered),
        "closed": sum(1 for line in ordered if line.selected_offer_id),
        "no_price": sum(1 for row in out_lines if row["status_code"] == "no_price"),
    }
    return {"suppliers": suppliers, "lines": out_lines, "summary": summary}


def _brief(offer: ProcOffer) -> dict:
    return {
        "offer_id": offer.id,
        "supplier": offer.supplier_name,
        "price_kzt": offer.price_kzt,
        "vat_included": offer.vat_included,
        "source_doc_id": offer.source_doc_id,
        "source_label": offer.source_label,
    }


def _with_vat(price: float, vat_included: bool | None, vat_rate: Decimal) -> Decimal | None:
    if vat_included is None:
        return None
    amount = as_decimal(price)
    if vat_included:
        return amount
    return amount * (Decimal(1) + vat_rate)


def _latest_offer_date(offers: list[ProcOffer]) -> str:
    parsed: list[tuple] = []
    raw: list[str] = []
    for offer in offers:
        text = (offer.offer_date or "").strip()
        if not text:
            continue
        raw.append(text)
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                parsed.append(datetime.strptime(text[:10], fmt).date())
                break
            except ValueError:
                continue
    if parsed:
        return max(parsed).isoformat()
    return max(raw) if raw else ""


def _reason(title: str, detail: str) -> str:
    return f"{title}: {detail}"


def compute_savings(
    lines: list[ProcLine],
    offers: list[ProcOffer],
    vat_rate: float,
    overprice_threshold: float = 0.15,
    documents: list[ProcDocument] | None = None,
) -> dict:
    """Savings against the next confirmed offer on the same VAT basis.

    The reference (website) price never enters savings_kzt. It only raises an
    overprice signal when a real offer is more than the threshold above it.
    Rounding to tenge happens once, on the totals.
    """
    rate = as_decimal(vat_rate)
    threshold = as_decimal(overprice_threshold)
    by_line: dict[str, list[ProcOffer]] = defaultdict(list)
    for offer in offers:
        by_line[offer.line_id].append(offer)
    by_id = {offer.id: offer for offer in offers}

    saving_sum = Decimal(0)
    base_sum = Decimal(0)
    rows: list[dict] = []
    overprice: list[dict] = []

    for line in lines:
        group = by_line.get(line.id, [])
        selected = by_id.get(line.selected_offer_id) if line.selected_offer_id else None
        if selected is not None and selected.line_id != line.id:
            selected = None
        row = {
            "line_id": line.id,
            "pos_no": line.pos_no,
            "title": line.title,
            "unit": line.unit,
            "qty": line.qty,
            "included": False,
            "reason": "",
            "not_cheapest": False,
            "selected": _brief(selected) if selected else None,
            "second": None,
            "saving_kzt": 0.0,
            "base_kzt": 0.0,
        }
        ref_vat = None
        if line.reference_price_kzt is not None:
            ref_vat = _with_vat(line.reference_price_kzt, line.reference_vat_included, rate)
        for offer in group:
            offer_vat = _with_vat(offer.price_kzt, offer.vat_included, rate)
            if offer_vat is None or ref_vat is None or ref_vat <= 0:
                continue
            if offer_vat > ref_vat * (Decimal(1) + threshold):
                per_unit = offer_vat - ref_vat
                overprice.append(
                    {
                        "offer_id": offer.id,
                        "line_id": line.id,
                        "title": line.title,
                        "unit": line.unit,
                        "supplier": offer.supplier_name,
                        "per_unit": float(per_unit),
                        "total": float(per_unit * as_decimal(line.qty)),
                        "total_kzt": round_kzt(per_unit * as_decimal(line.qty)),
                        "pct": float(per_unit / ref_vat),
                    }
                )
        if selected is None:
            row["reason"] = _reason(line.title, "нет выбранного предложения")
            rows.append(row)
            continue
        if not selected.confirmed or selected.vat_included is None:
            row["reason"] = _reason(line.title, "нет сравнения: разная база НДС")
            rows.append(row)
            continue
        candidates = [
            offer
            for offer in group
            if offer.id != selected.id and offer.confirmed and offer.vat_included == selected.vat_included
        ]
        if not candidates:
            detail = "нет сравнения: разная база НДС" if any(offer.id != selected.id for offer in group) else "нет сравнения"
            row["reason"] = _reason(line.title, detail)
            rows.append(row)
            continue
        second = min(candidates, key=lambda offer: (as_decimal(offer.price_kzt), offer.id))
        row["second"] = _brief(second)
        chosen = as_decimal(selected.price_kzt)
        other = as_decimal(second.price_kzt)
        qty = as_decimal(line.qty)
        if chosen <= other:
            saving = (other - chosen) * qty
            base = other * qty
            row["included"] = True
            row["saving_kzt"] = float(saving)
            row["base_kzt"] = float(base)
            saving_sum += saving
            base_sum += base
        else:
            gap = (chosen - other) * qty
            row["included"] = True
            row["not_cheapest"] = True
            row["saving_kzt"] = 0.0
            row["reason"] = f"выбрано не самое дешёвое: дороже на {round_kzt(gap)} ₸"
        rows.append(row)

    savings_kzt = round_kzt(saving_sum)
    base_kzt = round_kzt(base_sum)
    duplicates = []
    inactive = []
    for doc in documents or []:
        view = {
            "id": doc.id,
            "duplicate_of": doc.duplicate_of,
            "supplier_name": doc.supplier_name,
            "doc_number": doc.doc_number,
        }
        if doc.duplicate_of:
            duplicates.append(view)
        if not doc.is_actual:
            inactive.append(view)
    return {
        "savings_kzt": savings_kzt,
        "base_kzt": base_kzt,
        "savings_pct": float(Decimal(savings_kzt) / Decimal(base_kzt)) if base_kzt else 0.0,
        "savings_raw": format(saving_sum, "f"),
        "base_raw": format(base_sum, "f"),
        "lines": rows,
        "overprice": overprice,
        "duplicates": duplicates,
        "inactive": inactive,
        "last_offer_date": _latest_offer_date(offers),
    }
