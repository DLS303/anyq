"""Material approvals: company gate, versions, files, and a revocable reply link."""

import io
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from app.company_features import company_id_of
from app.main import app
from app.paths import publish_exclusive, uploads_dir, write_exclusive_temp
from app.pf0_tables import AuditLog
from app.rfi_service import PUSH_BODY
from app.schemas import User
from app.store import store
from app.submittal_tables import material_approval_files

client = TestClient(app)
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = json.loads((ROOT / "fixtures" / "anyq_procurement_fake.json").read_text(encoding="utf-8"))
BIN_A = "000000000099"
BIN_B = "000000000098"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(email: str, bin_no: str, role: str = "buyer") -> dict:
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77000000000",
            "company": FIXTURE["companies"][0]["name"],
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
        json={"key": "submittals", "enabled": enabled, "row_version": version},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text


def _project(token: str, title: str) -> str:
    res = client.post(
        "/v1/site/projects",
        json={"title": title, "address": FIXTURE["objects"][0]["address"]},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


def _sample():
    return next(item for item in FIXTURE["approvals"] if item["id"] == "ap-1")


def _pdf(name: str) -> bytes:
    return (ROOT / "fixtures" / name).read_bytes()


def _jpeg() -> bytes:
    image = Image.new("RGB", (24, 24), "white")
    exif = image.getexif()
    exif[270] = "SECRET-GPS-99"
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _create(token: str, pid: str, approver: str, **extra) -> dict:
    sample = _sample()
    body = {
        "id": str(uuid4()),
        "name": sample["name"],
        "brand": sample["brand"],
        "manufacturer": sample["manufacturer"],
        "unit": sample["unit"],
        "qty": sample["qty"],
        "need_by": sample["need_by"],
        "specs": sample["specs"],
        "analogs": sample["analogs"],
        "approver_ids": [approver],
        "indicative_price": 8900,
    }
    body.update(extra)
    res = client.post(f"/v1/site/projects/{pid}/material-approvals?pid=other-project", json=body, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _upload(token: str, pid: str, item: dict, name: str = "cert_demo.pdf", kind: str = "cert", file_id: str | None = None):
    res = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{item['id']}/files",
        files={"file": (name, _pdf(name), "application/pdf")},
        data={"id": file_id or str(uuid4()), "row_version": str(item["row_version"]), "kind": kind},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def test_publish_refuses_an_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_UPLOADS_DIR", str(tmp_path))
    key = "serverkey01"
    path = tmp_path / key
    path.write_bytes(b"original")
    tmp = write_exclusive_temp("upload", b"replacement")
    try:
        publish_exclusive("upload", tmp, key)
        raised = False
    except FileExistsError:
        raised = True
    assert raised
    assert path.read_bytes() == b"original"
    assert not tmp.exists()


def test_foreign_company_status_and_files(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner_token, owner = _owner("mat-owner@example.com", BIN_A)
    foreign_token, _foreign = _owner("mat-foreign@example.com", BIN_B)
    reviewer_email = "mat-reviewer@example.com"
    _register(reviewer_email, BIN_A)
    _promote(reviewer_email, "supervisor")
    reviewer_login = client.post(
        "/v1/auth/login",
        json={"email": reviewer_email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    reviewer_token = reviewer_login.json()["data"]["token"]
    reviewer = store.get_user_by_email(reviewer_email)
    assert reviewer is not None
    pid = _project(owner_token, FIXTURE["objects"][0]["name"])
    other = _project(foreign_token, "Other yard")
    client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": reviewer_email, "role": "supervisor"},
        headers=_auth(owner_token),
    )
    hidden = client.post(
        f"/v1/site/projects/{pid}/material-approvals?pid={other}",
        json={"id": str(uuid4()), "name": "Hidden", "brand": "X"},
        headers=_auth(owner_token),
    )
    assert hidden.status_code == 404
    _flag(owner_token, True, 0)
    _flag(foreign_token, True, 0)
    created = _create(owner_token, pid, reviewer.id)
    assert created["project_id"] == pid
    assert created["company_id"] == company_id_of(owner)
    assert created["status"] == "draft"
    assert created["row_version"] == 1
    assert created["created_at"].endswith("+00:00")
    assert created["indicative_price"] is None
    assert created["number"] == "MAT-001"
    assert created["push"]["body"] == PUSH_BODY
    assert created["project_only"] is True
    assert "8900" not in json.dumps(created["indicative_price"])

    second = _create(owner_token, pid, reviewer.id, id=str(uuid4()))
    assert second["number"] == "MAT-002"

    for token in (foreign_token,):
        assert client.get(f"/v1/site/projects/{pid}/material-approvals", headers=_auth(token)).status_code == 404
        assert client.get(f"/v1/site/material-approvals/{created['id']}?pid={other}", headers=_auth(token)).status_code == 404
        assert (
            client.post(
                f"/v1/site/projects/{pid}/material-approvals",
                json={"id": str(uuid4()), "name": "Foreign", "brand": "Y"},
                headers=_auth(token),
            ).status_code
            == 404
        )
        upload = client.post(
            f"/v1/site/projects/{pid}/material-approvals/{created['id']}/files?pid={other}",
            files={"file": ("cert_demo.pdf", _pdf("cert_demo.pdf"), "application/pdf")},
            data={"id": str(uuid4()), "row_version": "1", "kind": "cert"},
            headers=_auth(token),
        )
        assert upload.status_code == 404
        assert (
            client.post(
                f"/v1/site/projects/{pid}/material-approvals/{created['id']}/link?pid={other}",
                json={"id": str(uuid4())},
                headers=_auth(token),
            ).status_code
            == 404
        )

    stored = _upload(owner_token, pid, created, "cert_demo.pdf", "cert")
    assert stored["duplicate_warning"] is None
    saved = client.get(
        f"/v1/site/projects/{pid}/material-approvals/{created['id']}/files/{stored['file_id']}",
        headers=_auth(owner_token),
    )
    assert saved.status_code == 200
    assert b"Author" not in saved.content or b"/Author ()" in saved.content or b"/Author" not in saved.content

    photo_id = str(uuid4())
    photo = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{created['id']}/files",
        files={"file": ("sample.jpg", _jpeg(), "image/jpeg")},
        data={"id": photo_id, "row_version": str(stored["row_version"]), "kind": "photo"},
        headers=_auth(owner_token),
    )
    assert photo.status_code == 200, photo.text
    photo_bytes = client.get(
        f"/v1/site/projects/{pid}/material-approvals/{created['id']}/files/{photo_id}",
        headers=_auth(owner_token),
    )
    assert len(Image.open(io.BytesIO(photo_bytes.content)).getexif()) == 0

    same = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/files",
        files={"file": ("cert_demo.pdf", _pdf("cert_demo.pdf"), "application/pdf")},
        data={"id": str(uuid4()), "row_version": "1", "kind": "cert"},
        headers=_auth(owner_token),
    )
    assert same.status_code == 200, same.text
    assert same.json()["data"]["duplicate_warning"]
    assert same.json()["data"]["duplicate_warning"].startswith("этот файл уже загружен к счёту")
    assert "MAT-001" in same.json()["data"]["duplicate_warning"]

    foreign_item = _create(foreign_token, other, store.get_user_by_email("mat-foreign@example.com").id)
    foreign_same = _upload(foreign_token, other, foreign_item, "cert_demo.pdf")
    assert foreign_same["duplicate_warning"] is None

    stale = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={"status": "in_review", "row_version": 1},
        headers=_auth(owner_token),
    )
    assert stale.status_code == 409
    submitted = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={"status": "in_review", "row_version": photo.json()["data"]["row_version"]},
        headers=_auth(owner_token),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["status"] == "in_review"
    assert reviewer.id in submitted.json()["data"]["notify"]
    assert submitted.json()["data"]["push"] == {"body": PUSH_BODY, "id": created["id"]}

    early = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={"status": "approved", "row_version": 1},
        headers=_auth(reviewer_token),
    )
    assert early.status_code == 409
    bare = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={"status": "rejected", "row_version": submitted.json()["data"]["row_version"]},
        headers=_auth(reviewer_token),
    )
    assert bare.status_code == 409
    rejected = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={
            "status": "rejected",
            "comment": "brand",
            "row_version": submitted.json()["data"]["row_version"],
        },
        headers=_auth(reviewer_token),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "rejected"
    history = rejected.json()["data"]["versions"]
    assert [item["status"] for item in history] == ["rejected"]

    link_after = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{created['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(owner_token),
    )
    assert link_after.status_code == 409

    version_id = str(uuid4())
    version = client.post(
        f"/v1/site/material-approvals/{created['id']}/version",
        json={"id": version_id, "row_version": rejected.json()["data"]["row_version"]},
        headers=_auth(owner_token),
    )
    assert version.status_code == 200, version.text
    assert version.json()["data"]["status"] == "draft"
    assert version.json()["data"]["version"] == 2
    assert version.json()["data"]["parent_id"] == created["id"]
    assert any(item["id"] == created["id"] and item["status"] == "rejected" for item in version.json()["data"]["versions"])

    fresh = _upload(owner_token, pid, version.json()["data"], "pass_demo.pdf", "passport")
    sent = client.post(
        f"/v1/site/material-approvals/{version_id}/status",
        json={"status": "in_review", "row_version": fresh["row_version"]},
        headers=_auth(owner_token),
    )
    assert sent.status_code == 200, sent.text
    link = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{version_id}/link",
        json={"id": str(uuid4()), "expires_in_days": 14},
        headers=_auth(owner_token),
    )
    assert link.status_code == 200, link.text
    token = link.json()["data"]["token"]
    public = client.get(f"/v1/public/material/{token}")
    assert public.status_code == 200, public.text
    assert public.headers["referrer-policy"] == "no-referrer"
    assert public.headers["cache-control"] == "no-store"
    assert public.headers["x-robots-tag"] == "noindex, nofollow"
    assert "+7700" not in public.text
    decided = client.post(f"/v1/public/material/{token}", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["data"]["status"] == "approved"
    assert decided.json()["data"]["push"]["body"] == PUSH_BODY
    again = client.get(f"/v1/public/material/{token}")
    assert again.status_code == 404

    other_project = _project(owner_token, "Second object")
    moved = client.post(
        f"/v1/site/projects/{other_project}/material-approvals/{version_id}/to-request",
        headers=_auth(owner_token),
    )
    assert moved.status_code == 404
    ordered = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{version_id}/to-request",
        headers=_auth(owner_token),
    )
    assert ordered.status_code == 200, ordered.text
    line = ordered.json()["data"]["line"]
    assert line["brand"] == _sample()["brand"]
    assert line["requires_approval"] is True
    assert line["approval_id"] == version_id
    assert line["specs"]
    assert line["analogs"]
    assert ordered.json()["data"]["request"]["shared"] is True

    blocked = _create(owner_token, pid, reviewer.id, id=str(uuid4()), need_by=(datetime.now(UTC).date() + timedelta(days=1)).isoformat())
    blocked_file = _upload(owner_token, pid, blocked, "kp_sup-4_2026-10-13.pdf", "quote")
    waiting = client.post(
        f"/v1/site/material-approvals/{blocked['id']}/status",
        json={"status": "in_review", "row_version": blocked_file["row_version"]},
        headers=_auth(owner_token),
    )
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()["data"]["remind"] is True
    quick = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": blocked["name"], "unit": blocked["unit"], "qty": 1},
        headers=_auth(owner_token),
    )
    assert quick.status_code == 200, quick.text
    lid = quick.json()["data"]["line"]["id"]
    patched = client.patch(
        f"/v1/procurement/lines/{lid}",
        json={"requires_approval": True, "brand": blocked["brand"], "approval_id": blocked["id"]},
        headers=_auth(owner_token),
    )
    assert patched.status_code == 200, patched.text
    supplier = User(
        id="u-mat-sup",
        email="mat-sup@example.com",
        full_name=FIXTURE["suppliers"][0]["name"],
        role="supplier",
        company=FIXTURE["suppliers"][0]["name"],
        phone=FIXTURE["suppliers"][0]["phone"],
    )
    store._index_user(supplier)
    from app.authutil import hash_password

    store.credentials[supplier.id] = hash_password("secret12")
    supplier_login = client.post(
        "/v1/auth/login",
        json={"email": supplier.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert supplier_login.status_code == 200, supplier_login.text
    supplier_token = supplier_login.json()["data"]["token"]
    inbox = client.get("/v1/procurement/inbox", headers=_auth(supplier_token))
    assert inbox.status_code == 200, inbox.text
    visible_ids = [line["id"] for row in inbox.json()["data"] for line in row["lines"]]
    assert lid not in visible_ids
    offer = client.post(
        f"/v1/procurement/lines/{lid}/offers",
        json={"supplier_name": FIXTURE["suppliers"][0]["name"], "price_kzt": 100, "vat_included": True},
        headers=_auth(owner_token),
    )
    assert offer.status_code == 409

    quoted = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{version_id}/price",
        json={"price": 8900, "file_id": "missing", "row_version": decided.json()["data"].get("row_version", 1)},
        headers=_auth(owner_token),
    )
    assert quoted.status_code == 409

    mismatch = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{version_id}/mismatch",
        json={"brand": "ПП-СТ-100-ППС RAL9003", "row_version": client.get(f"/v1/site/material-approvals/{version_id}", headers=_auth(owner_token)).json()["data"]["row_version"]},
        headers=_auth(owner_token),
    )
    assert mismatch.status_code == 200, mismatch.text
    assert mismatch.json()["data"]["push"]["body"] == PUSH_BODY

    with store._sql.factory() as session:
        events = session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"])).all()
    blob = " ".join(json.dumps(row.changes or {}, ensure_ascii=True) for row in events)
    assert "submittal.create" in [row.action for row in events]
    assert "submittal.status_change" in [row.action for row in events]
    assert "+7700" not in blob
    assert "brand" not in blob

    _flag(owner_token, False, 1)
    gated = client.get(f"/v1/site/material-approvals/{created['id']}?pid={other}", headers=_auth(owner_token))
    assert gated.status_code == 404


def test_reused_file_id_and_revoked_link(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    owner_token, owner = _owner("mat-bytes@example.com", "000000000097")
    foreign_token, _foreign = _owner("mat-bytes-b@example.com", "000000000096")
    pid = _project(owner_token, "File yard")
    other = _project(foreign_token, "Other file yard")
    _flag(owner_token, True, 0)
    _flag(foreign_token, True, 0)
    first = _create(owner_token, pid, owner.id)
    shared_id = str(uuid4())
    uploaded = _upload(owner_token, pid, first, "cert_demo.pdf", "cert", shared_id)
    saved = client.get(
        f"/v1/site/projects/{pid}/material-approvals/{first['id']}/files/{shared_id}",
        headers=_auth(owner_token),
    )
    original = saved.content
    with store._sql.factory() as session:
        stored = session.execute(
            select(material_approval_files).where(material_approval_files.c.file_id == shared_id)
        ).mappings().one()
    assert shared_id not in stored.storage_key
    on_disk = uploads_dir() / stored.storage_key
    assert on_disk.read_bytes() == original
    later = _create(owner_token, pid, owner.id, id=str(uuid4()))
    again = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{later['id']}/files",
        files={"file": ("pass_demo.pdf", _pdf("pass_demo.pdf"), "application/pdf")},
        data={"id": shared_id, "row_version": "1", "kind": "passport"},
        headers=_auth(owner_token),
    )
    assert again.status_code == 200, again.text
    assert on_disk.read_bytes() == original
    conflict = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{first['id']}/files",
        files={"file": ("pass_demo.pdf", _pdf("pass_demo.pdf"), "application/pdf")},
        data={"id": shared_id, "row_version": str(uploaded["row_version"]), "kind": "passport"},
        headers=_auth(owner_token),
    )
    assert conflict.status_code == 409
    assert on_disk.read_bytes() == original
    foreign = _create(foreign_token, other, store.get_user_by_email("mat-bytes-b@example.com").id)
    foreign_up = client.post(
        f"/v1/site/projects/{other}/material-approvals/{foreign['id']}/files",
        files={"file": ("inv_sup-1_0001.pdf", _pdf("inv_sup-1_0001.pdf"), "application/pdf")},
        data={"id": shared_id, "row_version": "1", "kind": "invoice"},
        headers=_auth(foreign_token),
    )
    assert foreign_up.status_code == 200, foreign_up.text
    assert on_disk.read_bytes() == original
    assert list(uploads_dir().glob(".tmp-*")) == []

    sent = client.post(
        f"/v1/site/material-approvals/{later['id']}/status",
        json={"status": "in_review", "row_version": again.json()["data"]["row_version"]},
        headers=_auth(owner_token),
    )
    assert sent.status_code == 200, sent.text
    link = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{later['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(owner_token),
    )
    token = link.json()["data"]["token"]
    withdrawn = client.post(
        f"/v1/site/material-approvals/{later['id']}/status",
        json={"status": "withdrawn", "row_version": sent.json()["data"]["row_version"]},
        headers=_auth(owner_token),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert client.get(f"/v1/public/material/{token}").status_code == 404


def test_number_retries_after_a_unique_conflict(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    token, owner = _owner("mat-number@example.com", "000000000095")
    pid = _project(token, "Number yard")
    _flag(token, True, 0)
    first = _create(token, pid, owner.id)
    assert first["number"] == "MAT-001"
    from app import submittal_service as svc

    calls = {"n": 0}
    real = svc._next_number

    def fake(session, project_id):
        calls["n"] += 1
        if calls["n"] == 1:
            return "MAT-001"
        return real(session, project_id)

    monkeypatch.setattr(svc, "_next_number", fake)
    second = _create(token, pid, owner.id, id=str(uuid4()))
    assert second["number"] == "MAT-002"
    assert calls["n"] >= 2


def test_alembic_material_revision_is_one_head(tmp_path):
    db = tmp_path / "mat.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    api = os.path.join(os.path.dirname(__file__), "..")
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "downgrade", "-1"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "check"], cwd=api, env=env)
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(Path(api) / "alembic.ini")))
    assert script.get_heads() == ["20261019_0009_pf3b"]
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "material_approvals" in tables
    assert "material_approval_files" in tables
    indexes = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "uq_material_approvals_project_number" in indexes
    assert "uq_material_approval_files_approval_file" in indexes
    assert "ix_material_approval_files_company_sha256" in indexes
    assert "ix_material_approval_files_file_id" in indexes
    assert "ix_access_tokens_entity_id" in indexes
    assert "material_approval_links" in tables
    assert "ix_material_approval_links_entity_id" in indexes
    assert "ix_material_approval_links_token_sha256" in indexes
    link_columns = {row[1] for row in connection.execute("PRAGMA table_info(material_approval_links)")}
    assert {"token_sha256", "expires_at", "revoked_at", "used_at", "deleted_at", "entity_id"} <= link_columns
    connection.close()
    assert "data/" + "db.json" not in Path(__file__).read_text(encoding="utf-8")


def _person(email: str, bin_no: str, role: str) -> tuple[str, User]:
    _register(email, bin_no, "buyer")
    _promote(email, role)
    login = client.post(
        "/v1/auth/login",
        json={"email": email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    user = store.get_user_by_email(email)
    assert user is not None
    return login.json()["data"]["token"], user


def _join(owner_token: str, pid: str, email: str, role: str) -> None:
    added = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": email, "role": role},
        headers=_auth(owner_token),
    )
    assert added.status_code == 200, added.text


def _review(token: str, pid: str, item: dict) -> dict:
    stored = _upload(token, pid, item, "cert_demo.pdf", "cert")
    sent = client.post(
        f"/v1/site/material-approvals/{item['id']}/status",
        json={"status": "in_review", "row_version": stored["row_version"]},
        headers=_auth(token),
    )
    assert sent.status_code == 200, sent.text
    return sent.json()["data"]


def test_roles_limit_decision_withdraw_and_delete(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    bin_no = "000000000094"
    owner_token, _owner_user = _owner("role-owner@example.com", bin_no)
    foreman_token, foreman = _person("role-foreman@example.com", bin_no, "foreman")
    approver_token, approver = _person("role-approver@example.com", bin_no, "supervisor")
    buyer_token, buyer = _person("role-buyer@example.com", bin_no, "procurement")
    pid = _project(owner_token, "Role yard")
    _flag(owner_token, True, 0)
    _join(owner_token, pid, foreman.email, "foreman")
    _join(owner_token, pid, approver.email, "supervisor")
    _join(owner_token, pid, buyer.email, "procurement")

    created = _create(foreman_token, pid, approver.id)
    assert created["author_id"] == foreman.id
    reviewing = _review(foreman_token, pid, created)
    for token in (buyer_token, owner_token, foreman_token):
        denied = client.post(
            f"/v1/site/material-approvals/{created['id']}/status",
            json={"status": "approved", "row_version": reviewing["row_version"]},
            headers=_auth(token),
        )
        assert denied.status_code == 403, denied.text
    approved = client.post(
        f"/v1/site/material-approvals/{created['id']}/status",
        json={"status": "approved", "row_version": reviewing["row_version"]},
        headers=_auth(approver_token),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "approved"

    draft = _create(foreman_token, pid, approver.id, id=str(uuid4()))
    for token in (buyer_token, approver_token):
        blocked = client.post(
            f"/v1/site/material-approvals/{draft['id']}/status",
            json={"status": "withdrawn", "row_version": draft["row_version"]},
            headers=_auth(token),
        )
        assert blocked.status_code == 403, blocked.text
    withdrawn = client.post(
        f"/v1/site/material-approvals/{draft['id']}/status",
        json={"status": "withdrawn", "row_version": draft["row_version"]},
        headers=_auth(foreman_token),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    owned = _create(foreman_token, pid, approver.id, id=str(uuid4()))
    by_owner = client.post(
        f"/v1/site/material-approvals/{owned['id']}/status",
        json={"status": "withdrawn", "row_version": owned["row_version"]},
        headers=_auth(owner_token),
    )
    assert by_owner.status_code == 200, by_owner.text

    removable = _create(foreman_token, pid, approver.id, id=str(uuid4()))
    for token in (foreman_token, buyer_token, approver_token):
        kept = client.post(
            f"/v1/site/material-approvals/{removable['id']}/delete",
            json={"row_version": removable["row_version"]},
            headers=_auth(token),
        )
        assert kept.status_code == 403, kept.text
    removed = client.post(
        f"/v1/site/material-approvals/{removable['id']}/delete",
        json={"row_version": removable["row_version"]},
        headers=_auth(owner_token),
    )
    assert removed.status_code == 200, removed.text
    assert client.get(f"/v1/site/material-approvals/{removable['id']}", headers=_auth(owner_token)).status_code == 404


def test_decision_link_is_single_use_and_revocable(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    bin_no = "000000000093"
    owner_token, owner = _owner("link-owner@example.com", bin_no)
    author_token, author = _person("link-author@example.com", bin_no, "foreman")
    approver_token, approver = _person("link-approver@example.com", bin_no, "supervisor")
    other_token, _other = _person("link-other@example.com", bin_no, "customer")
    pid = _project(owner_token, "Link yard")
    _flag(owner_token, True, 0)
    _join(owner_token, pid, author.email, "foreman")
    _join(owner_token, pid, approver.email, "supervisor")
    _join(owner_token, pid, "link-other@example.com", "customer")

    first = _review(author_token, pid, _create(author_token, pid, approver.id))
    second = _review(author_token, pid, _create(author_token, pid, approver.id, id=str(uuid4())))
    link = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{first['id']}/link",
        json={"id": str(uuid4()), "expires_in_days": 14},
        headers=_auth(author_token),
    )
    assert link.status_code == 200, link.text
    body = link.json()["data"]
    token = body["token"]
    assert len(token) >= 43
    from app.shares import token_hash
    from app.submittal_tables import material_approval_links, material_approvals

    with store._sql.factory() as session:
        stored = session.execute(
            select(material_approval_links).where(material_approval_links.c.id == body["id"])
        ).mappings().one()
    assert stored.token_sha256 == token_hash(token)
    assert token not in stored.token_sha256
    assert stored.entity_id == first["id"]
    assert stored.revoked_at is None

    refused = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{first['id']}/links/{body['id']}/revoke",
        headers=_auth(other_token),
    )
    assert refused.status_code == 403, refused.text
    opened = client.get(f"/v1/public/material/{token}")
    assert opened.status_code == 200, opened.text
    assert opened.headers["cache-control"] == "no-store"
    assert opened.headers["referrer-policy"] == "no-referrer"
    assert approver.id not in opened.text
    assert "link-author@example.com" not in opened.text
    assert "+7700" not in opened.text
    from app.log_redact import redact_text

    assert token not in redact_text(f"GET /v1/public/material/{token} /ru/r/material/{token}")

    from fastapi import HTTPException

    from app import submittal_service as svc

    try:
        svc.set_status(None, second["id"], "approved", second["row_version"], "", token_id=body["id"], token_version=1)
        crossed = False
    except HTTPException as exc:
        crossed = exc.status_code == 404
    assert crossed
    assert client.get(f"/v1/site/material-approvals/{second['id']}", headers=_auth(owner_token)).json()["data"]["status"] == "in_review"

    decided = client.post(f"/v1/public/material/{token}", json={"decision": "approved"})
    assert decided.status_code == 200, decided.text
    assert decided.headers["cache-control"] == "no-store"
    used = client.post(f"/v1/public/material/{token}", json={"decision": "rejected", "comment": "again"})
    assert used.status_code == 404
    assert used.headers["referrer-policy"] == "no-referrer"
    assert client.get(f"/v1/site/material-approvals/{second['id']}", headers=_auth(owner_token)).json()["data"]["status"] == "in_review"

    expiring = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(author_token),
    )
    assert expiring.status_code == 200, expiring.text
    expiring_id = expiring.json()["data"]["id"]
    expiring_token = expiring.json()["data"]["token"]
    with store._sql.factory() as session:
        session.execute(
            material_approval_links.update()
            .where(material_approval_links.c.id == expiring_id)
            .values(expires_at="2020-01-01T00:00:00+00:00")
        )
        session.commit()
    expired = client.get(f"/v1/public/material/{expiring_token}")
    assert expired.status_code == 410
    assert expired.headers["cache-control"] == "no-store"
    assert client.post(f"/v1/public/material/{expiring_token}", json={"decision": "approved"}).status_code == 410
    with store._sql.factory() as session:
        current = session.execute(
            select(material_approvals.c.row_version).where(material_approvals.c.id == second["id"])
        ).scalar()
    try:
        svc.set_status(
            None, second["id"], "approved", int(current), "", token_id=expiring_id, token_version=1
        )
        expired_direct = False
    except HTTPException as exc:
        expired_direct = exc.status_code == 410
    assert expired_direct

    spent = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(author_token),
    )
    spent_id = spent.json()["data"]["id"]
    spent_token = spent.json()["data"]["token"]
    with store._sql.factory() as session:
        current = session.execute(
            select(material_approvals.c.row_version).where(material_approvals.c.id == second["id"])
        ).scalar()
        session.execute(
            material_approval_links.update()
            .where(material_approval_links.c.id == spent_id)
            .values(used_at="2026-10-19T00:00:00+00:00")
        )
        session.commit()
    assert client.get(f"/v1/public/material/{spent_token}").status_code == 200
    assert client.post(f"/v1/public/material/{spent_token}", json={"decision": "approved"}).status_code == 410
    try:
        svc.set_status(None, second["id"], "approved", int(current), "", token_id=spent_id, token_version=1)
        spent_direct = False
    except HTTPException as exc:
        spent_direct = exc.status_code == 410
    assert spent_direct

    owned = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(author_token),
    )
    owned_id = owned.json()["data"]["id"]
    owned_token = owned.json()["data"]["token"]
    revoked = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/links/{owned_id}/revoke",
        headers=_auth(owner_token),
    )
    assert revoked.status_code == 200, revoked.text
    assert client.get(f"/v1/public/material/{owned_token}").status_code == 404
    assert client.post(f"/v1/public/material/{owned_token}", json={"decision": "approved"}).status_code == 404
    with store._sql.factory() as session:
        row = session.execute(
            select(material_approval_links).where(material_approval_links.c.id == owned_id)
        ).mappings().one()
    assert row.revoked_at
    assert row.deleted_at

    from app.ratelimit import material_link_limiter

    fresh = client.post(
        f"/v1/site/projects/{pid}/material-approvals/{second['id']}/link",
        json={"id": str(uuid4())},
        headers=_auth(author_token),
    )
    fresh_token = fresh.json()["data"]["token"]
    material_link_limiter.limit = 2
    try:
        ip = {"X-Forwarded-For": "203.0.113.10"}
        assert client.get(f"/v1/public/material/{fresh_token}", headers=ip).status_code == 200
        assert client.get(f"/v1/public/material/{fresh_token}", headers=ip).status_code == 200
        limited = client.get(f"/v1/public/material/{fresh_token}", headers=ip)
        assert limited.status_code == 429
        assert limited.headers["cache-control"] == "no-store"
        assert limited.headers["referrer-policy"] == "no-referrer"
        assert (
            client.get(f"/v1/public/material/{fresh_token}", headers={"X-Forwarded-For": "203.0.113.11"}).status_code
            == 200
        )
    finally:
        material_link_limiter.limit = 30
    del approver_token, owner


def test_requires_approval_clears_only_through_an_approved_card(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    bin_no = "000000000092"
    owner_token, _owner_user = _owner("clear-owner@example.com", bin_no)
    approver_token, approver = _person("clear-approver@example.com", bin_no, "supervisor")
    pid = _project(owner_token, "Clear yard")
    _flag(owner_token, True, 0)
    _join(owner_token, pid, approver.email, "supervisor")
    waiting = _review(owner_token, pid, _create(owner_token, pid, approver.id))
    quick = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": waiting["name"], "unit": waiting["unit"], "qty": 1},
        headers=_auth(owner_token),
    )
    assert quick.status_code == 200, quick.text
    lid = quick.json()["data"]["line"]["id"]
    marked = client.patch(
        f"/v1/procurement/lines/{lid}",
        json={"requires_approval": True, "approval_id": waiting["id"], "brand": waiting["brand"]},
        headers=_auth(owner_token),
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["data"]["requires_approval"] is True
    direct = client.patch(
        f"/v1/procurement/lines/{lid}",
        json={"requires_approval": False},
        headers=_auth(owner_token),
    )
    assert direct.status_code == 409, direct.text
    assert store.proc_lines[lid].requires_approval is True
    approved = client.post(
        f"/v1/site/material-approvals/{waiting['id']}/status",
        json={"status": "approved", "row_version": waiting["row_version"]},
        headers=_auth(approver_token),
    )
    assert approved.status_code == 200, approved.text
    still = client.patch(
        f"/v1/procurement/lines/{lid}",
        json={"requires_approval": False, "approval_id": waiting["id"]},
        headers=_auth(owner_token),
    )
    assert still.status_code == 409, still.text
    assert store.proc_lines[lid].requires_approval is True
    cleared = client.patch(
        f"/v1/procurement/lines/{lid}",
        json={"approval_id": waiting["id"]},
        headers=_auth(owner_token),
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["requires_approval"] is False
    assert cleared.json()["data"]["approval_id"] == waiting["id"]
    paths = app.openapi()["paths"]
    assert not any("clear" in path and "approval" in path for path in paths)


def test_enabling_submittals_does_not_block_inflight_lines(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")
    bin_no = "000000000091"
    owner_token, owner = _owner("flight-owner@example.com", bin_no)
    approver_token, approver = _person("flight-approver@example.com", bin_no, "supervisor")
    buyer_token, _buyer = _person("flight-buyer@example.com", bin_no, "procurement")
    pid = _project(owner_token, "Flight yard")
    _join(owner_token, pid, approver.email, "supervisor")
    _join(owner_token, pid, "flight-buyer@example.com", "procurement")

    sent = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": "Sent board", "unit": "шт", "qty": 2},
        headers=_auth(owner_token),
    )
    assert sent.status_code == 200, sent.text
    sent_line = sent.json()["data"]["line"]["id"]
    sent_request = sent.json()["data"]["request"]["id"]
    assert sent.json()["data"]["line"]["requires_approval"] is False
    assert sent.json()["data"]["request"]["status"] == "collecting"

    paying = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": "Pay board", "unit": "шт", "qty": 1},
        headers=_auth(owner_token),
    )
    pay_line = paying.json()["data"]["line"]["id"]
    pay_request = paying.json()["data"]["request"]["id"]
    offer = client.post(
        f"/v1/procurement/lines/{pay_line}/offers",
        json={"supplier_name": FIXTURE["suppliers"][0]["name"], "price_kzt": 100, "vat_included": True},
        headers=_auth(owner_token),
    )
    assert offer.status_code == 200, offer.text
    chosen = client.post(
        f"/v1/procurement/lines/{pay_line}/select",
        json={"offer_id": offer.json()["data"]["id"]},
        headers=_auth(owner_token),
    )
    assert chosen.status_code == 200, chosen.text
    assert store.proc_requests[pay_request].status == "decided"

    from app.procurement_models import ProcLine

    def _draft_line(title: str) -> str:
        created_request = client.post(
            f"/v1/procurement/projects/{pid}/requests",
            json={"title": title},
            headers=_auth(owner_token),
        )
        assert created_request.status_code == 200, created_request.text
        line_id = uuid4().hex
        store.proc_lines[line_id] = ProcLine(
            id=line_id,
            request_id=created_request.json()["data"]["id"],
            pos_no="1",
            title=title,
            unit="шт",
            qty=1,
        )
        assert store.proc_requests[created_request.json()["data"]["id"]].status == "draft"
        return line_id

    waiting_id = _draft_line("Loose board")
    linked_id = _draft_line("Marked board")

    _flag(owner_token, True, 0)
    assert store.proc_lines[sent_line].requires_approval is False
    assert store.proc_lines[pay_line].requires_approval is False
    assert store.proc_lines[waiting_id].requires_approval is False

    supplier = User(
        id="u-flight-sup",
        email="flight-sup@example.com",
        full_name=FIXTURE["suppliers"][0]["name"],
        role="supplier",
        company=FIXTURE["suppliers"][0]["name"],
        phone=FIXTURE["suppliers"][0]["phone"],
    )
    store._index_user(supplier)
    from app.authutil import hash_password

    store.credentials[supplier.id] = hash_password("secret12")
    supplier_login = client.post(
        "/v1/auth/login",
        json={"email": supplier.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    supplier_token = supplier_login.json()["data"]["token"]
    inbox = client.get("/v1/procurement/inbox", headers=_auth(supplier_token))
    visible = [line["id"] for row in inbox.json()["data"] for line in row["lines"]]
    assert sent_line in visible
    assert pay_line not in visible
    still_open = client.post(
        f"/v1/procurement/lines/{sent_line}/offers",
        json={"supplier_name": FIXTURE["suppliers"][0]["name"], "price_kzt": 90, "vat_included": True},
        headers=_auth(owner_token),
    )
    assert still_open.status_code == 200, still_open.text

    for lid in (sent_line, pay_line):
        denied = client.patch(
            f"/v1/procurement/lines/{lid}",
            json={"requires_approval": True},
            headers=_auth(owner_token),
        )
        assert denied.status_code == 409, denied.text
        assert store.proc_lines[lid].requires_approval is False
    visible_after = [
        line["id"]
        for row in client.get("/v1/procurement/inbox", headers=_auth(supplier_token)).json()["data"]
        for line in row["lines"]
    ]
    assert sent_line in visible_after
    sheet = client.get(f"/v1/procurement/requests/{pay_request}/sheet", headers=_auth(owner_token))
    assert sheet.status_code == 200, sheet.text
    paid = next(row for row in sheet.json()["data"]["lines"] if row["id"] == pay_line)
    assert not paid.get("needs_approval")

    fresh = client.post(
        f"/v1/procurement/projects/{pid}/quick",
        json={"title": "New board", "unit": "шт", "qty": 1},
        headers=_auth(owner_token),
    )
    assert fresh.status_code == 200, fresh.text
    fresh_line = fresh.json()["data"]["line"]["id"]
    assert fresh.json()["data"]["line"]["requires_approval"] is True
    hidden = [
        line["id"]
        for row in client.get("/v1/procurement/inbox", headers=_auth(supplier_token)).json()["data"]
        for line in row["lines"]
    ]
    assert fresh_line not in hidden

    blocked = client.patch(
        f"/v1/procurement/lines/{waiting_id}",
        json={"requires_approval": True},
        headers=_auth(buyer_token),
    )
    assert blocked.status_code == 403, blocked.text
    assert store.proc_lines[waiting_id].requires_approval is False
    marked = client.patch(
        f"/v1/procurement/lines/{waiting_id}",
        json={"requires_approval": True},
        headers=_auth(owner_token),
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["data"]["requires_approval"] is True

    card = _create(owner_token, pid, approver.id)
    store.proc_lines[linked_id].approval_id = card["id"]
    assert store.proc_requests[store.proc_lines[linked_id].request_id].status == "draft"
    assert store.proc_lines[linked_id].requires_approval is False
    outsider = client.patch(
        f"/v1/procurement/lines/{linked_id}",
        json={"requires_approval": True},
        headers=_auth(buyer_token),
    )
    assert outsider.status_code == 403, outsider.text
    by_approver = client.patch(
        f"/v1/procurement/lines/{linked_id}",
        json={"requires_approval": True},
        headers=_auth(approver_token),
    )
    assert by_approver.status_code == 200, by_approver.text
    assert by_approver.json()["data"]["requires_approval"] is True
    del owner, sent_request
