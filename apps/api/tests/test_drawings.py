"""Drawing sheets: tenant isolation, one current revision, and cleaned PDF files."""

import io
import os
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.company_features import project_company_id
from app.drawing_models import DrawingRevisionRow
from app.drawings import MAX_PDF_BYTES
from app.main import app
from app.store import store

client = TestClient(app)
BIN_A = "510000000001"
BIN_B = "510000000002"
BIN_C = "510000000003"


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")


def _pdf(author: str = "SYNTH-AUTHOR-77") -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=240, height=160)
    writer.add_metadata({"/Author": author, "/Title": "Plan"})
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _register(email: str, bin_no: str, role: str = "buyer"):
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77010000001",
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


def _promote(email: str, role: str) -> None:
    user = store.get_user_by_email(email)
    assert user is not None
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    store._save()


def _project(token: str, title: str) -> str:
    res = client.post(
        "/v1/site/projects",
        json={"title": title, "address": "Test street 1"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


def _enable(token: str) -> None:
    res = client.post(
        "/v1/org/features",
        json={"key": "drawings", "enabled": True, "row_version": 0},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


def _upload(token: str, pid: str, **extra) -> object:
    drawing_id = extra.pop("id", str(uuid4()))
    fields = {
        "id": drawing_id,
        "revision_id": extra.pop("revision_id", str(uuid4())),
        "file_id": extra.pop("file_id", str(uuid4())),
        "title": extra.pop("title", "Level plan"),
        "row_version": extra.pop("row_version", "0"),
    }
    fields.update(extra)
    return client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(token),
        data=fields,
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )


def test_foreign_company_is_hidden_on_read_write_file_and_link(monkeypatch):
    owner = _register("draw-owner@example.com", BIN_A)
    _promote("draw-owner@example.com", "owner")
    other = _register("draw-other@example.com", BIN_B)
    _promote("draw-other@example.com", "owner")
    buyer = _register("draw-buyer@example.com", BIN_A)
    tech = _register("draw-tech@example.com", BIN_C)
    crew = _register("draw-crew@example.com", BIN_C)
    _promote("draw-crew@example.com", "foreman")
    pid = _project(owner["token"], "North yard")
    other_pid = _project(other["token"], "South yard")
    closed = _upload(owner["token"], pid)
    assert closed.status_code == 404, closed.text
    opened = client.get(
        f"/v1/site/projects/{pid}/drawing-sheets?pid={other_pid}",
        headers=_auth(owner["token"]),
    )
    assert opened.status_code == 404, opened.text

    _enable(owner["token"])
    _enable(other["token"])
    added = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "draw-tech@example.com", "role": "supervisor"},
        headers=_auth(owner["token"]),
    )
    assert added.status_code == 200, added.text
    blocked = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "draw-buyer@example.com", "role": "procurement"},
        headers=_auth(owner["token"]),
    )
    assert blocked.status_code == 200, blocked.text

    created = _upload(owner["token"], pid, company_id="bin:999999999999", title="Call +77019990000")
    assert created.status_code == 200, created.text
    sheet = created.json()["data"]
    assert sheet["id"]
    assert sheet["company_id"] == project_company_id(store.get_project(pid))
    assert sheet["company_id"] != "bin:999999999999"
    assert sheet["row_version"] == 1
    assert sheet["deleted_at"] is None
    assert sheet["updated_at"].endswith("+00:00")
    assert sheet["revisions"][0]["is_current"] is True
    assert sheet["revisions"][0]["file_id"]
    assert "storage_key" not in created.text
    assert "/private" not in created.text
    assert "SYNTH-AUTHOR" not in created.text

    body = client.get(f"/v1/site/drawings/{sheet['id']}/file", headers=_auth(owner["token"]))
    assert body.status_code == 200, body.text
    assert body.content.startswith(b"%PDF-")
    assert b"SYNTH-AUTHOR-77" not in body.content

    foreign_read = client.get(
        f"/v1/site/drawings/{sheet['id']}?pid={other_pid}&rev=A",
        headers=_auth(other["token"]),
    )
    assert foreign_read.status_code == 404, foreign_read.text
    foreign_write = _upload(other["token"], pid)
    assert foreign_write.status_code == 404, foreign_write.text
    foreign_file = client.get(
        f"/v1/site/drawings/{sheet['id']}/file?pid={other_pid}",
        headers=_auth(other["token"]),
    )
    assert foreign_file.status_code == 404, foreign_file.text
    foreign_link = client.get(
        f"/v1/files/{sheet['revisions'][0]['file_id']}?pid={other_pid}",
        headers=_auth(other["token"]),
    )
    assert foreign_link.status_code == 404, foreign_link.text
    same = client.get(
        f"/v1/site/drawings/{sheet['id']}?pid={other_pid}",
        headers=_auth(owner["token"]),
    )
    assert same.status_code == 200, same.text
    assert same.json()["data"]["project_id"] == pid

    buyer_write = _upload(buyer["token"], pid)
    assert buyer_write.status_code == 403, buyer_write.text
    tech_sheet = _upload(tech["token"], pid, title="Supervision copy")
    assert tech_sheet.status_code == 200, tech_sheet.text
    seated = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "draw-crew@example.com", "role": "foreman"},
        headers=_auth(owner["token"]),
    )
    assert seated.status_code == 200, seated.text
    crew_sheet = _upload(crew["token"], pid, title="Crew copy")
    assert crew_sheet.status_code == 403, crew_sheet.text

    monkeypatch.setattr("app.drawings.MAX_PDF_BYTES", 64)
    tiny = client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "revision_id": str(uuid4()), "file_id": str(uuid4()), "row_version": "0"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert tiny.status_code == 413, tiny.text
    monkeypatch.setattr("app.drawings.MAX_PDF_BYTES", MAX_PDF_BYTES)
    plain = client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "revision_id": str(uuid4()), "file_id": str(uuid4()), "row_version": "0"},
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert plain.status_code == 400, plain.text


def test_new_revision_becomes_current_and_conflict_is_409():
    owner = _register("draw-rev@example.com", "510000000004")
    _promote("draw-rev@example.com", "owner")
    pid = _project(owner["token"], "Revision yard")
    _enable(owner["token"])
    created = _upload(owner["token"], pid, rev="A")
    assert created.status_code == 200, created.text
    sheet = created.json()["data"]
    again = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions?pid=prj-ignored",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": "A", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert again.status_code == 409, again.text
    nxt = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": "B", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert nxt.status_code == 200, nxt.text
    body = nxt.json()["data"]
    assert body["row_version"] == 2
    assert body["current_rev"] == "B"
    archived = {item["rev"]: item["is_current"] for item in body["revisions"]}
    assert archived == {"A": False, "B": True}
    stale = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": "C", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert stale.status_code == 409, stale.text
    fresh = client.get(f"/v1/site/drawings/{sheet['id']}?rev=A", headers=_auth(owner["token"]))
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["data"]["newer"] is True
    assert fresh.json()["data"]["current_rev"] == "B"
    with store._sql.factory() as session:
        extra = DrawingRevisionRow(
            id=str(uuid4()),
            company_id=body["company_id"],
            project_id=pid,
            drawing_id=sheet["id"],
            rev="Z",
            file_id=body["revisions"][-1]["file_id"],
            is_current=True,
            uploaded_by="u-test",
            uploaded_at="2026-10-19T00:00:00+00:00",
            created_at="2026-10-19T00:00:00+00:00",
            updated_at="2026-10-19T00:00:00+00:00",
            row_version=1,
            deleted_at=None,
        )
        session.add(extra)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        audit = session.execute(
            text("SELECT event, changes FROM audit_log WHERE entity_id = :id"),
            {"id": sheet["revisions"][0]["id"]},
        ).first()
    assert audit is not None
    assert audit.event == "drawing.upload"
    assert "7701" not in (audit.changes or "")
    assert "storage_key" not in (audit.changes or "")


def test_alembic_drawing_revision_roundtrip(tmp_path):
    db = tmp_path / "drawings.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    root = os.path.join(os.path.dirname(__file__), "..")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "downgrade", "-1"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "check"], cwd=root, env=env)
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"files", "drawing_sets", "drawings", "drawing_revisions"} <= tables
    indexes = {
        row[0]: row[1] or ""
        for row in connection.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")
    }
    assert "WHERE is_current = 1 AND deleted_at IS NULL" in indexes["ux_drawing_current"]
    columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= columns
    connection.close()
