from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.main import app
from app.schemas import User
from app.store import store

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _demo(user_id: str, email: str, password: str) -> str:
    store.credentials[user_id] = hash_password(password)
    res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _inspection(title: str = "Приёмка арматуры") -> dict:
    return {
        "title": title,
        "day": "2026-10-19",
        "notes": "Осмотр до обеда",
        "items": [
            {"label": "Сертификат", "result": "pass", "comment": ""},
            {"label": "Шаг хомутов", "result": "fail", "comment": "реже проекта"},
            {"label": "Защитный слой", "result": "na", "comment": ""},
        ],
    }


def _meeting() -> dict:
    return {
        "title": "Планёрка фундамента",
        "day": "2026-10-20",
        "agenda": "Ограждение и повторная приёмка",
        "participants": [
            {"role": "supervisor", "name": "Марат"},
            {"role": "contractor", "name": "Бригада 2"},
        ],
        "decision_items": [
            {"text": "Закрыть ограждение", "owner_role": "foreman", "due": "2026-10-21"},
        ],
    }


def test_change_approval_is_only_for_the_assigned_supervisor():
    contractor = _demo("u-smr", "contractor@demo.superapp", "smr-pass-hub")
    owner = _demo("u-owner", "owner@demo.superapp", "owner-pass-hub")
    supervisor = _demo("u-nadzor", "supervisor@demo.superapp", "nadzor-pass-hub")
    other = User(
        id="u-sup-other",
        email="other-supervisor@example.com",
        full_name="Другой технадзор",
        role="supervisor",
        phone="+77001112233",
        company="Other Supervision",
        company_bin="123456789111",
    )
    store._index_user(other)
    store.credentials[other.id] = hash_password("secret12")
    login = client.post(
        "/v1/auth/login",
        json={"email": other.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    outsider = login.json()["data"]["token"]

    created = client.post(
        "/v1/site/projects/pr-besagash/changes",
        json={"title": "Дополнительная опалубка", "amount_kzt": 250000, "reason": "узел КЖ"},
        headers=_auth(contractor),
    )
    assert created.status_code == 200, created.text
    change_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "submitted"

    for token in (contractor, owner):
        denied = client.post(
            f"/v1/site/changes/{change_id}/status",
            json={"status": "approved"},
            headers=_auth(token),
        )
        assert denied.status_code == 403, denied.text
        assert store.change_orders[change_id].status == "submitted"
    missing = client.post(
        f"/v1/site/changes/{change_id}/status",
        json={"status": "approved"},
        headers=_auth(outsider),
    )
    assert missing.status_code == 404, missing.text
    assert store.change_orders[change_id].status == "submitted"

    approved = client.post(
        f"/v1/site/changes/{change_id}/status",
        json={"status": "approved"},
        headers=_auth(supervisor),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["data"]["status"] == "approved"

    mine = client.get("/v1/site/projects", headers=_auth(supervisor))
    assert mine.status_code == 200, mine.text
    ids = [row["project"]["id"] for row in mine.json()["data"]]
    assert ids == ["pr-besagash"]
    hidden = client.get("/v1/site/projects", headers=_auth(outsider))
    assert hidden.json()["data"] == []


def test_inspection_and_meeting_validation():
    supervisor = _demo("u-nadzor", "supervisor@demo.superapp", "nadzor-pass-forms")
    empty = client.post(
        "/v1/site/projects/pr-besagash/inspections",
        json={"title": "Пустая", "items": []},
        headers=_auth(supervisor),
    )
    assert empty.status_code == 400
    bad_item = client.post(
        "/v1/site/projects/pr-besagash/inspections",
        json={"title": "Проверка", "items": [{"label": "Шов", "result": "maybe"}]},
        headers=_auth(supervisor),
    )
    assert bad_item.status_code == 400

    created = client.post(
        "/v1/site/projects/pr-besagash/inspections",
        json=_inspection(),
        headers=_auth(supervisor),
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data["result"] == "fail"
    assert [item["result"] for item in data["items"]] == ["pass", "fail", "na"]
    assert data["inspector"]

    no_people = client.post(
        "/v1/site/projects/pr-besagash/meetings",
        json={"title": "Планёрка", "day": "2026-10-20", "agenda": "Сроки", "participants": []},
        headers=_auth(supervisor),
    )
    assert no_people.status_code == 400
    no_due = client.post(
        "/v1/site/projects/pr-besagash/meetings",
        json={
            "title": "Планёрка",
            "day": "2026-10-20",
            "agenda": "Сроки",
            "participants": [{"role": "contractor", "name": ""}],
            "decision_items": [{"text": "Закрыть замечание", "owner_role": "foreman", "due": ""}],
        },
        headers=_auth(supervisor),
    )
    assert no_due.status_code == 400

    meeting = client.post(
        "/v1/site/projects/pr-besagash/meetings",
        json=_meeting(),
        headers=_auth(supervisor),
    )
    assert meeting.status_code == 200, meeting.text
    saved = meeting.json()["data"]
    assert saved["agenda"] == "Ограждение и повторная приёмка"
    assert saved["participants"][0]["role"] == "supervisor"
    assert saved["decision_items"][0]["owner_role"] == "foreman"
    assert saved["decision_items"][0]["due"] == "2026-10-21"

    downtime = client.post(
        "/v1/site/projects/pr-besagash/daily",
        json={"day": "2026-10-19", "weather": "rain", "delay_hours": 3, "delays": ""},
        headers=_auth(supervisor),
    )
    assert downtime.status_code == 400
    logged = client.post(
        "/v1/site/projects/pr-besagash/daily",
        json={
            "day": "2026-10-19",
            "weather": "rain",
            "delay_hours": 3,
            "delays": "Нет миксера",
            "workers": 4,
            "notes": "Ждали бетон",
        },
        headers=_auth(supervisor),
    )
    assert logged.status_code == 200, logged.text
    assert logged.json()["data"]["weather"] == "rain"
    assert logged.json()["data"]["delay_hours"] == 3
    assert logged.json()["data"]["delays"] == "Нет миксера"


def test_duplicate_submit_with_the_same_key_is_one_record():
    supervisor = _demo("u-nadzor", "supervisor@demo.superapp", "nadzor-pass-idem")
    before = len(store.inspections)
    headers = {**_auth(supervisor), "Idempotency-Key": "insp-once-1"}
    first = client.post("/v1/site/projects/pr-besagash/inspections", json=_inspection("Повтор"), headers=headers)
    second = client.post("/v1/site/projects/pr-besagash/inspections", json=_inspection("Повтор"), headers=headers)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert len(store.inspections) == before + 1
    clash = client.post(
        "/v1/site/projects/pr-besagash/inspections",
        json=_inspection("Другое название"),
        headers=headers,
    )
    assert clash.status_code == 409
    assert len(store.inspections) == before + 1
