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
    connection.close()
    assert "data/db.json" not in Path(__file__).read_text(encoding="utf-8")
