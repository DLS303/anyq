"""Copy records(collection='acts') into ks_acts.

Run with `python -m app.ks_legacy`. This is a service script, not an Alembic
revision. A second run leaves rows that were already copied.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.sql_backend import resolve_database_url

_STATUSES = {"draft", "submitted", "signed", "rejected", "cancelled"}
_Q = Decimal("0.001")


def _uuid(value: object) -> str | None:
    try:
        parsed = str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None
    return parsed if len(parsed) == 36 else None


def _day(value: object) -> str | None:
    raw = str(value or "").strip()
    if len(raw) < 10:
        return None
    raw = raw[:10]
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None
    return raw


def _money(value: object, default: int | None = 0) -> int | None:
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _qty(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        return None
    if number < 0:
        return None
    return number.quantize(_Q, rounding=ROUND_HALF_UP)


def _payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _alloc(conn, company_id: str, project_id: str, stamp: str) -> int:
    conn.execute(
        text(
            """
            INSERT INTO ks_act_counters (company_id, project_id, next_no, updated_at)
            VALUES (:company_id, :project_id, 1, :stamp)
            ON CONFLICT (company_id, project_id) DO NOTHING
            """
        ),
        {"company_id": company_id, "project_id": project_id, "stamp": stamp},
    )
    number = conn.execute(
        text(
            """
            UPDATE ks_act_counters
            SET next_no = next_no + 1, updated_at = :stamp
            WHERE company_id = :company_id AND project_id = :project_id
            RETURNING next_no - 1
            """
        ),
        {"company_id": company_id, "project_id": project_id, "stamp": stamp},
    ).scalar_one()
    return int(number)


def _bump(conn, company_id: str, project_id: str, number: int, stamp: str) -> None:
    conn.execute(
        text(
            """
            INSERT INTO ks_act_counters (company_id, project_id, next_no, updated_at)
            VALUES (:company_id, :project_id, :next_no, :stamp)
            ON CONFLICT (company_id, project_id) DO UPDATE
            SET next_no = CASE
                  WHEN ks_act_counters.next_no <= :number THEN :next_no
                  ELSE ks_act_counters.next_no
                END,
                updated_at = :stamp
            """
        ),
        {
            "company_id": company_id,
            "project_id": project_id,
            "number": number,
            "next_no": number + 1,
            "stamp": stamp,
        },
    )


def _lines(conn, payload: dict, act: dict, stamp: str) -> None:
    items = payload.get("lines") or []
    if not isinstance(items, list):
        return
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        line_id = _uuid(item.get("id")) or str(uuid4())
        name = str(item.get("name") or item.get("title") or "").strip()[:500]
        if not name:
            continue
        qty_contract = _qty(item.get("qty_contract") if item.get("qty_contract") is not None else item.get("qty"))
        qty_prev = _qty(item.get("qty_prev"))
        qty_period = _qty(item.get("qty_period"))
        price = _money(item.get("unit_price_tiyn"))
        if price is None:
            kzt = _money(item.get("unit_price_kzt"))
            price = None if kzt is None else kzt * 100
        amount = _money(item.get("amount_tiyn"))
        if None in (qty_contract, qty_prev, qty_period, price, amount):
            continue
        over = bool(item.get("over_contract")) or (qty_prev + qty_period > qty_contract)
        conn.execute(
            text(
                """
                INSERT INTO ks_act_lines (
                  id, company_id, project_id, act_id, line_no, estimate_line_id,
                  name, unit, qty_contract, qty_prev, qty_period,
                  unit_price_tiyn, amount_tiyn, over_contract,
                  created_at, updated_at, created_by, updated_by, row_version
                ) VALUES (
                  :id, :company_id, :project_id, :act_id, :line_no, :estimate_line_id,
                  :name, :unit, :qty_contract, :qty_prev, :qty_period,
                  :price, :amount, :over,
                  :stamp, :stamp, 'migration', 'migration', 1
                )
                """
            ),
            {
                "id": line_id,
                "company_id": act["company_id"],
                "project_id": act["project_id"],
                "act_id": act["id"],
                "line_no": int(item.get("line_no") or index),
                "estimate_line_id": (str(item.get("estimate_line_id") or "")[:80] or None),
                "name": name,
                "unit": (str(item.get("unit") or "pcs").strip()[:20] or "pcs"),
                "qty_contract": format(qty_contract, "f"),
                "qty_prev": format(qty_prev, "f"),
                "qty_period": format(qty_period, "f"),
                "price": price,
                "amount": amount,
                "over": 1 if over else 0,
                "stamp": stamp,
            },
        )


def copy_legacy_acts(engine) -> int:
    """Insert each legacy act once. Returns how many acts were inserted."""
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    copied = 0
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT doc_id, project_id, company_key, payload
                FROM records
                WHERE collection = 'acts'
                """
            )
        ).mappings()
        for row in rows:
            try:
                payload = _payload(row["payload"])
            except json.JSONDecodeError:
                continue
            act_id = _uuid(row["doc_id"]) or _uuid(payload.get("id"))
            project_id = str(payload.get("project_id") or row["project_id"] or "").strip()[:80]
            company_id = str(payload.get("company_id") or row["company_key"] or "").strip()[:180]
            act_date = _day(payload.get("act_date"))
            period_from = _day(payload.get("period_from"))
            period_to = _day(payload.get("period_to"))
            if not act_id or not project_id or not company_id or not act_date or not period_from or not period_to:
                continue
            if period_to < period_from:
                continue
            total = _money(payload.get("total_tiyn"))
            vat = _money(payload.get("vat_tiyn"))
            rate = _money(payload.get("vat_rate_bp"))
            if total is None or vat is None or rate is None or rate > 10000:
                continue
            status = str(payload.get("status") or "draft")
            if status not in _STATUSES:
                status = "draft"
            contract = str(payload.get("contract_ref") or "").strip()[:120]
            number = _money(payload.get("number"), default=None)
            inserted = False
            try:
                with conn.begin_nested():
                    taken = conn.execute(text("SELECT 1 FROM ks_acts WHERE id = :id"), {"id": act_id}).first()
                    if taken:
                        continue
                    if number is None or number < 1:
                        number = _alloc(conn, company_id, project_id, stamp)
                    else:
                        _bump(conn, company_id, project_id, number, stamp)
                    act = {
                        "id": act_id,
                        "company_id": company_id,
                        "project_id": project_id,
                        "contract_ref": contract or None,
                        "contract_ref_key": contract,
                        "number": number,
                        "act_date": act_date,
                        "period_from": period_from,
                        "period_to": period_to,
                        "status": status,
                        "total": total,
                        "vat": vat,
                        "gross": total + vat,
                        "rate": rate,
                        "stamp": stamp,
                    }
                    conn.execute(
                        text(
                            """
                            INSERT INTO ks_acts (
                              id, company_id, project_id, contract_ref, contract_ref_key,
                              number, act_date, period_from, period_to, status,
                              total_tiyn, vat_tiyn, total_with_vat_tiyn, vat_rate_bp,
                              currency, created_at, updated_at, created_by, updated_by, row_version
                            ) VALUES (
                              :id, :company_id, :project_id, :contract_ref, :contract_ref_key,
                              :number, :act_date, :period_from, :period_to, :status,
                              :total, :vat, :gross, :rate,
                              'KZT', :stamp, :stamp, 'migration', 'migration', 1
                            )
                            """
                        ),
                        act,
                    )
                    _lines(conn, payload, act, stamp)
                    inserted = True
            except IntegrityError:
                inserted = False
            if inserted:
                copied += 1
    return copied


def main() -> int:
    engine = create_engine(resolve_database_url())
    print(copy_legacy_acts(engine))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
