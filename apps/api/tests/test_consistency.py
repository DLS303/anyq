import importlib.util
import os
import threading
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import DatabaseError

from alembic import command
from app.invitations import InvitationClosed, accept, create_invitation
from app.schemas import RegisterBody
from app.seed import PLOTS
from app.sql_backend import ChangedByOther
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
    with pytest.raises(RuntimeError, match="baseline revision cannot be downgraded"):
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
