"""Meeting tasks: company gate, compare-and-swap, and the assignee index."""

import json
import os
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select as sa_select
from sqlalchemy import text

from app.company_features import project_company_id
from app.main import app
from app.meetings import pushes, tasks_for_assignee
from app.pf0_tables import AuditLog
from app.store import store

client = TestClient(app)
BIN_B = "666666666666"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register(email: str, bin_no: str, name: str, phone: str):
    res = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": name,
            "phone": phone,
            "company": "North Yard LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


def _promote(email: str, role: str):
    user = store.get_user_by_email(email)
    assert user is not None
    updated = user.model_copy(update={"role": role})
    store.users_by_id[user.id] = updated
    store.users[email.lower()] = updated
    return updated


def _enable(token: str, key: str = "meetings"):
    listed = client.get("/v1/org/features", headers=_auth(token))
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"] if item["key"] == key)
    saved = client.post(
        "/v1/org/features",
        json={"key": key, "enabled": True, "row_version": row["row_version"], "id": row["id"]},
        headers=_auth(token),
    )
    assert saved.status_code == 200, saved.text


def _project(token: str, title: str) -> str:
    created = client.post(
        "/v1/site/projects",
        json={"title": title, "address": "Test street 1"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


def _plan(token: str, pid: str, assignee: str, text_value: str = "Set the fence", due: str = "2026-10-21", **extra):
    body = {
        "id": str(uuid4()),
        "title": "Yard plan",
        "day": "2026-10-20",
        "agenda": extra.pop("agenda", "Fence line"),
        "participants": [assignee],
        "action_items": [
            {
                "id": str(uuid4()),
                "text": text_value,
                "assignee_id": assignee,
                "due_date": due,
                "source": "meeting",
            }
        ],
    }
    body.update(extra)
    res = client.post(f"/v1/site/projects/{pid}/meeting-tasks", json=body, headers=_auth(token))
    return res


@pytest.fixture
def yard():
    previous = os.environ.get("ANYQ_DEMO_MODE")
    os.environ["ANYQ_DEMO_MODE"] = "0"
    suffix = uuid4().hex[:8]
    bin_a = f"{uuid4().int % 10**12:012d}"
    bin_b = f"{(uuid4().int + 1) % 10**12:012d}"
    owner = _register(f"mt-owner-{suffix}@example.com", bin_a, "Nuri Owner", "+77019998877")
    _promote(owner["user"]["email"], "owner")
    hand = _register(f"mt-hand-{suffix}@example.com", bin_a, "Sulu Hand", "+77018887766")
    _promote(hand["user"]["email"], "foreman")
    foreign = _register(f"mt-other-{suffix}@example.com", bin_b, "Bota Other", "+77017776655")
    _promote(foreign["user"]["email"], "owner")
    _enable(owner["token"])
    pid = _project(owner["token"], "North Yard")
    added = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": hand["user"]["email"], "role": "foreman"},
        headers=_auth(owner["token"]),
    )
    assert added.status_code == 200, added.text
    _enable(foreign["token"])
    other_pid = _project(foreign["token"], "South Yard")
    try:
        yield {
            "owner": owner["token"],
            "hand": hand["token"],
            "foreign": foreign["token"],
            "pid": pid,
            "other_pid": other_pid,
            "owner_id": owner["user"]["id"],
            "hand_id": hand["user"]["id"],
            "phone": "+77019998877",
            "name": "Nuri Owner",
            "bin": bin_a,
        }
    finally:
        if previous is None:
            os.environ.pop("ANYQ_DEMO_MODE", None)
        else:
            os.environ["ANYQ_DEMO_MODE"] = previous


def test_member_can_create_and_foreign_company_is_404(yard):
    before = len(pushes)
    created = _plan(yard["owner"], yard["pid"], yard["hand_id"])
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    meeting = data["meeting"]
    item = data["action_items"][0]
    assert meeting["participants"] == [yard["hand_id"]]
    assert meeting["company_id"] == project_company_id(store.get_project(yard["pid"]))
    assert meeting["company_id"].startswith("bin:")
    assert meeting["created_at"].endswith("+00:00")
    assert meeting["row_version"] == 1
    assert meeting["deleted_at"] is None
    assert item["source"] == "meeting"
    assert item["source_id"] == meeting["id"]
    assert item["carried_from_id"] is None
    assert item["assignee_id"] == yard["hand_id"]
    assert pushes[-1] == {"text": "Новое событие по объекту", "id": meeting["id"]}
    assert len(pushes) == before + 1
    assert yard["phone"] not in str(pushes[-1])
    assert yard["name"] not in str(pushes[-1])

    for token in (yard["foreign"],):
        assert client.get(f"/v1/site/projects/{yard['pid']}/action-items", headers=_auth(token)).status_code == 404
        assert (
            client.post(
                f"/v1/site/projects/{yard['pid']}/meeting-tasks",
                json={"action_items": []},
                headers=_auth(token),
            ).status_code
            == 404
        )
        assert client.get(f"/v1/site/meetings/{meeting['id']}/file", headers=_auth(token)).status_code == 404
        assert client.get(f"/v1/site/meetings/{meeting['id']}/links", headers=_auth(token)).status_code == 404
        assert (
            client.post(
                f"/v1/site/action-items/{item['id']}/status",
                json={"status": "done", "row_version": 1},
                headers=_auth(token),
            ).status_code
            == 404
        )

    flagged = client.get(
        f"/v1/site/meetings/{meeting['id']}/file?pid={yard['other_pid']}",
        headers=_auth(yard["foreign"]),
    )
    assert flagged.status_code == 404

    pdf = client.get(f"/v1/site/meetings/{meeting['id']}/file", headers=_auth(yard["hand"]))
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
    assert b"/Author" not in pdf.content
    assert yard["phone"].encode() not in pdf.content
    assert yard["name"].encode() not in pdf.content
    assert b"Set the fence" in pdf.content

    links = client.get(f"/v1/site/meetings/{meeting['id']}/links", headers=_auth(yard["owner"]))
    assert links.status_code == 200, links.text
    assert links.json()["data"]["user_ids"] == [yard["hand_id"]]
    assert yard["phone"] not in links.text

    with store._sql.factory() as session:
        events = session.scalars(sa_select(AuditLog)).all()
    joined = " ".join(row.action + json.dumps(row.changes or {}, ensure_ascii=False) for row in events)
    assert "meeting.create" in joined
    assert "Set the fence" not in joined
    assert yard["phone"] not in joined
    assert yard["name"] not in joined


def test_flag_off_and_query_pid_stay_404(yard):
    created = _plan(yard["owner"], yard["pid"], yard["owner_id"], text_value="Mark the trench", due="2026-11-02")
    assert created.status_code == 200, created.text
    meeting_id = created.json()["data"]["meeting"]["id"]
    listed = client.get("/v1/org/features", headers=_auth(yard["owner"]))
    row = next(item for item in listed.json()["data"] if item["key"] == "meetings")
    closed = client.post(
        "/v1/org/features",
        json={"key": "meetings", "enabled": False, "row_version": row["row_version"]},
        headers=_auth(yard["owner"]),
    )
    assert closed.status_code == 200, closed.text

    hidden = client.get(
        f"/v1/site/projects/{yard['pid']}/action-items?pid={yard['other_pid']}",
        headers=_auth(yard["owner"]),
    )
    assert hidden.status_code == 404
    still = client.get(
        f"/v1/site/meetings/{meeting_id}/links?pid={yard['other_pid']}",
        headers=_auth(yard["owner"]),
    )
    assert still.status_code == 404
    write = client.post(
        f"/v1/site/projects/{yard['pid']}/meeting-tasks?pid={yard['other_pid']}",
        json={"title": "Nope", "action_items": []},
        headers=_auth(yard["owner"]),
    )
    assert write.status_code == 404

    bundle = client.get(f"/v1/site/projects/{yard['pid']}/bundle", headers=_auth(yard["owner"]))
    assert bundle.status_code == 200, bundle.text
    body = bundle.json()["data"]
    assert body["action_items"] == []
    assert body["plan_meetings"] == []
    assert "punches" in body


def test_status_conflict_and_carry(yard):
    first = _plan(yard["hand"], yard["pid"], yard["hand_id"], text_value="Set the fence", due="2026-11-02")
    assert first.status_code == 200, first.text
    item = first.json()["data"]["action_items"][0]
    late = _plan(yard["hand"], yard["pid"], yard["hand_id"], text_value="Check the gate", due="2026-11-01")
    assert late.status_code == 200, late.text
    carried = [row for row in late.json()["data"]["action_items"] if row["carried_from_id"] == item["id"]]
    assert len(carried) == 1
    assert carried[0]["text"] == "Set the fence"
    mine = tasks_for_assignee(yard["hand_id"], "open", yard["pid"])
    assert [row["due_date"] for row in mine] == ["2026-11-01", "2026-11-02"]
    assert item["id"] not in {row["id"] for row in mine}

    moved = client.post(
        f"/v1/site/action-items/{carried[0]['id']}/status",
        json={"status": "done", "row_version": carried[0]["row_version"]},
        headers=_auth(yard["hand"]),
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["data"]["status"] == "done"
    assert moved.json()["data"]["row_version"] == 2

    again = client.post(
        f"/v1/site/action-items/{carried[0]['id']}/status",
        json={"status": "cancelled", "row_version": 2},
        headers=_auth(yard["hand"]),
    )
    assert again.status_code == 409
    stale = client.post(
        f"/v1/site/action-items/{carried[0]['id']}/status?pid={yard['other_pid']}",
        json={"status": "cancelled", "row_version": 1},
        headers=_auth(yard["hand"]),
    )
    assert stale.status_code == 409

    bad = client.post(
        f"/v1/site/projects/{yard['pid']}/meeting-tasks",
        json={"id": "not-a-uuid", "action_items": []},
        headers=_auth(yard["owner"]),
    )
    assert bad.status_code == 400

    with store._sql.engine.connect() as conn:
        sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'ix_actions_assignee'")
        ).scalar()
    assert sql
    assert "assignee_id" in sql and "status" in sql and "due_date" in sql


def test_company_id_from_body_is_ignored(yard):
    created = _plan(
        yard["owner"],
        yard["pid"],
        yard["owner_id"],
        company_id=f"bin:{BIN_B}",
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["meeting"]["company_id"] == f"bin:{yard['bin']}"


def test_alembic_meeting_revision_roundtrip(tmp_path):
    db = tmp_path / "meetings.sqlite"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db}"
    env["ANYQ_ENV"] = "development"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    api = os.path.join(os.path.dirname(__file__), "..")

    def alembic(*args: str) -> None:
        subprocess.check_call([sys.executable, "-m", "alembic", *args], cwd=api, env=env)

    alembic("upgrade", "head")
    alembic("downgrade", "-1")
    alembic("upgrade", "head")
    alembic("check")
    connection = sqlite3.connect(db)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"meetings", "action_items", "meeting_participants"} <= tables
    columns = {row[1] for row in connection.execute("PRAGMA table_info(action_items)")}
    for name in ("company_id", "project_id", "created_at", "updated_at", "row_version", "deleted_at", "source", "carried_from_id"):
        assert name in columns
    audit_columns = {row[1] for row in connection.execute("PRAGMA table_info(audit_log)")}
    assert {"entity_type", "entity_id", "project_id", "changes"} <= audit_columns
    index_sql = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'ix_actions_assignee'"
    ).fetchone()[0]
    assert "assignee_id" in index_sql and "status" in index_sql and "due_date" in index_sql
    connection.close()
