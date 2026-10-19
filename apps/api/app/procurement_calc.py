"""Pure comparison for a procurement request. No store access."""

from __future__ import annotations

import re
from collections import defaultdict

from app.procurement_models import ProcLine, ProcOffer

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
