"""Registration stays closed unless REGISTRATION_ENABLED is set.

The older register route still drops a phone in demo mode. Sign-up by phone uses
the demo stub code instead.
"""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import String, cast, func, select

from app.main import app
from app.sql_backend import AccountRow, Record
from app.store import store

client = TestClient(app)
_CLOSED = "Регистрация недоступна"


def _register(email: str, phone: str = "+77015550199"):
    return client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Тест Регистрация",
            "phone": phone,
            "company": "Тест ТОО",
            "company_bin": f"{uuid4().int % 10**12:012d}",
            "city": "Алматы",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )


def _signup(contact: str):
    return client.post(
        "/v1/auth/signup",
        json={
            "role": "customer",
            "contact": contact,
            "account_kind": "individual",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )


def _users() -> int:
    with store._sql.factory() as session:
        return int(session.scalar(select(func.count()).select_from(Record).where(Record.collection == "users")) or 0)


def _phone_saved(phone: str) -> int:
    with store._sql.factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(Record)
                .where(Record.collection == "users", cast(Record.payload, String).contains(phone))
            )
            or 0
        )


def test_registration_disabled_blocks_register_and_code_send(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "")
    before_users = _users()
    with store._sql.factory() as session:
        before_accounts = int(session.scalar(select(func.count()).select_from(AccountRow)) or 0)
    registered = _register(f"closed-{uuid4().hex[:8]}@demo.superapp")
    sent = _signup(f"closed-{uuid4().hex[:8]}@demo.superapp")
    assert registered.status_code == 403
    assert sent.status_code == 403
    assert registered.json()["detail"] == _CLOSED
    assert sent.json()["detail"] == _CLOSED
    assert "REGISTRATION_ENABLED" not in registered.text
    assert _users() == before_users
    with store._sql.factory() as session:
        assert int(session.scalar(select(func.count()).select_from(AccountRow)) or 0) == before_accounts


def test_closed_production_signup_rejects_an_external_email_before_validation(monkeypatch):
    monkeypatch.setenv("ANYQ_ENV", "production")
    monkeypatch.setenv("REGISTRATION_ENABLED", "")
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    before = _users()
    with store._sql.factory() as session:
        before_accounts = int(session.scalar(select(func.count()).select_from(AccountRow)) or 0)
    sent = _signup("person@example.com")
    confirmed = client.post(
        "/v1/auth/signup/confirm",
        json={"contact": "person@example.com", "code": "123456"},
    )
    assert sent.status_code == 403
    assert confirmed.status_code == 403
    assert sent.json()["detail"] == _CLOSED
    assert confirmed.json()["detail"] == _CLOSED
    assert "@demo.superapp" not in sent.text
    assert "@demo.superapp" not in confirmed.text
    assert _users() == before
    with store._sql.factory() as session:
        assert int(session.scalar(select(func.count()).select_from(AccountRow)) or 0) == before_accounts

    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    demo_sent = _signup("person@example.com")
    demo_confirmed = client.post(
        "/v1/auth/signup/confirm",
        json={"contact": "person@example.com", "code": "123456"},
    )
    assert demo_sent.status_code == 403
    assert demo_confirmed.status_code == 403
    assert demo_sent.json()["detail"] == _CLOSED
    assert demo_confirmed.json()["detail"] == _CLOSED
    assert "@demo.superapp" not in demo_confirmed.text
    assert _users() == before


def test_demo_register_accepts_only_demo_email_and_drops_the_phone(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "1")
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    phone = "+7701666" + f"{uuid4().int % 10000:04d}"
    foreign = _register(f"real-{uuid4().hex[:8]}@example.com", phone)
    assert foreign.status_code == 422
    assert "@demo.superapp" in foreign.json()["detail"]
    assert _phone_saved(phone) == 0
    created = _register(f"demo-{uuid4().hex[:8]}@demo.superapp", phone)
    assert created.status_code == 200, created.text
    assert created.json()["data"]["user"]["phone"] == ""
    assert _phone_saved(phone) == 0


def test_demo_signup_accepts_a_phone_stub_and_rejects_a_foreign_email(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "1")
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    monkeypatch.setenv("ANYQ_ENV", "development")
    before = _users()
    foreign = _signup(f"real-{uuid4().hex[:8]}@example.com")
    assert foreign.status_code == 422
    assert "@demo.superapp" in foreign.json()["detail"]
    assert _users() == before
    phone = _signup("+7701" + f"{uuid4().int % 10_000_000:07d}")
    assert phone.status_code == 200, phone.text
    assert phone.json()["data"]["demo_stub"] is True
    assert phone.json()["data"]["channel"] == "phone"
    assert "000000" not in phone.json()["data"]["notice"]
    assert _users() == before + 1
