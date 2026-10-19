"""Upgrade a database that still has pre-PR company keys, then check the live API.

The fixture is inserted at revision 20261019_0001b_store_fixes. Users have a
BIN and a records.company_key, and no stored company_key in the payload.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import uuid4


def _user(doc_id: str, email: str, bin_no: str, company: str) -> dict:
    return {
        "id": doc_id,
        "email": email,
        "full_name": company,
        "role": "owner" if doc_id == "u-legacy" else "buyer",
        "phone": "+77001110001",
        "company": company,
        "company_bin": bin_no,
        "city": "Almaty",
        "pilot": "",
    }


def _insert(conn, collection: str, doc_id: str, payload: dict, **columns) -> None:
    from sqlalchemy import text

    conn.execute(
        text(
            "INSERT INTO records ("
            "collection, doc_id, project_id, company_key, owner_id, user_id, "
            "email, search_text, seq, row_version, payload"
            ") VALUES ("
            ":collection, :doc_id, :project_id, :company_key, :owner_id, :user_id, "
            ":email, '', :seq, 1, :payload)"
        ),
        {
            "collection": collection,
            "doc_id": doc_id,
            "project_id": columns.get("project_id"),
            "company_key": columns.get("company_key"),
            "owner_id": columns.get("owner_id"),
            "user_id": columns.get("user_id"),
            "email": columns.get("email"),
            "seq": columns["seq"],
            "payload": json.dumps(payload, ensure_ascii=False),
        },
    )


def _seed(url: str) -> None:
    from sqlalchemy import create_engine, text

    from app.authutil import hash_password

    legacy = _user(
        "u-legacy", "legacy-owner@example.com", "880000000001", "Legacy Yard LLP"
    )
    split_a = _user("u-split-a", "split-a@example.com", "770000000001", "Split A")
    split_b = _user("u-split-b", "split-b@example.com", "770000000001", "Split B")
    project = {
        "id": "prj-legacy",
        "slug": "legacy-yard",
        "title": "Legacy Yard",
        "owner_id": "u-legacy",
        "address": "Test street",
        "status": "active",
        "start": "",
        "finish": "",
    }
    contact = {
        "id": "cnt-secret",
        "name": "Secret Client",
        "phone": "+77001110002",
        "owner_id": "u-legacy",
        "created_at": "2026-10-01T00:00:00+00:00",
        "company_name": "Hidden",
        "city": "Almaty",
        "contact_type": "client",
    }
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        _insert(
            conn,
            "users",
            "u-legacy",
            legacy,
            company_key="bin:880000000001",
            email=legacy["email"],
            seq=1,
        )
        _insert(
            conn,
            "users",
            "u-split-a",
            split_a,
            company_key="bin:770000000001",
            email=split_a["email"],
            seq=2,
        )
        _insert(
            conn,
            "users",
            "u-split-b",
            split_b,
            company_key="name:split-b",
            email=split_b["email"],
            seq=3,
        )
        _insert(
            conn,
            "projects",
            "prj-legacy",
            project,
            company_key="bin:880000000001",
            owner_id="u-legacy",
            project_id="prj-legacy",
            seq=4,
        )
        _insert(
            conn,
            "crm_contacts",
            "cnt-secret",
            contact,
            company_key="bin:880000000001",
            owner_id="u-legacy",
            seq=5,
        )
        _insert(
            conn,
            "credentials",
            "u-legacy",
            {"password_hash": hash_password("secret12")},
            seq=6,
        )
        conn.execute(
            text(
                "INSERT INTO invitations ("
                "id, token_hash, role, company_key, company, company_bin, "
                "project_id, invited_by, created_at, expires_at"
                ") VALUES ("
                "'inv-legacy', :token_a, 'buyer', 'bin:880000000001', 'Legacy Yard LLP', "
                "'880000000001', 'prj-legacy', 'u-legacy', "
                "'2026-10-01T00:00:00+00:00', '2026-11-01T00:00:00+00:00')"
            ),
            {"token_a": "a" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO invitations ("
                "id, token_hash, role, company_key, company, company_bin, "
                "invited_by, created_at, expires_at"
                ") VALUES ("
                "'inv-split', :token_b, 'buyer', 'name:split-b', 'Split B', "
                "'770000000001', 'u-split-b', "
                "'2026-10-01T00:00:00+00:00', '2026-11-01T00:00:00+00:00')"
            ),
            {"token_b": "b" * 64},
        )
    engine.dispose()


def _assert_backfill(url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(url, future=True)
    with engine.connect() as conn:
        legacy = conn.execute(
            text(
                "SELECT company_key, payload FROM records WHERE collection = 'users' AND doc_id = 'u-legacy'"
            )
        ).one()
        project = conn.execute(
            text(
                "SELECT company_key FROM records WHERE collection = 'projects' AND doc_id = 'prj-legacy'"
            )
        ).scalar()
        contact = conn.execute(
            text(
                "SELECT company_key FROM records WHERE collection = 'crm_contacts' AND doc_id = 'cnt-secret'"
            )
        ).scalar()
        invite = conn.execute(
            text("SELECT company_key FROM invitations WHERE id = 'inv-legacy'")
        ).scalar()
        split_invite = conn.execute(
            text("SELECT company_key FROM invitations WHERE id = 'inv-split'")
        ).scalar()
        split_a = conn.execute(
            text(
                "SELECT company_key, payload FROM records WHERE collection = 'users' AND doc_id = 'u-split-a'"
            )
        ).one()
        split_b = conn.execute(
            text(
                "SELECT company_key, payload FROM records WHERE collection = 'users' AND doc_id = 'u-split-b'"
            )
        ).one()
        keys = {
            row[0]
            for row in conn.execute(text("SELECT legacy_key FROM companies")).all()
        }
    engine.dispose()
    payload = (
        json.loads(legacy.payload)
        if isinstance(legacy.payload, str)
        else legacy.payload
    )
    assert legacy.company_key == "bin:880000000001"
    assert payload["company_key"] == "bin:880000000001"
    assert payload["company_review"] is False
    assert project == "bin:880000000001"
    assert contact == "bin:880000000001"
    assert invite == "bin:880000000001"
    assert "bin:880000000001" in keys
    for row in (split_a, split_b):
        body = json.loads(row.payload) if isinstance(row.payload, str) else row.payload
        assert row.company_key.startswith("user:")
        assert body["company_review"] is True
    assert split_invite == "user:u-split-b"
    assert "bin:770000000001" not in keys


def _assert_api() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    login = client.post(
        "/v1/auth/login",
        json={
            "email": "legacy-owner@example.com",
            "password": "secret12",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    owner = login.json()["data"]["token"]
    auth = {"Authorization": f"Bearer {owner}"}
    opened = client.post(
        "/v1/org/features",
        json={"key": "rfi", "enabled": True, "row_version": 0},
        headers=auth,
    )
    assert opened.status_code == 200, opened.text
    bundle = client.get("/v1/site/projects/prj-legacy/bundle", headers=auth)
    assert bundle.status_code == 200, bundle.text
    assert bundle.json()["data"]["features"]["rfi"] is True
    created = client.post(
        "/v1/site/projects/prj-legacy/rfis",
        json={
            "id": str(uuid4()),
            "title": "Door swing",
            "question": "Which way does it open?",
        },
        headers=auth,
    )
    assert created.status_code == 200, created.text
    own_contacts = client.get("/v1/crm/contacts", headers=auth)
    assert own_contacts.status_code == 200, own_contacts.text
    assert any(row["name"] == "Secret Client" for row in own_contacts.json()["data"])
    registered = client.post(
        "/v1/auth/register",
        json={
            "email": "same-bin@example.com",
            "password": "secret12",
            "full_name": "Same BIN",
            "phone": "+77001110009",
            "company": "Other Yard LLP",
            "company_bin": "880000000001",
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert registered.status_code == 200, registered.text
    foreign = client.get(
        "/v1/crm/contacts",
        headers={"Authorization": f"Bearer {registered.json()['data']['token']}"},
    )
    assert foreign.status_code == 200, foreign.text
    assert all(row["name"] != "Secret Client" for row in foreign.json()["data"])


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    root = Path(tempfile.mkdtemp(prefix="anyq-pre-pr-"))
    os.environ["ANYQ_DB_PATH"] = str(root / "db.json")
    os.environ.pop("DATABASE_URL", None)
    os.environ["ANYQ_DEMO_MODE"] = "0"
    os.environ["ANYQ_DEMO_PASSWORD"] = ""
    os.environ["ANYQ_ENV"] = "development"
    os.environ["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"

    from alembic.config import Config

    from alembic import command
    from app.sql_backend import resolve_database_url

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(cfg, "20261019_0001b_store_fixes")
    url = resolve_database_url()
    _seed(url)
    command.upgrade(cfg, "head")
    _assert_backfill(url)
    _assert_api()


if __name__ == "__main__":
    main()
