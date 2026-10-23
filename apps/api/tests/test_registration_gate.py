"""Registration stays closed unless REGISTRATION_ENABLED is set, and demo mode keeps phones out."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

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
                text(
                    "SELECT count(*) FROM records WHERE collection = 'users' "
                    "AND CAST(payload AS TEXT) LIKE :phone"
                ),
                {"phone": f"%{phone}%"},
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


def test_demo_signup_rejects_phone_and_foreign_email(monkeypatch):
    monkeypatch.setenv("REGISTRATION_ENABLED", "1")
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    before = _users()
    phone = _signup("+77017778899")
    foreign = _signup(f"real-{uuid4().hex[:8]}@example.com")
    assert phone.status_code == 422
    assert "телефон" in phone.json()["detail"].lower()
    assert foreign.status_code == 422
    assert "@demo.superapp" in foreign.json()["detail"]
    assert _users() == before
