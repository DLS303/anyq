from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.legal import ai_document, privacy_document
from app.main import app
from app.schemas import User
from app.store import store

client = TestClient(app)
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 24


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(user_id: str, email: str, password: str) -> str:
    store.credentials[user_id] = hash_password(password)
    res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _person(user_id: str, email: str, role: str = "contractor") -> str:
    store._index_user(
        User(
            id=user_id,
            email=email,
            full_name="Аскар Берик",
            role=role,  # type: ignore[arg-type]
            phone="+77009998877",
            company="Бригада",
        )
    )
    return _login(user_id, email, "secret12")


def test_object_creation_stores_only_given_fields():
    owner = _login("u-owner", "owner@demo.superapp", "owner-pass-object")
    contractor = _login("u-smr", "contractor@demo.superapp", "smr-pass-object")
    owner_id = client.get("/v1/auth/me", headers=_auth(owner)).json()["data"]["id"]

    bare = client.post(
        "/v1/site/projects",
        json={"title": "Склад у трассы", "address": "Каскелен"},
        headers=_auth(owner),
    )
    assert bare.status_code == 200, bare.text
    data = bare.json()["data"]
    assert data["title"] == "Склад у трассы"
    assert data["address"] == "Каскелен"
    assert data["budget_kzt"] is None
    assert data["start"] == ""
    assert data["finish"] == ""
    assert data["owner_id"] == owner_id
    assert data["contractor_id"] is None
    assert data["plot_id"] is None
    stored = store.projects[data["id"]]
    assert stored.budget_kzt is None
    assert stored.start == ""
    assert stored.finish == ""

    denied = client.post(
        "/v1/site/projects",
        json={"title": "Чужой объект", "address": "Алматы"},
        headers=_auth(contractor),
    )
    assert denied.status_code == 403

    filled = client.post(
        "/v1/site/projects",
        json={
            "title": "Склад север",
            "address": "Алматы",
            "deadline": "2027-05-01",
            "budget_kzt": 1_500_000,
        },
        headers=_auth(owner),
    )
    assert filled.status_code == 200, filled.text
    full = filled.json()["data"]
    assert full["finish"] == "2027-05-01"
    assert full["budget_kzt"] == 1_500_000
    assert full["start"] == ""


def test_participant_add_and_remove_changes_access():
    owner = _login("u-owner", "owner@demo.superapp", "owner-pass-members")
    member = _person("u-crew-day", "foreman-new@example.com")
    created = client.post(
        "/v1/site/projects",
        json={"title": "Объект бригады", "address": "Талгар"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    pid = created.json()["data"]["id"]

    hidden = client.get(f"/v1/site/projects/{pid}", headers=_auth(member))
    assert hidden.status_code == 403
    blocked = client.post(
        f"/v1/site/projects/{pid}/daily",
        json={"day": "2026-10-19", "weather": "clear", "workers": 4, "notes": "Каркас"},
        headers=_auth(member),
    )
    assert blocked.status_code == 403

    missing = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "nobody@example.com", "role": "customer"},
        headers=_auth(owner),
    )
    assert missing.status_code == 404

    added = client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "Foreman-New@example.com", "role": "foreman"},
        headers=_auth(owner),
    )
    assert added.status_code == 200, added.text
    card = added.json()["data"]
    assert set(card) == {"user_id", "name", "role", "email"}
    assert card["role"] == "foreman"
    assert card["email"] == "f***@example.com"
    assert "phone" not in added.text
    assert "+7700" not in added.text

    opened = client.get(f"/v1/site/projects/{pid}", headers=_auth(member))
    assert opened.status_code == 200
    logged = client.post(
        f"/v1/site/projects/{pid}/daily",
        json={"day": "2026-10-19", "weather": "cloud", "workers": 6, "notes": "Кладка"},
        headers=_auth(member),
    )
    assert logged.status_code == 200, logged.text

    removed = client.delete(f"/v1/site/projects/{pid}/members/{card['user_id']}", headers=_auth(owner))
    assert removed.status_code == 200, removed.text
    assert client.get(f"/v1/site/projects/{pid}", headers=_auth(member)).status_code == 403
    assert (
        client.post(
            f"/v1/site/projects/{pid}/daily",
            json={"day": "2026-10-20", "weather": "clear", "workers": 1, "notes": "Уборка"},
            headers=_auth(member),
        ).status_code
        == 403
    )


def test_voice_upload_access_and_limits():
    owner = _login("u-owner", "owner@demo.superapp", "owner-pass-voice")
    member = _person("u-crew-voice", "voice-member@example.com")
    outsider = _person("u-crew-out", "voice-outsider@example.com", role="buyer")
    created = client.post(
        "/v1/site/projects",
        json={"title": "Объект с голосом", "address": "Есик"},
        headers=_auth(owner),
    )
    pid = created.json()["data"]["id"]
    client.post(
        f"/v1/site/projects/{pid}/members",
        json={"email": "voice-member@example.com", "role": "supervisor"},
        headers=_auth(owner),
    )
    log = client.post(
        f"/v1/site/projects/{pid}/daily",
        json={"day": "2026-10-19", "weather": "wind", "workers": 3, "notes": "Кровля"},
        headers=_auth(member),
    )
    assert log.status_code == 200, log.text
    log_id = log.json()["data"]["id"]

    def upload(token: str, payload: bytes, content_type: str, duration: str = "4"):
        return client.post(
            f"/v1/site/daily/{log_id}/voice",
            files={"file": ("note.bin", payload, content_type)},
            data={"duration_s": duration},
            headers=_auth(token),
        )

    denied = upload(outsider, WEBM, "audio/webm")
    assert denied.status_code == 403

    bad_type = upload(member, b"this is text", "text/plain")
    assert bad_type.status_code == 400
    too_long = upload(member, WEBM, "audio/webm", duration="121")
    assert too_long.status_code == 400
    too_big = upload(member, b"\x1a\x45\xdf\xa3" + b"\x00" * (2 * 1024 * 1024), "audio/webm")
    assert too_big.status_code == 400

    saved = upload(member, WEBM, "audio/webm")
    assert saved.status_code == 200, saved.text
    note = saved.json()["data"]["voice_notes"][0]
    assert note["duration_s"] == 4
    file_id = note["file_id"]

    own = client.get(note["url"], headers=_auth(member))
    assert own.status_code == 200
    assert own.headers["content-type"].startswith("audio/")
    assert own.content == WEBM
    foreign = client.get(note["url"], headers=_auth(outsider))
    assert foreign.status_code == 403

    shared = client.post(f"/v1/site/daily/{log_id}/share", json={"expires_in_days": 14}, headers=_auth(member))
    assert shared.status_code == 200, shared.text
    token = shared.json()["data"]["token"]
    public = client.get(f"/v1/public/daily/{token}")
    assert public.status_code == 200, public.text
    assert "voice_notes" not in public.json()["data"]
    assert file_id not in public.text


def test_ai_consent_revoke_appends_a_row():
    created = client.post(
        "/v1/auth/register",
        json={
            "email": "consent-ai@example.com",
            "password": "secret12",
            "full_name": "Алия Тест",
            "phone": "+77001110022",
            "company": "Test LLP",
            "company_bin": "123456789111",
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test", "X-Forwarded-For": "203.0.113.40"},
    )
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]
    user_id = created.json()["data"]["user"]["id"]
    offer = next(row for row in store.consents_for(user_id) if row.type == "offer_pd")
    privacy = privacy_document()
    assert offer.privacy_version == privacy.version
    assert offer.privacy_sha256 == privacy.sha256
    assert offer.text_sha256

    docs = client.get("/v1/auth/consents/documents", headers=_auth(token))
    assert docs.status_code == 200, docs.text
    by_key = {item["key"]: item for item in docs.json()["data"]}
    assert set(by_key) == {"offer_pd", "privacy", "ai"}
    ai_doc = ai_document()
    assert by_key["ai"]["version"] == ai_doc.version
    assert by_key["ai"]["sha256"] == ai_doc.sha256

    before = [row.model_dump() for row in store.consents_for(user_id)]
    granted = client.post(
        "/v1/auth/consents/ai",
        json={"text_version": "client-must-not-win", "provider": "hidden"},
        headers={**_auth(token), "User-Agent": "anyq-test"},
    )
    assert granted.status_code == 200, granted.text
    row = granted.json()["data"]
    assert row["type"] == "ai"
    assert row["action"] == "grant"
    assert row["text_version"] == ai_doc.version
    assert row["text_sha256"] == ai_doc.sha256
    assert row["provider"] == ""
    assert row["revoked_at"] is None

    mid = [item.model_dump() for item in store.consents_for(user_id)]
    assert mid[: len(before)] == before
    assert len(mid) == len(before) + 1

    revoked = client.post(f"/v1/auth/consents/{row['id']}/revoke", headers=_auth(token))
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["data"]["action"] == "revoke"
    assert revoked.json()["data"]["revoked_at"]
    after = [item.model_dump() for item in store.consents_for(user_id)]
    assert after[: len(mid)] == mid
    assert len(after) == len(mid) + 1
    assert after[-1]["action"] == "revoke"
    assert store.consents_for(user_id)[-2].action == "grant"
    assert store.consents_for(user_id)[-2].revoked_at is None
