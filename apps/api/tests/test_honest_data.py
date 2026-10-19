from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.main import app
from app.store import store
from app.tax import vat_rate

client = TestClient(app)


def _register(email: str, role: str = "buyer"):
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": "Test LLP",
            "company_bin": "123456789012",
            "city": "Almaty",
            "role": role,
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    return data["token"], data["user"]["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _demo(user_id: str, email: str, password: str) -> str:
    store.credentials[user_id] = hash_password(password)
    res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def test_vat_rate_follows_act_date_and_no_vat_mode():
    assert vat_rate("2025-12-31") == 0.12
    assert vat_rate("2026-01-01") == 0.16
    assert vat_rate("2026-10-19", no_vat=True) == 0.0

    early = client.get("/v1/acts/vat", params={"act_date": "2025-12-31", "project_id": "pr-besagash"})
    assert early.status_code == 200, early.text
    assert early.json()["data"]["vat_percent"] == 12
    assert early.json()["data"]["no_vat"] is False
    assert early.json()["data"]["prior_signed_kzt"] == 0
    assert "214-VIII" in early.json()["data"]["basis"]

    current = client.get("/v1/acts/vat", params={"act_date": "2026-01-01"})
    assert current.status_code == 200, current.text
    assert current.json()["data"]["vat_percent"] == 16
    assert current.json()["data"]["prior_signed_kzt"] == 0

    exempt = client.get("/v1/acts/vat", params={"act_date": "2026-03-15", "no_vat": "true"})
    assert exempt.status_code == 200, exempt.text
    body = exempt.json()["data"]
    assert body["vat_percent"] == 0
    assert body["vat_rate"] == 0
    assert body["no_vat"] is True
    assert body["basis"] == ""

    bad = client.get("/v1/acts/vat", params={"act_date": "31-12-2025"})
    assert bad.status_code == 400


def test_review_requires_stars_text_and_completed_order():
    buyer, buyer_id = _register("review-buyer@example.com")
    created = client.post(
        "/v1/specialists/sp-surv/orders",
        json={"specialist_id": "sp-surv", "message": "Нужна топосъёмка"},
        headers=_auth(buyer),
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["data"]["id"]

    too_early = client.post(
        f"/v1/orders/{order_id}/review",
        json={"stars": 4, "text": "Рано"},
        headers=_auth(buyer),
    )
    assert too_early.status_code == 400

    surveyor = _demo("u-surv", "surveyor@demo.superapp", "survey-pass-1")
    quoted = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "quoted", "quote_kzt": 120000, "quote_term": "5 дней", "quote_comment": "Выезд"},
        headers=_auth(surveyor),
    )
    assert quoted.status_code == 200, quoted.text
    accepted = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "accepted"},
        headers=_auth(buyer),
    )
    assert accepted.status_code == 200, accepted.text
    started = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "in_progress"},
        headers=_auth(surveyor),
    )
    assert started.status_code == 200, started.text
    done = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "completed"},
        headers=_auth(surveyor),
    )
    assert done.status_code == 200, done.text

    for payload in ({"stars": 0, "text": "текст"}, {"stars": 6, "text": "текст"}, {"stars": 5, "text": ""}):
        rejected = client.post(f"/v1/orders/{order_id}/review", json=payload, headers=_auth(buyer))
        assert rejected.status_code == 422, rejected.text

    blank = client.post(
        f"/v1/orders/{order_id}/review",
        json={"stars": 5, "text": "   "},
        headers=_auth(buyer),
    )
    assert blank.status_code == 400

    stranger, _ = _register("review-stranger@example.com")
    forbidden = client.post(
        f"/v1/orders/{order_id}/review",
        json={"stars": 2, "text": "Чужой отзыв"},
        headers=_auth(stranger),
    )
    assert forbidden.status_code == 403

    ok = client.post(
        f"/v1/orders/{order_id}/review",
        json={"stars": 4, "text": "Выехали в срок, контур совпал."},
        headers=_auth(buyer),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["stars"] == 4
    assert ok.json()["data"]["client_id"] == buyer_id

    again = client.post(
        f"/v1/orders/{order_id}/review",
        json={"stars": 1, "text": "Второй отзыв"},
        headers=_auth(buyer),
    )
    assert again.status_code == 400


def test_quote_amount_must_be_positive_and_keeps_term():
    buyer, _ = _register("quote-buyer@example.com")
    created = client.post(
        "/v1/specialists/sp-surv/orders",
        json={"specialist_id": "sp-surv", "message": "Нужно КП"},
        headers=_auth(buyer),
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["data"]["id"]
    surveyor = _demo("u-surv", "surveyor@demo.superapp", "survey-pass-1")

    missing = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "quoted"},
        headers=_auth(surveyor),
    )
    assert missing.status_code == 400

    zero = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "quoted", "quote_kzt": 0, "quote_term": "10 дней", "quote_comment": "нет"},
        headers=_auth(surveyor),
    )
    assert zero.status_code == 400

    quoted = client.post(
        f"/v1/orders/{order_id}/status",
        json={
            "status": "quoted",
            "quote_kzt": 180000,
            "quote_term": "10 рабочих дней",
            "quote_comment": "С выездом и планом.",
        },
        headers=_auth(surveyor),
    )
    assert quoted.status_code == 200, quoted.text
    data = quoted.json()["data"]
    assert data["quote_kzt"] == 180000
    assert data["quote_term"] == "10 рабочих дней"
    assert data["quote_comment"] == "С выездом и планом."
    assert data["status"] == "quoted"


def test_invoice_is_marked_manually_by_recipient_only():
    owner = _demo("u-owner", "owner@demo.superapp", "owner-pass-2")
    buyer = _demo("u-buyer", "buyer@demo.superapp", "buyer-pass-2")
    created = client.post(
        "/v1/crm/invoices",
        json={
            "deal_id": "deal-land-1",
            "title": "Задаток",
            "amount_kzt": 100000,
            "payer_name": "Алия",
            "escrow_enabled": True,
        },
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    invoice = created.json()["data"]
    assert invoice["escrow_enabled"] is False
    assert invoice["can_mark_paid"] is True
    invoice_id = invoice["id"]

    buyer_view = client.get("/v1/crm/invoices", headers=_auth(buyer))
    assert buyer_view.status_code == 200
    seen = next(row for row in buyer_view.json()["data"] if row["id"] == invoice_id)
    assert seen["can_mark_paid"] is False
    assert seen["escrow_enabled"] is False

    denied = client.post(f"/v1/crm/invoices/{invoice_id}/pay", headers=_auth(buyer))
    assert denied.status_code == 403

    paid = client.post(f"/v1/crm/invoices/{invoice_id}/pay", headers=_auth(owner))
    assert paid.status_code == 200, paid.text
    assert paid.json()["data"]["status"] == "paid"
    assert paid.json()["data"]["marked_manually"] is True
    blob = paid.text.lower()
    assert "kaspi" not in blob
    assert "эскроу" not in blob
    assert paid.json()["data"]["escrow_enabled"] is False

    deal = client.get("/v1/crm/deals/deal-land-1", headers=_auth(owner))
    titles = " ".join(row["title"] + " " + row["description"] for row in deal.json()["activities"])
    assert "отмечено вручную" in titles.lower()
    assert "kaspi" not in titles.lower()
    assert "эскроу" not in titles.lower()


def test_deal_to_project_does_not_invent_fields_and_is_idempotent():
    token, _ = _register("project-maker@example.com")
    created = client.post(
        "/v1/crm/deals",
        json={"title": "Коробка без сметы", "amount_kzt": 0, "funnel": "construction"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    deal_id = created.json()["data"]["id"]
    first = client.post(f"/v1/crm/deals/{deal_id}/to-project", json={}, headers=_auth(token))
    assert first.status_code == 200, first.text
    project = first.json()["data"]
    assert project["address"] == ""
    assert project["finish"] == ""
    assert project["budget_kzt"] == 0
    assert not project["contractor_id"]
    assert project["budget_kzt"] != 25_000_000
    lines = [row for row in store.budget_lines.values() if row.project_id == project["id"]]
    assert lines == []

    second = client.post(
        f"/v1/crm/deals/{deal_id}/to-project",
        json={"address": "не должно перезаписать", "finish": "2030-01-01", "budget_kzt": 25000000},
        headers=_auth(token),
    )
    assert second.status_code == 200, second.text
    again = second.json()["data"]
    assert again["id"] == project["id"]
    assert again["address"] == ""
    assert again["finish"] == ""
    assert again["budget_kzt"] == 0
    assert [row for row in store.budget_lines.values() if row.project_id == project["id"]] == []

    filled = client.post(
        "/v1/crm/deals",
        json={"title": "Коробка со сметой", "amount_kzt": 0, "funnel": "construction"},
        headers=_auth(token),
    )
    filled_id = filled.json()["data"]["id"]
    made = client.post(
        f"/v1/crm/deals/{filled_id}/to-project",
        json={"address": "ул. Абая 10", "finish": "2026-12-01", "budget_kzt": 900000},
        headers=_auth(token),
    )
    assert made.status_code == 200, made.text
    body = made.json()["data"]
    assert body["address"] == "ул. Абая 10"
    assert body["finish"] == "2026-12-01"
    assert body["budget_kzt"] == 900000


def test_crm_conversion_is_computed():
    token, _ = _register("analytics-user@example.com")
    res = client.get("/v1/crm/analytics", headers=_auth(token))
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert "lead_to_deal_pct" in data
    assert "68.4" not in res.text
    assert "escrow" not in res.text.lower()
    assert "эскроу" not in res.text.lower()
    if data["lead_to_deal_pct"] is not None:
        assert 0 <= data["lead_to_deal_pct"] <= 100
