"""Pilot procurement flows: sourced prices, duplicate invoices, repeat and plan savings."""

import json
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.budget_calc import plan_vs_chosen
from app.config import settings
from app.main import app
from app.procurement_calc import gross_tiyn, price_is_suspicious
from app.procurement_models import ProcLine, ProcOffer
from app.schemas import Material
from app.store import store

FIXTURE = json.loads(Path(__file__).parent.joinpath("fixtures/procurement_fake.json").read_text())

client = TestClient(app)


def _register(email: str) -> str:
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Тест Снабженец",
            "phone": "+77000000008",
            "company": "ТОО «Демо Стройкомпания»",
            "company_bin": "000000000099",
            "city": "Алматы",
            "role": "buyer",
            "consent_offer_pd": True,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner() -> str:
    store.credentials["u-owner"] = hash_password("owner-pass-pilot")
    res = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-pilot", "consent_offer_pd": True},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _project(owner: str, title: str) -> str:
    created = client.post(
        "/v1/site/projects",
        json={"title": title, "address": "Алматы, тестовый адрес"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


def _line(owner: str, project_id: str, title: str) -> tuple[str, str]:
    quick = client.post(
        f"/v1/procurement/projects/{project_id}/quick",
        json={"title": title, "unit": "м", "qty": 120},
        headers=_auth(owner),
    )
    assert quick.status_code == 200, quick.text
    data = quick.json()["data"]
    return data["request"]["id"], data["line"]["id"]


def test_price_without_source_is_422_and_low_price_is_excluded_until_confirmed():
    assert settings.price_suspicious_below == 0.5
    assert settings.price_compare_days == 30
    below = settings.price_suspicious_below
    # 1 100 ₸ without VAT is 1 276 ₸ with VAT, which is not more than half under 2 450 ₸.
    gross_ex_vat = gross_tiyn(1100 * 100, False, settings.vat_rate)
    assert price_is_suspicious(gross_ex_vat, [2450 * 100], None, below=below) is False
    assert price_is_suspicious(16 * 100, [2450 * 100], None, below=below) is True
    assert price_is_suspicious(2450 * 100, [], None, below=below) is True
    assert price_is_suspicious(1600 * 100, [], 2000 * 100, below=below) is False
    assert price_is_suspicious(800 * 100, [], 2000 * 100, below=below) is True

    owner = _owner()
    project_id = _project(owner, "Демо-объект: склад 24×48")
    _request_id, line_id = _line(owner, project_id, "Профтруба 60×40×2")
    missing = client.post(
        f"/v1/procurement/lines/{line_id}/offers",
        json={"supplier_name": "ТОО «Тест Металл»", "price_kzt": 16, "vat_included": True, "confirmed": True},
        headers=_auth(owner),
    )
    assert missing.status_code == 422, missing.text
    empty = client.post(
        f"/v1/procurement/lines/{line_id}/offers",
        json={
            "supplier_name": "ТОО «Тест Металл»",
            "price_kzt": 16,
            "vat_included": True,
            "source_kind": "",
        },
        headers=_auth(owner),
    )
    assert empty.status_code == 422, empty.text

    normal = client.post(
        f"/v1/procurement/lines/{line_id}/offers",
        json={
            "supplier_name": "ТОО «Тест Металл»",
            "price_kzt": 2450,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp_sup-1_2026-10-17.pdf",
        },
        headers=_auth(owner),
    )
    assert normal.status_code == 200, normal.text
    assert normal.json()["data"]["price_tiyn"] == 245000
    assert isinstance(normal.json()["data"]["price_tiyn"], int)
    assert normal.json()["data"]["suspicious"] is True
    alone = client.get(f"/v1/procurement/requests/{_request_id}/sheet", headers=_auth(owner))
    assert alone.json()["data"]["lines"][0]["best_offer_id"] is None

    low = client.post(
        f"/v1/procurement/lines/{line_id}/offers",
        json={
            "supplier_name": "ИП «Фиктив Строй»",
            "price_kzt": 16,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "url",
            "source_label": "https://example.com/sup-5/price",
        },
        headers=_auth(owner),
    )
    assert low.status_code == 200, low.text
    body = low.json()["data"]
    assert body["price_tiyn"] == 1600
    assert isinstance(body["price_tiyn"], int)
    assert body["suspicious"] is True
    assert body["confirmed"] is False

    sheet = client.get(f"/v1/procurement/requests/{_request_id}/sheet", headers=_auth(owner))
    assert sheet.status_code == 200, sheet.text
    row = sheet.json()["data"]["lines"][0]
    assert row["best_offer_id"] == normal.json()["data"]["id"]
    low_cell = next(offer for offer in row["offers"] if offer["id"] == body["id"])
    assert low_cell["is_best"] is False

    blocked = client.post(
        f"/v1/procurement/lines/{line_id}/select",
        json={"offer_id": body["id"]},
        headers=_auth(owner),
    )
    assert blocked.status_code == 400

    confirmed = client.post(f"/v1/procurement/offers/{body['id']}/confirm", headers=_auth(owner))
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["suspicion_confirmed"] is True
    chosen = client.post(
        f"/v1/procurement/lines/{line_id}/select",
        json={"offer_id": body["id"]},
        headers=_auth(owner),
    )
    assert chosen.status_code == 200, chosen.text


def test_profile_pipe_unit_comes_from_the_catalog_and_old_price_is_the_benchmark():
    pipe = next(item for item in FIXTURE["items"] if item["id"] == "it-1")
    assert pipe["name"] == "Профтруба 60×40×2"
    assert pipe["unit"] == "м"
    quotes = [row for row in FIXTURE["prices"] if row["item_id"] == "it-1"]
    assert {row["unit_price"] for row in quotes} >= {2450, 2290, 2600}

    owner = _owner()
    project_id = _project(owner, "Демо-объект: профтруба")
    with store._lock:
        store.materials["mat-it-1"] = Material(
            id="mat-it-1",
            slug="proftruba-it-1",
            supplier_id="u-owner",
            category="metal",
            title_ru=pipe["name"],
            unit=pipe["unit"],
            price_kzt=2450,
        )
        store._save_unlocked()
    picker = client.get(
        f"/v1/procurement/projects/{project_id}/picker",
        params={"q": "Профтруба"},
        headers=_auth(owner),
    )
    assert picker.status_code == 200, picker.text
    match = next(item for item in picker.json()["data"]["catalog"] if item["title"] == pipe["name"])
    assert match["unit"] == "м"
    assert match["unit"] != "шт"
    quick = client.post(
        f"/v1/procurement/projects/{project_id}/quick",
        json={"title": pipe["name"], "unit": match["unit"], "qty": pipe["qty"]},
        headers=_auth(owner),
    )
    assert quick.status_code == 200, quick.text
    assert quick.json()["data"]["line"]["unit"] == "м"

    line_id = quick.json()["data"]["line"]["id"]
    today = date.today().isoformat()
    for row in quotes:
        posted = client.post(
            f"/v1/procurement/lines/{line_id}/offers",
            json={
                "supplier_name": next(item["name"] for item in FIXTURE["suppliers"] if item["id"] == row["supplier_id"]),
                "price_kzt": row["unit_price"],
                "vat_included": row["vat_included"],
                "confirmed": True,
                "source_kind": row["source_kind"],
                "source_label": row["source"],
                "offer_date": today,
            },
            headers=_auth(owner),
        )
        assert posted.status_code == 200, posted.text
    sheet = client.get(
        f"/v1/procurement/requests/{quick.json()['data']['request']['id']}/sheet",
        headers=_auth(owner),
    )
    row = sheet.json()["data"]["lines"][0]
    assert row["unit"] == "м"
    assert all(offer["suspicious"] is False for offer in row["offers"])

    aged = _project(owner, "Демо-объект: старая цена")
    _aged_request, aged_line = _line(owner, aged, "Уголок 50×50×5")
    old_day = (date.today() - timedelta(days=settings.price_compare_days + 5)).isoformat()
    anchor = client.post(
        f"/v1/procurement/lines/{aged_line}/offers",
        json={
            "supplier_name": "ТОО «Тест Металл»",
            "price_kzt": 2000,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp_old.pdf",
            "offer_date": old_day,
        },
        headers=_auth(owner),
    )
    assert anchor.status_code == 200, anchor.text
    assert anchor.json()["data"]["suspicious"] is True
    opened = client.post(f"/v1/procurement/offers/{anchor.json()['data']['id']}/confirm", headers=_auth(owner))
    assert opened.status_code == 200, opened.text
    near = client.post(
        f"/v1/procurement/lines/{aged_line}/offers",
        json={
            "supplier_name": "ТОО «Образец Утепление»",
            "price_kzt": 1600,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp_near.pdf",
            "offer_date": today,
        },
        headers=_auth(owner),
    )
    assert near.status_code == 200, near.text
    assert near.json()["data"]["suspicious"] is False
    _far_request, far_line = _line(owner, aged, "Швеллер 10")
    far_anchor = client.post(
        f"/v1/procurement/lines/{far_line}/offers",
        json={
            "supplier_name": "ТОО «Тест Металл»",
            "price_kzt": 2000,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp_old.pdf",
            "offer_date": old_day,
        },
        headers=_auth(owner),
    )
    assert far_anchor.status_code == 200, far_anchor.text
    client.post(f"/v1/procurement/offers/{far_anchor.json()['data']['id']}/confirm", headers=_auth(owner))
    far = client.post(
        f"/v1/procurement/lines/{far_line}/offers",
        json={
            "supplier_name": "ИП «Фиктив Строй»",
            "price_kzt": 800,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "url",
            "source_label": "https://example.com/low",
            "offer_date": today,
        },
        headers=_auth(owner),
    )
    assert far.status_code == 200, far.text
    assert far.json()["data"]["suspicious"] is True


def test_median_uses_gross_tiyn_of_confirmed_sourced_offers_as_of_the_offer_date():
    below = settings.price_suspicious_below
    ex_vat = gross_tiyn(1000 * 100, False, settings.vat_rate)
    assert ex_vat == 116000
    # Half of the raw 1 000 / 2 000 median is exactly 750, so that price is not suspicious.
    # Half of the VAT-inclusive tiyn median is higher, so the same 750 is suspicious.
    assert price_is_suspicious(750 * 100, [1000 * 100, 2000 * 100], None, below=below) is False
    assert price_is_suspicious(750 * 100, [ex_vat, 2000 * 100], None, below=below) is True

    owner = _owner()
    project_id = _project(owner, "Демо-объект: медиана")
    _request_id, line_id = _line(owner, project_id, "Швеллер 12")
    today = date.today()

    def post(price: float, day: str, supplier: str, **extra) -> dict:
        body = {
            "supplier_name": supplier,
            "price_kzt": price,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp.pdf",
            "offer_date": day,
        }
        body.update(extra)
        res = client.post(f"/v1/procurement/lines/{line_id}/offers", json=body, headers=_auth(owner))
        assert res.status_code == 200, res.text
        return res.json()["data"]

    anchor = post(2000, (today - timedelta(days=10)).isoformat(), "ТОО «Тест Металл»")
    assert anchor["suspicious"] is True
    opened = client.post(f"/v1/procurement/offers/{anchor['id']}/confirm", headers=_auth(owner))
    assert opened.status_code == 200, opened.text

    loud = post(8000, today.isoformat(), "ИП «Фиктив Строй»", confirmed=False)
    assert loud["confirmed"] is False
    bare = post(4000, today.isoformat(), "ТОО «Пример Панель»")
    with store._lock:
        stored = store.proc_offers[bare["id"]]
        stored.source_kind = ""
        stored.confirmed = True
        stored.suspicious = False
        store.proc_offers[stored.id] = stored
        store._save_unlocked()
    old = post(10000, (today - timedelta(days=45)).isoformat(), "ТОО «Образец Утепление»")
    assert old["suspicious"] is True
    client.post(f"/v1/procurement/offers/{old['id']}/confirm", headers=_auth(owner))

    near = post(1200, today.isoformat(), "ИП «Демо Крепёж»")
    assert near["price_tiyn"] == 120000
    assert isinstance(near["price_tiyn"], int)
    assert near["suspicious"] is False


def test_duplicate_invoice_returns_409_and_fact_counts_it_once():
    owner = _owner()
    project_id = _project(owner, "Демо-объект: счета")
    request_id, _line_id = _line(owner, project_id, "Профтруба 60×40×2")
    payload = {
        "company_id": "demo-co",
        "supplier_id": "sup-1",
        "supplier_name": "ТОО «Тест Металл»",
        "number": "СФ-0001",
        "date": "2026-10-18",
        "amount_kzt": 354000,
        "request_id": request_id,
    }
    first = client.post("/v1/procurement/invoices", json=payload, headers=_auth(owner))
    assert first.status_code == 200, first.text
    second = client.post("/v1/procurement/invoices", json=payload, headers=_auth(owner))
    assert second.status_code == 409, second.text
    assert second.json() == {"code": "duplicate_invoice"}
    budget = client.get(f"/v1/site/projects/{project_id}/object-budget", headers=_auth(owner))
    assert budget.status_code == 200, budget.text
    assert budget.json()["data"]["procurement_kzt"] == 354000
    assert budget.json()["data"]["fact_kzt"] == 354000

    stored = first.json()["data"]["id"]
    with store._lock:
        doc = store.proc_docs[stored]
        doc.deleted = True
        store.proc_docs[stored] = doc
        store._save_unlocked()
    again = client.post("/v1/procurement/invoices", json=payload, headers=_auth(owner))
    assert again.status_code == 200, again.text
    budget = client.get(f"/v1/site/projects/{project_id}/object-budget", headers=_auth(owner))
    assert budget.json()["data"]["procurement_kzt"] == 354000


def test_repeat_previous_copies_completed_request_into_a_draft():
    owner = _owner()
    outsider = _register("pilot-out@example.com")
    project_id = _project(owner, "Демо-объект: повтор")
    request_id, line_id = _line(owner, project_id, "Профнастил С21-0,5 оцинк.")
    offer = client.post(
        f"/v1/procurement/lines/{line_id}/offers",
        json={
            "supplier_name": "ТОО «Тест Металл»",
            "price_kzt": 3100,
            "vat_included": True,
            "confirmed": True,
            "source_kind": "file",
            "source_label": "fixtures/kp_sup-1_2026-10-04.pdf",
        },
        headers=_auth(owner),
    )
    assert offer.status_code == 200, offer.text
    assert offer.json()["data"]["suspicious"] is True
    reviewed = client.post(f"/v1/procurement/offers/{offer.json()['data']['id']}/confirm", headers=_auth(owner))
    assert reviewed.status_code == 200, reviewed.text
    selected = client.post(
        f"/v1/procurement/lines/{line_id}/select",
        json={"offer_id": offer.json()["data"]["id"]},
        headers=_auth(owner),
    )
    assert selected.status_code == 200, selected.text
    listed = client.get(f"/v1/procurement/projects/{project_id}/requests", headers=_auth(owner))
    assert listed.json()["data"]["previous_completed"]["id"] == request_id

    denied = client.post(f"/v1/procurement/projects/{project_id}/repeat-previous", headers=_auth(outsider))
    assert denied.status_code == 403
    repeated = client.post(f"/v1/procurement/projects/{project_id}/repeat-previous", headers=_auth(owner))
    assert repeated.status_code == 200, repeated.text
    draft = repeated.json()["data"]
    assert draft["request"]["status"] == "draft"
    assert draft["request"]["repeated_from"] == request_id
    assert [(row["title"], row["unit"], row["qty"]) for row in draft["lines"]] == [("Профнастил С21-0,5 оцинк.", "м", 120.0)]
    sheet = client.get(f"/v1/procurement/requests/{draft['request']['id']}/sheet", headers=_auth(owner))
    assert all(row["offers"] == [] for row in sheet.json()["data"]["lines"])
    published = client.post(f"/v1/procurement/requests/{draft['request']['id']}/publish", headers=_auth(owner))
    assert published.status_code == 200, published.text
    assert published.json()["data"]["status"] == "collecting"


def test_plan_minus_chosen_price_is_the_saved_total():
    line = ProcLine(
        id="it-6",
        request_id="req-demo-2",
        pos_no="1",
        title="Профнастил С21-0,5 оцинк.",
        unit="м²",
        qty=300,
        selected_offer_id="pr-10",
        reference_price_kzt=3250,
        reference_vat_included=True,
    )
    chosen = ProcOffer(
        id="pr-10",
        line_id="it-6",
        supplier_name="ТОО «Тест Металл»",
        price_kzt=3100,
        vat_included=True,
        confirmed=True,
        source_kind="file",
    )
    other = ProcOffer(
        id="pr-12",
        line_id="it-6",
        supplier_name="ТОО «Образец Утепление»",
        price_kzt=3250,
        vat_included=True,
        confirmed=True,
        source_kind="file",
    )
    saved = plan_vs_chosen([line], [chosen, other], vat_rate=0.16)
    assert saved["plan_kzt"] == 3250 * 300
    assert saved["chosen_kzt"] == 3100 * 300
    assert saved["total_saved_kzt"] == 150 * 300
    assert saved["lines"][0]["saved_kzt"] == saved["plan_kzt"] - saved["chosen_kzt"]
