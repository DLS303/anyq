"""Designer questions: company gate, compare-and-swap, and a one-time reply link."""

import io
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.audit import _mask
from app.company_features import company_id_of
from app.log_redact import TokenRedactingFilter, redact_text
from app.main import app
from app.paths import publish_exclusive, uploads_dir, write_exclusive_temp
from app.pf0_tables import AuditLog
from app.rfi_service import add_business_days, count_open_by_project, create_rfi
from app.rfi_tables import access_tokens, rfi_files
from app.schemas import User
from app.site_models import RFI
from app.store import store

client = TestClient(app)
BIN_A = "555555555555"
BIN_B = "666666666666"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(email: str, bin_no: str, role: str = "buyer") -> dict:
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+15550001111",
            "company": "North Test LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": role,
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _promote(email: str, role: str) -> User:
    user = store.get_user_by_email(email)
    assert user is not None
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    return updated


def _owner(email: str, bin_no: str) -> tuple[str, User]:
    data = _register(email, bin_no, "buyer")
    user = _promote(email, "owner")
    return data["token"], user


def _flag(token: str, enabled: bool, version: int) -> None:
    res = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": enabled, "row_version": version},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


def _project(token: str, title: str) -> str:
    res = client.post(
        "/v1/site/projects",
        json={"title": title, "address": "1 Test Street"},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


def _jpeg() -> bytes:
    image = Image.new("RGB", (24, 24), "white")
    exif = image.getexif()
    exif[270] = "SECRET-GPS-99"
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _pdf(author: str) -> bytes:
    return (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
        f"4 0 obj\n<< /Author ({author}) /Creator (Tool) /Producer (Tool) >>\nendobj\n"
        "trailer\n<< /Root 1 0 R /Info 4 0 R >>\n%%EOF\n"
    ).encode("ascii")


def test_business_days_skip_the_weekend():
    assert add_business_days(date(2026, 10, 16), 5) == date(2026, 10, 23)


def test_audit_mask_hides_phone_and_name():
    masked = _mask({"status": ["open", "answered"], "phone": "+15551230000", "full_name": "Ada North"})
    blob = json.dumps(masked)
    assert masked["status"] == ["open", "answered"]
    assert masked["phone"] == "***"
    assert masked["full_name"] == "***"
    assert "+1555" not in blob
    assert "Ada" not in blob


def test_foreign_company_is_404_on_read_write_files_and_links(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner_token, owner = _owner("rfi-owner@example.com", BIN_A)
    foreign_token, _foreign = _owner("rfi-foreign@example.com", BIN_B)
    foreman_email = "rfi-foreman@example.com"
    supervisor_email = "rfi-supervisor@example.com"
    _register(foreman_email, BIN_A)
    _register(supervisor_email, BIN_A)
    _promote(foreman_email, "foreman")
    _promote(supervisor_email, "supervisor")
    foreman = client.post(
        "/v1/auth/login",
        json={"email": foreman_email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    supervisor = client.post(
        "/v1/auth/login",
        json={"email": supervisor_email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert foreman.status_code == 200, foreman.text
    assert supervisor.status_code == 200, supervisor.text
    foreman_token = foreman.json()["data"]["token"]
    supervisor_token = supervisor.json()["data"]["token"]

    pid = _project(owner_token, "North Yard")
    other = _project(foreign_token, "South Yard")
    client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": foreman_email, "role": "foreman"},
        headers=_auth(owner_token),
    )
    client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": supervisor_email, "role": "supervisor"},
        headers=_auth(owner_token),
    )

    hidden = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Hidden while the flag is off?"},
        headers=_auth(owner_token),
    )
    assert hidden.status_code == 404

    _flag(owner_token, True, 0)
    _flag(foreign_token, True, 0)
    record_id = str(uuid4())
    contact_id = str(uuid4())
    created = client.post(
        f"/v1/site/projects/{pid}/rfis?pid={other}",
        json={
            "id": record_id,
            "question": "Where does the north stair land?",
            "company_id": "bin:000000000000",
            "due_date": "2020-01-06",
            "drawing_revision_id": "rev-north-1",
            "contact": {
                "id": contact_id,
                "full_name": "Ada North",
                "phone": "+15551230000",
                "email": "ada@example.com",
                "organization": "North Design",
            },
        },
        headers=_auth(owner_token),
    )
    assert created.status_code == 200, created.text
    body = created.json()["data"]
    assert body["id"] == record_id
    assert body["company_id"] == company_id_of(owner)
    assert body["company_id"] != "bin:000000000000"
    assert body["drawing_revision_id"] == "rev-north-1"
    assert body["due_date"] == "2020-01-06"
    assert body["row_version"] == 1
    assert body["deleted_at"] is None
    assert body["created_at"].endswith("+00:00")
    assert body["updated_at"].endswith("+00:00")
    assert body["overdue"] is True
    assert body["contact"]["phone"] == "+15551230000"
    assert body["push"] == {"body": "Новое событие по объекту", "id": record_id}
    assert "Ada" not in body["push"]["body"]
    assert "+1555" not in json.dumps(body["push"])

    for token in (foreign_token,):
        assert client.get(f"/v1/site/projects/{pid}/rfis", headers=_auth(token)).status_code == 404
        assert client.get(f"/v1/site/rfis/{record_id}?pid={other}", headers=_auth(token)).status_code == 404
        assert (
            client.post(
                f"/v1/site/projects/{pid}/rfis",
                json={"id": str(uuid4()), "question": "Foreign write"},
                headers=_auth(token),
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/v1/site/rfis/{record_id}/answer?pid={other}",
                json={"answer": "no", "row_version": 1},
                headers=_auth(token),
            ).status_code
            == 404
        )
        upload = client.post(
            f"/v1/site/projects/{pid}/rfis/{record_id}/files?pid={other}",
            files={"file": ("note.jpg", _jpeg(), "image/jpeg")},
            data={"id": str(uuid4()), "row_version": "1"},
            headers=_auth(token),
        )
        assert upload.status_code == 404
        assert (
            client.post(
                f"/v1/site/projects/{pid}/rfis/{record_id}/link?pid={other}",
                json={"id": str(uuid4()), "expires_in_days": 14},
                headers=_auth(token),
            ).status_code
            == 404
        )

    foreman_list = client.get(f"/v1/site/projects/{pid}/rfis", headers=_auth(foreman_token))
    supervisor_list = client.get(f"/v1/site/projects/{pid}/rfis", headers=_auth(supervisor_token))
    assert foreman_list.status_code == 200, foreman_list.text
    assert supervisor_list.status_code == 200, supervisor_list.text
    assert foreman_list.json()["data"][0]["overdue"] is True
    assert supervisor_list.json()["data"][0]["overdue"] is True
    assert "Ada North" not in foreman_list.text
    assert "+15551230000" not in foreman_list.text
    assert "Ada North" not in supervisor_list.text

    owner_list = client.get(f"/v1/site/projects/{pid}/rfis", headers=_auth(owner_token))
    assert "Ada North" in owner_list.text
    assert "+15551230000" in owner_list.text

    stale = client.post(
        f"/v1/site/rfis/{record_id}/answer",
        json={"answer": "too soon", "row_version": 0},
        headers=_auth(owner_token),
    )
    assert stale.status_code == 409
    illegal = client.post(
        f"/v1/site/rfis/{record_id}/status",
        json={"status": "answered", "row_version": 1},
        headers=_auth(owner_token),
    )
    assert illegal.status_code == 409

    file_id = str(uuid4())
    uploaded = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/files",
        files={"file": ("note.jpg", _jpeg(), "image/jpeg")},
        data={"id": file_id, "row_version": "1"},
        headers=_auth(owner_token),
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["data"]["attachments"] == [file_id]
    assert "/" not in file_id
    saved = client.get(
        f"/v1/site/projects/{pid}/rfis/{record_id}/files/{file_id}",
        headers=_auth(owner_token),
    )
    assert saved.status_code == 200, saved.text
    assert len(Image.open(io.BytesIO(saved.content)).getexif()) == 0
    foreign_file = client.get(
        f"/v1/site/projects/{pid}/rfis/{record_id}/files/{file_id}?pid={other}",
        headers=_auth(foreign_token),
    )
    assert foreign_file.status_code == 404

    pdf_id = str(uuid4())
    pdf_up = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/files",
        files={"file": ("note.pdf", _pdf("AUTHORSECRET99"), "application/pdf")},
        data={"id": pdf_id, "row_version": "2"},
        headers=_auth(owner_token),
    )
    assert pdf_up.status_code == 200, pdf_up.text
    stored_pdf = client.get(
        f"/v1/site/projects/{pid}/rfis/{record_id}/files/{pdf_id}",
        headers=_auth(owner_token),
    )
    assert b"AUTHORSECRET99" not in stored_pdf.content

    exported = client.get(f"/v1/site/projects/{pid}/rfis/{record_id}/pdf", headers=_auth(owner_token))
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/pdf")
    assert b"Ada North" not in exported.content
    assert b"+15551230000" not in exported.content
    assert b"Sam Foreman" not in exported.content
    assert b"/Author ()" in exported.content

    short = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link",
        json={"id": str(uuid4()), "expires_in_days": 13},
        headers=_auth(owner_token),
    )
    assert short.status_code == 400
    link = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link",
        json={"id": str(uuid4()), "expires_in_days": 14},
        headers=_auth(owner_token),
    )
    assert link.status_code == 200, link.text
    token = link.json()["data"]["token"]
    assert len(token) >= 43
    assert "+1555" not in token
    public = client.get(f"/v1/public/rfi/{token}")
    assert public.status_code == 200, public.text
    assert public.headers["x-robots-tag"] == "noindex, nofollow"
    assert public.headers["referrer-policy"] == "no-referrer"
    assert "+15551230000" not in public.text
    assert "Ada North" not in public.text
    replied = client.post(f"/v1/public/rfi/{token}", json={"answer": "Land it on grid C"})
    assert replied.status_code == 200, replied.text
    again = client.post(f"/v1/public/rfi/{token}", json={"answer": "second"})
    assert again.status_code == 410
    back = client.post(
        f"/v1/site/rfis/{record_id}/status",
        json={"status": "open", "row_version": 3},
        headers=_auth(owner_token),
    )
    assert back.status_code == 409
    closed = client.post(
        f"/v1/site/rfis/{record_id}/status",
        json={"status": "closed", "row_version": 4},
        headers=_auth(owner_token),
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["data"]["status"] == "closed"
    reclose = client.post(
        f"/v1/site/rfis/{record_id}/status",
        json={"status": "closed", "row_version": 5},
        headers=_auth(owner_token),
    )
    assert reclose.status_code == 409

    with store._sql.factory() as session:
        events = session.scalars(select(AuditLog).where(AuditLog.entity_id == record_id)).all()
    actions = [row.action for row in events]
    assert "rfi.create" in actions
    assert "rfi.answer" in actions
    blob = " ".join(json.dumps(row.changes or {}, ensure_ascii=True) for row in events)
    assert "Land it on grid C" not in blob
    assert "+15551230000" not in blob
    assert "Ada North" not in blob

    _flag(owner_token, False, 1)
    gated = client.get(f"/v1/site/rfis/{record_id}?pid={other}", headers=_auth(owner_token))
    assert gated.status_code == 404
    public_off = client.get(f"/v1/public/rfi/{token}")
    assert public_off.status_code == 404


def test_default_due_date_and_fresh_token_expiry(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    token, _owner_user = _owner("rfi-due@example.com", "777777777777")
    pid = _project(token, "East Yard")
    _flag(token, True, 0)
    created = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Which way is north?"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    expected = add_business_days(datetime.now(UTC).date(), 5).isoformat()
    assert created.json()["data"]["due_date"] == expected
    record_id = created.json()["data"]["id"]
    link_id = str(uuid4())
    link = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link",
        json={"id": link_id, "expires_in_days": 30},
        headers=_auth(token),
    )
    assert link.status_code == 200, link.text
    share = link.json()["data"]["token"]
    with store._sql.factory() as session:
        session.execute(
            update(access_tokens)
            .where(access_tokens.c.id == link_id)
            .values(expires_at="2020-01-01T00:00:00+00:00")
        )
        session.commit()
    expired = client.get(f"/v1/public/rfi/{share}")
    assert expired.status_code == 410
    missing = client.get("/v1/public/rfi/" + "x" * 40)
    assert missing.status_code == 404


def _jpeg_color(color: str) -> bytes:
    image = Image.new("RGB", (24, 24), color)
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_reused_file_id_does_not_replace_bytes(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner_token, _owner_user = _owner("rfi-bytes-a@example.com", "888888888888")
    foreign_token, _foreign = _owner("rfi-bytes-b@example.com", "999999999999")
    pid = _project(owner_token, "West Yard")
    other = _project(foreign_token, "East Lot")
    _flag(owner_token, True, 0)
    _flag(foreign_token, True, 0)
    shared_id = str(uuid4())
    first = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Keep the first photo"},
        headers=_auth(owner_token),
    )
    assert first.status_code == 200, first.text
    first_id = first.json()["data"]["id"]
    original = _jpeg_color("red")
    uploaded = client.post(
        f"/v1/site/projects/{pid}/rfis/{first_id}/files",
        files={"file": ("a.jpg", original, "image/jpeg")},
        data={"id": shared_id, "row_version": "1"},
        headers=_auth(owner_token),
    )
    assert uploaded.status_code == 200, uploaded.text
    saved = client.get(
        f"/v1/site/projects/{pid}/rfis/{first_id}/files/{shared_id}",
        headers=_auth(owner_token),
    )
    assert saved.status_code == 200, saved.text
    original_bytes = saved.content
    with store._sql.factory() as session:
        stored = session.execute(select(rfi_files).where(rfi_files.c.file_id == shared_id)).mappings().one()
    assert shared_id not in stored.storage_key
    assert "/" not in stored.storage_key
    on_disk = uploads_dir() / stored.storage_key
    assert on_disk.read_bytes() == original_bytes

    second = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "A later photo"},
        headers=_auth(owner_token),
    )
    assert second.status_code == 200, second.text
    later = client.post(
        f"/v1/site/projects/{pid}/rfis/{second.json()['data']['id']}/files",
        files={"file": ("b.jpg", _jpeg_color("blue"), "image/jpeg")},
        data={"id": shared_id, "row_version": "1"},
        headers=_auth(owner_token),
    )
    assert later.status_code == 200, later.text
    assert on_disk.read_bytes() == original_bytes

    foreign_rfi = client.post(
        f"/v1/site/projects/{other}/rfis",
        json={"id": str(uuid4()), "question": "Other company photo"},
        headers=_auth(foreign_token),
    )
    assert foreign_rfi.status_code == 200, foreign_rfi.text
    foreign_up = client.post(
        f"/v1/site/projects/{other}/rfis/{foreign_rfi.json()['data']['id']}/files",
        files={"file": ("c.jpg", _jpeg_color("green"), "image/jpeg")},
        data={"id": shared_id, "row_version": "1"},
        headers=_auth(foreign_token),
    )
    assert foreign_up.status_code == 200, foreign_up.text
    assert on_disk.read_bytes() == original_bytes
    again = client.get(
        f"/v1/site/projects/{pid}/rfis/{first_id}/files/{shared_id}",
        headers=_auth(owner_token),
    )
    assert again.content == original_bytes

    conflict = client.post(
        f"/v1/site/projects/{pid}/rfis/{first_id}/files",
        files={"file": ("d.jpg", _jpeg_color("black"), "image/jpeg")},
        data={"id": shared_id, "row_version": "1"},
        headers=_auth(owner_token),
    )
    assert conflict.status_code == 409
    assert on_disk.read_bytes() == original_bytes
    assert list(uploads_dir().glob(".tmp-*")) == []

    fresh_version = int(uploaded.json()["data"]["row_version"])
    before = {path.name for path in uploads_dir().iterdir() if path.is_file()}
    reused = client.post(
        f"/v1/site/projects/{pid}/rfis/{first_id}/files",
        files={"file": ("e.jpg", _jpeg_color("white"), "image/jpeg")},
        data={"id": shared_id, "row_version": str(fresh_version)},
        headers=_auth(owner_token),
    )
    assert reused.status_code == 409, reused.text
    assert on_disk.read_bytes() == original_bytes
    after = {path.name for path in uploads_dir().iterdir() if path.is_file()}
    assert after == before
    assert list(uploads_dir().glob(".tmp-*")) == []
    with store._sql.factory() as session:
        rows = session.execute(
            select(rfi_files).where(rfi_files.c.rfi_id == first_id, rfi_files.c.file_id == shared_id)
        ).mappings().all()
    assert len(rows) == 1


def test_alembic_rfi_revision_roundtrip(tmp_path):
    db = tmp_path / "rfi.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    api = os.path.join(os.path.dirname(__file__), "..")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "downgrade", "-1"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "check"], cwd=api, env=env)
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"rfis", "external_contacts", "access_tokens", "rfi_files", "audit_log"} <= tables
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_rfis_project_status_due" in indexes
    assert "ix_rfis_company_updated" in indexes
    assert "uq_rfi_files_rfi_file" in indexes
    assert "ix_access_tokens_entity_id" in indexes
    rfi_sql = connection.execute("SELECT sql FROM sqlite_master WHERE name = 'rfis'").fetchone()[0]
    assert "uq_rfis_project_number" in rfi_sql
    file_fks = {row[2] for row in connection.execute("PRAGMA foreign_key_list(rfi_files)")}
    token_fks = {row[2] for row in connection.execute("PRAGMA foreign_key_list(access_tokens)")}
    rfi_fks = {row[2] for row in connection.execute("PRAGMA foreign_key_list(rfis)")}
    assert "rfis" in file_fks
    assert "rfis" in token_fks
    assert "external_contacts" in rfi_fks
    file_columns = {row[1] for row in connection.execute("PRAGMA table_info(rfi_files)")}
    assert {"file_id", "storage_key", "created_by", "updated_by"} <= file_columns
    columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= columns
    connection.close()


def test_parallel_creates_use_distinct_numbers(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    _token, user = _owner("rfi-race@example.com", "101010101010")
    pid = _project(_token, "Race Yard")
    _flag(_token, True, 0)
    access = {"project_id": pid, "company_id": company_id_of(user)}
    barrier = threading.Barrier(6)
    errors: list[BaseException] = []
    numbers: list[str] = []
    lock = threading.Lock()

    def once(index: int) -> None:
        barrier.wait()
        try:
            data = create_rfi(user, access, {"id": str(uuid4()), "question": f"Race {index}"})
        except (HTTPException, IntegrityError, OperationalError) as exc:
            with lock:
                errors.append(exc)
            return
        with lock:
            numbers.append(data["number"])

    threads = [threading.Thread(target=once, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert sorted(numbers) == [f"RFI-{index:03d}" for index in range(1, 7)]
    counts = count_open_by_project([pid, "missing-project"])
    assert counts[pid] == 6
    assert counts["missing-project"] == 0


def test_revoke_and_close_invalidate_the_reply_link(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    token, _user = _owner("rfi-revoke@example.com", "202020202020")
    pid = _project(token, "Link Yard")
    _flag(token, True, 0)
    created = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Can this link be withdrawn?"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    record_id = created.json()["data"]["id"]
    link_id = str(uuid4())
    link = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link",
        json={"id": link_id, "expires_in_days": 14},
        headers=_auth(token),
    )
    assert link.status_code == 200, link.text
    share = link.json()["data"]["token"]
    opened = client.get(f"/v1/public/rfi/{share}")
    assert opened.status_code == 200, opened.text
    revoked = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link/revoke",
        json={"id": link_id},
        headers=_auth(token),
    )
    assert revoked.status_code == 200, revoked.text
    assert "token" not in revoked.json()["data"]
    assert client.get(f"/v1/public/rfi/{share}").status_code == 404
    again = client.post(
        f"/v1/site/projects/{pid}/rfis/{record_id}/link",
        json={"id": str(uuid4()), "expires_in_days": 14},
        headers=_auth(token),
    )
    assert again.status_code == 200, again.text
    second = again.json()["data"]["token"]
    closed = client.post(
        f"/v1/site/rfis/{record_id}/status",
        json={"status": "closed", "row_version": 1},
        headers=_auth(token),
    )
    assert closed.status_code == 200, closed.text
    assert client.get(f"/v1/public/rfi/{second}").status_code == 404
    other = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Delete this question"},
        headers=_auth(token),
    )
    assert other.status_code == 200, other.text
    other_id = other.json()["data"]["id"]
    third = client.post(
        f"/v1/site/projects/{pid}/rfis/{other_id}/link",
        json={"id": str(uuid4()), "expires_in_days": 14},
        headers=_auth(token),
    )
    assert third.status_code == 200, third.text
    removed = client.post(
        f"/v1/site/rfis/{other_id}/delete",
        json={"row_version": 1},
        headers=_auth(token),
    )
    assert removed.status_code == 200, removed.text
    assert client.get(f"/v1/public/rfi/{third.json()['data']['token']}").status_code == 404


def test_demo_bundle_omits_questions_when_the_flag_is_off(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "1")
    token, _user = _owner("rfi-demo@example.com", "303030303030")
    pid = _project(token, "Demo Yard")
    _flag(token, True, 0)
    created = client.post(
        f"/v1/site/projects/{pid}/rfis",
        json={"id": str(uuid4()), "question": "Shown only while the flag is on"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    record_id = created.json()["data"]["id"]
    legacy = RFI(id="legacy-hidden", project_id=pid, number="RFI-OLD", title="Old", question="Old")
    store.rfis[legacy.id] = legacy
    try:
        _flag(token, False, 1)
        hidden = client.get(f"/v1/site/projects/{pid}/bundle", headers=_auth(token))
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["data"]["rfis"] == []
        _flag(token, True, 0)
        shown = client.get(f"/v1/site/projects/{pid}/bundle", headers=_auth(token))
        assert shown.status_code == 200, shown.text
        ids = [row["id"] for row in shown.json()["data"]["rfis"]]
        assert ids == [record_id]
    finally:
        store.rfis.pop(legacy.id, None)


def test_publish_exclusive_leaves_the_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_UPLOADS_DIR", str(tmp_path))
    first = write_exclusive_temp("upload", b"one")
    publish_exclusive("upload", first, "abc123")
    second = write_exclusive_temp("upload", b"two")
    with pytest.raises(FileExistsError):
        publish_exclusive("upload", second, "abc123")
    assert (tmp_path / "abc123").read_bytes() == b"one"
    assert list(tmp_path.glob(".tmp-*")) == []


def test_reply_token_is_redacted_in_logs():
    secret = "a" * 43
    message = f'GET /v1/public/rfi/{secret} HTTP/1.1 referer /ru/r/rfi/{secret}'
    assert secret not in redact_text(message)
    assert "/v1/public/rfi/[redacted]" in redact_text(message)
    logger = logging.getLogger("test.rfi.redact")
    logger.addFilter(TokenRedactingFilter())
    logger.setLevel(logging.INFO)
    captured: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = Capture()
    logger.addHandler(handler)
    try:
        logger.info('"%s"', f"GET /v1/public/rfi/{secret} HTTP/1.1")
    finally:
        logger.removeHandler(handler)
    assert captured
    assert secret not in captured[0]
