"""Company feature flags: company_id, optimistic version, and append-only audit."""

import os
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.schema import CreateTable

from app.authutil import hash_password
from app.company_features import FEATURE_KEYS, audit_events, company_id_of
from app.main import app
from app.schemas import User
from app.sql_backend import AuditLog, CompanyFeature
from app.store import store

client = TestClient(app)
BIN_A = "111111111111"
BIN_B = "222222222222"


def _register(email: str, bin_no: str, role: str = "buyer"):
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": "Test LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": role,
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _promote(email: str, role: str = "owner") -> User:
    user = store.get_user_by_email(email)
    assert user is not None
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    return updated


def _owner_token(email: str, bin_no: str) -> str:
    data = _register(email, bin_no)
    _promote(email, "owner")
    return data["token"]


def test_company_id_is_bin_or_user_never_name():
    named = User(id="u-one", email="one@example.com", full_name="One", role="owner", company="Same Name", company_bin="")
    other = User(id="u-two", email="two@example.com", full_name="Two", role="buyer", company="Same Name", company_bin="")
    binned = User(
        id="u-three",
        email="three@example.com",
        full_name="Three",
        role="owner",
        company="Same Name",
        company_bin="12-3456-789012",
    )
    assert company_id_of(named) == "user:u-one"
    assert company_id_of(other) == "user:u-two"
    assert company_id_of(binned) == "bin:123456789012"
    assert not company_id_of(named).startswith("name:")


def test_feature_api_company_id_access_and_version(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner = _owner_token("flags-owner@example.com", BIN_A)
    buyer = _register("flags-buyer@example.com", BIN_A)["token"]
    foreign = _register("flags-foreign@example.com", BIN_B)["token"]
    foreign_own = client.get("/v1/org/features", headers=_auth(foreign))
    assert foreign_own.status_code == 200
    assert foreign_own.json()["data"][0]["company_id"] == f"bin:{BIN_B}"

    listed = client.get("/v1/org/features", headers=_auth(owner))
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]
    assert [row["key"] for row in rows] == list(FEATURE_KEYS)
    assert {row["company_id"] for row in rows} == {f"bin:{BIN_A}"}
    assert all(row["enabled"] is False and row["row_version"] == 0 and row["deleted_at"] is None for row in rows)
    assert all(not row["company_id"].startswith("name:") for row in rows)

    denied = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": True, "row_version": 0},
        headers=_auth(buyer),
    )
    assert denied.status_code == 403

    admin = _register("flags-admin@example.com", BIN_A)["token"]
    _promote("flags-admin@example.com", "admin")
    still_denied = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": True, "row_version": 0},
        headers=_auth(admin),
    )
    assert still_denied.status_code == 403

    for bad in (f"bin:{BIN_B}", "name:test llp", "user:someone-else"):
        foreign_get = client.get("/v1/org/features", params={"company_id": bad}, headers=_auth(owner))
        assert foreign_get.status_code == 404, bad
        foreign_post = client.post(
            "/v1/org/features",
            json={"key": "rfi", "enabled": True, "company_id": bad, "row_version": 0},
            headers=_auth(owner),
        )
        assert foreign_post.status_code == 404, bad

    record_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    created = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": True, "id": record_id, "row_version": 0},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    saved = created.json()["data"]
    assert saved["id"] == record_id
    assert saved["company_id"] == f"bin:{BIN_A}"
    assert saved["enabled"] is True
    assert saved["row_version"] == 1
    assert saved["deleted_at"] is None
    assert saved["updated_at"].endswith("+00:00")
    assert saved["changed_by"]

    stale = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": False, "row_version": 0},
        headers=_auth(owner),
    )
    assert stale.status_code == 409

    updated = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": False, "row_version": 1},
        headers=_auth(owner),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["row_version"] == 2
    assert updated.json()["data"]["enabled"] is False

    unknown = client.post(
        "/v1/org/features",
        json={"key": "not-a-flag", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert unknown.status_code == 400

    events = audit_events(f"bin:{BIN_A}")
    assert [row["event"] for row in events] == ["feature.enable", "feature.disable"]
    assert events[0]["key"] == "rfi"
    assert events[0]["actor"]
    first_id = events[0]["id"]
    with store._sql.factory() as session:
        row = session.get(CompanyFeature, record_id)
        assert row is not None
        row.deleted_at = "2026-10-19T00:00:00+00:00"
        session.commit()
    hidden = client.get("/v1/org/features", headers=_auth(owner))
    tomb = next(item for item in hidden.json()["data"] if item["key"] == "rfi")
    assert tomb["enabled"] is False
    assert tomb["row_version"] == 0
    revived = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert revived.status_code == 200, revived.text
    assert revived.json()["data"]["deleted_at"] is None
    assert revived.json()["data"]["row_version"] == 3
    again = audit_events(f"bin:{BIN_A}")
    assert again[0]["id"] == first_id
    assert again[0]["event"] == "feature.enable"
    assert again[-1]["event"] == "feature.enable"

    with store._sql.factory() as session, pytest.raises((IntegrityError, DatabaseError)):
        session.execute(AuditLog.__table__.update().values(event="rewritten"))
        session.commit()
    with store._sql.factory() as session, pytest.raises((IntegrityError, DatabaseError)):
        session.execute(AuditLog.__table__.delete())
        session.commit()


def test_flag_gates_routes_and_leaves_pilot_routes(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    store.credentials["u-owner"] = hash_password("owner-pass-1")
    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-1", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    owner = login.json()["data"]["token"]
    outsider = _register("flags-outsider@example.com", BIN_B)["token"]

    drawings = client.get("/v1/site/projects/pr-besagash/drawings", headers=_auth(owner))
    assert drawings.status_code == 404
    rfi = client.post(
        "/v1/site/projects/pr-besagash/rfis",
        json={"title": "Door", "question": "Which way?"},
        headers=_auth(owner),
    )
    assert rfi.status_code == 404
    with_photo = client.post(
        "/v1/site/projects/pr-besagash/punches",
        json={"title": "Crack", "photo": "uploads/fake.jpg"},
        headers=_auth(owner),
    )
    assert with_photo.status_code == 404
    plain = client.post(
        "/v1/site/projects/pr-besagash/punches",
        json={"title": "Crack without photo"},
        headers=_auth(owner),
    )
    assert plain.status_code == 200, plain.text

    bundle = client.get("/v1/site/projects/pr-besagash/bundle", headers=_auth(owner))
    assert bundle.status_code == 200, bundle.text
    body = bundle.json()["data"]
    assert body["drawings"] == []
    assert body["rfis"] == []
    assert body["company_id"].startswith("user:")
    assert body["features"]["drawings"] is False
    assert "name:" not in body["company_id"]

    requests = client.get("/v1/procurement/projects/pr-besagash/requests", headers=_auth(owner))
    assert requests.status_code == 200, requests.text
    budget = client.get("/v1/site/projects/pr-besagash/object-budget", headers=_auth(owner))
    assert budget.status_code == 200, budget.text

    opened = client.post(
        "/v1/org/features",
        json={"key": "drawings", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["data"]["company_id"].startswith("user:")
    shown = client.get("/v1/site/projects/pr-besagash/drawings", headers=_auth(owner))
    assert shown.status_code == 200, shown.text
    hidden = client.get("/v1/site/projects/pr-besagash/drawings", headers=_auth(outsider))
    assert hidden.status_code == 404


def test_unique_company_key_and_postgres_ddl():
    company_id = "bin:333333333333"
    with store._sql.factory() as session:
        session.add(
            CompanyFeature(
                id=str(uuid4()),
                company_id=company_id,
                key="offline",
                enabled=True,
                changed_by="u-test",
                changed_at="2026-10-19T00:00:00+00:00",
                row_version=1,
                updated_at="2026-10-19T00:00:00+00:00",
            )
        )
        session.commit()
    with store._sql.factory() as session:
        session.add(
            CompanyFeature(
                id=str(uuid4()),
                company_id=company_id,
                key="offline",
                enabled=False,
                changed_by="u-test",
                changed_at="2026-10-19T00:00:01+00:00",
                row_version=1,
                updated_at="2026-10-19T00:00:01+00:00",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    ddl = str(CreateTable(CompanyFeature.__table__).compile(dialect=postgresql.dialect()))
    audit = str(CreateTable(AuditLog.__table__).compile(dialect=postgresql.dialect()))
    assert "company_id" in ddl and "row_version" in ddl and "deleted_at" in ddl
    assert "org_id" not in ddl and "org_id" not in audit
    assert "event" in audit and "actor" in audit


def test_alembic_upgrade_installs_append_only_triggers(tmp_path):
    db = tmp_path / "migrate.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    subprocess.check_call(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
    )
    connection = sqlite3.connect(db)
    triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "trg_audit_log_no_update" in triggers
    assert "trg_audit_log_no_delete" in triggers
    connection.execute(
        "INSERT INTO audit_log (event, company_id, actor, at, key) VALUES (?, ?, ?, ?, ?)",
        ("feature.enable", "bin:444444444444", "u-test", "2026-10-19T00:00:00+00:00", "offline"),
    )
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE audit_log SET event = 'rewritten'")
        connection.commit()
    connection.close()
