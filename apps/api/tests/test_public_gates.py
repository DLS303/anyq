from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.main import app
from app.store import store

client = TestClient(app)

_VALID = {
    "email": "closed-gate@example.com",
    "password": "secret12",
    "full_name": "Closed Gate",
    "phone": "+77001112233",
    "company": "Closed LLP",
    "company_bin": "123456789012",
    "city": "Almaty",
    "role": "buyer",
    "consent_offer_pd": True,
}


def test_register_is_closed_before_validation(monkeypatch):
    monkeypatch.delenv("REGISTRATION_ENABLED", raising=False)
    before = len(store.users_by_id)
    malformed = client.post(
        "/v1/auth/register",
        content=b"not-json",
        headers={"Content-Type": "application/json", "User-Agent": "anyq-test"},
    )
    assert malformed.status_code == 403
    assert malformed.json()["detail"] == "Регистрация недоступна"

    for value in ("", "0", "true", "yes"):
        monkeypatch.setenv("REGISTRATION_ENABLED", value)
        res = client.post("/v1/auth/register", json=_VALID, headers={"User-Agent": "anyq-test"})
        assert res.status_code == 403, value
        assert res.json()["detail"] == "Регистрация недоступна"
    assert store.get_user_by_email(_VALID["email"]) is None
    assert len(store.users_by_id) == before

    monkeypatch.setenv("REGISTRATION_ENABLED", "1")
    invalid = client.post("/v1/auth/register", json={}, headers={"User-Agent": "anyq-test"})
    assert invalid.status_code == 422


def test_demo_login_stays_open_when_registration_is_closed(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "0")
    store.credentials["u-owner"] = hash_password("owner-pass-gate")
    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-gate", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["data"]["user"]["email"] == "owner@demo.superapp"
    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['data']['token']}"})
    assert me.status_code == 200
    closed = client.post("/v1/auth/register", json=_VALID)
    assert closed.status_code == 403


def test_openapi_ui_is_hidden_in_production(monkeypatch):
    monkeypatch.setenv("ANYQ_ENV", "development")
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/").json()["docs"] == "/docs"

    monkeypatch.setenv("ANYQ_ENV", "production")
    for path in ("/docs", "/docs/", "/redoc", "/openapi.json"):
        hidden = client.get(path)
        assert hidden.status_code == 404, path
        assert hidden.json()["detail"] == "Not Found"
    assert "docs" not in client.get("/").json()
