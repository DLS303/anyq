"""Object budget: plan, procurement fact, manual expenses, and the colour signal."""

import io
from datetime import date

from fastapi.testclient import TestClient
from PIL import Image

from app.authutil import hash_password
from app.budget_calc import (
    forecast_overrun,
    planned_window,
    procurement_actual,
    signal_for,
)
from app.main import app
from app.procurement_models import ProcDocument, ProcLine, ProcOffer, ProcRequest
from app.site_models import DirectoryRow
from app.store import store
from app.store_budget import load_budget

client = TestClient(app)


def _register(email: str, company: str) -> tuple[str, str]:
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": company,
            "company_bin": "123456789012",
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    return data["token"], data["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner() -> str:
    store.credentials["u-owner"] = hash_password("owner-pass-budget")
    res = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-budget", "consent_offer_pd": True},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 90, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_legacy_db_without_budget_keys():
    class Bag:
        pass

    bag = Bag()
    load_budget(bag, {"projects": []})
    assert bag.object_budgets == {}
    assert bag.object_expenses == {}


def test_signal_bands():
    assert signal_for(79, 100) == ("green", 79)
    assert signal_for(80, 100)[0] == "yellow"
    assert signal_for(100, 100)[0] == "yellow"
    assert signal_for(101, 100)[0] == "red"
    assert signal_for(0, 0)[0] == "green"
    assert signal_for(1, 0)[0] == "red"


def test_forecast_without_dates_is_omitted():
    missing = forecast_overrun(400_000, 382_174, None, None, date(2026, 10, 19))
    assert missing["forecast_reason"] == "no_dates"
    assert missing["overrun_kind"] == "none"
    assert missing["forecast_kzt"] is None
    assert missing["overrun_kzt"] == 0
    assert planned_window("", "", []) is None
    assert planned_window("", "", [("2026-13-01", "2026-10-01")]) is None


def test_forecast_early_in_the_schedule_is_omitted():
    # 19 of 100 days is under 20%. 20 of 100 days is the first day a forecast is allowed.
    start = date(2026, 10, 1)
    finish = date(2027, 1, 9)
    early = forecast_overrun(1000, 900, start, finish, date(2026, 10, 20))
    assert early["elapsed_days"] == 19
    assert early["span_days"] == 100
    assert early["forecast_reason"] == "early"
    assert early["forecast_kzt"] is None
    assert early["overrun_kzt"] == 0
    opened = forecast_overrun(1000, 400, start, finish, date(2026, 10, 21))
    assert opened["elapsed_share"] == 0.2
    assert opened["forecast_kzt"] == 2000
    assert opened["overrun_kzt"] == 1000
    assert opened["overrun_kind"] == "forecast"


def test_forecast_when_fact_already_exceeds_the_plan():
    start = date(2026, 10, 1)
    finish = date(2026, 10, 31)
    today = date(2026, 10, 16)
    actual = forecast_overrun(1000, 1100, start, finish, today)
    assert actual["overrun_kind"] == "actual"
    assert actual["overrun_kzt"] == 100
    assert actual["forecast_kzt"] == 1100
    assert actual["forecast_reason"] == "actual"
    # Same gap with no dates: still the current overrun, not a projection.
    bare = forecast_overrun(1000, 1100, None, None, today)
    assert bare["overrun_kind"] == "actual"
    assert bare["overrun_kzt"] == 100
    assert bare["forecast_reason"] == "actual"


def test_forecast_above_twice_the_plan_is_withheld():
    # 20% elapsed and 900 spent on a 1000 plan would project 4500, above the 2000 bound.
    start = date(2026, 10, 1)
    finish = date(2027, 1, 9)
    wild = forecast_overrun(1000, 900, start, finish, date(2026, 10, 21))
    assert wild["forecast_raw_kzt"] == 4500
    assert wild["forecast_bound_kzt"] == 2000
    assert wild["forecast_reason"] == "above_bound"
    assert wild["forecast_kzt"] is None
    assert wild["overrun_kzt"] == 0
    assert wild["overrun_kind"] == "none"


def test_forecast_uses_object_dates_ahead_of_schedule_tasks():
    window = planned_window("2026-06-01", "2026-12-01", [("2026-10-01", "2026-10-05")])
    assert window == (date(2026, 6, 1), date(2026, 12, 1))
    fallback = planned_window("", "", [("2026-10-01", "2026-11-01"), ("2026-09-01", "2026-09-15")])
    assert fallback == (date(2026, 9, 1), date(2026, 11, 1))


def test_procurement_fact_uses_chosen_price_and_skips_a_covered_invoice():
    line = ProcLine(
        id="bl",
        request_id="br",
        pos_no="1",
        title="Кабель",
        unit="м",
        qty=2,
        selected_offer_id="bo",
    )
    offer = ProcOffer(
        id="bo",
        line_id="bl",
        supplier_name="Поставщик A",
        price_kzt=100,
        vat_included=False,
        confirmed=True,
    )
    invoice = ProcDocument(
        id="doc",
        request_id="br",
        supplier_name="Поставщик A",
        stored_name="a.pdf",
        mime="application/pdf",
        size=10,
        sha256="abc",
        uploaded_at="2026-10-19T00:00:00+00:00",
        uploaded_by="u",
        amount_kzt=999,
        is_actual=True,
    )
    fact = procurement_actual([line], [offer], [invoice], vat_rate=0.16)
    assert fact["materials"] == 232
    bare = ProcDocument(
        id="doc2",
        request_id="other",
        supplier_name="Поставщик B",
        stored_name="b.pdf",
        mime="application/pdf",
        size=10,
        sha256="def",
        uploaded_at="2026-10-19T00:00:00+00:00",
        uploaded_by="u",
        amount_kzt=80,
        is_actual=True,
    )
    only_invoice = procurement_actual([], [], [bare], vat_rate=0.16)
    assert only_invoice["materials"] == 80


def test_budget_permissions_expenses_and_colours(monkeypatch):
    owner = _owner()
    outsider, _outsider_id = _register("budget-outsider@demo.superapp", "Чужая компания")
    viewer_token, viewer_id = _register("budget-viewer@demo.superapp", "Другая контора")
    created = client.post(
        "/v1/site/projects",
        json={"title": "Объект с бюджетом", "address": "Тестовый адрес"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["data"]["id"]
    with store._lock:
        store.directory[f"dir-{viewer_id}"] = DirectoryRow(
            id=f"dir-{viewer_id}",
            project_id=project_id,
            user_id=viewer_id,
            company="Другая контора",
            role_on_site="architect",
        )
        store._save_unlocked()

    assert client.get(f"/v1/site/projects/{project_id}/object-budget", headers=_auth(outsider)).status_code == 403
    assert client.get("/v1/site/projects/missing-budget/object-budget", headers=_auth(owner)).status_code == 404
    viewed = client.get(f"/v1/site/projects/{project_id}/object-budget", headers=_auth(viewer_token))
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["data"]["can_edit"] is False
    assert (
        client.put(
            f"/v1/site/projects/{project_id}/object-budget",
            json={"total_kzt": 1000},
            headers=_auth(viewer_token),
        ).status_code
        == 403
    )
    denied_expense = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 10, "category": "works", "note": ""},
        headers=_auth(viewer_token),
    )
    assert denied_expense.status_code == 403

    overflow = client.put(
        f"/v1/site/projects/{project_id}/object-budget",
        json={"total_kzt": 1000, "materials_kzt": 800, "works_kzt": 300},
        headers=_auth(owner),
    )
    assert overflow.status_code == 422
    negative = client.put(
        f"/v1/site/projects/{project_id}/object-budget",
        json={"total_kzt": -1},
        headers=_auth(owner),
    )
    assert negative.status_code == 422

    planned = client.put(
        f"/v1/site/projects/{project_id}/object-budget",
        json={"total_kzt": 1000, "materials_kzt": 600, "works_kzt": 400},
        headers={**_auth(owner), "Idempotency-Key": "plan-budget-1"},
    )
    assert planned.status_code == 200, planned.text
    replay = client.put(
        f"/v1/site/projects/{project_id}/object-budget",
        json={"total_kzt": 1000, "materials_kzt": 600, "works_kzt": 400},
        headers={**_auth(owner), "Idempotency-Key": "plan-budget-1"},
    )
    assert replay.status_code == 200
    clash = client.put(
        f"/v1/site/projects/{project_id}/object-budget",
        json={"total_kzt": 2000},
        headers={**_auth(owner), "Idempotency-Key": "plan-budget-1"},
    )
    assert clash.status_code == 409
    assert planned.json()["data"]["signal"] == "green"
    assert planned.json()["data"]["fact_kzt"] == 0
    assert planned.json()["data"]["remaining_kzt"] == 1000

    bad_amount = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 0, "category": "works"},
        headers=_auth(owner),
    )
    assert bad_amount.status_code == 422
    bad_category = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 10, "category": "travel"},
        headers=_auth(owner),
    )
    assert bad_category.status_code == 422

    request = ProcRequest(
        id="req-budget-fact",
        project_id=project_id,
        number=1,
        title="Кабель",
        status="decided",
        created_at="2026-10-19T00:00:00+00:00",
        created_by="u-owner",
    )
    line = ProcLine(
        id="line-budget-fact",
        request_id=request.id,
        pos_no="1",
        title="Кабель",
        unit="м",
        qty=2,
        selected_offer_id="offer-budget-fact",
    )
    offer = ProcOffer(
        id="offer-budget-fact",
        line_id=line.id,
        supplier_name="Поставщик A",
        price_kzt=100,
        vat_included=True,
        confirmed=True,
    )
    with store._lock:
        store.proc_requests[request.id] = request
        store.proc_lines[line.id] = line
        store.proc_offers[offer.id] = offer
        store._save_unlocked()

    spent = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 50, "category": "works", "note": "бригада"},
        headers={**_auth(owner), "Idempotency-Key": "expense-works-1"},
    )
    assert spent.status_code == 200, spent.text
    body = spent.json()["data"]
    assert body["procurement_kzt"] == 200
    assert body["manual_kzt"] == 50
    assert body["fact_kzt"] == 250
    assert body["fact_by_category"]["materials"] == 200
    assert body["fact_by_category"]["works"] == 50
    assert body["signal"] == "green"
    assert body["forecast_reason"] == "no_dates"
    assert body["overrun_kind"] == "none"
    again = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 50, "category": "works", "note": "бригада"},
        headers={**_auth(owner), "Idempotency-Key": "expense-works-1"},
    )
    assert again.status_code == 200
    assert again.json()["data"]["manual_kzt"] == 50
    conflict = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 70, "category": "works", "note": "другое"},
        headers={**_auth(owner), "Idempotency-Key": "expense-works-1"},
    )
    assert conflict.status_code == 409

    task = client.post(
        f"/v1/site/projects/{project_id}/schedule",
        json={"title": "Каркас", "start": "2026-10-01", "finish": "2026-10-20", "pct": 40},
        headers=_auth(owner),
    )
    assert task.status_code == 200, task.text
    # 10 of 19 days elapsed. Task percent is not the forecast input.
    monkeypatch.setattr("app.store_budget.today_date", lambda: date(2026, 10, 11))
    more = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        json={"amount_kzt": 700, "category": "materials", "note": ""},
        headers=_auth(owner),
    )
    assert more.status_code == 200, more.text
    yellow = more.json()["data"]
    assert yellow["fact_kzt"] == 950
    assert yellow["signal"] == "yellow"
    assert yellow["overrun_kind"] == "forecast"
    assert yellow["forecast_reason"] == "ok"
    assert yellow["elapsed_days"] == 10
    assert yellow["span_days"] == 19
    assert yellow["forecast_kzt"] == 1805
    assert yellow["overrun_kzt"] == 805

    photo = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        data={"amount_kzt": "100", "category": "other", "note": "чек"},
        files={"photo": ("receipt.png", _png(), "image/png")},
        headers=_auth(owner),
    )
    assert photo.status_code == 200, photo.text
    red = photo.json()["data"]
    assert red["fact_kzt"] == 1050
    assert red["signal"] == "red"
    assert red["overrun_kind"] == "actual"
    assert red["overrun_kzt"] == 50
    saved = next(item for item in red["expenses"] if item["has_photo"])
    picture = client.get(
        f"/v1/site/projects/{project_id}/expenses/{saved['id']}/photo",
        headers=_auth(owner),
    )
    assert picture.status_code == 200
    assert picture.content.startswith(b"\x89PNG")
    assert (
        client.get(f"/v1/site/projects/{project_id}/expenses/{saved['id']}/photo", headers=_auth(outsider)).status_code
        == 403
    )
    assert client.get(f"/uploads/{saved['id']}.png").status_code in (401, 404)

    duplicate = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        data={"amount_kzt": "100", "category": "other", "note": "ещё раз"},
        files={"photo": ("receipt.png", _png(), "image/png")},
        headers=_auth(owner),
    )
    assert duplicate.status_code == 409
    broken = client.post(
        f"/v1/site/projects/{project_id}/expenses",
        data={"amount_kzt": "15", "category": "equipment"},
        files={"photo": ("note.txt", b"not-an-image", "text/plain")},
        headers=_auth(owner),
    )
    assert broken.status_code == 422

    removed = client.delete(
        f"/v1/site/projects/{project_id}/expenses/{saved['id']}",
        headers=_auth(viewer_token),
    )
    assert removed.status_code == 403
    gone = client.delete(
        f"/v1/site/projects/{project_id}/expenses/{saved['id']}",
        headers=_auth(owner),
    )
    assert gone.status_code == 200
    missing_expense = client.delete(
        f"/v1/site/projects/{project_id}/expenses/{saved['id']}",
        headers=_auth(owner),
    )
    assert missing_expense.status_code == 404
