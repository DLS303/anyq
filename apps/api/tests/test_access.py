import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.authutil import hash_password, reset_secret_cache
from app.main import app
from app.store import store

client = TestClient(app)


def _register(email: str, consent: bool = True, bin_no: str = "123456789012"):
    return client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Test User",
            "phone": "+77001112233",
            "company": "Test LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": consent,
        },
        headers={"User-Agent": "anyq-test"},
    )


def _token(email: str, bin_no: str = "123456789012") -> str:
    res = _register(email, bin_no=bin_no)
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _jpeg() -> bytes:
    img = Image.new("RGB", (32, 24), (12, 80, 200))
    exif = img.getexif()
    exif[270] = "pilot-note"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_session_required_for_protected_routes():
    res = client.get("/v1/cabinet/me", headers={"x-demo-user": "admin@demo.superapp"})
    assert res.status_code == 401
    res = client.get("/v1/site/projects/pr-besagash/bundle")
    assert res.status_code == 401
    res = client.get("/uploads/missing.jpg")
    assert res.status_code == 401
    res = client.get("/v1/files/missing")
    assert res.status_code == 401


def test_user_directory_is_not_public():
    res = client.get("/v1/auth/users")
    assert res.status_code == 401
    token = _token("buyer-users@example.com")
    res = client.get("/v1/auth/users", headers=_auth(token))
    assert res.status_code == 403
    store.credentials["u-admin"] = hash_password("admin-pass-1")
    res = client.post(
        "/v1/auth/login",
        json={"email": "admin@demo.superapp", "password": "admin-pass-1", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    admin = res.json()["data"]["token"]
    res = client.get("/v1/auth/users", headers=_auth(admin))
    assert res.status_code == 200, res.text
    body = res.text.lower()
    assert "password" not in body
    assert "credential" not in body
    for row in res.json()["data"]:
        assert set(row) == {"email", "full_name", "role"}


def test_project_membership():
    outsider = _token("outsider@example.com")
    denied = client.get("/v1/site/projects/pr-besagash/bundle", headers=_auth(outsider))
    assert denied.status_code == 403
    denied_write = client.post(
        "/v1/site/projects/pr-besagash/daily",
        json={"day": "2026-10-18", "notes": "no"},
        headers=_auth(outsider),
    )
    assert denied_write.status_code == 403
    hidden = client.get("/v1/site/projects", headers=_auth(outsider))
    assert hidden.status_code == 200
    assert all(row["project"]["id"] != "pr-besagash" for row in hidden.json()["data"])

    store.credentials["u-owner"] = hash_password("owner-pass-1")
    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-1", "consent_offer_pd": True},
    )
    assert login.status_code == 200, login.text
    owner = login.json()["data"]["token"]
    allowed = client.get("/v1/site/projects/pr-besagash/bundle", headers=_auth(owner))
    assert allowed.status_code == 200


def test_upload_access_and_metadata():
    raw = _jpeg()
    assert b"pilot-note" in raw
    owner = _token("photo-owner@example.com")
    other = _token("photo-other@example.com")
    denied = client.post(
        "/v1/cabinet/photos",
        files={"file": ("shot.jpg", raw, "image/jpeg")},
    )
    assert denied.status_code == 401
    uploaded = client.post(
        "/v1/cabinet/photos",
        files={"file": ("shot.jpg", raw, "image/jpeg")},
        headers=_auth(owner),
    )
    assert uploaded.status_code == 200, uploaded.text
    url = uploaded.json()["data"]["url"]
    assert url.startswith("/v1/files/")
    open_read = client.get(url)
    assert open_read.status_code == 401
    foreign = client.get(url, headers=_auth(other))
    assert foreign.status_code == 403
    own = client.get(url, headers=_auth(owner))
    assert own.status_code == 200
    assert b"pilot-note" not in own.content
    assert len(Image.open(io.BytesIO(own.content)).getexif()) == 0


def test_registration_consent_is_required_and_logged():
    missing = _register("noconsent@example.com", consent=False)
    assert missing.status_code == 400
    assert store.consents_for(store.get_user_by_email("noconsent@example.com").id if store.get_user_by_email("noconsent@example.com") else "") == []
    created = _register("withconsent@example.com", consent=True, bin_no="123456789013")
    assert created.status_code == 200, created.text
    token = created.json()["data"]["token"]
    user_id = created.json()["data"]["user"]["id"]
    listed = client.get("/v1/auth/consents", headers=_auth(token))
    assert listed.status_code == 200
    rows = listed.json()["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["user_id"] == user_id
    assert row["type"] == "offer_pd"
    assert row["text_version"]
    assert len(row["text_sha256"]) == 64
    assert row["granted_at"]
    assert row["ip"]
    assert row["user_agent"] == "anyq-test"
    before = len(store.consents)
    again = client.get("/v1/auth/consents", headers=_auth(token))
    assert again.status_code == 200
    assert len(store.consents) == before


def test_login_without_consent_is_rejected():
    from app.schemas import User

    user = User(
        id="u-plain",
        email="plain@example.com",
        full_name="Plain User",
        role="buyer",
        phone="+77001112233",
        company="Plain LLP",
        company_bin="123456789014",
    )
    store._index_user(user)
    store.credentials[user.id] = hash_password("secret12")
    denied = client.post("/v1/auth/login", json={"email": user.email, "password": "secret12"})
    assert denied.status_code == 428
    allowed = client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert allowed.status_code == 200, allowed.text
    rows = store.consents_for(user.id)
    assert len(rows) == 1
    assert rows[0].ip
    assert rows[0].user_agent == "anyq-test"


def test_crm_ownership():
    owner = _token("crm-owner@example.com", "111111111111")
    other = _token("crm-other@example.com", "222222222222")
    created = client.post(
        "/v1/crm/deals",
        json={"title": "Private deal", "amount_kzt": 1500, "client_name": "Owner"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    deal_id = created.json()["data"]["id"]
    assert client.get(f"/v1/crm/deals/{deal_id}", headers=_auth(other)).status_code == 403
    assert client.get(f"/v1/crm/deals/{deal_id}", headers=_auth(owner)).status_code == 200
    listed = client.get("/v1/crm/deals", headers=_auth(other))
    assert listed.status_code == 200
    assert all(row["id"] != deal_id for row in listed.json()["data"])
    invoice = client.post(
        "/v1/crm/invoices",
        json={"deal_id": deal_id, "title": "Bill", "amount_kzt": 100, "payer_name": "Owner"},
        headers=_auth(other),
    )
    assert invoice.status_code == 403
    moved = client.post(f"/v1/crm/deals/{deal_id}/move", json={"stage": "request"}, headers=_auth(other))
    assert moved.status_code == 403
    lead = client.post(
        "/v1/crm/leads",
        json={"title": "Private lead", "name": "Ada", "phone": "+77009998877"},
        headers=_auth(owner),
    )
    assert lead.status_code == 200, lead.text
    lead_id = lead.json()["data"]["id"]
    others_leads = client.get("/v1/crm/leads", headers=_auth(other))
    assert all(row["id"] != lead_id for row in others_leads.json()["data"])
    assert client.post(f"/v1/crm/leads/{lead_id}/convert", json={"funnel": "construction"}, headers=_auth(other)).status_code == 403
    activity = client.post(
        "/v1/crm/activities",
        json={"deal_id": deal_id, "title": "Call", "activity_type": "call"},
        headers=_auth(owner),
    )
    assert activity.status_code == 200, activity.text
    activity_id = activity.json()["data"]["id"]
    assert client.post(
        f"/v1/crm/activities/{activity_id}/toggle",
        json={"completed": True},
        headers=_auth(other),
    ).status_code == 403
    contact = client.post(
        "/v1/crm/contacts",
        json={"name": "Private Contact", "phone": "+77001110000"},
        headers=_auth(owner),
    )
    assert contact.status_code == 200, contact.text
    others_contacts = client.get("/v1/crm/contacts", headers=_auth(other))
    assert all(row["name"] != "Private Contact" for row in others_contacts.json()["data"])


def test_cors_allowlist():
    blocked = client.get("/health", headers={"Origin": "https://evil.example"})
    assert blocked.headers.get("access-control-allow-origin") is None
    allowed = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_production_requires_secret(monkeypatch):
    from app import authutil
    from app.config import resolve_cors_origins

    monkeypatch.setenv("ANYQ_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPERAPP_SECRET", raising=False)
    reset_secret_cache()
    with pytest.raises(RuntimeError):
        authutil.load_secret()
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    with pytest.raises(RuntimeError):
        resolve_cors_origins()
    reset_secret_cache()
