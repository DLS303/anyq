import importlib.util
import json
import os
import queue
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError

from alembic import command
from app.invitations import InvitationClosed, accept, create_invitation, revoke
from app.legal import PD_VERSION, pd_sha256
from app.main import app
from app.procurement_models import ProcRequest
from app.schemas import ConsentRecord, RegisterBody
from app.seed import PLOTS
from app.sql_backend import ChangedByOther, InvitationRow, Record
from app.store import MemoryStore


def _alembic(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")


def _fresh_postgres() -> str:
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
    previous = os.environ.get("DATABASE_URL")
    try:
        _alembic(url)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
    return url


def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    monkeypatch.setenv("ANYQ_DEMO_PASSWORD", "")
    if os.environ.get("ANYQ_TEST_POSTGRES") == "1" and os.environ.get("DATABASE_URL"):
        monkeypatch.setenv("DATABASE_URL", _fresh_postgres())
        return
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ANYQ_DB_PATH", str(tmp_path / "db.json"))


def _register(store: MemoryStore):
    return store.register(
        RegisterBody(
            email="owner.consistency@example.com",
            password="secret12",
            full_name="Nurlan Beketov",
            phone="+77010001122",
            company="North Test LLP",
            company_bin="880000000001",
            role="buyer",
            consent_offer_pd=True,
        )
    )


def test_changed_rows_reload_without_a_full_read(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    writer = MemoryStore()
    _register(writer)
    plot = deepcopy(PLOTS[0])
    plot.id = "plot-seq"
    plot.owner_id = next(iter(writer.users_by_id))
    plot.title_ru = "Before"
    writer.plots[plot.id] = plot
    writer._save()

    reader = MemoryStore()
    before = reader._sql.full_loads
    writer.plots[plot.id] = plot.model_copy(update={"title_ru": "After"})
    writer._save()
    reader._enter()
    try:
        assert reader.plots[plot.id].title_ru == "After"
    finally:
        reader._leave()
    assert reader._sql.full_loads == before
    assert reader._sql.revisions()["plots"] >= 1


def test_parallel_edits_keep_every_increment(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    origin = MemoryStore()
    plot = deepcopy(PLOTS[0])
    plot.id = "plot-cas"
    plot.owner_id = "u-cas"
    plot.soil = "0"
    origin.plots[plot.id] = plot
    origin._save()
    left = MemoryStore()
    right = MemoryStore()

    def bump(store: MemoryStore) -> None:
        for _ in range(25):
            while True:
                advanced = False
                store._enter()
                try:
                    current = store.plots[plot.id]
                    nxt = current.model_copy(update={"soil": str(int(current.soil or "0") + 1)})
                    store.plots[plot.id] = nxt
                    store._save_unlocked()
                    advanced = True
                except ChangedByOther:
                    bag = store.plots
                    bag.dirty.discard(plot.id)
                    bag.synced_rev = None
                    store._sql.load_changes(store, "plots", int(bag.last_seq or 0))
                finally:
                    store._leave()
                if advanced:
                    break

    workers = [threading.Thread(target=bump, args=(left,)), threading.Thread(target=bump, args=(right,))]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    fresh = MemoryStore()
    assert fresh.plots[plot.id].soil == "50"


def test_stale_write_is_rejected(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    writer = MemoryStore()
    plot = deepcopy(PLOTS[0])
    plot.id = "plot-stale"
    plot.owner_id = "u-stale"
    plot.title_ru = "Original"
    writer.plots[plot.id] = plot
    writer._save()
    reader = MemoryStore()
    stale = reader.plots.peek(plot.id)
    writer.plots[plot.id] = plot.model_copy(update={"title_ru": "Saved"})
    writer._save()
    reader.plots[plot.id] = stale.model_copy(update={"title_kk": "Other"})
    with pytest.raises(ChangedByOther):
        reader._save()
    check = MemoryStore()
    assert check.plots[plot.id].title_ru == "Saved"


def test_consent_events_reject_delete(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    store = MemoryStore()
    _register(store)
    with store._sql.factory() as session:
        count = session.execute(text("SELECT count(*) FROM consent_events")).scalar()
    assert count >= 1
    with pytest.raises(DatabaseError), store._sql.factory() as session:
        session.execute(text("DELETE FROM consent_events"))
        session.commit()
    with store._sql.factory() as session:
        again = session.execute(text("SELECT count(*) FROM consent_events")).scalar()
    assert again == count


def test_baseline_revision_cannot_be_downgraded():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261019_0001_sql_store.py"
    spec = importlib.util.spec_from_file_location("rev_0001", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match="baseline: downgrade not allowed"):
        module.downgrade()


def _migrate(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "head")
    command.check(cfg)
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_migration_round_trip(tmp_path):
    previous = os.environ.get("DATABASE_URL")
    try:
        _migrate("sqlite:///" + (tmp_path / "mig.sqlite").as_posix())
        if os.environ.get("ANYQ_TEST_POSTGRES") == "1" and previous:
            parsed = make_url(previous)
            name = "m" + uuid4().hex[:12]
            admin = create_engine(
                parsed.set(database="postgres").render_as_string(hide_password=False),
                isolation_level="AUTOCOMMIT",
                future=True,
            )
            with admin.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
            admin.dispose()
            _migrate(parsed.set(database=name).render_as_string(hide_password=False))
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def test_one_invitation_accepts_once(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    import app.store as store_module

    store = MemoryStore()
    owner, _token = _register(store)
    previous = store_module.store
    store_module.store = store
    outcomes: list[str] = []
    try:
        created = create_invitation(owner, "foreman", None)
        barrier = threading.Barrier(20)
        guard = threading.Lock()

        def once(index: int) -> None:
            body = type(
                "Body",
                (),
                {
                    "email": f"person{index}@example.com",
                    "password": "secret12",
                    "full_name": "Aigul Serik",
                    "phone": "+77015550101",
                    "consent_offer_pd": True,
                },
            )()
            barrier.wait()
            try:
                accept(created["token"], body)
                kind = "ok"
            except InvitationClosed:
                kind = "closed"
            with guard:
                outcomes.append(kind)

        threads = [threading.Thread(target=once, args=(index,)) for index in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        store_module.store = previous
    assert outcomes.count("ok") == 1
    assert outcomes.count("closed") == 19
    with store._sql.factory() as session:
        users = session.execute(text("SELECT count(*) FROM records WHERE collection = 'users'")).scalar()
    assert users == 2


def _loadtest():
    path = Path(__file__).resolve().parents[1] / "scripts" / "loadtest.py"
    spec = importlib.util.spec_from_file_location("anyq_loadtest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_two_workers_see_each_other(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    writer = MemoryStore()
    reader = MemoryStore()
    before = int(writer._sql.revisions().get("rev", 0))
    loads = reader._sql.full_loads
    base = deepcopy(PLOTS[0])
    written: list[str] = []
    guard = threading.Lock()
    finished: queue.Queue[int] = queue.Queue()

    def batch(index: int) -> None:
        ids: list[str] = []
        for number in range(50):
            plot = base.model_copy(deep=True)
            plot.id = f"plot-w-{index}-{number}"
            plot.owner_id = "u-bench"
            plot.title_ru = "черновик"
            writer._enter()
            try:
                writer.plots[plot.id] = plot
                writer._save_unlocked()
                writer.plots[plot.id] = plot.model_copy(update={"title_ru": f"ТОО Тест {index}-{number}"})
                writer._save_unlocked()
            finally:
                writer._leave()
            ids.append(plot.id)
        with guard:
            written.extend(ids)
        finished.put(index)

    threads = [threading.Thread(target=batch, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for _ in range(4):
        finished.get(timeout=120)
        reader._enter()
        try:
            with guard:
                ids = list(written)
            for doc_id in ids:
                assert reader.plots[doc_id].title_ru.startswith("ТОО Тест")
        finally:
            reader._leave()
    for thread in threads:
        thread.join()
    assert len(written) == 200
    assert reader._sql.full_loads == loads
    after = int(reader._sql.revisions().get("rev", 0))
    assert after - before == 400


def test_concurrent_update_conflict(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    first = MemoryStore()
    req = ProcRequest(
        id="req-test-1",
        project_id="pr-test",
        number=1,
        title="ТОО Тест заявка",
        status="draft",
        created_at="2026-10-20T00:00:00+00:00",
        created_by="u-test",
    )
    first.proc_requests[req.id] = req
    first._save()
    second = MemoryStore()
    first.proc_requests[req.id] = req.model_copy(update={"status": "collecting"})
    second.proc_requests[req.id] = req.model_copy(update={"status": "decided"})
    first._save()
    with pytest.raises(ChangedByOther):
        second._save()
    response = app.exception_handlers[ChangedByOther](None, ChangedByOther())
    assert response.status_code == 409
    assert json.loads(response.body)["code"] == "conflict"
    with first._sql.factory() as session:
        row = session.get(Record, ("proc_requests", req.id))
        assert row is not None
        assert int(row.row_version) == 2
        assert row.payload["status"] == "collecting"
    fresh = MemoryStore()
    assert fresh.proc_requests[req.id].status == "collecting"
    left = MemoryStore()
    right = MemoryStore()
    created = req.model_copy(update={"id": "req-test-2", "number": 2, "title": "ТОО Тест новая"})
    left.proc_requests[created.id] = created
    right.proc_requests[created.id] = created.model_copy(update={"status": "collecting"})
    left._save()
    with pytest.raises(ChangedByOther):
        right._save()


def test_consents_append_only(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    store = MemoryStore()
    user, _token = store.register(
        RegisterBody(
            email="consent@example.com",
            password="secret12",
            full_name="Тест Пользователь",
            phone="+77000000001",
            company="ТОО Тест Согласие",
            company_bin="880000000099",
            role="buyer",
            consent_offer_pd=True,
        )
    )
    granted = [item for item in store.consents if item.user_id == user.id and item.type == "offer_pd"]
    assert len(granted) == 1
    store.revoke_consent(user, granted[0].id, ip="127.0.0.1", user_agent="test")
    again = ConsentRecord(
        id="c-regrant",
        user_id=user.id,
        type="offer_pd",
        text_version=PD_VERSION,
        text_sha256=pd_sha256(),
        granted_at="2026-10-20T01:00:00+00:00",
        action="grant",
        ip="127.0.0.1",
        user_agent="test",
        login=user.email,
    )
    store.consents.append(again)
    store._save()
    with store._sql.factory() as session:
        rows = session.execute(
            text("SELECT action FROM consent_events WHERE subject_user_id = :user_id ORDER BY id"),
            {"user_id": user.id},
        ).all()
    assert [row[0] for row in rows] == ["grant", "withdraw", "grant"]
    with pytest.raises(DatabaseError), store._sql.factory() as session:
        session.execute(text("DELETE FROM consent_events"))
        session.commit()
    with pytest.raises(DatabaseError), store._sql.factory() as session:
        session.execute(text("UPDATE consent_events SET action = 'grant'"))
        session.commit()
    with store._sql.factory() as session:
        count = session.execute(
            text("SELECT count(*) FROM consent_events WHERE subject_user_id = :user_id"),
            {"user_id": user.id},
        ).scalar()
    assert count == 3
    fresh = MemoryStore()
    latest = fresh._latest_consent(user.id, "offer_pd", PD_VERSION)
    assert latest is not None
    assert latest.id == "c-regrant"
    assert latest.action == "grant"


def test_invite_single_use_parallel(tmp_path, monkeypatch):
    _isolated(monkeypatch, tmp_path)
    import app.store as store_module

    store = MemoryStore()
    owner, _token = store.register(
        RegisterBody(
            email="owner.invite@example.com",
            password="secret12",
            full_name="Тест Владелец",
            phone="+77000000002",
            company="ТОО Тест Приглашение",
            company_bin="880000000098",
            role="buyer",
            consent_offer_pd=True,
        )
    )
    previous = store_module.store
    store_module.store = store
    try:
        created = create_invitation(owner, "foreman", None)
        barrier = threading.Barrier(20)
        guard = threading.Lock()
        codes: list[int] = []
        closed: list[str] = []

        def once(index: int) -> None:
            barrier.wait()
            with TestClient(app) as client:
                response = client.post(
                    f"/v1/invitations/token/{created['token']}/accept",
                    json={
                        "email": f"person{index}@example.com",
                        "password": "secret12",
                        "full_name": "Тест Пользователь",
                        "phone": f"+770000000{index:02d}",
                        "consent_offer_pd": True,
                    },
                )
            with guard:
                codes.append(response.status_code)
                if response.status_code == 410:
                    closed.append(response.json()["code"])

        threads = [threading.Thread(target=once, args=(index,)) for index in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert codes.count(200) == 1
        assert codes.count(410) == 19
        assert closed.count("used") == 19
        with store._sql.factory() as session:
            users = session.execute(text("SELECT count(*) FROM records WHERE collection = 'users'")).scalar()
        assert users == 2

        expired = create_invitation(owner, "supervisor", None)
        past = (datetime.now(UTC) - timedelta(days=8)).isoformat(timespec="seconds")
        with store._sql.factory() as session:
            row = session.get(InvitationRow, expired["id"])
            assert row is not None
            row.expires_at = past
            session.commit()
        with TestClient(app) as client:
            stale = client.post(
                f"/v1/invitations/token/{expired['token']}/accept",
                json={
                    "email": "late@example.com",
                    "password": "secret12",
                    "full_name": "Тест Пользователь",
                    "phone": "+77000000021",
                    "consent_offer_pd": True,
                },
            )
        assert stale.status_code == 410
        assert stale.json()["code"] == "expired"

        revoked = create_invitation(owner, "procurement", None)
        revoke(owner, revoked["id"])
        with TestClient(app) as client:
            gone = client.post(
                f"/v1/invitations/token/{revoked['token']}/accept",
                json={
                    "email": "revoked@example.com",
                    "password": "secret12",
                    "full_name": "Тест Пользователь",
                    "phone": "+77000000022",
                    "consent_offer_pd": True,
                },
            )
        assert gone.status_code == 410
        assert gone.json()["code"] == "revoked"
        with store._sql.factory() as session:
            users = session.execute(text("SELECT count(*) FROM records WHERE collection = 'users'")).scalar()
        assert users == 2
    finally:
        store_module.store = previous


def test_reload_p50_does_not_grow_with_db_size(tmp_path, monkeypatch):
    measure = _loadtest().measure_reload_p50
    _isolated(monkeypatch, tmp_path / "small")
    small = measure(500)
    _isolated(monkeypatch, tmp_path / "big")
    big = measure(5000)
    assert big <= small * 1.2 + 8, {"p50_500": small, "p50_5000": big}


def test_production_start_does_not_create_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "empty.sqlite").as_posix())
    monkeypatch.setenv("ANYQ_DB_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    from app.sql_backend import SqlRuntime

    runtime = SqlRuntime()
    try:
        names = set(inspect(runtime.engine).get_table_names())
    finally:
        runtime.engine.dispose()
    assert "records" not in names
    assert "consent_events" not in names
    fresh = MemoryStore()
    try:
        names = set(inspect(fresh._sql.engine).get_table_names())
    finally:
        fresh._sql.engine.dispose()
    assert "records" not in names


def test_ready_is_unavailable_until_schema_head(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_ENV", "production")
    from app.sql_backend import SqlRuntime
    from app.store import store

    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "empty.sqlite").as_posix())
    empty = SqlRuntime()
    monkeypatch.setattr(store, "_sql", empty)
    with TestClient(app) as client:
        closed = client.get("/ready")
    empty.engine.dispose()
    assert closed.status_code == 503
    assert closed.json()["ok"] is False

    migrated = "sqlite:///" + (tmp_path / "migrated.sqlite").as_posix()
    _alembic(migrated)
    ready = SqlRuntime()
    monkeypatch.setattr(store, "_sql", ready)
    with TestClient(app) as client:
        opened = client.get("/ready")
    ready.engine.dispose()
    assert opened.status_code == 200
    assert opened.json()["ok"] is True
