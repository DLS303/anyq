"""Designer questions: company gate, compare-and-swap, and a one-time reply link."""

import io
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from app.audit import _mask
from app.company_features import company_id_of
from app.main import app
from app.pf0_tables import AuditLog
from app.rfi_service import add_business_days
from app.rfi_tables import access_tokens
from app.schemas import User
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
    assert {"rfis", "external_contacts", "access_tokens", "audit_log"} <= tables
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "ix_rfis_project_status_due" in indexes
    assert "ix_rfis_company_updated" in indexes
    columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= columns
    connection.close()
