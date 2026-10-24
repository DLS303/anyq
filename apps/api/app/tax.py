"""VAT for KS-2 / KS-3 by the act date.

Rates come from vat_rates (seeded from Tax Code No. 214-VIII, article 503).
The document stores the chosen rate. Non-payers use a zero rate.
"""

from datetime import date

from sqlalchemy import text

VAT_BASIS = "НК РК № 214-VIII, ст. 503"


def parse_act_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    raw = (value or "").strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError("Дата акта в формате ГГГГ-ММ-ДД") from exc


def lookup_vat(session, act_date: date | str) -> tuple[str, int, str]:
    """Return rate id, basis points, and basis text. More than one row is an overlap."""
    day = parse_act_date(act_date).isoformat()
    rows = session.execute(
        text(
            """
            SELECT id, rate_bp, basis
            FROM vat_rates
            WHERE country = 'KZ'
              AND deleted_at IS NULL
              AND valid_from <= :day
              AND (valid_to IS NULL OR valid_to >= :day)
            ORDER BY valid_from DESC
            """
        ),
        {"day": day},
    ).all()
    if len(rows) != 1:
        raise ValueError("Нет ставки НДС на эту дату")
    return str(rows[0][0]), int(rows[0][1]), str(rows[0][2] or "")


def vat_rate(act_date: date | str, no_vat: bool = False) -> float:
    if no_vat:
        return 0.0
    from app.store import store

    with store._sql.factory() as session:
        _rate_id, basis_points, _basis = lookup_vat(session, act_date)
    return basis_points / 10000


def vat_quote(act_date: date | str, no_vat: bool = False) -> dict:
    day = parse_act_date(act_date)
    if no_vat:
        return {
            "act_date": day.isoformat(),
            "no_vat": True,
            "vat_rate": 0.0,
            "vat_percent": 0,
            "vat_rate_bp": 0,
            "vat_rate_id": None,
            "basis": "",
        }
    from app.store import store

    with store._sql.factory() as session:
        rate_id, basis_points, basis = lookup_vat(session, day)
    return {
        "act_date": day.isoformat(),
        "no_vat": False,
        "vat_rate": basis_points / 10000,
        "vat_percent": basis_points // 100,
        "vat_rate_bp": basis_points,
        "vat_rate_id": rate_id,
        "basis": basis,
    }
