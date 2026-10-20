import time

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.authutil import hash_password
from app.main import app
from app.ratelimit import LoginRateLimiter, RateLimited, login_limiter
from app.store import store

client = TestClient(app)


def _register(email: str, role: str = "buyer", pilot: str | None = None, **extra):
    body = {
        "email": email,
        "password": "secret12",
        "full_name": "Test User",
        "phone": "+77001112233",
        "company": "Test LLP",
        "company_bin": extra.pop("company_bin", "123456789012"),
        "city": "Almaty",
        "role": role,
        "consent_offer_pd": True,
    }
    if pilot is not None:
        body["pilot"] = pilot
    body.update(extra)
    return client.post("/v1/auth/register", json=body, headers={"User-Agent": "anyq-test"})


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


def test_healthz_is_liveness_only():
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body == {"ok": True}


def test_security_headers_on_api():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert res.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert res.headers["strict-transport-security"] == "max-age=86400"
    policy = res.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    assert "default-src 'none'" in policy


def test_empty_pilot_is_not_engicon_and_role_is_required():
    omitted = _register("pilot-off@example.com")
    assert omitted.status_code == 200, omitted.text
    user = store.get_user_by_email("pilot-off@example.com")
    assert user is not None
    assert user.pilot == ""

    blank = _register("pilot-blank@example.com", pilot="   ", company_bin="123456789013")
    assert blank.status_code == 200, blank.text
    assert store.get_user_by_email("pilot-blank@example.com").pilot == ""

    opted = _register("pilot-on@example.com", pilot="engicon", company_bin="123456789014")
    assert opted.status_code == 200, opted.text
    assert store.get_user_by_email("pilot-on@example.com").pilot == "engicon"

    missing_role = client.post(
        "/v1/auth/register",
        json={
            "email": "norole@example.com",
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": "Test LLP",
            "company_bin": "123456789015",
            "consent_offer_pd": True,
        },
    )
    assert missing_role.status_code == 422
    assert store.get_user_by_email("norole@example.com") is None


def test_service_order_rejects_illegal_transition():
    created = _register("order-buyer@example.com")
    assert created.status_code == 200, created.text
    buyer = created.json()["data"]["token"]
    order = client.post(
        "/v1/specialists/sp-surv/orders",
        json={"specialist_id": "sp-surv", "message": "Нужна топосъёмка"},
        headers=_auth(buyer),
    )
    assert order.status_code == 200, order.text
    order_id = order.json()["data"]["id"]
    surveyor = _demo("u-surv", "surveyor@demo.superapp", "survey-pass-1")

    jumped = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "completed"},
        headers=_auth(surveyor),
    )
    assert jumped.status_code == 409

    buyer_quote = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "quoted", "quote_kzt": 90000},
        headers=_auth(buyer),
    )
    assert buyer_quote.status_code == 409

    quoted = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "quoted", "quote_kzt": 90000, "quote_term": "7 дней", "quote_comment": "План"},
        headers=_auth(surveyor),
    )
    assert quoted.status_code == 200, quoted.text

    stranger = _register("order-stranger@example.com", company_bin="123456789016")
    assert stranger.status_code == 200, stranger.text
    denied = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "accepted"},
        headers=_auth(stranger.json()["data"]["token"]),
    )
    assert denied.status_code == 403

    accepted = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "accepted"},
        headers=_auth(buyer),
    )
    assert accepted.status_code == 200, accepted.text
    skip_done = client.post(
        f"/v1/orders/{order_id}/status",
        json={"status": "completed"},
        headers=_auth(surveyor),
    )
    assert skip_done.status_code == 409
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
    assert done.json()["data"]["status"] == "completed"


def test_material_order_follows_supplier_flow():
    buyer_res = _register("mat-buyer@example.com", company_bin="123456789017")
    assert buyer_res.status_code == 200, buyer_res.text
    buyer = buyer_res.json()["data"]["token"]
    supplier = _demo("u-supply", "supplier@demo.superapp", "supply-pass-1")
    created = client.post(
        "/v1/material-orders",
        json={"material_id": "mat-sand", "qty": 10, "address": "Бесагаш", "phone": "+77001112233"},
        headers=_auth(buyer),
    )
    assert created.status_code == 200, created.text
    order_id = created.json()["data"]["id"]

    shipped = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "shipped"},
        headers=_auth(supplier),
    )
    assert shipped.status_code == 409

    buyer_confirm = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "confirmed"},
        headers=_auth(buyer),
    )
    assert buyer_confirm.status_code == 409

    confirmed = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "confirmed"},
        headers=_auth(supplier),
    )
    assert confirmed.status_code == 200, confirmed.text
    delivered = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "delivered"},
        headers=_auth(supplier),
    )
    assert delivered.status_code == 409
    shipped_ok = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "shipped"},
        headers=_auth(supplier),
    )
    assert shipped_ok.status_code == 200, shipped_ok.text
    done = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "delivered"},
        headers=_auth(supplier),
    )
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "delivered"

    again = client.post(
        f"/v1/material-orders/{order_id}/status",
        params={"status": "cancelled"},
        headers=_auth(supplier),
    )
    assert again.status_code == 409


def test_login_rate_limit_is_per_account_and_ip(monkeypatch):
    email = "limit-user@example.com"
    created = _register(email, company_bin="123456789018")
    assert created.status_code == 200, created.text
    clock = {"now": 1_700_000_000.0}
    monkeypatch.setattr(time, "time", lambda: clock["now"])

    def attempt(password: str, ip: str = "203.0.113.10", account: str = email):
        return client.post(
            "/v1/auth/login",
            json={"email": account, "password": password, "consent_offer_pd": True},
            headers={"X-Forwarded-For": ip, "User-Agent": "anyq-test"},
        )

    for _ in range(5):
        failed = attempt("wrong-pass")
        assert failed.status_code == 401
    locked = attempt("secret12")
    assert locked.status_code == 429

    same_bucket = attempt("wrong-pass", ip="203.0.113.50")
    assert same_bucket.status_code == 429
    other_ip = attempt("wrong-pass", ip="198.51.100.10")
    assert other_ip.status_code == 401
    other_account = attempt("wrong-pass", account="someone-else@example.com")
    assert other_account.status_code == 401

    shared = False
    try:
        LoginRateLimiter().check(email, "203.0.113.10")
    except RateLimited:
        shared = True
    assert shared

    clock["now"] += 600
    allowed = attempt("secret12")
    assert allowed.status_code == 200, allowed.text
    assert login_limiter.count(email, "203.0.113.10") == 0


def test_login_failures_store_a_hash_and_expire():
    login_limiter.record_failure("Person@Example.com", "203.0.113.10")
    columns = {column["name"] for column in inspect(store._sql.engine).get_columns("login_failures")}
    assert "account" not in columns
    assert "ip" not in columns
    with store._sql.factory() as session:
        stored = session.execute(text("SELECT key_hash FROM login_failures")).scalar()
    assert stored
    assert "example.com" not in stored
    assert "203.0.113" not in stored
    assert login_limiter.count("person@example.com", "203.0.113.20") == 1
    with store._sql.factory() as session:
        session.execute(text("UPDATE login_failures SET created_at = :old"), {"old": time.time() - 90_000})
        session.commit()
    login_limiter.record_failure("other@example.com", "198.51.100.8")
    with store._sql.factory() as session:
        left = session.execute(text("SELECT count(*) FROM login_failures")).scalar()
    assert left == 1


def test_cross_border_consent_is_appended():
    created = _register("border@example.com", company_bin="123456789019")
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]
    user_id = created.json()["data"]["user"]["id"]
    before = [row.model_dump() for row in store.consents_for(user_id)]

    missing = client.post(
        "/v1/auth/consents/cross-border",
        json={"provider": "   ", "country": "DE"},
        headers=_auth(token),
    )
    assert missing.status_code == 400

    saved = client.post(
        "/v1/auth/consents/cross-border",
        json={"provider": "Example Maps", "country": "DE"},
        headers={**_auth(token), "User-Agent": "anyq-test"},
    )
    assert saved.status_code == 200, saved.text
    row = saved.json()["data"]
    assert row["type"] == "cross_border"
    assert row["provider"] == "Example Maps"
    assert row["country"] == "DE"
    assert row["user_id"] == user_id

    again = client.post(
        "/v1/auth/consents/cross-border",
        json={"provider": "Example Maps", "country": "DE"},
        headers=_auth(token),
    )
    assert again.status_code == 200, again.text
    listed = client.get("/v1/auth/consents", headers=_auth(token))
    assert listed.status_code == 200
    cross = [item for item in listed.json()["data"] if item["type"] == "cross_border"]
    assert len(cross) == 2
    current = [row.model_dump() for row in store.consents_for(user_id)]
    assert current[: len(before)] == before
    assert len(current) == len(before) + 2
