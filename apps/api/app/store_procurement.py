"""Procurement collections for MemoryStore. Callers pass the store."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from app.config import settings
from app.procurement_calc import (
    assert_org_name,
    build_sheet,
    clean_note,
    gross_tiyn,
    norm_supplier,
    price_is_suspicious,
    strip_contacts,
)
from app.procurement_models import ProcDocument, ProcLine, ProcOffer, ProcRequest, kzt_to_tiyn
from app.sql_backend import DuplicateInvoice

_REQUEST_ROLES = {"foreman", "supervisor", "procurement", "customer"}
_OFFER_ROLES = {"procurement", "supervisor"}
_DECIDE_ROLES = {"procurement", "supervisor", "customer"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def offer_day(value: str, today: date | None = None) -> date:
    """The offer's own date. A blank or unreadable date is today."""
    current = today or date.today()
    text = (value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return current


def _sourced(offer: ProcOffer) -> bool:
    return bool((offer.source_kind or "").strip())


def _in_median(offer: ProcOffer) -> bool:
    """A benchmark price is confirmed, names a source, and is not waiting for review."""
    if not _sourced(offer):
        return False
    if offer.suspicion_confirmed:
        return True
    return bool(offer.confirmed) and not offer.suspicious


def _item_offers(store, project_id: str, title: str) -> list[ProcOffer]:
    key = norm_supplier(title)
    found: list[ProcOffer] = []
    for line in store.proc_lines.values():
        if norm_supplier(line.title) != key:
            continue
        request = store.proc_requests.get(line.request_id)
        if request is None or request.project_id != project_id:
            continue
        found.extend(offer for offer in store.proc_offers.values() if offer.line_id == line.id)
    return found


def price_benchmarks(
    store,
    line: ProcLine,
    as_of: date,
    exclude_id: str | None = None,
) -> tuple[list[int], int | None]:
    """VAT-inclusive tiyn of other confirmed, sourced offers as of `as_of`.

    The median uses prices inside the configured window ending on that date.
    Quotes after that date, raw tenge amounts, unconfirmed quotes, and quotes
    with no source stay out. When the window is empty, the return is the latest
    confirmed sourced price on or before that date.
    """
    request = store.proc_requests.get(line.request_id)
    if request is None:
        return [], None
    start = as_of - timedelta(days=settings.price_compare_days)
    recent: list[int] = []
    earlier: list[tuple[date, str, int]] = []
    for offer in _item_offers(store, request.project_id, line.title):
        if offer.id == exclude_id or not _in_median(offer):
            continue
        day = offer_day(offer.offer_date, as_of)
        if day > as_of:
            continue
        gross = gross_tiyn(offer.price_tiyn, offer.vat_included, settings.vat_rate)
        if start <= day <= as_of:
            recent.append(gross)
        else:
            earlier.append((day, offer.id, gross))
    last = None
    if earlier:
        earlier.sort()
        last = earlier[-1][2]
    return recent, None if recent else last


def _release_review(offer: ProcOffer, suspicious: bool) -> None:
    held = offer.suspicious and not offer.suspicion_confirmed
    offer.suspicious = suspicious
    if offer.suspicion_confirmed:
        offer.confirmed = True
    elif suspicious:
        offer.confirmed = False
    elif held:
        offer.confirmed = True


def _keep(bag, item) -> None:
    """Reassign so a mutated model is marked dirty and flushed."""
    bag[item.id] = item


def _reassess_item(store, project_id: str, title: str) -> None:
    today = date.today()
    offers = _item_offers(store, project_id, title)
    for offer in offers:
        if offer_day(offer.offer_date, today) == today and not (offer.offer_date or "").strip():
            offer.offer_date = today.isoformat()
    for offer in offers:
        line = store.proc_lines[offer.line_id]
        recent, last = price_benchmarks(store, line, offer_day(offer.offer_date, today), exclude_id=offer.id)
        gross = gross_tiyn(offer.price_tiyn, offer.vat_included, settings.vat_rate)
        suspicious = price_is_suspicious(gross, recent, last, below=settings.price_suspicious_below)
        _release_review(offer, suspicious)
        _keep(store.proc_offers, offer)


def load_into(store, raw: dict) -> None:
    store.proc_requests = {item["id"]: ProcRequest.model_validate(item) for item in raw.get("proc_requests", [])}
    store.proc_lines = {item["id"]: ProcLine.model_validate(item) for item in raw.get("proc_lines", [])}
    store.proc_offers = {item["id"]: ProcOffer.model_validate(item) for item in raw.get("proc_offers", [])}
    store.proc_docs = {item["id"]: ProcDocument.model_validate(item) for item in raw.get("proc_docs", [])}


def dump_lists(store) -> dict:
    return {
        "proc_requests": [item.model_dump() for item in store.proc_requests.values()],
        "proc_lines": [item.model_dump() for item in store.proc_lines.values()],
        "proc_offers": [item.model_dump() for item in store.proc_offers.values()],
        "proc_docs": [item.model_dump() for item in store.proc_docs.values()],
    }


def read_collections(raw: dict) -> dict:
    class _Bag:
        pass

    bag = _Bag()
    load_into(bag, raw)
    return {
        "proc_requests": bag.proc_requests,
        "proc_lines": bag.proc_lines,
        "proc_offers": bag.proc_offers,
        "proc_docs": bag.proc_docs,
    }


def access_flags(store, user, project) -> dict:
    member = store.can_access_project(user, project)
    roles = {
        row.role_on_site
        for row in store.directory.values()
        if row.project_id == project.id and row.user_id == user.id and row.role_on_site
    }
    manager = user.role == "admin" or project.owner_id == user.id or project.contractor_id == user.id
    return {
        "member": bool(member),
        "can_request": bool(member and (manager or roles & _REQUEST_ROLES)),
        "can_offer": bool(member and (manager or roles & _OFFER_ROLES)),
        "can_decide": bool(member and (manager or roles & _DECIDE_ROLES)),
        "can_invoice": bool(member and (manager or roles & _OFFER_ROLES)),
    }


def member_anywhere(store, user) -> bool:
    if user.role == "admin":
        return True
    return any(store.can_access_project(user, project) for project in store.projects.values())


def _lines(store, request_id: str) -> list[ProcLine]:
    return [item for item in store.proc_lines.values() if item.request_id == request_id]


def _offers_for(store, line_ids: set[str]) -> list[ProcOffer]:
    return [item for item in store.proc_offers.values() if item.line_id in line_ids]


def _docs(store, request_id: str) -> list[ProcDocument]:
    return [item for item in store.proc_docs.values() if item.request_id == request_id]


def _refresh(request: ProcRequest, lines: list[ProcLine]) -> None:
    if not lines:
        request.status = "draft"
    elif all(line.selected_offer_id for line in lines):
        request.status = "decided"
    else:
        request.status = "collecting"


def _title(value: str) -> str:
    text, removed = strip_contacts(" ".join((value or "").split()))
    if removed or not text or len(text) > 200:
        raise ValueError("Укажите название заявки без телефона")
    return text


def list_requests(store, project_id: str) -> list[dict]:
    rows = [item for item in store.proc_requests.values() if item.project_id == project_id]
    rows.sort(key=lambda item: item.number)
    out = []
    for req in rows:
        lines = _lines(store, req.id)
        ids = {line.id for line in lines}
        view = req.model_dump()
        view["lines"] = len(lines)
        view["offers"] = len(_offers_for(store, ids))
        view["documents"] = len(_docs(store, req.id))
        out.append(view)
    return out


def create_request(store, project, user, title: str) -> dict:
    name = _title(title)
    with store._lock:
        number = max((item.number for item in store.proc_requests.values() if item.project_id == project.id), default=0) + 1
        req = ProcRequest(
            id=uuid4().hex,
            project_id=project.id,
            number=number,
            title=name,
            status="draft",
            created_at=_now(),
            created_by=user.id,
        )
        store.proc_requests[req.id] = req
        store._save_unlocked()
        return req.model_dump()


def quick_request(store, project, user, title: str, unit: str, qty: float) -> dict:
    name = _title(title)
    unit_text = clean_note(unit, 40)
    if not unit_text:
        raise ValueError("Укажите единицу")
    amount = float(qty)
    if amount <= 0:
        raise ValueError("Количество должно быть больше нуля")
    with store._lock:
        number = max((item.number for item in store.proc_requests.values() if item.project_id == project.id), default=0) + 1
        req = ProcRequest(
            id=uuid4().hex,
            project_id=project.id,
            number=number,
            title=name,
            status="collecting",
            created_at=_now(),
            created_by=user.id,
            shared=True,
        )
        line = ProcLine(
            id=uuid4().hex,
            request_id=req.id,
            pos_no="1",
            title=name,
            unit=unit_text,
            qty=amount,
        )
        store.proc_requests[req.id] = req
        store.proc_lines[line.id] = line
        store._save_unlocked()
        return {"request": req.model_dump(), "line": line.model_dump()}


def repeat_request(store, source: ProcRequest, user) -> dict:
    with store._lock:
        number = max((item.number for item in store.proc_requests.values() if item.project_id == source.project_id), default=0) + 1
        req = ProcRequest(
            id=uuid4().hex,
            project_id=source.project_id,
            number=number,
            title=source.title,
            status="draft",
            created_at=_now(),
            created_by=user.id,
            shared=True,
            repeated_from=source.id,
        )
        copied: list[ProcLine] = []
        for line in sorted(_lines(store, source.id), key=lambda item: (item.pos_no, item.id)):
            clone = ProcLine(
                id=uuid4().hex,
                request_id=req.id,
                pos_no=line.pos_no,
                title=line.title,
                unit=line.unit,
                qty=line.qty,
                note=line.note,
            )
            store.proc_lines[clone.id] = clone
            copied.append(clone)
        _refresh(req, copied)
        store.proc_requests[req.id] = req
        store._save_unlocked()
        return {"request": req.model_dump(), "lines": [line.model_dump() for line in copied]}


def _completed_requests(store, project_id: str) -> list[ProcRequest]:
    rows = [item for item in store.proc_requests.values() if item.project_id == project_id and item.status == "decided"]
    rows.sort(key=lambda item: (item.created_at, item.number), reverse=True)
    return rows


def previous_completed(store, project_id: str) -> dict | None:
    rows = _completed_requests(store, project_id)
    if not rows:
        return None
    source = rows[0]
    return {
        "id": source.id,
        "number": source.number,
        "title": source.title,
        "lines": len(_lines(store, source.id)),
    }


def repeat_previous(store, project, user) -> dict:
    """Copy the latest completed request into a new draft. Offers stay behind."""
    with store._lock:
        rows = _completed_requests(store, project.id)
        if not rows:
            raise LookupError("Нет завершённой заявки")
        source = rows[0]
        number = max((item.number for item in store.proc_requests.values() if item.project_id == project.id), default=0) + 1
        req = ProcRequest(
            id=uuid4().hex,
            project_id=project.id,
            number=number,
            title=source.title,
            status="draft",
            created_at=_now(),
            created_by=user.id,
            shared=False,
            repeated_from=source.id,
        )
        copied: list[ProcLine] = []
        for line in sorted(_lines(store, source.id), key=lambda item: (item.pos_no, item.id)):
            clone = ProcLine(
                id=uuid4().hex,
                request_id=req.id,
                pos_no=line.pos_no,
                title=line.title,
                unit=line.unit,
                qty=line.qty,
                note=line.note,
            )
            store.proc_lines[clone.id] = clone
            copied.append(clone)
        store.proc_requests[req.id] = req
        store._save_unlocked()
        return {
            "request": req.model_dump(),
            "lines": [line.model_dump() for line in copied],
            "source_id": source.id,
        }


def publish_request(store, request: ProcRequest) -> dict:
    with store._lock:
        if request.status != "draft":
            raise ValueError("Заявка уже отправлена")
        lines = _lines(store, request.id)
        if not lines:
            raise ValueError("Нет позиций")
        request.shared = True
        request.status = "collecting"
        _keep(store.proc_requests, request)
        store._save_unlocked()
        return request.model_dump()


def confirm_suspicious(store, offer: ProcOffer) -> dict:
    with store._lock:
        offer.suspicion_confirmed = True
        offer.confirmed = True
        _keep(store.proc_offers, offer)
        line = store.proc_lines[offer.line_id]
        request = _request_of_line(store, line)
        _reassess_item(store, request.project_id, line.title)
        _refresh(request, _lines(store, line.request_id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
        return offer.model_dump()


def material_picker(store, project, query: str) -> dict:
    needle = " ".join((query or "").casefold().split())
    recent: list[dict] = []
    seen: set[str] = set()
    requests = [item for item in store.proc_requests.values() if item.project_id == project.id]
    requests.sort(key=lambda item: item.created_at, reverse=True)
    for req in requests:
        for line in _lines(store, req.id):
            key = norm_supplier(line.title)
            if not key or key in seen:
                continue
            if needle and needle not in key and needle not in line.unit.casefold():
                continue
            seen.add(key)
            recent.append({"title": line.title, "unit": line.unit, "qty": line.qty, "source": "recent"})
            if len(recent) >= 8:
                break
        if len(recent) >= 8:
            break
    catalog: list[dict] = []
    for mat in store.list_materials(q=needle or None):
        title = mat.title_ru
        if not needle and norm_supplier(title) in seen:
            continue
        unit = (mat.unit or "").strip()
        if not unit:
            continue
        catalog.append({"id": mat.id, "title": title, "unit": unit, "source": "catalog"})
        if len(catalog) >= 12:
            break
    if not needle:
        catalog = catalog[:6]
    return {"recent": recent, "catalog": catalog}


def supplier_can_bid(user, request: ProcRequest) -> bool:
    return user.role == "supplier" and bool(request.shared) and request.status == "collecting"


def supplier_inbox(store, user) -> list[dict]:
    if user.role != "supplier":
        raise PermissionError("Недостаточно прав")
    rows = []
    for req in store.proc_requests.values():
        if not supplier_can_bid(user, req):
            continue
        project = store.get_project(req.project_id)
        lines = [
            {"id": line.id, "title": line.title, "unit": line.unit, "qty": line.qty}
            for line in _lines(store, req.id)
        ]
        rows.append(
            {
                "id": req.id,
                "number": req.number,
                "title": req.title,
                "project_id": req.project_id,
                "project_title": project.title if project else "",
                "created_at": req.created_at,
                "lines": lines,
            }
        )
    rows.sort(key=lambda item: item["created_at"], reverse=True)
    return rows


def request_lines(store, request_id: str) -> list[ProcLine]:
    return _lines(store, request_id)


def sheet_for(store, request: ProcRequest) -> dict:
    lines = _lines(store, request.id)
    offers = _offers_for(store, {line.id for line in lines})
    body = build_sheet(lines, offers)
    body["request"] = request.model_dump()
    body["documents"] = [item.model_dump() for item in sorted(_docs(store, request.id), key=lambda item: item.uploaded_at)]
    return body


def _warn(rows: list[dict]) -> list[dict]:
    warnings = [{"row": row["row"], "code": code} for row in rows for code in row.get("errors") or []]
    for row in rows:
        if row.get("phone_removed"):
            warnings.append({"row": row["row"], "code": "phone_removed"})
    return warnings


def _public_rows(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return [{key: row.get(key) for key in keys} for row in rows]


_LINE_KEYS = ("row", "pos_no", "title", "unit", "qty", "note", "errors")


def preview_lines(rows: list[dict], contact_ignored: bool) -> dict:
    skipped = sum(1 for row in rows if row.get("errors"))
    return {
        "preview": True,
        "created": 0,
        "updated": 0,
        "skipped": skipped,
        "warnings": _warn(rows),
        "rows": _public_rows(rows, _LINE_KEYS),
        "contact_ignored": contact_ignored,
    }


def apply_lines(store, request: ProcRequest, rows: list[dict], contact_ignored: bool) -> dict:
    valid = [row for row in rows if not row.get("errors")]
    with store._lock:
        existing = {line.pos_no: line for line in _lines(store, request.id)}
        created = updated = 0
        for row in valid:
            current = existing.get(row["pos_no"])
            if current:
                current.title = row["title"]
                current.unit = row["unit"]
                current.qty = float(row["qty"])
                current.note = row["note"]
                _keep(store.proc_lines, current)
                updated += 1
            else:
                line = ProcLine(
                    id=uuid4().hex,
                    request_id=request.id,
                    pos_no=row["pos_no"],
                    title=row["title"],
                    unit=row["unit"],
                    qty=float(row["qty"]),
                    note=row["note"] or "",
                )
                store.proc_lines[line.id] = line
                existing[line.pos_no] = line
                created += 1
        _refresh(request, _lines(store, request.id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
    return {
        "preview": False,
        "created": created,
        "updated": updated,
        "skipped": len(rows) - len(valid),
        "warnings": _warn(rows),
        "rows": _public_rows(rows, _LINE_KEYS),
        "contact_ignored": contact_ignored,
    }


def _match_line(lines: list[ProcLine], row: dict) -> ProcLine | None:
    pos = (row.get("pos_no") or "").strip()
    if pos:
        for line in lines:
            if line.pos_no == pos:
                return line
        return None
    title = norm_supplier(row.get("title") or "")
    if not title:
        return None
    hits = [line for line in lines if norm_supplier(line.title) == title]
    if len(hits) == 1:
        return hits[0]
    return None


_OFFER_KEYS = (
    "row",
    "pos_no",
    "title",
    "supplier_name",
    "price_kzt",
    "vat_included",
    "qty_available",
    "source_label",
    "offer_date",
    "confirmed",
    "note",
    "delivery_term",
    "errors",
)


def preview_offers(rows: list[dict], contact_ignored: bool) -> dict:
    return {
        "preview": True,
        "created": 0,
        "updated": 0,
        "skipped": sum(1 for row in rows if row.get("errors")),
        "warnings": _warn(rows),
        "rows": _public_rows(rows, _OFFER_KEYS),
        "contact_ignored": contact_ignored,
    }


def apply_offers(store, request: ProcRequest, rows: list[dict], contact_ignored: bool, default_supplier: str = "") -> dict:
    fallback = ""
    if default_supplier.strip():
        fallback = assert_org_name(default_supplier)
    lines = _lines(store, request.id)
    prepared: list[tuple[ProcLine, str, dict]] = []
    extra_warnings: list[dict] = []
    for row in rows:
        if row.get("errors"):
            continue
        supplier = (row.get("supplier_name") or "").strip() or fallback
        try:
            supplier = assert_org_name(supplier) if supplier else ""
        except ValueError:
            supplier = ""
        if not supplier:
            extra_warnings.append({"row": row["row"], "code": "supplier_required"})
            continue
        line = _match_line(lines, row)
        if line is None:
            extra_warnings.append({"row": row["row"], "code": "pos_missing"})
            continue
        prepared.append((line, supplier, row))
    with store._lock:
        created = updated = 0
        for line, supplier, row in prepared:
            label = (row.get("source_label") or "").strip().casefold()
            found = None
            for offer in store.proc_offers.values():
                if offer.line_id != line.id:
                    continue
                if norm_supplier(offer.supplier_name) == norm_supplier(supplier) and offer.source_label.strip().casefold() == label:
                    found = offer
                    break
            tiyn = kzt_to_tiyn(float(row["price_kzt"]))
            if found:
                found.supplier_name = supplier
                found.price_tiyn = tiyn
                found.price_kzt = tiyn / 100
                found.vat_included = row.get("vat_included")
                found.qty_available = row.get("qty_available")
                found.source_label = row.get("source_label") or "xlsx"
                found.source_kind = "file"
                found.offer_date = row.get("offer_date") or found.offer_date or date.today().isoformat()
                found.confirmed = bool(row.get("confirmed"))
                found.note = row.get("note") or ""
                found.delivery_term = row.get("delivery_term") or ""
                _keep(store.proc_offers, found)
                updated += 1
            else:
                offer = ProcOffer(
                    id=uuid4().hex,
                    line_id=line.id,
                    supplier_name=supplier,
                    price_kzt=tiyn / 100,
                    price_tiyn=tiyn,
                    vat_included=row.get("vat_included"),
                    qty_available=row.get("qty_available"),
                    source_label=row.get("source_label") or "xlsx",
                    source_kind="file",
                    offer_date=row.get("offer_date") or date.today().isoformat(),
                    confirmed=bool(row.get("confirmed")),
                    suspicious=False,
                    note=row.get("note") or "",
                    delivery_term=row.get("delivery_term") or "",
                )
                store.proc_offers[offer.id] = offer
                created += 1
            if row.get("reference_price_kzt") is not None:
                line.reference_price_kzt = float(row["reference_price_kzt"])
                line.reference_vat_included = row.get("reference_vat_included")
                line.reference_source = "price_list"
                _keep(store.proc_lines, line)
        for title in {line.title for line, _supplier, _row in prepared}:
            _reassess_item(store, request.project_id, title)
        _refresh(request, _lines(store, request.id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
    skipped = len(rows) - len(prepared)
    return {
        "preview": False,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "warnings": _warn(rows) + extra_warnings,
        "rows": _public_rows(rows, _OFFER_KEYS),
        "contact_ignored": contact_ignored,
    }


def _request_of_line(store, line: ProcLine) -> ProcRequest:
    req = store.proc_requests.get(line.request_id)
    if not req:
        raise LookupError("Заявка не найдена")
    return req


def add_offer(store, line: ProcLine, payload: dict) -> dict:
    supplier = assert_org_name(payload["supplier_name"])
    source_kind = (payload.get("source_kind") or "").strip()
    if not source_kind:
        raise ValueError("Укажите источник цены")
    tiyn = int(payload["price_tiyn"]) if payload.get("price_tiyn") else kzt_to_tiyn(float(payload["price_kzt"]))
    if tiyn <= 0:
        raise ValueError("Цена должна быть больше нуля")
    qty_available = payload.get("qty_available")
    if qty_available is not None and float(qty_available) < 0:
        raise ValueError("Доступный объём не может быть отрицательным")
    source_doc = payload.get("source_doc_id") or None
    if source_doc and source_doc not in {item.id for item in _docs(store, line.request_id)}:
        raise LookupError("Счёт не найден")
    offered_on = (payload.get("offer_date") or "").strip()[:32] or date.today().isoformat()
    with store._lock:
        offer = ProcOffer(
            id=uuid4().hex,
            line_id=line.id,
            supplier_name=supplier,
            price_kzt=tiyn / 100,
            price_tiyn=tiyn,
            vat_included=payload.get("vat_included"),
            qty_available=None if qty_available is None else float(qty_available),
            source_doc_id=source_doc,
            source_label=clean_note(payload.get("source_label") or "", 200),
            source_kind=source_kind[:32],
            offer_date=offered_on,
            confirmed=bool(payload.get("confirmed", True)),
            suspicious=False,
            suspicion_confirmed=False,
            note=clean_note(payload.get("note") or ""),
            delivery_term=clean_note(payload.get("delivery_term") or "", 120),
        )
        store.proc_offers[offer.id] = offer
        request = _request_of_line(store, line)
        _reassess_item(store, request.project_id, line.title)
        _refresh(request, _lines(store, line.request_id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
        return offer.model_dump()


def patch_offer(store, offer: ProcOffer, payload: dict) -> dict:
    with store._lock:
        if "supplier_name" in payload:
            offer.supplier_name = assert_org_name(payload["supplier_name"])
        if "price_kzt" in payload or "price_tiyn" in payload:
            tiyn = int(payload["price_tiyn"]) if payload.get("price_tiyn") else kzt_to_tiyn(float(payload["price_kzt"]))
            if tiyn <= 0:
                raise ValueError("Цена должна быть больше нуля")
            offer.price_tiyn = tiyn
            offer.price_kzt = tiyn / 100
        if "vat_included" in payload:
            offer.vat_included = payload["vat_included"]
        if "qty_available" in payload:
            raw = payload["qty_available"]
            if raw is not None and float(raw) < 0:
                raise ValueError("Доступный объём не может быть отрицательным")
            offer.qty_available = None if raw is None else float(raw)
        if "delivery_term" in payload:
            offer.delivery_term = clean_note(payload["delivery_term"] or "", 120)
        if "note" in payload:
            offer.note = clean_note(payload["note"] or "")
        if "confirmed" in payload:
            offer.confirmed = bool(payload["confirmed"])
        if "source_label" in payload:
            offer.source_label = clean_note(payload["source_label"] or "", 200)
        if "offer_date" in payload:
            offer.offer_date = (payload["offer_date"] or "")[:32]
        if "source_doc_id" in payload:
            source_doc = payload["source_doc_id"] or None
            line = store.proc_lines[offer.line_id]
            if source_doc and source_doc not in {item.id for item in _docs(store, line.request_id)}:
                raise LookupError("Счёт не найден")
            offer.source_doc_id = source_doc
        line = store.proc_lines[offer.line_id]
        request = _request_of_line(store, line)
        _reassess_item(store, request.project_id, line.title)
        _refresh(request, _lines(store, line.request_id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
        return offer.model_dump()


def delete_offer(store, offer: ProcOffer) -> dict:
    with store._lock:
        line = store.proc_lines.get(offer.line_id)
        store.proc_offers.pop(offer.id, None)
        if line and line.selected_offer_id == offer.id:
            line.selected_offer_id = None
            _keep(store.proc_lines, line)
        if line:
            request = _request_of_line(store, line)
            _reassess_item(store, request.project_id, line.title)
            _refresh(request, _lines(store, line.request_id))
            _keep(store.proc_requests, request)
        store._save_unlocked()
        return {"id": offer.id}


def patch_line(store, line: ProcLine, payload: dict) -> dict:
    with store._lock:
        if "qty" in payload:
            qty = float(payload["qty"])
            if qty <= 0:
                raise ValueError("Количество должно быть больше нуля")
            line.qty = qty
        if "note" in payload:
            line.note = clean_note(payload["note"] or "")
        if payload.get("title"):
            line.title = clean_note(payload["title"], 300)
        if payload.get("unit"):
            line.unit = clean_note(payload["unit"], 40)
        if "reference_price_kzt" in payload:
            raw = payload["reference_price_kzt"]
            line.reference_price_kzt = None if raw is None else float(raw)
        if "reference_vat_included" in payload:
            line.reference_vat_included = payload["reference_vat_included"]
        if "reference_source" in payload:
            line.reference_source = clean_note(payload["reference_source"] or "", 200)
        _keep(store.proc_lines, line)
        request = _request_of_line(store, line)
        if request.status != "draft":
            _refresh(request, _lines(store, line.request_id))
            _keep(store.proc_requests, request)
        store._save_unlocked()
        return line.model_dump()


def select_offer(store, line: ProcLine, offer_id: str | None) -> dict:
    with store._lock:
        if offer_id:
            offer = store.proc_offers.get(offer_id)
            if not offer or offer.line_id != line.id:
                raise LookupError("Предложение не найдено")
            if offer.suspicious and not offer.suspicion_confirmed:
                raise ValueError("Подтвердите подозрительную цену")
            line.selected_offer_id = offer.id
        else:
            line.selected_offer_id = None
        _keep(store.proc_lines, line)
        request = _request_of_line(store, line)
        _refresh(request, _lines(store, line.request_id))
        _keep(store.proc_requests, request)
        store._save_unlocked()
        return line.model_dump()


def select_best(store, request: ProcRequest) -> dict:
    with store._lock:
        lines = _lines(store, request.id)
        offers = _offers_for(store, {line.id for line in lines})
        sheet = build_sheet(lines, offers)
        by_id = {line.id: line for line in lines}
        for row in sheet["lines"]:
            if row["best_offer_id"]:
                chosen = by_id[row["id"]]
                chosen.selected_offer_id = row["best_offer_id"]
                _keep(store.proc_lines, chosen)
        _refresh(request, lines)
        _keep(store.proc_requests, request)
        store._save_unlocked()
    return sheet_for(store, request)


def norm_doc_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        sample = text[:10] if fmt == "%Y-%m-%d" else text
        try:
            return datetime.strptime(sample, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Дата в формате ГГГГ-ММ-ДД")


def _money(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _number_key(value: str) -> str:
    return " ".join((value or "").casefold().split())


def find_duplicate(docs: list[ProcDocument], *, sha256: str, supplier: str, doc_number: str, amount: float | None, doc_date: str):
    supplier_key = norm_supplier(supplier)
    number_key = _number_key(doc_number)
    amount_key = _money(amount)
    for doc in docs:
        if doc.sha256 == sha256:
            return doc, "file"
        same_supplier = norm_supplier(doc.supplier_name) == supplier_key
        if number_key and same_supplier and _number_key(doc.doc_number) == number_key:
            return doc, "supplier_number"
        if amount_key is not None and doc_date and _money(doc.amount_kzt) == amount_key and doc.doc_date == doc_date:
            return doc, "amount_date"
    return None, ""


def _forget_doc(store, doc_id: str) -> None:
    bag = store.proc_docs
    bag._tracking = False
    try:
        dict.pop(bag, doc_id, None)
        bag.dirty.discard(str(doc_id))
        bag.deleted.discard(str(doc_id))
    finally:
        bag._tracking = True


def _invoice_number(doc: ProcDocument) -> str:
    return " ".join((doc.number or doc.doc_number or "").casefold().split())


def add_invoice(store, request: ProcRequest, user, payload: dict) -> dict:
    company = (payload.get("company_id") or "").strip()
    supplier_id = (payload.get("supplier_id") or "").strip()
    raw_number = (payload.get("number") or "").strip()
    number = " ".join(raw_number.casefold().split())
    doc_date = norm_doc_date(payload.get("date") or "")
    if not company or not supplier_id or not number or not doc_date:
        raise ValueError("Укажите компанию, поставщика, номер и дату")
    amount = float(payload["amount_kzt"])
    if amount <= 0:
        raise ValueError("Сумма счёта должна быть больше нуля")
    supplier_name = assert_org_name(payload.get("supplier_name") or supplier_id)
    with store._lock:
        for doc in list(store.proc_docs.values()):
            if doc.deleted:
                continue
            if (
                doc.company_id == company
                and doc.supplier_id == supplier_id
                and _invoice_number(doc) == number
                and doc.doc_date == doc_date
            ):
                raise DuplicateInvoice()
        identity = f"{company}|{supplier_id}|{number}|{doc_date}"
        item = ProcDocument(
            id=uuid4().hex,
            request_id=request.id,
            supplier_name=supplier_name,
            doc_number=raw_number,
            doc_date=doc_date,
            amount_kzt=_money(amount),
            stored_name=f"invoice-{uuid4().hex}.txt",
            mime="text/plain",
            size=0,
            sha256=hashlib.sha256(identity.encode()).hexdigest(),
            uploaded_at=_now(),
            uploaded_by=user.id,
            company_id=company,
            supplier_id=supplier_id,
            number=number,
            deleted=False,
            is_actual=True,
        )
        store.proc_docs[item.id] = item
        try:
            store._save_unlocked()
        except DuplicateInvoice:
            _forget_doc(store, item.id)
            raise
        return item.model_dump()


def add_document(store, request: ProcRequest, user, meta: dict) -> dict:
    supplier = assert_org_name(meta["supplier_name"])
    doc_date = norm_doc_date(meta.get("doc_date") or "")
    doc_number = clean_note(meta.get("doc_number") or "", 80)
    amount = meta.get("amount_kzt")
    if amount is not None:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("Сумма счёта должна быть больше нуля")
        amount = _money(amount)
    with store._lock:
        docs = _docs(store, request.id)
        duplicate, reason = find_duplicate(
            docs,
            sha256=meta["sha256"],
            supplier=supplier,
            doc_number=doc_number,
            amount=amount,
            doc_date=doc_date,
        )
        number_key = _number_key(doc_number)
        new_version = False
        if duplicate is None and number_key:
            for doc in docs:
                if norm_supplier(doc.supplier_name) != norm_supplier(supplier):
                    continue
                other = _number_key(doc.doc_number)
                if other and other != number_key:
                    new_version = True
                    break
        item = ProcDocument(
            id=uuid4().hex,
            request_id=request.id,
            supplier_name=supplier,
            doc_number=doc_number,
            doc_date=doc_date,
            amount_kzt=amount,
            stored_name=meta["stored_name"],
            mime=meta["mime"],
            size=meta["size"],
            sha256=meta["sha256"],
            uploaded_at=_now(),
            uploaded_by=user.id,
            duplicate_of=duplicate.id if duplicate else None,
            duplicate_reason=reason,
            is_actual=True,
        )
        store.proc_docs[item.id] = item
        store._save_unlocked()
        return {
            "document": item.model_dump(),
            "duplicate": duplicate is not None,
            "duplicate_of": duplicate.id if duplicate else None,
            "duplicate_reason": reason,
            "new_version_of_supplier": new_version,
        }


def patch_document(store, doc: ProcDocument, is_actual: bool) -> dict:
    with store._lock:
        doc.is_actual = is_actual
        _keep(store.proc_docs, doc)
        if is_actual:
            for other in _docs(store, doc.request_id):
                if other.id != doc.id and norm_supplier(other.supplier_name) == norm_supplier(doc.supplier_name):
                    other.is_actual = False
                    _keep(store.proc_docs, other)
        store._save_unlocked()
        return doc.model_dump()
