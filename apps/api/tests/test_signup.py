"""Sign-up accounts, phone uniqueness, demo limits, and the first request."""

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.authutil import hash_password, make_token
from app.main import app
from app.permissions import FOREMAN_PERMISSIONS, permissions_for
from app.signup import hash_code
from app.sql_backend import (
    AccountRow,
    CompanyMember,
    CompanyRow,
    ConsentEvent,
    Record,
    SignupCodeRow,
)
from app.store import store

client = TestClient(app)
STUB = "246810"


@pytest.fixture
def open_signup(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    monkeypatch.setenv("SIGNUP_STUB_CODE", STUB)


def _email() -> str:
    return f"u-{uuid4().hex[:10]}@example.com"


def _phone() -> str:
    return "+7701" + f"{uuid4().int % 10_000_000:07d}"


def _start(role: str, contact: str, *, consent: bool = True, kind: str = "individual", name: str = ""):
    return client.post(
        "/v1/auth/signup",
        json={
            "role": role,
            "contact": contact,
            "full_name": name,
            "account_kind": kind,
            "consent_offer_pd": consent,
        },
    )


def _confirm(contact: str, code: str = STUB):
    return client.post("/v1/auth/signup/confirm", json={"contact": contact, "code": code})


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _count(model) -> int:
    with store._sql.factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_revision_follows_app_role_without_truncate():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261021_0002_signup_accounts.py"
    source = path.read_text()
    assert 'revision = "20261021_0002_signup_accounts"' in source
    assert 'down_revision = "20261021_0001c_app_role"' in source
    assert "op.execute" not in source
    assert "CREATE ROLE" not in source


def test_roles_create_company_and_do_not_take_the_site_owner_slot(open_signup):
    assert not permissions_for("contractor") & FOREMAN_PERMISSIONS
    assert permissions_for("supplier", status="pending") == frozenset()
    for role, member in (("supplier", "supplier"), ("contractor", "owner"), ("customer", "owner")):
        contact = _email()
        started = _start(role, contact, kind="company" if role == "customer" else "individual")
        assert started.status_code == 200, started.text
        body = started.json()["data"]
        assert body["role"] == role
        assert body["status"] == "pending"
        assert body["access"] == "none"
        with store._sql.factory() as session:
            account = session.get(AccountRow, body["user_id"])
            company = session.get(CompanyRow, body["company_id"])
            membership = session.get(CompanyMember, (body["company_id"], body["user_id"]))
            status = session.execute(
                text("SELECT status FROM records WHERE collection = 'users' AND doc_id = :id"),
                {"id": body["user_id"]},
            ).scalar()
        assert account is not None and account.email == contact
        assert company is not None and company.role == role and company.bin is None and company.iin is None
        assert membership is not None and membership.role == member
        assert status != "owner"
        confirmed = _confirm(contact)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["data"]["status"] == "active"
        with store._sql.factory() as session:
            status = session.execute(
                text("SELECT status FROM records WHERE collection = 'users' AND doc_id = :id"),
                {"id": body["user_id"]},
            ).scalar()
        assert status == "active"


def test_phone_stays_pending_and_unverified_numbers_do_not_block(open_signup):
    phone = _phone()
    first = _start("supplier", "8" + phone[2:])
    second = _start("contractor", phone)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["notice"] == "Подтверждение по SMS появится позже"
    left = first.json()["data"]["user_id"]
    right = second.json()["data"]["user_id"]
    with store._sql.factory() as session:
        rows = session.scalars(select(AccountRow).where(AccountRow.phone == phone)).all()
    assert len(rows) == 2
    assert all(row.phone_verified_at is None and row.status == "pending" for row in rows)
    denied = client.get("/v1/auth/me", headers=_auth(make_token(left)))
    assert denied.status_code == 401
    login = client.post("/v1/auth/login/phone", json={"phone": phone, "password": "secret12"})
    assert login.status_code == 401
    _mark_verified(left)
    store.credentials[left] = hash_password("secret12")
    ok = client.post("/v1/auth/login/phone", json={"phone": "8" + phone[2:], "password": "secret12"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["user"]["id"] == left
    blocked = _start("customer", phone)
    assert blocked.status_code == 409
    with pytest.raises(IntegrityError), store._sql.factory() as session:
        row = session.get(AccountRow, right)
        assert row is not None
        row.phone_verified_at = "2026-10-21T00:00:00+00:00"
        row.status = "active"
        session.commit()


def test_invalid_input_and_missing_consent_write_nothing(open_signup):
    before = (_count(AccountRow), _count(CompanyRow), _count(ConsentEvent))
    missing = _start("customer", _email(), consent=False)
    bad_role = _start("foreman", _email())
    bad_contact = _start("customer", "12345")
    assert missing.status_code == 400
    assert bad_role.status_code == 400
    assert bad_contact.status_code == 400
    assert (_count(AccountRow), _count(CompanyRow), _count(ConsentEvent)) == before


def test_email_code_is_hashed_expires_and_locks_after_five_tries(open_signup, monkeypatch):
    contact = _email()
    started = _start("customer", contact.upper())
    assert started.status_code == 200, started.text
    user_id = started.json()["data"]["user_id"]
    with store._sql.factory() as session:
        saved = session.scalar(select(SignupCodeRow).where(SignupCodeRow.user_id == user_id))
        stored_email = session.get(AccountRow, user_id)
        assert saved is not None and stored_email is not None
        assert stored_email.email == contact
        assert saved.code_hash != STUB
        assert saved.code_hash == hash_code(user_id, STUB)
    for _ in range(4):
        wrong = _confirm(contact, "000000")
        assert wrong.status_code == 400
        assert wrong.json()["detail"] == "Неверный код"
    locked = _confirm(contact, "000000")
    assert locked.status_code == 400
    assert locked.json()["detail"] == "Код больше не действует"
    with store._sql.factory() as session:
        assert session.scalar(select(SignupCodeRow).where(SignupCodeRow.user_id == user_id)) is None

    again = _email()
    assert _start("supplier", again).status_code == 200
    from app import signup

    later = signup.signup_now() + timedelta(minutes=11)
    monkeypatch.setattr(signup, "signup_now", lambda: later)
    expired = _confirm(again)
    assert expired.status_code == 400
    assert expired.json()["detail"] == "Срок кода истёк"


def test_duplicate_email_is_rejected(open_signup):
    contact = _email()
    assert _start("customer", contact).status_code == 200
    duplicate = _start("supplier", contact)
    assert duplicate.status_code == 409


def test_customer_and_contractor_can_open_an_object_and_a_request(open_signup):
    for role in ("customer", "contractor"):
        contact = _email()
        assert _start(role, contact).status_code == 200
        confirmed = _confirm(contact)
        assert confirmed.status_code == 200, confirmed.text
        headers = _auth(confirmed.json()["data"]["token"])
        project = client.post("/v1/site/projects", json={"title": "Объект тест"}, headers=headers)
        assert project.status_code == 200, project.text
        pid = project.json()["data"]["id"]
        request = client.post(
            f"/v1/procurement/projects/{pid}/requests",
            json={"title": "Цемент"},
            headers=headers,
        )
        assert request.status_code == 200, request.text
        assert request.json()["data"]["title"] == "Цемент"


def test_supplier_inbox_is_limited_to_recipient_rows(open_signup):
    supplier_contact = _email()
    other_contact = _email()
    customer_contact = _email()
    assert _start("supplier", supplier_contact).status_code == 200
    other = _start("supplier", other_contact)
    assert other.status_code == 200, other.text
    assert _start("customer", customer_contact).status_code == 200
    supplier = _confirm(supplier_contact).json()["data"]
    customer = _confirm(customer_contact).json()["data"]
    other_user = _confirm(other_contact)
    assert other_user.status_code == 200, other_user.text
    headers = _auth(customer["token"])
    project = client.post("/v1/site/projects", json={"title": "Склад"}, headers=headers)
    assert project.status_code == 200, project.text
    pid = project.json()["data"]["id"]
    quick = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": "Песок", "unit": "т", "qty": 2},
        headers=headers,
    )
    assert quick.status_code == 200, quick.text
    request_id = quick.json()["data"]["request"]["id"]
    company_id = other.json()["data"]["company_id"]
    with store._sql.factory() as session:
        session.execute(
            text(
                "DELETE FROM request_recipients "
                "WHERE request_id = :request_id AND supplier_company_id = :company_id"
            ),
            {"request_id": request_id, "company_id": company_id},
        )
        session.commit()
    seen = client.get("/v1/procurement/inbox", headers=_auth(supplier["token"]))
    hidden = client.get("/v1/procurement/inbox", headers=_auth(other_user.json()["data"]["token"]))
    assert seen.status_code == 200, seen.text
    assert request_id in {item["id"] for item in seen.json()["data"]}
    assert hidden.status_code == 200, hidden.text
    assert request_id not in {item["id"] for item in hidden.json()["data"]}
    denied = client.post("/v1/site/projects", json={"title": "Чужой объект"}, headers=_auth(supplier["token"]))
    assert denied.status_code == 403


def test_demo_mode_accepts_only_demo_email(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    monkeypatch.setenv("SIGNUP_STUB_CODE", STUB)
    before = _count(AccountRow)
    phone = _start("customer", _phone())
    foreign = _start("customer", _email())
    assert phone.status_code == 422
    assert "телефон" in phone.json()["detail"].lower()
    assert foreign.status_code == 422
    assert "@demo.superapp" in foreign.json()["detail"]
    assert _count(AccountRow) == before
    contact = f"u-{uuid4().hex[:10]}@demo.superapp"
    created = _start("supplier", contact)
    assert created.status_code == 200, created.text
    with store._sql.factory() as session:
        account = session.get(AccountRow, created.json()["data"]["user_id"])
    assert account is not None and account.phone is None and account.email == contact


def test_profile_keeps_vat_unset(open_signup):
    contact = _email()
    assert _start("supplier", contact).status_code == 200
    confirmed = _confirm(contact)
    assert confirmed.status_code == 200, confirmed.text
    headers = _auth(confirmed.json()["data"]["token"])
    profile = client.get("/v1/auth/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["data"]["vat_label"] == "НДС не указан"
    saved = client.patch(
        "/v1/auth/profile",
        json={"city": "Астана", "vat": "unset", "company_bin": ""},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["city"] == "Астана"
    assert saved.json()["data"]["vat_included"] is None


def test_production_refuses_stub_code(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            "ANYQ_ENV": "production",
            "APP_ENV": "production",
            "SIGNUP_STUB_CODE": "135790",
            "CORS_ORIGINS": "https://demo.example",
            "JWT_SECRET": "test-only-secret-value-with-32-characters",
            "LOGIN_HASH_SECRET": "test-only-login-hash-secret-value-32ch",
            "ANYQ_DEMO_MODE": "",
            "ANYQ_DEMO_PASSWORD": "",
            "ANYQ_DB_PATH": str(tmp_path / "db.json"),
            "ANYQ_UPLOADS_DIR": str(tmp_path / "uploads"),
        }
    )
    env.pop("DATABASE_URL", None)
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "SIGNUP_STUB_CODE" in (proc.stderr + proc.stdout)


def _mark_verified(user_id: str) -> None:
    with store._sql.factory() as session:
        account = session.get(AccountRow, user_id)
        record = session.get(Record, ("users", user_id))
        assert account is not None and record is not None
        account.phone_verified_at = "2026-10-21T00:00:00+00:00"
        account.status = "active"
        payload = dict(record.payload or {})
        payload["status"] = "active"
        payload["phone_verified_at"] = account.phone_verified_at
        record.payload = payload
        record.status = "active"
        session.commit()
