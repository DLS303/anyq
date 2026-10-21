"""Procurement collections for MemoryStore. Callers pass the store."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.procurement_calc import (
    assert_org_name,
    build_sheet,
    clean_note,
    norm_supplier,
    strip_contacts,
)
from app.procurement_models import ProcDocument, ProcLine, ProcOffer, ProcRequest

_REQUEST_ROLES = {"foreman", "supervisor", "procurement", "customer"}
_OFFER_ROLES = {"procurement", "supervisor"}
_DECIDE_ROLES = {"procurement", "supervisor", "customer"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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
    lines_by = {item.id: [] for item in rows}
    for line in store.proc_lines.values():
        bucket = lines_by.get(line.request_id)
        if bucket is not None:
            bucket.append(line)
    line_request = {line.id: request_id for request_id, lines in lines_by.items() for line in lines}
    offer_counts = {item.id: 0 for item in rows}
    for offer in store.proc_offers.values():
        request_id = line_request.get(offer.line_id)
        if request_id:
            offer_counts[request_id] += 1
    doc_counts = {item.id: 0 for item in rows}
    for doc in store.proc_docs.values():
        if doc.request_id in doc_counts:
            doc_counts[doc.request_id] += 1
    out = []
    for req in rows:
        view = req.model_dump()
        view["lines"] = len(lines_by[req.id])
        view["offers"] = offer_counts[req.id]
        view["documents"] = doc_counts[req.id]
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


def record_recipients(store, request_id: str, company_ids: list[str] | None = None) -> None:
    """Insert one row per supplier company. The pair is unique, so repeats are skipped."""
    from app.sql_backend import CompanyRow, RequestRecipient

    now = _now()
    with store._sql.factory() as session:
        if company_ids is None:
            company_ids = list(session.scalars(select(CompanyRow.id).where(CompanyRow.role == "supplier")).all())
        for company_id in company_ids:
            key = (request_id, company_id)
            if not company_id or session.get(RequestRecipient, key) is not None:
                continue
            session.add(
                RequestRecipient(
                    request_id=request_id,
                    supplier_company_id=company_id,
                    status="sent",
                    sent_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()


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
        request_id = req.id
        shared = bool(req.shared)
        status = req.status
    if shared and status == "collecting":
        record_recipients(store, request_id)
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
        request_id = req.id
        shared = bool(req.shared)
        status = req.status
        payload = {"request": req.model_dump(), "lines": [line.model_dump() for line in copied]}
    if shared and status == "collecting":
        record_recipients(store, request_id)
    return payload


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
        catalog.append({"id": mat.id, "title": title, "unit": mat.unit or "шт", "source": "catalog"})
        if len(catalog) >= 12:
            break
    if not needle:
        catalog = catalog[:6]
    return {"recent": recent, "catalog": catalog}


def _recipient_rows(store, company_id: str) -> dict[str, str]:
    from app.sql_backend import RequestRecipient

    if not company_id:
        return {}
    with store._sql.factory() as session:
        rows = session.scalars(
            select(RequestRecipient).where(RequestRecipient.supplier_company_id == company_id)
        ).all()
    return {str(row.request_id): row.status for row in rows}


def _recipient_ids(store, company_id: str) -> set[str]:
    return set(_recipient_rows(store, company_id))


def supplier_can_bid(user, request: ProcRequest) -> bool:
    if user.role != "supplier" or not request.shared or request.status != "collecting":
        return False
    company_id = str(getattr(user, "company_id", "") or "").strip()
    if not company_id:
        return False
    from app.store import store

    return request.id in _recipient_ids(store, company_id)


def supplier_inbox(store, user) -> list[dict]:
    if user.role != "supplier":
        raise PermissionError("Недостаточно прав")
    company_id = str(getattr(user, "company_id", "") or "").strip()
    addressed = _recipient_rows(store, company_id)
    rows = []
    for req in store.proc_requests.values():
        if req.id not in addressed or not req.shared or req.status != "collecting":
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
                "status": addressed[req.id],
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
            if found:
                found.supplier_name = supplier
                found.price_kzt = float(row["price_kzt"])
                found.vat_included = row.get("vat_included")
                found.qty_available = row.get("qty_available")
                found.source_label = row.get("source_label") or ""
                found.offer_date = row.get("offer_date") or ""
                found.confirmed = bool(row.get("confirmed"))
                found.note = row.get("note") or ""
                found.delivery_term = row.get("delivery_term") or ""
                updated += 1
            else:
                offer = ProcOffer(
                    id=uuid4().hex,
                    line_id=line.id,
                    supplier_name=supplier,
                    price_kzt=float(row["price_kzt"]),
                    vat_included=row.get("vat_included"),
                    qty_available=row.get("qty_available"),
                    source_label=row.get("source_label") or "",
                    offer_date=row.get("offer_date") or "",
                    confirmed=bool(row.get("confirmed")),
                    note=row.get("note") or "",
                    delivery_term=row.get("delivery_term") or "",
                )
                store.proc_offers[offer.id] = offer
                created += 1
            if row.get("reference_price_kzt") is not None:
                line.reference_price_kzt = float(row["reference_price_kzt"])
                line.reference_vat_included = row.get("reference_vat_included")
                line.reference_source = "price_list"
        _refresh(request, _lines(store, request.id))
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
    price = float(payload["price_kzt"])
    if price <= 0:
        raise ValueError("Цена должна быть больше нуля")
    qty_available = payload.get("qty_available")
    if qty_available is not None and float(qty_available) < 0:
        raise ValueError("Доступный объём не может быть отрицательным")
    source_doc = payload.get("source_doc_id") or None
    if source_doc and source_doc not in {item.id for item in _docs(store, line.request_id)}:
        raise LookupError("Счёт не найден")
    with store._lock:
        offer = ProcOffer(
            id=uuid4().hex,
            line_id=line.id,
            supplier_name=supplier,
            price_kzt=price,
            vat_included=payload.get("vat_included"),
            qty_available=None if qty_available is None else float(qty_available),
            source_doc_id=source_doc,
            source_label=clean_note(payload.get("source_label") or "", 200),
            offer_date=(payload.get("offer_date") or "")[:32],
            confirmed=bool(payload.get("confirmed", True)),
            note=clean_note(payload.get("note") or ""),
            delivery_term=clean_note(payload.get("delivery_term") or "", 120),
        )
        store.proc_offers[offer.id] = offer
        _refresh(_request_of_line(store, line), _lines(store, line.request_id))
        store._save_unlocked()
        return offer.model_dump()


def patch_offer(store, offer: ProcOffer, payload: dict) -> dict:
    with store._lock:
        if "supplier_name" in payload:
            offer.supplier_name = assert_org_name(payload["supplier_name"])
        if "price_kzt" in payload:
            price = float(payload["price_kzt"])
            if price <= 0:
                raise ValueError("Цена должна быть больше нуля")
            offer.price_kzt = price
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
        _refresh(_request_of_line(store, line), _lines(store, line.request_id))
        store._save_unlocked()
        return offer.model_dump()


def delete_offer(store, offer: ProcOffer) -> dict:
    with store._lock:
        line = store.proc_lines.get(offer.line_id)
        store.proc_offers.pop(offer.id, None)
        if line and line.selected_offer_id == offer.id:
            line.selected_offer_id = None
        if line:
            _refresh(_request_of_line(store, line), _lines(store, line.request_id))
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
        _refresh(_request_of_line(store, line), _lines(store, line.request_id))
        store._save_unlocked()
        return line.model_dump()


def select_offer(store, line: ProcLine, offer_id: str | None) -> dict:
    with store._lock:
        if offer_id:
            offer = store.proc_offers.get(offer_id)
            if not offer or offer.line_id != line.id:
                raise LookupError("Предложение не найдено")
            line.selected_offer_id = offer.id
        else:
            line.selected_offer_id = None
        _refresh(_request_of_line(store, line), _lines(store, line.request_id))
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
                by_id[row["id"]].selected_offer_id = row["best_offer_id"]
        _refresh(request, lines)
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
        if is_actual:
            for other in _docs(store, doc.request_id):
                if other.id != doc.id and norm_supplier(other.supplier_name) == norm_supplier(doc.supplier_name):
                    other.is_actual = False
        store._save_unlocked()
        return doc.model_dump()
