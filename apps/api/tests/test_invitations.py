from fastapi.testclient import TestClient

from app.authutil import hash_password
from app.main import app
from app.sql_backend import InvitationRow
from app.store import store

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user_id: str, email: str, password: str) -> str:
    store.credentials[user_id] = hash_password(password)
    res = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password, "consent_offer_pd": True},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _owner() -> str:
    owner = store.get_user("u-owner")
    assert owner is not None
    owner.company = "North Test LLP"
    owner.company_bin = "880000000001"
    store.users_by_id[owner.id] = owner
    store._index_user(owner)
    return _token("u-owner", "owner@demo.superapp", "owner-invite-pass")


def _accept(token: str, email: str, **extra):
    body = {
        "email": email,
        "password": "secret12",
        "full_name": "Nurlan Beketov",
        "phone": "+77007654321",
        "consent_offer_pd": True,
    }
    body.update(extra)
    return client.post(f"/v1/invitations/token/{token}/accept", json=body)


def test_invite_expiry_reuse_and_role_lock():
    owner = _owner()
    blocked = client.post(
        "/v1/site/projects/pr-besagash/invitations",
        json={"role": "admin"},
        headers=_auth(owner),
    )
    assert blocked.status_code == 400

    buyer = _token("u-buyer", "buyer@demo.superapp", "buyer-invite-pass")
    denied = client.post(
        "/v1/invitations",
        json={"role": "foreman"},
        headers=_auth(buyer),
    )
    assert denied.status_code == 403

    created = client.post(
        "/v1/site/projects/pr-besagash/invitations",
        json={"role": "foreman"},
        headers=_auth(owner),
    )
    assert created.status_code == 200, created.text
    payload = created.json()["data"]
    assert payload["path"].startswith("/invite/")
    assert payload["token"] not in store._sql.stored_text()

    preview = client.get(f"/v1/invitations/token/{payload['token']}")
    assert preview.status_code == 200
    assert preview.json()["data"]["role"] == "foreman"
    assert preview.json()["data"]["status"] == "open"

    accepted = _accept(payload["token"], "foreman@example.com", role="admin")
    assert accepted.status_code == 200, accepted.text
    user = accepted.json()["data"]["user"]
    assert user["role"] == "foreman"
    assert user["role"] != "admin"
    assert user["company"] == "North Test LLP"
    assert user["company_bin"] == "880000000001"
    assert user["company_key"] == "user:u-owner"
    member = store.get_user(user["id"])
    assert member is not None
    assert any(row.user_id == member.id and row.role_on_site == "foreman" for row in store.directory.values())

    reused = _accept(payload["token"], "other@example.com")
    assert reused.status_code == 410

    expired_link = client.post(
        "/v1/invitations",
        json={"role": "moderator"},
        headers=_auth(owner),
    )
    assert expired_link.status_code == 200, expired_link.text
    expired = expired_link.json()["data"]
    with store._sql.factory() as session:
        row = session.get(InvitationRow, expired["id"])
        assert row is not None
        row.expires_at = "2000-01-01T00:00:00+00:00"
        session.commit()
    stale = _accept(expired["token"], "late@example.com")
    assert stale.status_code == 410

    revoked_link = client.post(
        "/v1/site/projects/pr-besagash/invitations",
        json={"role": "supervisor"},
        headers=_auth(owner),
    )
    assert revoked_link.status_code == 200, revoked_link.text
    revoked = revoked_link.json()["data"]
    gone = client.post(f"/v1/invitations/{revoked['id']}/revoke", headers=_auth(owner))
    assert gone.status_code == 200
    assert gone.json()["data"]["status"] == "revoked"
    after = _accept(revoked["token"], "revoked@example.com")
    assert after.status_code == 410
