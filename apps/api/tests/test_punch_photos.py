"""Photo punch items: path-only access, status rules, and stripped files."""

import io
import json
import os
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text

from app.audit import write as audit_write
from app.company_features import project_company_id, resolve_path_company
from app.tenant import company_key
from app.main import app
from app.punch_photos import PUSH_TEXT, legacy_punch_id, migrate_status
from app.site_models import PunchItem
from app.store import store

client = TestClient(app)


def _bin(seed: int) -> str:
    return f"{seed:012d}"


def _register(email: str, bin_no: str, name: str = "Casey North"):
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": name,
            "phone": "+77005550001",
            "company": "Northwind Test LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _promote(email: str, role: str = "owner"):
    user = store.get_user_by_email(email)
    assert user is not None
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    return updated


def _jpeg(artist: str = "", color: str = "red") -> bytes:
    image = Image.new("RGB", (24, 16), color)
    buffer = io.BytesIO()
    if artist:
        exif = image.getexif()
        exif[315] = artist
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _enable(token: str):
    opened = client.post(
        "/v1/org/features",
        json={"key": "punch_photos", "enabled": True, "row_version": 0},
        headers=_auth(token),
    )
    assert opened.status_code == 200, opened.text


def _project(token: str, title: str) -> str:
    created = client.post(
        "/v1/site/projects",
        json={"title": title, "address": "1 Test quay"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


def _world(monkeypatch, seed: int, *, flag: bool = True):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner_email = f"punch-owner-{seed}@example.com"
    other_email = f"punch-other-{seed}@example.com"
    owner = _register(owner_email, _bin(seed))
    _promote(owner_email, "owner")
    other = _register(other_email, _bin(seed + 1), name="Zvenislava Petrova")
    if flag:
        _enable(owner["token"])
    pid = _project(owner["token"], f"Warehouse {seed}")
    return owner, other, pid


def _create(token: str, pid: str, **extra) -> dict:
    body = {"id": str(uuid4()), "title": "Crack in the slab", "location": "bay 2", "trade": "concrete"}
    body.update(extra)
    res = client.post(f"/v1/site/projects/{pid}/punch-items", json=body, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _photo(token: str, pid: str, item: dict, phase: str = "before") -> dict:
    res = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/photos",
        data={"phase": phase, "row_version": str(item["row_version"]), "id": str(uuid4()), "file_id": str(uuid4())},
        files={"file": ("shot.jpg", _jpeg("SecretArtist"), "image/jpeg")},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_audit_write_masks_contact_fields():
    with store._sql.factory() as session:
        audit_write(
            "punch.status_change",
            "punch_item",
            "00000000-0000-4000-8000-000000000099",
            "prj-mask",
            {"from": "open", "to": "fixed", "name": "Ada Lovelace", "phone": "+77005550001"},
            session=session,
            company_id="bin:610000000099",
            actor_user_id="u-mask",
        )
        session.commit()
        raw = session.execute(
            text("SELECT changes FROM audit_log WHERE entity_id = :id"),
            {"id": "00000000-0000-4000-8000-000000000099"},
        ).scalar()
    payload = raw if isinstance(raw, dict) else json.loads(raw)
    assert payload["from"] == "open"
    assert payload["to"] == "fixed"
    assert payload["name"] == "***"
    assert payload["phone"] == "***"
    assert migrate_status("ready") == "fixed"
    assert migrate_status("closed") == "accepted"


def test_flag_off_hides_new_routes_and_keeps_the_pilot_punch(monkeypatch):
    owner, _other, pid = _world(monkeypatch, 610000000101, flag=False)
    hidden = client.get(f"/v1/site/projects/{pid}/punch-items", headers=_auth(owner["token"]))
    assert hidden.status_code == 404
    write = client.post(
        f"/v1/site/projects/{pid}/punch-items",
        json={"id": str(uuid4()), "title": "Hidden"},
        headers=_auth(owner["token"]),
    )
    assert write.status_code == 404
    pilot = client.post(
        f"/v1/site/projects/{pid}/punches",
        json={"title": "Pilot crack"},
        headers=_auth(owner["token"]),
    )
    assert pilot.status_code == 200, pilot.text
    moved = client.post(
        f"/v1/site/punches/{pilot.json()['data']['id']}/status",
        json={"status": "ready"},
        headers=_auth(owner["token"]),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["status"] == "ready"


def test_query_pid_does_not_bypass_the_gate(monkeypatch):
    owner_a, _other, pid_a = _world(monkeypatch, 610000000201, flag=False)
    owner_b = _register("punch-b-201@example.com", _bin(610000000301))
    _promote("punch-b-201@example.com", "owner")
    _enable(owner_b["token"])
    pid_b = _project(owner_b["token"], "Other warehouse 201")
    blocked = client.get(
        f"/v1/site/projects/{pid_a}/punch-items?pid={pid_b}",
        headers=_auth(owner_a["token"]),
    )
    assert blocked.status_code == 404
    foreign = client.get(
        f"/v1/site/projects/{pid_a}/punch-items?pid={pid_b}",
        headers=_auth(owner_b["token"]),
    )
    assert foreign.status_code == 404
    opened = client.get(
        f"/v1/site/projects/{pid_b}/punch-items?pid={pid_a}",
        headers=_auth(owner_b["token"]),
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["data"] == []


def test_foreign_company_is_404_on_read_write_file_and_link(monkeypatch):
    owner, foreign, pid = _world(monkeypatch, 610000000401)
    item = _create(owner["token"], pid, title="Leak +77005550999")
    item = _photo(owner["token"], pid, item, "before")
    file_id = item["photos_before"][0]
    headers = _auth(foreign["token"])
    assert client.get(f"/v1/site/projects/{pid}/punch-items", headers=headers).status_code == 404
    assert (
        client.post(
            f"/v1/site/projects/{pid}/punch-items",
            json={"id": str(uuid4()), "title": "Nope"},
            headers=headers,
        ).status_code
        == 404
    )
    assert client.get(f"/v1/site/projects/{pid}/punch-items/{item['id']}/files/{file_id}", headers=headers).status_code == 404
    assert client.get(f"/v1/site/projects/{pid}/punch-items/{item['id']}/link", headers=headers).status_code == 404
    own_file = client.get(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/files/{file_id}",
        headers=_auth(owner["token"]),
    )
    assert own_file.status_code == 200, own_file.text
    assert b"SecretArtist" not in own_file.content
    opened = Image.open(io.BytesIO(own_file.content))
    assert 315 not in opened.getexif()
    link = client.get(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/link",
        headers=_auth(owner["token"]),
    )
    assert link.status_code == 200
    assert link.json()["data"]["href"].endswith(f"/punch-items/{item['id']}")


def test_status_rules_version_and_audit(monkeypatch):
    owner, _foreign, pid = _world(monkeypatch, 610000000501)
    foreman = _register("punch-foreman-501@example.com", _bin(610000000501), name="Foreman Example")
    supervisor = _register("punch-super-501@example.com", _bin(610000000501), name="Supervisor Example")
    _promote("punch-foreman-501@example.com", "foreman")
    added_f = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "punch-foreman-501@example.com", "role": "foreman"},
        headers=_auth(owner["token"]),
    )
    assert added_f.status_code == 200, added_f.text
    added_s = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "punch-super-501@example.com", "role": "supervisor"},
        headers=_auth(owner["token"]),
    )
    assert added_s.status_code == 200, added_s.text
    item = _create(owner["token"], pid, assignee_id=foreman["user"]["id"], due_date="2020-01-02")
    owner_user = store.get_user(owner["user"]["id"])
    stored = company_key(owner_user)
    assert item["company_id"] == stored
    assert item["company_id"] == project_company_id(store.get_project(pid))
    assert resolve_path_company("projects", pid, owner_user) == stored
    assert item["company_id"].startswith("bin:")
    assert item["row_version"] == 1
    assert item["created_at"].endswith("+00:00")
    assert item["push"] == {"text": PUSH_TEXT, "id": item["id"]}
    assert "Crack" not in json.dumps(item["push"])
    skip = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "accepted", "row_version": item["row_version"]},
        headers=_auth(owner["token"]),
    )
    assert skip.status_code == 409
    no_photo = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "fixed", "row_version": item["row_version"]},
        headers=_auth(foreman["token"]),
    )
    assert no_photo.status_code == 409
    item = _photo(foreman["token"], pid, item, "after")
    fixed = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "fixed", "row_version": item["row_version"]},
        headers=_auth(foreman["token"]),
    )
    assert fixed.status_code == 200, fixed.text
    fixed_body = fixed.json()["data"]
    assert fixed_body["status"] == "fixed"
    denied = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "accepted", "row_version": fixed_body["row_version"]},
        headers=_auth(foreman["token"]),
    )
    assert denied.status_code == 403
    stale = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "accepted", "row_version": item["row_version"]},
        headers=_auth(owner["token"]),
    )
    assert stale.status_code == 409
    accepted = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/status",
        json={"status": "returned", "row_version": fixed_body["row_version"]},
        headers=_auth(supervisor["token"]),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "returned"
    with store._sql.factory() as session:
        rows = session.execute(
            text("SELECT changes FROM audit_log WHERE action = 'punch.status_change' AND entity_id = :id"),
            {"id": item["id"]},
        ).all()
    parts = []
    for row in rows:
        value = row[0]
        parts.append(value if isinstance(value, str) else json.dumps(value or {}))
    blob = " ".join(parts)
    assert "Crack" not in blob
    assert "+7700" not in blob
    assert "Foreman" not in blob
    listed = client.get(f"/v1/site/projects/{pid}/punch-items?overdue=1", headers=_auth(owner["token"]))
    assert listed.status_code == 200
    assert any(row["id"] == item["id"] and row["overdue"] for row in listed.json()["data"])
    mine = client.get(
        f"/v1/site/projects/{pid}/punch-items?mine=1",
        headers=_auth(foreman["token"]),
    )
    assert mine.status_code == 200
    assert [row["id"] for row in mine.json()["data"]] == [item["id"]]


def test_legacy_status_migration_does_not_change_the_pilot_row(monkeypatch):
    owner, _foreign, pid = _world(monkeypatch, 610000000601)
    legacy = PunchItem(
        id="pu-synthetic-601",
        project_id=pid,
        title="Loose tile",
        location="stair",
        trade="finish",
        status="ready",
        created_at="2026-10-01T00:00:00+00:00",
    )
    store.punches[legacy.id] = legacy
    listed = client.get(f"/v1/site/projects/{pid}/punch-items", headers=_auth(owner["token"]))
    assert listed.status_code == 200, listed.text
    copied = [row for row in listed.json()["data"] if row["id"] == legacy_punch_id(pid, legacy.id)]
    assert copied and copied[0]["status"] == "fixed"
    assert store.punches[legacy.id].status == "ready"
    again = client.get(f"/v1/site/projects/{pid}/punch-items", headers=_auth(owner["token"]))
    assert sum(1 for row in again.json()["data"] if row["title"] == "Loose tile") == 1


def test_pdf_has_no_author_names_or_phones(monkeypatch):
    owner, _foreign, pid = _world(monkeypatch, 610000000701)
    _create(owner["token"], pid, title="Call +77005550777 about the leak")
    pdf = client.get(f"/v1/site/projects/{pid}/punch-items.pdf", headers=_auth(owner["token"]))
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    body = pdf.content
    assert b"/Author" not in body
    assert b"Zvenislava" not in body
    assert b"77005550777" not in body
    assert b"Casey" not in body
    foreign = client.get(f"/v1/site/projects/{pid}/punch-items.pdf", headers=_auth(_foreign["token"]))
    assert foreign.status_code == 404


def test_client_uuid_company_and_tombstone(monkeypatch):
    owner, _foreign, pid = _world(monkeypatch, 610000000801)
    bad = client.post(
        f"/v1/site/projects/{pid}/punch-items",
        json={"id": "pu-short", "title": "Bad id", "company_id": "bin:000000000000"},
        headers=_auth(owner["token"]),
    )
    assert bad.status_code == 400
    item = _create(owner["token"], pid)
    assert item["company_id"] != "bin:000000000000"
    removed = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/delete",
        json={"row_version": item["row_version"]},
        headers=_auth(owner["token"]),
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["deleted_at"]
    listed = client.get(f"/v1/site/projects/{pid}/punch-items", headers=_auth(owner["token"]))
    assert all(row["id"] != item["id"] for row in listed.json()["data"])
    missing = client.get(f"/v1/site/projects/{pid}/punch-items/{item['id']}", headers=_auth(owner["token"]))
    assert missing.status_code == 404


def test_reused_file_id_does_not_change_stored_bytes(monkeypatch):
    owner, foreign, pid = _world(monkeypatch, 610000000901)
    item = _create(owner["token"], pid)
    file_id = str(uuid4())
    first = client.post(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/photos",
        data={"phase": "before", "row_version": str(item["row_version"]), "id": str(uuid4()), "file_id": file_id},
        files={"file": ("shot.jpg", _jpeg(color="red"), "image/jpeg")},
        headers=_auth(owner["token"]),
    )
    assert first.status_code == 200, first.text
    original = client.get(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/files/{file_id}",
        headers=_auth(owner["token"]),
    )
    assert original.status_code == 200
    saved = original.content

    _promote("punch-other-610000000901@example.com", "owner")
    _enable(foreign["token"])
    other_pid = _project(foreign["token"], "Other yard 901")
    other_item = _create(foreign["token"], other_pid)
    foreign_upload = client.post(
        f"/v1/site/projects/{other_pid}/punch-items/{other_item['id']}/photos",
        data={
            "phase": "before",
            "row_version": str(other_item["row_version"]),
            "id": str(uuid4()),
            "file_id": file_id,
        },
        files={"file": ("other.jpg", _jpeg(color="blue"), "image/jpeg")},
        headers=_auth(foreign["token"]),
    )
    assert foreign_upload.status_code == 409, foreign_upload.text

    same = _create(owner["token"], pid, title="Second crack")
    again = client.post(
        f"/v1/site/projects/{pid}/punch-items/{same['id']}/photos",
        data={"phase": "before", "row_version": str(same["row_version"]), "id": str(uuid4()), "file_id": file_id},
        files={"file": ("again.jpg", _jpeg(color="green"), "image/jpeg")},
        headers=_auth(owner["token"]),
    )
    assert again.status_code == 409, again.text
    reread = client.get(
        f"/v1/site/projects/{pid}/punch-items/{item['id']}/files/{file_id}",
        headers=_auth(owner["token"]),
    )
    assert reread.status_code == 200
    assert reread.content == saved

    from app.punch_photos import FileRow, PunchItemRow

    with store._sql.factory() as session:
        row = session.get(FileRow, file_id)
        punch = session.get(PunchItemRow, item["id"])
        assert row is not None and punch is not None
        assert file_id not in (row.storage_key or "")
        assert row.created_by == owner["user"]["id"]
        assert row.updated_by == owner["user"]["id"]
        assert punch.created_by == owner["user"]["id"]
        assert punch.updated_by == owner["user"]["id"]


def test_alembic_upgrade_downgrade_upgrade(tmp_path):
    db = tmp_path / "punch.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    cwd = os.path.join(os.path.dirname(__file__), "..")

    def run(*args: str):
        subprocess.check_call([sys.executable, "-m", "alembic", *args], cwd=cwd, env=env)

    run("upgrade", "head")
    run("downgrade", "-1")
    run("upgrade", "head")
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"punch_items", "punch_photos", "files"} <= tables
    columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= columns
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_punch_items_project_status_due" in indexes
    assert "ix_punch_items_assignee_status" in indexes
    assert "ix_punch_items_company_updated" in indexes
    assert "ix_punch_photos_file_id" in indexes
    for table in ("files", "punch_items", "punch_photos"):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        assert {"created_by", "updated_by"} <= columns
    connection.close()

