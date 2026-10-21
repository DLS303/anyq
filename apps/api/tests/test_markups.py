"""Drawing markups: tenant isolation, compare-and-set, and cleaned photos."""

import io
import os
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import text

from app.company_features import project_company_id
from app.drawing_models import StoredFile
from app.main import app
from app.markup_models import MarkupRow
from app.paths import publish_upload, resolve_stored_file, stage_upload
from app.store import store

client = TestClient(app)
BIN_A = "520000000001"
BIN_B = "520000000002"


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "0")


def _pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=240, height=160)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _jpeg() -> bytes:
    image = Image.new("RGB", (24, 16), (20, 40, 60))
    exif = image.getexif()
    exif[270] = "SYNTH-MARK-77"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
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


def _enable(token: str, enabled: bool = True, row_version: int = 0) -> dict:
    res = client.post(
        "/v1/org/features",
        json={"key": "drawings", "enabled": enabled, "row_version": row_version},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _sheet(token: str, pid: str) -> dict:
    res = client.post(
        f"/v1/site/projects/{pid}/drawings",
        headers=_auth(token),
        data={
            "id": str(uuid4()),
            "revision_id": str(uuid4()),
            "file_id": str(uuid4()),
            "title": "Level plan",
            "row_version": "0",
        },
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _arrow(x1: float = 0.1, y1: float = 0.2, x2: float = 0.4, y2: float = 0.5) -> dict:
    return {"type": "arrow", "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _post(token: str, revision_id: str, shapes: list, **extra):
    payload = {
        "id": extra.pop("id", str(uuid4())),
        "shapes": shapes,
        "visibility": extra.pop("visibility", "project"),
        "row_version": extra.pop("row_version", 0),
        "company_id": "bin:999999999999",
        "created_by": "Synthetic Person",
    }
    payload.update(extra)
    return client.post(
        f"/v1/site/revisions/{revision_id}/markups",
        headers=_auth(token),
        json=payload,
    )


def test_storage_key_is_server_generated_and_publish_does_not_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_DATA_DIR", str(tmp_path))
    client_id = str(uuid4())
    key, staged = stage_upload("markup_photo", b"kept")
    assert client_id not in key
    assert client_id.replace("-", "") not in key
    assert ".part-" not in key
    publish_upload("markup_photo", key, staged)
    _other, again = stage_upload("markup_photo", b"replaced")
    with pytest.raises(FileExistsError):
        publish_upload("markup_photo", key, again)
    assert resolve_stored_file("markup_photo", key).read_bytes() == b"kept"
    assert not staged.exists()
    assert not again.exists()


def test_foreign_company_query_and_customer_are_blocked():
    owner = _register("markup-owner@example.com", BIN_A)
    _promote("markup-owner@example.com", "owner")
    other = _register("markup-other@example.com", BIN_B)
    _promote("markup-other@example.com", "owner")
    guest = _register("markup-guest@example.com", BIN_A)
    customer = _register("markup-customer@example.com", BIN_A)
    crew = _register("markup-crew@example.com", BIN_A)
    pid = _project(owner["token"], "North yard")
    other_pid = _project(other["token"], "South yard")
    flag = _enable(owner["token"])
    _enable(other["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    off = _enable(owner["token"], False, flag["row_version"])
    hidden = client.get(
        f"/v1/site/revisions/{revision_id}/markups?pid={other_pid}",
        headers=_auth(owner["token"]),
    )
    assert hidden.status_code == 404, hidden.text
    blocked = _post(owner["token"], revision_id, [_arrow()])
    assert blocked.status_code == 404, blocked.text
    _enable(owner["token"], True, off["row_version"])
    seated = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "markup-crew@example.com", "role": "foreman"},
        headers=_auth(owner["token"]),
    )
    assert seated.status_code == 200, seated.text
    watched = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "markup-customer@example.com", "role": "customer"},
        headers=_auth(owner["token"]),
    )
    assert watched.status_code == 200, watched.text

    created = _post(owner["token"], revision_id, [_arrow()], visibility="project")
    assert created.status_code == 200, created.text
    saved = created.json()["data"]
    user = store.get_user_by_email("markup-owner@example.com")
    assert user is not None
    assert saved["company_id"] == project_company_id(store.get_project(pid))
    assert saved["company_id"] != "bin:999999999999"
    assert saved["project_id"] == pid
    assert saved["revision_id"] == revision_id
    assert saved["author_id"] == user.id
    assert saved["created_by"] == user.id
    assert saved["updated_by"] == user.id
    assert saved["created_by"] != "Synthetic Person"
    assert saved["row_version"] == 1
    assert saved["deleted_at"] is None
    assert saved["updated_at"].endswith("+00:00")
    assert saved["file_id"] is None
    assert "storage_key" not in created.text
    assert "/private" not in created.text

    same = client.get(
        f"/v1/site/revisions/{revision_id}/markups?pid={other_pid}",
        headers=_auth(owner["token"]),
    )
    assert same.status_code == 200, same.text
    assert same.json()["data"]["markups"][0]["project_id"] == pid
    assert same.json()["data"]["can_write"] is True

    foreign_read = client.get(
        f"/v1/site/revisions/{revision_id}/markups?pid={pid}",
        headers=_auth(other["token"]),
    )
    assert foreign_read.status_code == 404, foreign_read.text
    foreign_write = _post(other["token"], revision_id, [_arrow()])
    assert foreign_write.status_code == 404, foreign_write.text
    outsider = client.get(
        f"/v1/site/revisions/{revision_id}/markups?pid={other_pid}",
        headers=_auth(guest["token"]),
    )
    assert outsider.status_code == 404, outsider.text

    looked = client.get(f"/v1/site/revisions/{revision_id}/markups", headers=_auth(customer["token"]))
    assert looked.status_code == 200, looked.text
    assert looked.json()["data"]["can_write"] is False
    denied = _post(customer["token"], revision_id, [_arrow()])
    assert denied.status_code == 403, denied.text
    noted = _post(crew["token"], revision_id, [_arrow(0.2, 0.2, 0.3, 0.3)])
    assert noted.status_code == 200, noted.text


def test_compare_and_set_audit_and_archived_revision(monkeypatch):
    owner = _register("markup-rev@example.com", "520000000004")
    _promote("markup-rev@example.com", "owner")
    mate = _register("markup-mate@example.com", "520000000004")
    pid = _project(owner["token"], "Revision yard")
    _enable(owner["token"])
    added = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "markup-mate@example.com", "role": "supervisor"},
        headers=_auth(owner["token"]),
    )
    assert added.status_code == 200, added.text
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    markup_id = str(uuid4())
    mismatch = _post(owner["token"], revision_id, [_arrow()], id=markup_id, row_version=2)
    assert mismatch.status_code == 409, mismatch.text
    private = _post(
        owner["token"],
        revision_id,
        [{"type": "text", "x": 0.2, "y": 0.3, "text": "Call +77019990000"}],
        id=markup_id,
        visibility="me",
    )
    assert private.status_code == 200, private.text
    hidden = client.get(f"/v1/site/revisions/{revision_id}/markups", headers=_auth(mate["token"]))
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["data"]["markups"] == []
    stale = _post(
        owner["token"],
        revision_id,
        [_arrow()],
        id=markup_id,
        row_version=1,
        visibility="project",
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["data"]["row_version"] == 2
    assert stale.json()["data"]["updated_by"] == store.get_user_by_email("markup-rev@example.com").id
    conflict = _post(owner["token"], revision_id, [_arrow()], id=markup_id, row_version=1, visibility="project")
    assert conflict.status_code == 409, conflict.text
    with store._sql.factory() as session:
        audit = session.execute(
            text("SELECT action, changes FROM audit_log WHERE entity_id = :id ORDER BY id"),
            {"id": markup_id},
        ).all()
    assert len(audit) == 2
    assert {row.action for row in audit} == {"markup.write"}
    blob = " ".join(str(row.changes) for row in audit)
    assert "77019990000" not in blob
    assert "storage_key" not in blob
    assert "Synthetic" not in blob

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("app.markups.audit_write", boom)
    failed_id = str(uuid4())
    with pytest.raises(RuntimeError, match="audit failed"):
        _post(owner["token"], revision_id, [_arrow()], id=failed_id)
    with store._sql.factory() as session:
        assert session.get(MarkupRow, failed_id) is None

    nxt = client.post(
        f"/v1/site/drawings/{sheet['id']}/revisions",
        headers=_auth(owner["token"]),
        data={"id": str(uuid4()), "file_id": str(uuid4()), "rev": "B", "row_version": "1"},
        files={"file": ("level.pdf", _pdf(), "application/pdf")},
    )
    assert nxt.status_code == 200, nxt.text
    body = nxt.json()["data"]
    current_id = next(item["id"] for item in body["revisions"] if item["is_current"])
    archived = client.get(f"/v1/site/revisions/{revision_id}/markups", headers=_auth(owner["token"]))
    assert archived.status_code == 200, archived.text
    assert len(archived.json()["data"]["markups"]) == 1
    empty = client.get(f"/v1/site/revisions/{current_id}/markups", headers=_auth(owner["token"]))
    assert empty.status_code == 200, empty.text
    assert empty.json()["data"]["markups"] == []


def test_photo_strips_exif_and_file_link_stays_on_the_revision():
    owner = _register("markup-photo@example.com", "520000000005")
    _promote("markup-photo@example.com", "owner")
    other = _register("markup-photo-other@example.com", "520000000006")
    _promote("markup-photo-other@example.com", "owner")
    pid = _project(owner["token"], "Photo yard")
    other_pid = _project(other["token"], "Other yard")
    _enable(owner["token"])
    _enable(other["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    file_id = str(uuid4())
    markup_id = str(uuid4())
    raw = _jpeg()
    assert b"SYNTH-MARK-77" in raw
    payload = {
        "id": markup_id,
        "row_version": 0,
        "visibility": "project",
        "company_id": "bin:999999999999",
        "shapes": [{"type": "photo", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "file_id": file_id}],
    }
    import json

    saved = client.post(
        f"/v1/site/revisions/{revision_id}/markups?pid={other_pid}",
        headers=_auth(owner["token"]),
        data={"payload": json.dumps(payload)},
        files={"file": ("shot.jpg", raw, "image/jpeg")},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()["data"]
    assert body["file_id"] == file_id
    assert body["project_id"] == pid
    assert body["shapes"][0]["file_id"] == file_id
    assert "storage_key" not in saved.text
    with store._sql.factory() as session:
        stored = session.get(StoredFile, file_id)
        assert stored is not None
        assert stored.meta_stripped is True
        assert stored.kind == "markup_photo"
        assert file_id not in stored.storage_key
        assert file_id.replace("-", "") not in stored.storage_key
        owner_user = store.get_user_by_email("markup-photo@example.com")
        assert owner_user is not None
        assert stored.created_by == owner_user.id
        assert stored.updated_by == owner_user.id
        parts = list(stored.storage_key)
    assert ".part-" not in "".join(parts)
    link = f"/v1/site/revisions/{revision_id}/markups/files/{file_id}"
    own = client.get(f"{link}?pid={other_pid}", headers=_auth(owner["token"]))
    assert own.status_code == 200, own.text
    assert 'filename="photo.jpg"' in own.headers["content-disposition"]
    assert b"SYNTH-MARK-77" not in own.content
    assert len(Image.open(io.BytesIO(own.content)).getexif()) == 0
    foreign = client.get(f"{link}?pid={pid}", headers=_auth(other["token"]))
    assert foreign.status_code == 404, foreign.text
    missing = client.get(
        f"/v1/site/revisions/{revision_id}/markups/files/{uuid4()}?pid={pid}",
        headers=_auth(owner["token"]),
    )
    assert missing.status_code == 404, missing.text


def _image(fmt: str) -> bytes:
    image = Image.new("RGB", (12, 8), (8, 16, 24))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _photo_post(token: str, revision_id: str, file_id: str, raw: bytes, name: str, mime: str, **extra):
    import json

    payload = {
        "id": extra.pop("id", str(uuid4())),
        "row_version": extra.pop("row_version", 0),
        "visibility": "project",
        "shapes": [{"type": "photo", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "file_id": file_id}],
    }
    return client.post(
        f"/v1/site/revisions/{revision_id}/markups",
        headers=_auth(token),
        data={"payload": json.dumps(payload)},
        files={"file": (name, raw, mime)},
    )


def test_delete_tombstone_repeat_and_other_company():
    owner = _register("markup-del@example.com", "520000000007")
    _promote("markup-del@example.com", "owner")
    other = _register("markup-del-other@example.com", "520000000008")
    _promote("markup-del-other@example.com", "owner")
    pid = _project(owner["token"], "Delete yard")
    _project(other["token"], "Elsewhere")
    _enable(owner["token"])
    _enable(other["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    markup_id = str(uuid4())
    created = _post(owner["token"], revision_id, [_arrow()], id=markup_id)
    assert created.status_code == 200, created.text
    version = created.json()["data"]["row_version"]
    path = f"/v1/site/revisions/{revision_id}/markups/{markup_id}"
    foreign = client.delete(f"{path}?row_version={version}&pid={pid}", headers=_auth(other["token"]))
    assert foreign.status_code == 404, foreign.text
    removed = client.delete(f"{path}?row_version={version}", headers=_auth(owner["token"]))
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["deleted_at"].endswith("+00:00")
    assert removed.json()["data"]["row_version"] == version + 1
    again = client.delete(f"{path}?row_version={version}", headers=_auth(owner["token"]))
    assert again.status_code == 409, again.text
    listed = client.get(f"/v1/site/revisions/{revision_id}/markups", headers=_auth(owner["token"]))
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["markups"] == []
    with store._sql.factory() as session:
        audit = session.execute(
            text("SELECT action, changes FROM audit_log WHERE entity_id = :id AND action = 'markup.delete'"),
            {"id": markup_id},
        ).all()
    assert len(audit) == 1
    assert "storage_key" not in str(audit[0].changes)


def test_delete_then_stale_update_conflicts():
    owner = _register("markup-stale-del@example.com", "520000000012")
    _promote("markup-stale-del@example.com", "owner")
    pid = _project(owner["token"], "Stale delete yard")
    _enable(owner["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    markup_id = str(uuid4())
    created = _post(owner["token"], revision_id, [_arrow()], id=markup_id)
    assert created.status_code == 200, created.text
    version = created.json()["data"]["row_version"]
    path = f"/v1/site/revisions/{revision_id}/markups/{markup_id}"
    removed = client.delete(f"{path}?row_version={version}", headers=_auth(owner["token"]))
    assert removed.status_code == 200, removed.text
    assert removed.json()["data"]["row_version"] == version + 1
    stale = _post(owner["token"], revision_id, [_arrow(0.2, 0.2, 0.3, 0.3)], id=markup_id, row_version=version)
    assert stale.status_code == 409, stale.text
    fresh = _post(
        owner["token"],
        revision_id,
        [_arrow(0.2, 0.2, 0.3, 0.3)],
        id=markup_id,
        row_version=version + 1,
    )
    assert fresh.status_code == 404, fresh.text
    listed = client.get(f"/v1/site/revisions/{revision_id}/markups", headers=_auth(owner["token"]))
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"]["markups"] == []
    with store._sql.factory() as session:
        row = session.get(MarkupRow, markup_id)
    assert row is not None
    assert row.deleted_at is not None
    assert row.row_version == version + 1


def test_concurrent_delete_one_writer():
    owner = _register("markup-race-del@example.com", "520000000013")
    _promote("markup-race-del@example.com", "owner")
    pid = _project(owner["token"], "Race delete yard")
    _enable(owner["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    markup_id = str(uuid4())
    created = _post(owner["token"], revision_id, [_arrow()], id=markup_id)
    assert created.status_code == 200, created.text
    version = created.json()["data"]["row_version"]
    path = f"/v1/site/revisions/{revision_id}/markups/{markup_id}?row_version={version}"
    barrier = threading.Barrier(2)

    def once():
        barrier.wait()
        return client.delete(path, headers=_auth(owner["token"]))

    with ThreadPoolExecutor(max_workers=2) as pool:
        done = list(pool.map(lambda _item: once(), (0, 1)))
    assert sorted(item.status_code for item in done) == [200, 409]
    winner = next(item for item in done if item.status_code == 200)
    assert winner.json()["data"]["row_version"] == version + 1
    with store._sql.factory() as session:
        row = session.get(MarkupRow, markup_id)
        audit = session.execute(
            text("SELECT action FROM audit_log WHERE entity_id = :id AND action = 'markup.delete'"),
            {"id": markup_id},
        ).all()
    assert row is not None
    assert row.deleted_at is not None
    assert row.row_version == version + 1
    assert len(audit) == 1


def test_other_company_file_and_download_names():
    owner = _register("markup-kind@example.com", "520000000009")
    _promote("markup-kind@example.com", "owner")
    other = _register("markup-kind-other@example.com", "520000000010")
    _promote("markup-kind-other@example.com", "owner")
    pid = _project(owner["token"], "Kind yard")
    other_pid = _project(other["token"], "Other kind")
    _enable(owner["token"])
    _enable(other["token"])
    sheet = _sheet(owner["token"], pid)
    other_sheet = _sheet(other["token"], other_pid)
    revision_id = sheet["revisions"][0]["id"]
    other_revision = other_sheet["revisions"][0]["id"]
    file_id = str(uuid4())
    saved = _photo_post(owner["token"], revision_id, file_id, _jpeg(), "shot.jpg", "image/jpeg")
    assert saved.status_code == 200, saved.text
    with store._sql.factory() as session:
        stored = session.get(StoredFile, file_id)
        assert stored is not None
        kept = resolve_stored_file(stored.kind, stored.storage_key).read_bytes()
        key = stored.storage_key
    stolen = _photo_post(other["token"], other_revision, file_id, _jpeg(), "shot.jpg", "image/jpeg")
    assert stolen.status_code == 404, stolen.text
    assert resolve_stored_file("markup_photo", key).read_bytes() == kept
    for fmt, name, mime, filename in (
        ("PNG", "shot.png", "image/png", "photo.png"),
        ("WEBP", "shot.webp", "image/webp", "photo.webp"),
    ):
        photo_id = str(uuid4())
        created = _photo_post(owner["token"], revision_id, photo_id, _image(fmt), name, mime)
        assert created.status_code == 200, created.text
        fetched = client.get(
            f"/v1/site/revisions/{revision_id}/markups/files/{photo_id}",
            headers=_auth(owner["token"]),
        )
        assert fetched.status_code == 200, fetched.text
        assert f'filename="{filename}"' in fetched.headers["content-disposition"]
        assert Image.open(io.BytesIO(fetched.content)).format == fmt


def test_duplicate_file_insert_is_a_conflict(monkeypatch):
    from sqlalchemy.orm import Session

    owner = _register("markup-dup@example.com", "520000000011")
    _promote("markup-dup@example.com", "owner")
    pid = _project(owner["token"], "Dup yard")
    _enable(owner["token"])
    sheet = _sheet(owner["token"], pid)
    revision_id = sheet["revisions"][0]["id"]
    file_id = str(uuid4())
    first = _photo_post(owner["token"], revision_id, file_id, _jpeg(), "shot.jpg", "image/jpeg")
    assert first.status_code == 200, first.text
    original = Session.get

    def hide_existing(self, entity, ident, **kwargs):
        if entity is StoredFile and str(ident) == file_id:
            return None
        return original(self, entity, ident, **kwargs)

    monkeypatch.setattr(Session, "get", hide_existing)
    second = _photo_post(owner["token"], revision_id, file_id, _jpeg(), "shot.jpg", "image/jpeg")
    assert second.status_code == 409, second.text


def test_upload_limit_stops_before_the_rest_of_the_body(monkeypatch):
    import asyncio

    from starlette.datastructures import Headers

    from app.routers.markups import _form_parts

    monkeypatch.setattr("app.routers.markups.MAX_UPLOAD_BYTES", 32)
    boundary = "limitbound"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="payload"\r\n\r\n'
        '{"id":"x"}\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="big.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    body = head + (b"x" * 8000) + f"\r\n--{boundary}--\r\n".encode()
    chunks = [body[index : index + 64] for index in range(0, len(body), 64)]
    pulled = {"n": 0}

    async def stream():
        for chunk in chunks:
            pulled["n"] += len(chunk)
            yield chunk

    async def run():
        with pytest.raises(HTTPException) as caught:
            await _form_parts(Headers({"content-type": f"multipart/form-data; boundary={boundary}"}), stream())
        assert caught.value.status_code == 413

    asyncio.run(run())
    assert pulled["n"] < len(body)


def test_alembic_markup_revision_is_the_only_head(tmp_path):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = os.path.join(os.path.dirname(__file__), "..")
    script = ScriptDirectory.from_config(Config(os.path.join(root, "alembic.ini")))
    assert script.get_heads() == ["20261019_0008_pf1b"]
    revision = script.get_revision("20261019_0008_pf1b")
    assert revision.down_revision == "20261019_0003_pf1a"

    db = tmp_path / "markups.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "downgrade", "-1"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "check"], cwd=root, env=env)
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "markups" in tables
    columns = {row[1] for row in connection.execute("PRAGMA table_info(markups)")}
    assert {
        "id",
        "company_id",
        "project_id",
        "revision_id",
        "author_id",
        "file_id",
        "shapes",
        "visibility",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "row_version",
        "deleted_at",
    } <= columns
    indexes = {
        row[0]: row[1] or ""
        for row in connection.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")
    }
    assert "company_id" in indexes["ix_markups_company_updated"]
    assert "updated_at" in indexes["ix_markups_company_updated"]
    assert "revision_id" in indexes["ix_markups_revision_created"]
    assert "created_at" in indexes["ix_markups_revision_created"]
    assert "file_id" in indexes["ix_markups_file_id"]
    connection.close()
