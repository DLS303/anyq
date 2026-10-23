import json
from pathlib import Path

from alembic.config import Config
from fastapi.testclient import TestClient

from alembic import command
from app.import_json import import_file
from app.main import app
from app.schemas import RegisterBody
from app.store import MemoryStore

client = TestClient(app)


def test_plots_are_paged_in_sql():
    first = client.get("/v1/plots", params={"limit": 1, "offset": 0})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["total"] >= 2
    assert len(body["data"]) == 1
    second = client.get("/v1/plots", params={"limit": 1, "offset": 1})
    assert second.status_code == 200
    assert second.json()["data"][0]["id"] != body["data"][0]["id"]
    assert "total" not in second.json()


def test_two_connections_see_each_others_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ANYQ_DB_PATH", str(tmp_path / "db.json"))
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    first = MemoryStore()
    second = MemoryStore()
    user, _token = first.register(
        RegisterBody(
            email="worker@example.com",
            password="secret12",
            full_name="Worker One",
            phone="+77001112233",
            company="Shared LLP",
            company_bin="123456789012",
            role="buyer",
            consent_offer_pd=True,
        )
    )
    found = second.get_user_by_email("worker@example.com")
    assert found is not None
    assert found.id == user.id
    assert found.role == "owner"


def test_json_import_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("ANYQ_DEMO_MODE", "")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ANYQ_DB_PATH", str(tmp_path / "live.json"))
    source = tmp_path / "db.json"
    source.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "id": "u-import",
                        "email": "import@example.com",
                        "full_name": "Import User",
                        "role": "owner",
                        "phone": "+77001000000",
                        "company": "Import LLP",
                        "company_bin": "123456789012",
                        "city": "Almaty",
                        "pilot": "",
                    }
                ],
                "credentials": {"u-import": "hash"},
                "plots": [],
            }
        ),
        encoding="utf-8",
    )
    dry = import_file(source, dry_run=True)
    assert dry["dry_run"] is True
    assert dry["collections"]["users"]["insert"] == 1
    assert dry["total"]["insert"] == 2
    fresh = MemoryStore()
    assert fresh.get_user("u-import") is None

    written = import_file(source, dry_run=False)
    assert written["dry_run"] is False
    assert written["collections"]["users"]["insert"] == 1
    assert written["collections"]["credentials"]["insert"] == 1
    again = import_file(source, dry_run=False)
    assert again["collections"]["users"]["same"] == 1
    assert again["collections"]["users"]["insert"] == 0
    assert again["total"]["update"] == 0
    loaded = MemoryStore()
    user = loaded.get_user("u-import")
    assert user is not None
    assert user.email == "import@example.com"
    assert loaded.credentials["u-import"] == "hash"
