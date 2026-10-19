"""Company feature flags: company_id, optimistic version, and append-only audit."""

import os
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.schema import CreateTable

from app.authutil import hash_password
from app.company_features import FEATURE_KEYS, audit_events, company_id_of
from app.main import app
from app.pf0_tables import AuditLog, CompanyFeature
from app.schemas import User
from app.store import store

client = TestClient(app)
BIN_A = "910000000001"
BIN_B = "910000000002"


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


def test_company_id_is_stored_not_taken_from_the_profile():
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
    stored = binned.model_copy(update={"company_key": "bin:123456789012", "company_bin": "999999999999"})
    assert company_id_of(named) == "user:u-one"
    assert company_id_of(other) == "user:u-two"
    assert company_id_of(binned) == "user:u-three"
    assert company_id_of(stored) == "bin:123456789012"
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
    assert saved["created_at"].endswith("+00:00")
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
    assert updated.json()["data"]["enabled"] is False
    assert updated.json()["data"]["row_version"] == 0
    with store._sql.factory() as session:
        disabled = session.get(CompanyFeature, record_id)
        assert disabled is not None
        assert disabled.enabled is False
        assert disabled.deleted_at
        assert disabled.deleted_at.endswith("+00:00")
        assert disabled.row_version == 2

    unknown = client.post(
        "/v1/org/features",
        json={"key": "not-a-flag", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert unknown.status_code == 400

    events = audit_events(f"bin:{BIN_A}")
    assert [row["action"] for row in events] == ["feature.enable", "feature.disable"]
    assert events[0]["entity_id"] == "rfi"
    assert events[0]["actor_user_id"]
    assert events[0]["occurred_at"].endswith("+00:00")
    assert events[1]["prev_hash"] == events[0]["row_hash"]
    first_id = events[0]["id"]
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
    assert again[0]["action"] == "feature.enable"
    assert again[-1]["action"] == "feature.enable"
    with store._sql.factory() as session:
        live = session.get(CompanyFeature, record_id)
        assert live is not None
        assert live.deleted_at is None

    with store._sql.factory() as session, pytest.raises((IntegrityError, DatabaseError)):
        session.execute(AuditLog.__table__.update().values(action="rewritten"))
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
    assert "company_id" in ddl and "row_version" in ddl and "deleted_at" in ddl and "created_at" in ddl
    assert "ix_company_features_company_id" not in ddl
    assert "org_id" not in ddl and "org_id" not in audit
    assert "action" in audit and "row_hash" in audit and "occurred_at" in audit


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
    source = (Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261019_0002_pf0.py").read_text()
    assert "app.sql_backend" not in source
    assert "op.create_table" in source
    assert "checkfirst" not in source
    assert "PARTITION BY RANGE" in source
    assert "BEFORE TRUNCATE" in source
    assert "Do not run downgrade in production" in source
    connection = sqlite3.connect(db)
    triggers = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert "trg_audit_log_no_update" in triggers
    assert "trg_audit_log_no_delete" in triggers
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "companies" in tables
    assert "company_features" in tables
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_company_features_company_id" not in indexes
    connection.execute(
        "INSERT INTO audit_log (occurred_at, company_id, actor_kind, actor_user_id, action, entity_type, entity_id, changes, row_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "2026-10-19T00:00:00+00:00",
            "bin:444444444444",
            "user",
            "u-test",
            "feature.enable",
            "company_feature",
            "offline",
            "{}",
            b"\x01",
        ),
    )
    connection.commit()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE audit_log SET action = 'rewritten'")
        connection.commit()
    connection.close()


def test_duplicate_bin_does_not_join_that_company(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner = _owner_token("flags-bin-owner@example.com", "333333333331")
    opened = client.post(
        "/v1/org/features",
        json={"key": "offline", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert opened.status_code == 200, opened.text
    second = _register("flags-bin-copy@example.com", "333333333331")
    user = store.get_user_by_email("flags-bin-copy@example.com")
    assert user is not None
    assert user.company_key == f"user:{user.id}"
    assert user.company_review is True
    own = client.get("/v1/org/features", headers=_auth(second["token"]))
    assert own.status_code == 200, own.text
    assert own.json()["data"][0]["company_id"] == f"user:{user.id}"
    foreign = client.get("/v1/org/features", params={"company_id": "bin:333333333331"}, headers=_auth(second["token"]))
    assert foreign.status_code == 404


def test_query_pid_cannot_open_a_disabled_feature(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    store.credentials["u-owner"] = hash_password("owner-pass-query")
    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-query", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    owner = login.json()["data"]["token"]
    other = _owner_token("flags-other-co@example.com", "444444444441")
    created = client.post(
        "/v1/site/projects",
        json={"title": "Other yard", "address": "Test street"},
        headers=_auth(other),
    )
    assert created.status_code == 200, created.text
    other_pid = created.json()["data"]["id"]
    for key in ("rfi", "changes", "gantt"):
        opened = client.post(
            "/v1/org/features",
            json={"key": key, "enabled": True, "row_version": 0},
            headers=_auth(other),
        )
        assert opened.status_code == 200, opened.text
    answer = client.post(
        "/v1/site/rfis/rfi-1/answer",
        params={"pid": other_pid},
        json={"answer": "from the query"},
        headers=_auth(owner),
    )
    assert answer.status_code == 404, answer.text
    status = client.post(
        "/v1/site/changes/co-1/status",
        params={"pid": other_pid},
        json={"status": "draft"},
        headers=_auth(owner),
    )
    assert status.status_code == 404, status.text
    progress = client.post(
        "/v1/site/schedule/st-1/progress",
        params={"pid": other_pid},
        json={"pct": 12},
        headers=_auth(owner),
    )
    assert progress.status_code == 404, progress.text
    enabled = client.post(
        "/v1/org/features",
        json={"key": "gantt", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert enabled.status_code == 200, enabled.text
    allowed = client.post(
        "/v1/site/schedule/st-1/progress",
        params={"pid": other_pid},
        json={"pct": 12},
        headers=_auth(owner),
    )
    assert allowed.status_code == 200, allowed.text


def test_bundle_reads_flags_once(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    store.credentials["u-owner"] = hash_password("owner-pass-once")
    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-once", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["token"]
    import app.company_features as features
    from app.routers import site

    calls = {"n": 0}
    real = features.flag_map

    def wrapped(company_id: str):
        calls["n"] += 1
        return real(company_id)

    monkeypatch.setattr(features, "flag_map", wrapped)
    monkeypatch.setattr(site, "flag_map", wrapped)
    bundle = client.get("/v1/site/projects/pr-besagash/bundle", headers=_auth(token))
    assert bundle.status_code == 200, bundle.text
    assert calls["n"] == 1


def test_project_snapshot_zeroes_closed_counters(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    shown = store.project_snapshot("pr-besagash", {})
    assert shown is not None
    assert shown["counts"]["drawings"] > 0
    assert shown["open_rfi"] > 0
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    hidden = store.project_snapshot("pr-besagash", {})
    assert hidden is not None
    assert hidden["open_rfi"] == 0
    assert hidden["counts"]["rfi"] == 0
    assert hidden["fail_inspections"] == 0
    assert hidden["counts"]["inspections"] == 0
    assert hidden["counts"]["drawings"] == 0
    assert hidden["counts"]["punch"] > 0
    drawings = store.project_snapshot("pr-besagash", {"drawings": True})
    assert drawings is not None
    assert drawings["counts"]["drawings"] > 0
    assert drawings["counts"]["rfi"] == 0


def test_snapshot_exports_company_features(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner = _owner_token("flags-export@example.com", "555555555551")
    saved = client.post(
        "/v1/org/features",
        json={"key": "offline", "enabled": True, "row_version": 0},
        headers=_auth(owner),
    )
    assert saved.status_code == 200, saved.text
    off = client.post(
        "/v1/org/features",
        json={"key": "offline", "enabled": False, "row_version": 1},
        headers=_auth(owner),
    )
    assert off.status_code == 200, off.text
    rows = store.snapshot()["company_features"]
    match = [row for row in rows if row["company_id"] == "bin:555555555551" and row["key"] == "offline"]
    assert len(match) == 1
    assert match[0]["deleted_at"]


def test_one_row_version_accepts_a_single_writer():
    from app.company_features import set_feature

    company_id = "bin:666666666661"
    set_feature(company_id, "offline", True, "u-race", row_version=0)
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def once() -> None:
        barrier.wait()
        try:
            set_feature(company_id, "offline", False, "u-race", row_version=1)
            codes.append(200)
        except HTTPException as exc:
            codes.append(exc.status_code)

    threads = [threading.Thread(target=once) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(codes) == [200, 409]
