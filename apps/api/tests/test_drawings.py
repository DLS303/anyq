"""Drawing sheets: tenant isolation, one current revision, and cleaned PDF files."""

import io
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.company_features import project_company_id
from app.drawing_models import DrawingRevisionRow, StoredFile
from app.drawings import MAX_PDF_BYTES, LegacyDrawingsClosed, reconcile_drawing_files
from app.main import app
from app.paths import kind_root, publish_upload, resolve_stored_file, stage_upload
from app.site_models import Drawing
from app.store import store

client = TestClient(app)
BIN_A = "510000000001"
BIN_B = "510000000002"
BIN_C = "510000000003"


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")


def _pdf(author: str = "SYNTH-AUTHOR-77", width: float = 240) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=160)
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
    """Move the single site-owner slot, then store the new role.

    records.status is 'owner' for at most one users row. Demote the current
    site owner and commit that before assigning the slot again.
    """
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


@pytest.fixture(autouse=True)
def _restore_demo_owner():
    yield
    demo = store.get_user("u-owner")
    if demo is not None and demo.role != "owner":
        _promote(demo.email, "owner")


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
    width = extra.pop("width", None)
    fields.update(extra)
    payload = _pdf(width=width) if width else _pdf()
    return client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(token),
        data=fields,
        files={"file": ("level.pdf", payload, "application/pdf")},
    )


def test_foreign_company_is_hidden_on_read_write_file_and_link(monkeypatch):
    owner = _register("draw-owner@example.com", BIN_A)
    other = _register("draw-other@example.com", BIN_B)
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

    _promote("draw-owner@example.com", "owner")
    _enable(owner["token"])
    _promote("draw-other@example.com", "owner")
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
            text("SELECT action, changes FROM audit_log WHERE entity_id = :id"),
            {"id": sheet["revisions"][0]["id"]},
        ).first()
    assert audit is not None
    assert audit.action == "drawing.upload"
    assert "7701" not in (audit.changes or "")
    assert "storage_key" not in (audit.changes or "")


def test_reused_file_id_leaves_the_other_file_unchanged():
    owner = _register("draw-file-a@example.com", "510000000011")
    other = _register("draw-file-b@example.com", "510000000012")
    pid = _project(owner["token"], "File yard")
    other_pid = _project(other["token"], "Other file yard")
    _promote("draw-file-a@example.com", "owner")
    _enable(owner["token"])
    _promote("draw-file-b@example.com", "owner")
    _enable(other["token"])
    shared = str(uuid4())
    created = _upload(owner["token"], pid, file_id=shared)
    assert created.status_code == 200, created.text
    sheet = created.json()["data"]
    original = client.get(f"/v1/site/drawings/{sheet['id']}/file", headers=_auth(owner["token"]))
    assert original.status_code == 200, original.text
    with store._sql.factory() as session:
        stored = session.get(StoredFile, shared)
    assert stored is not None
    assert shared not in stored.storage_key
    on_disk = resolve_stored_file(stored.kind, stored.storage_key).read_bytes()
    assert on_disk == original.content

    foreign = _upload(other["token"], other_pid, file_id=shared, width=320)
    assert foreign.status_code == 409, foreign.text
    assert not list(kind_root("drawing_pdf").glob(".part-*"))
    again = client.get(f"/v1/site/drawings/{sheet['id']}/file", headers=_auth(owner["token"]))
    assert again.content == original.content
    assert resolve_stored_file(stored.kind, stored.storage_key).read_bytes() == on_disk

    reused = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "file_id": shared, "rev": "B", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(width=360), "application/pdf")},
    )
    assert reused.status_code == 409, reused.text
    assert not list(kind_root("drawing_pdf").glob(".part-*"))
    kept = client.get(f"/v1/site/drawings/{sheet['id']}/file", headers=_auth(owner["token"]))
    assert kept.content == original.content
    assert resolve_stored_file(stored.kind, stored.storage_key).read_bytes() == on_disk


def test_sheet_company_is_the_owner_stored_key():
    owner = _register("draw-key@example.com", "510000000015")
    _promote("draw-key@example.com", "owner")
    pid = _project(owner["token"], "Key yard")
    _enable(owner["token"])
    stored = project_company_id(store.get_project(pid))
    assert stored.startswith("bin:")
    with store._sql.factory() as session:
        session.execute(
            text("UPDATE records SET company_key = :key WHERE collection = 'projects' AND doc_id = :id"),
            {"key": "bin:000000000099", "id": pid},
        )
        session.commit()
    created = _upload(owner["token"], pid, title="Stored key")
    assert created.status_code == 200, created.text
    assert created.json()["data"]["company_id"] == stored
    assert created.json()["data"]["company_id"] != "bin:000000000099"


def test_sheet_can_join_an_existing_set():
    owner = _register("draw-set@example.com", "510000000013")
    _promote("draw-set@example.com", "owner")
    pid = _project(owner["token"], "Set yard")
    _enable(owner["token"])
    set_id = str(uuid4())
    first = _upload(owner["token"], pid, set_id=set_id, set_title="Plans", code="A1")
    assert first.status_code == 200, first.text
    second = _upload(owner["token"], pid, set_id=set_id, title="Section", code="A2")
    assert second.status_code == 200, second.text
    assert second.json()["data"]["set_id"] == set_id


def test_concurrent_revision_uploads():
    owner = _register("draw-race@example.com", "510000000014")
    _promote("draw-race@example.com", "owner")
    pid = _project(owner["token"], "Race yard")
    _enable(owner["token"])
    created = _upload(owner["token"], pid, rev="A")
    assert created.status_code == 200, created.text
    sheet = created.json()["data"]

    def send(rev: str):
        return client.post(
            f"/v1/site/drawings/{sheet['id']}/revisions",
            headers=_auth(owner["token"]),
            data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": rev, "row_version": "1"},
            files={"file": ("level.pdf", _pdf(), "application/pdf")},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        done = list(pool.map(send, ("B", "C")))
    assert sorted(item.status_code for item in done) == [200, 409]
    fresh = client.get(f"/v1/site/drawings/{sheet['id']}", headers=_auth(owner["token"]))
    assert fresh.status_code == 200, fresh.text
    current = [item for item in fresh.json()["data"]["revisions"] if item["is_current"]]
    assert len(current) == 1


def _feature(token: str, enabled: bool, row_version: int) -> dict:
    res = client.post(
        "/v1/org/features",
        json={"key": "drawings", "enabled": enabled, "row_version": row_version},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _quiet_drawing(drawing_id: str, previous: Drawing | None) -> None:
    bag = store.drawings
    bag._tracking = False
    if previous is None and dict.__contains__(bag, drawing_id):
        dict.__delitem__(bag, drawing_id)
    elif previous is not None:
        dict.__setitem__(bag, drawing_id, previous)
    bag._tracking = True
    bag.dirty.discard(drawing_id)
    bag.deleted.discard(drawing_id)


def _sheets(token: str, pid: str) -> list[dict]:
    res = client.get(f"/v1/site/projects/{pid}/drawing-sheets", headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]["sheets"]


def test_publish_oserror_removes_the_temp(monkeypatch):
    _key, tmp = stage_upload("drawing_pdf", b"%PDF-1.4\n")

    def boom(*_args, **_kwargs):
        raise PermissionError("no link")

    monkeypatch.setattr("app.paths.os.link", boom)
    with pytest.raises(PermissionError):
        publish_upload("drawing_pdf", f"{uuid4().hex}.pdf", tmp)
    assert not tmp.exists()
    assert tmp.name not in {path.name for path in kind_root("drawing_pdf").glob(".part-*")}


def test_stale_parts_and_missing_files_are_swept():
    _key, tmp = stage_upload("drawing_pdf", b"%PDF-1.4\n")
    os.utime(tmp, (0, 0))
    missing_id = str(uuid4())
    young_id = str(uuid4())
    with store._sql.factory() as session:
        session.add(
            StoredFile(
                id=missing_id,
                company_id="bin:510000000099",
                project_id="prj-sweep",
                storage_key=f"{uuid4().hex}.pdf",
                kind="drawing_pdf",
                mime="application/pdf",
                size_bytes=1,
                sha256="ab" * 32,
                meta_stripped=True,
                created_by="u",
                updated_by="u",
                created_at="2020-01-01T00:00:00+00:00",
                updated_at="2020-01-01T00:00:00+00:00",
                row_version=1,
                deleted_at=None,
            )
        )
        session.add(
            StoredFile(
                id=young_id,
                company_id="bin:510000000099",
                project_id="prj-sweep",
                storage_key=f"{uuid4().hex}.pdf",
                kind="drawing_pdf",
                mime="application/pdf",
                size_bytes=1,
                sha256="cd" * 32,
                meta_stripped=True,
                created_by="u",
                updated_by="u",
                created_at="2099-01-01T00:00:00+00:00",
                updated_at="2099-01-01T00:00:00+00:00",
                row_version=1,
                deleted_at=None,
            )
        )
        session.commit()
    result = reconcile_drawing_files()
    assert tmp.name in result["removed_parts"]
    assert missing_id in result["missing_files"]
    assert young_id not in result["missing_files"]
    assert not tmp.exists()


def test_enabling_drawings_imports_legacy_and_locks_writes():
    owner = _register("draw-legacy@example.com", "510000000021")
    _promote("draw-legacy@example.com", "owner")
    pid = _project(owner["token"], "Legacy yard")
    legacy_id = "dr-legacy-yard"
    first = Drawing(id=legacy_id, project_id=pid, code="L1", title="First plan", revision="A", current=True)
    store.drawings[legacy_id] = first
    store._save()
    enabled = _feature(owner["token"], True, 0)
    body = _sheets(owner["token"], pid)
    assert len(body) == 1
    assert body[0]["legacy_id"] == legacy_id
    assert body[0]["title"] == "First plan"
    assert body[0]["current_rev"] == "A"
    bundle = client.get(f"/v1/site/projects/{pid}/bundle", headers=_auth(owner["token"]))
    assert bundle.status_code == 200, bundle.text
    payload = bundle.json()["data"]
    assert [item["id"] for item in payload["drawings"]] == [item["id"] for item in body]
    assert payload["snapshot"]["counts"]["drawings"] == 1
    listed = client.get(f"/v1/site/projects/{pid}/drawings", headers=_auth(owner["token"]))
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["data"]] == [item["id"] for item in body]

    again = _feature(owner["token"], True, enabled["row_version"])
    repeat = _sheets(owner["token"], pid)
    assert [item["id"] for item in repeat] == [body[0]["id"]]
    assert repeat[0]["title"] == "First plan"
    assert repeat[0]["current_rev"] == "A"
    assert again["row_version"] == enabled["row_version"] + 1

    closed = _feature(owner["token"], False, again["row_version"])
    edited = first.model_copy(update={"title": "Second plan", "revision": "B"})
    store.drawings[legacy_id] = edited
    store._save()
    reopened = _feature(owner["token"], True, closed["row_version"])
    latest = _sheets(owner["token"], pid)
    assert len(latest) == 1
    assert latest[0]["id"] == body[0]["id"]
    assert latest[0]["title"] == "Second plan"
    assert latest[0]["current_rev"] == "B"

    _feature(owner["token"], True, reopened["row_version"])
    noop = _sheets(owner["token"], pid)
    assert len(noop) == 1
    assert noop[0]["id"] == body[0]["id"]
    assert noop[0]["title"] == "Second plan"
    assert noop[0]["current_rev"] == "B"

    store.drawings[legacy_id] = edited.model_copy(update={"title": "Third plan"})
    with pytest.raises(LegacyDrawingsClosed):
        store._save()
    _quiet_drawing(legacy_id, edited)
    assert _sheets(owner["token"], pid)[0]["title"] == "Second plan"


def _pages(count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(count):
        writer.add_blank_page(width=40, height=40)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _invite(token: str, pid: str, role: str, email: str) -> str:
    created = client.post(
        f"/v1/site/projects/{pid}/invitations",
        json={"role": role},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    accepted = client.post(
        f"/v1/invitations/token/{created.json()['data']['token']}/accept",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Site Member",
            "phone": "+77010000009",
            "consent_offer_pd": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    return accepted.json()["data"]["token"]


def test_revision_number_must_be_positive():
    owner = _register("draw-revno@example.com", "510000000041")
    _promote("draw-revno@example.com", "owner")
    pid = _project(owner["token"], "Number yard")
    _enable(owner["token"])
    for bad in ("0", "-1", "00", "-0"):
        rejected = _upload(owner["token"], pid, rev=bad)
        assert rejected.status_code == 422, rejected.text
        assert not list(kind_root("drawing_pdf").glob(".part-*"))
    kept = _upload(owner["token"], pid, rev="1")
    assert kept.status_code == 200, kept.text
    assert kept.json()["data"]["current_rev"] == "1"


def test_pdf_page_count_is_capped(monkeypatch):
    from app.pdf_clean import PdfPageLimitError, strip_pdf

    monkeypatch.setattr("app.pdf_clean.MAX_PDF_PAGES", 2)
    with pytest.raises(PdfPageLimitError, match="exceeds limit 2"):
        strip_pdf(_pages(3))
    owner = _register("draw-pages@example.com", "510000000042")
    _promote("draw-pages@example.com", "owner")
    pid = _project(owner["token"], "Page yard")
    _enable(owner["token"])
    res = client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "revision_id": str(uuid4()), "file_id": str(uuid4()), "row_version": "0"},
        files={"file": ("many.pdf", _pages(3), "application/pdf")},
    )
    assert res.status_code == 400, res.text
    assert "лимит 2" in res.text
    assert not list(kind_root("drawing_pdf").glob(".part-*"))


def test_oversized_body_is_refused_before_spool(monkeypatch):
    owner = _register("draw-cap@example.com", "510000000043")
    _promote("draw-cap@example.com", "owner")
    pid = _project(owner["token"], "Cap yard")
    _enable(owner["token"])
    monkeypatch.setattr("app.drawings.MAX_PDF_BYTES", 64)

    def boom(*_args, **_kwargs):
        raise AssertionError("spooled")

    monkeypatch.setattr("app.routers.drawings.spool_upload", boom)
    res = client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "revision_id": str(uuid4()), "file_id": str(uuid4()), "row_version": "0"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert res.status_code == 413, res.text
    assert not list(kind_root("drawing_pdf").glob(".part-*"))


def test_spool_deletes_the_partial_over_the_cap(tmp_path):
    from app.routers.drawings import spool_upload

    dest = tmp_path / ".part-over"
    with pytest.raises(HTTPException) as caught:
        spool_upload(io.BytesIO(b"x" * 100), dest, limit=40, chunk=16)
    assert caught.value.status_code == 413
    assert not dest.exists()


def test_upload_role_is_this_project_and_admin_can_read():
    owner = _register("draw-role-owner@example.com", "510000000044")
    _promote("draw-role-owner@example.com", "owner")
    admin = _register("draw-role-admin@example.com", "510000000045")
    _promote("draw-role-admin@example.com", "admin")
    pid = _project(owner["token"], "Role yard")
    other = _project(owner["token"], "Other role yard")
    _enable(owner["token"])
    created = _upload(owner["token"], pid, rev="A")
    assert created.status_code == 200, created.text
    sheet = created.json()["data"]
    sup = _invite(owner["token"], other, "supervisor", "draw-role-sup@example.com")
    wide = _invite(owner["token"], other, "customer", "draw-role-wide@example.com")
    _promote("draw-role-wide@example.com", "owner")

    for token in (sup, wide, admin["token"]):
        read = client.get(f"/v1/site/projects/{pid}/drawing-sheets", headers=_auth(token))
        assert read.status_code == 200, read.text
        denied = _upload(token, pid, title="Not this object")
        assert denied.status_code == 403, denied.text

    admin_file = client.get(f"/v1/site/drawings/{sheet['id']}/file", headers=_auth(admin["token"]))
    assert admin_file.status_code == 200, admin_file.text
    admin_sheet = client.get(f"/v1/site/drawings/{sheet['id']}", headers=_auth(admin["token"]))
    assert admin_sheet.status_code == 200, admin_sheet.text
    admin_rev = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions",
        headers=_auth(admin["token"]),
        data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": "B", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert admin_rev.status_code == 403, admin_rev.text

    on_other = _upload(sup, other, title="Their object")
    assert on_other.status_code == 200, on_other.text
    seated = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "draw-role-sup@example.com", "role": "supervisor"},
        headers=_auth(owner["token"]),
    )
    assert seated.status_code == 200, seated.text
    allowed = _upload(sup, pid, title="This object")
    assert allowed.status_code == 200, allowed.text


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
    assert "ix_drawings_set_id" in indexes
    assert "ix_drawing_revisions_file_id" in indexes
    file_columns = {row[1] for row in connection.execute("PRAGMA table_info(files)")}
    assert {"created_by", "updated_by"} <= file_columns
    drawing_columns = {row[1] for row in connection.execute("PRAGMA table_info(drawings)")}
    assert "legacy_id" in drawing_columns
    assert "ix_drawing_revisions_project_id" in indexes
    assert "legacy_id" in indexes["ux_drawings_legacy"]
    columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= columns
    connection.close()
