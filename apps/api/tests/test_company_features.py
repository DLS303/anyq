"""Company feature flags: company_id, optimistic version, and append-only audit."""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
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
    if role == "owner":
        moved = False
        for existing in list(store.users_by_id.values()):
            if existing.id == user.id or existing.role != "owner":
                continue
            demoted = existing.model_copy(update={"role": "buyer"})
            store.users_by_id[existing.id] = demoted
            if existing.email:
                store.users[existing.email.lower()] = demoted
            moved = True
        if moved:
            store._save()
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    store._save()
    return updated


@pytest.fixture(autouse=True)
def _restore_demo_owner():
    yield
    demo = store.get_user("u-owner")
    if demo is not None and demo.role != "owner":
        _promote(demo.email, "owner")


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
    spec = importlib.util.spec_from_file_location(
        "pf0_migration",
        Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261019_0002_pf0.py",
    )
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    for name in ("audit_log_2026_10", "audit_log_2026_11", "audit_log_default"):
        statement = migration.audit_truncate_trigger(name)
        assert f"BEFORE TRUNCATE ON {name}" in statement
        assert name in source
    assert "2026-10-01 00:00:00+00" in source
    assert "2026-11-01 00:00:00+00" in source
    assert "2026-12-01 00:00:00+00" in source
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM anyq_app" in source
    assert "def audit_truncate_trigger" in source
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
    _promote("owner@demo.superapp", "owner")
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


def _worker(args: list[str], dest: Path, ready: Path, start: Path, err: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["ANYQ_DEMO_MODE"] = "0"
    root = Path(__file__).resolve().parents[1]
    handle = err.open("w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(root / "tests" / "pf0_worker.py"), *args, str(dest), str(ready), str(start)],
        cwd=root,
        env=env,
        stderr=handle,
    )


def _release_after_init(*procs: tuple[subprocess.Popen, Path, Path]) -> None:
    start = procs[0][2]
    deadline = time.time() + 45
    while time.time() < deadline:
        if all(ready.exists() for _proc, ready, _start in procs):
            start.write_text("go", encoding="utf-8")
            return
        if any(proc.poll() is not None for proc, _ready, _start in procs):
            break
        time.sleep(0.02)
    for proc, _ready, _start in procs:
        proc.wait(timeout=5)
    raise AssertionError("workers did not finish startup")


def test_two_workers_claim_one_bin(tmp_path):
    bin_no = f"{uuid4().int % 10**12:012d}"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    start = tmp_path / "start"
    left = _worker(
        ["register", f"race-a-{bin_no}@example.com", bin_no],
        first,
        tmp_path / "ready-a",
        start,
        tmp_path / "err-a.txt",
    )
    right = _worker(
        ["register", f"race-b-{bin_no}@example.com", bin_no],
        second,
        tmp_path / "ready-b",
        start,
        tmp_path / "err-b.txt",
    )
    _release_after_init((left, tmp_path / "ready-a", start), (right, tmp_path / "ready-b", start))
    assert left.wait(timeout=60) == 0, (tmp_path / "err-a.txt").read_text()
    assert right.wait(timeout=60) == 0, (tmp_path / "err-b.txt").read_text()
    rows = [json.loads(first.read_text()), json.loads(second.read_text())]
    winners = [row for row in rows if row["key"] == f"bin:{bin_no}"]
    losers = [row for row in rows if row["key"].startswith("user:")]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0]["review"] is True
    assert losers[0]["key"] == f"user:{losers[0]['id']}"


def test_two_workers_first_flag_creation(tmp_path):
    company_id = f"bin:{uuid4().int % 10**12:012d}"
    first = tmp_path / "flag-a.json"
    second = tmp_path / "flag-b.json"
    start = tmp_path / "start"
    left = _worker(["flag", company_id], first, tmp_path / "ready-a", start, tmp_path / "err-a.txt")
    right = _worker(["flag", company_id], second, tmp_path / "ready-b", start, tmp_path / "err-b.txt")
    _release_after_init((left, tmp_path / "ready-a", start), (right, tmp_path / "ready-b", start))
    assert left.wait(timeout=60) == 0, (tmp_path / "err-a.txt").read_text()
    assert right.wait(timeout=60) == 0, (tmp_path / "err-b.txt").read_text()
    codes = sorted(json.loads(path.read_text())["code"] for path in (first, second))
    assert codes == [200, 409]


def test_first_flag_creation_conflict_returns_409(monkeypatch):
    from sqlalchemy.orm import Session

    from app.company_features import set_feature

    company_id = f"bin:{uuid4().int % 10**12:012d}"
    set_feature(company_id, "offline", True, "u-race", row_version=0)

    def hidden(self, statement, *args, **kwargs):
        return None

    monkeypatch.setattr(Session, "scalar", hidden)
    with pytest.raises(HTTPException) as caught:
        set_feature(company_id, "offline", True, "u-race", row_version=0)
    assert caught.value.status_code == 409


def test_audit_partition_statements_cover_truncate_and_revoke():
    from app.audit_partitions import partition_statements

    sql = "\n".join(partition_statements(2027, 1))
    assert "CREATE TABLE IF NOT EXISTS audit_log_2027_01" in sql
    assert "2027-01-01 00:00:00+00" in sql
    assert "2027-02-01 00:00:00+00" in sql
    assert "BEFORE TRUNCATE ON audit_log_2027_01" in sql
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log_2027_01 FROM anyq_app" in sql


def test_failed_register_does_not_keep_the_bin(monkeypatch):
    from sqlalchemy import text

    import app.store as store_mod
    from app.schemas import RegisterBody

    def boom(*_args, **_kwargs):
        raise RuntimeError("disk")

    monkeypatch.setattr(store_mod, "bump_revisions", boom)
    bin_no = f"{uuid4().int % 10**12:012d}"
    with pytest.raises(RuntimeError):
        store.register(
            RegisterBody(
                email=f"fail-{bin_no}@example.com",
                password="secret12",
                full_name="Fail User",
                phone="+77001112233",
                company="Fail LLP",
                company_bin=bin_no,
                city="Almaty",
                role="buyer",
                consent_offer_pd=True,
            )
        )
    with store._sql.factory() as session:
        found = session.execute(
            text("SELECT 1 FROM companies WHERE legacy_key = :key"),
            {"key": f"bin:{bin_no}"},
        ).first()
    assert found is None


def test_upgrade_from_pre_pr_data():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["ANYQ_DEMO_MODE"] = "0"
    subprocess.check_call([sys.executable, str(root / "tests" / "upgrade_pre_pr.py")], cwd=root, env=env)


def test_upgrade_same_bin_different_companies_on_postgres():
    if os.environ.get("ANYQ_TEST_POSTGRES") != "1" or not os.environ.get("DATABASE_URL"):
        pytest.skip("postgres")
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine.url import make_url

    parsed = make_url(os.environ["DATABASE_URL"])
    name = "t" + uuid4().hex[:12]
    admin = create_engine(
        parsed.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    url = parsed.set(database=name).render_as_string(hide_password=False)
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["ANYQ_UPGRADE_KEEP_URL"] = "1"
    env["ANYQ_DEMO_MODE"] = "0"
    subprocess.check_call([sys.executable, str(root / "tests" / "upgrade_pre_pr.py")], cwd=root, env=env)
