import base64
import io
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from PIL import Image

from app.authutil import hash_password
from app.main import app
from app.paths import resolve_stored_file
from app.store import store

client = TestClient(app)


def _jpeg() -> bytes:
    img = Image.new("RGB", (64, 48), (30, 120, 40))
    exif = img.getexif()
    exif[270] = "SECRET-GPS-99"
    exif[36867] = "2026:10:18 09:00:00"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def _register(email: str, bin_no: str) -> object:
    return client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "secret12",
            "full_name": "Share Outsider",
            "phone": "+77001112233",
            "company": "Share LLP",
            "company_bin": bin_no,
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        },
        headers={"User-Agent": "anyq-test"},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner() -> str:
    store.credentials["u-owner"] = hash_password("owner-pass-share")
    res = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-pass-share", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _outsider() -> str:
    res = _register("share-outsider@demo.superapp", bin_no="123456789099")
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _new_log(token: str) -> dict:
    res = client.post(
        "/v1/site/projects/pr-besagash/daily",
        json={"day": "2026-10-19", "weather": "clear", "temp_c": 16, "workers": 7, "notes": "Бетон", "delays": ""},
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert "share_token_sha256" not in body
    assert body["author_role"] == "owner"
    assert body["author_name"] == "Ерлан Сатыбалды"
    assert "author_id" in body
    return body


def _share(token: str, log_id: str, days: int = 30):
    return client.post(f"/v1/site/daily/{log_id}/share", json={"expires_in_days": days}, headers=_auth(token))


def test_share_expiry_revoke_and_public_copy():
    owner = _owner()
    log = _new_log(owner)
    raw = _jpeg()
    uploaded = client.post(
        f"/v1/site/daily/{log['id']}/photos",
        files=[("files", ("shot.jpg", raw, "image/jpeg"))],
        headers=_auth(owner),
    )
    assert uploaded.status_code == 200, uploaded.text
    photo = uploaded.json()["data"]["log"]["photos"][0]
    assert photo["original_url"].startswith("/v1/files/")
    assert photo["taken_at"] == "2026-10-18T09:00:00"
    original_id = photo["original_url"].rsplit("/", 1)[-1]

    too_short = _share(owner, log["id"], 13)
    assert too_short.status_code == 422
    too_long = _share(owner, log["id"], 91)
    assert too_long.status_code == 422

    created = _share(owner, log["id"], 14)
    assert created.status_code == 200, created.text
    payload = created.json()["data"]
    token = payload["token"]
    assert token
    pad = "=" * (-len(token) % 4)
    assert len(base64.urlsafe_b64decode(token + pad)) >= 16
    db_text = store._sql.stored_text()
    assert token not in db_text
    assert store.daily_logs[log["id"]].share_token_sha256 in db_text
    assert original_id in db_text
    expires = datetime.fromisoformat(payload["expires_at"])
    assert timedelta(days=13, hours=23) < expires - datetime.now(UTC) < timedelta(days=15)

    again = _share(owner, log["id"], 30)
    assert again.status_code == 200
    assert again.json()["data"]["token"] is None

    outsider = _outsider()
    denied = _share(outsider, log["id"], 30)
    assert denied.status_code == 403
    denied_revoke = client.delete(f"/v1/site/daily/{log['id']}/share", headers=_auth(outsider))
    assert denied_revoke.status_code == 403
    demo = client.post(
        f"/v1/site/daily/{log['id']}/share",
        json={"expires_in_days": 30},
        headers={"x-demo-user": "owner@demo.superapp"},
    )
    assert demo.status_code == 401

    public = client.get(f"/v1/public/daily/{token}")
    assert public.status_code == 200, public.text
    assert "noindex" in public.headers["x-robots-tag"]
    assert "private" in public.headers["cache-control"]
    data = public.json()["data"]
    assert set(data) == {
        "day",
        "weather",
        "temp_c",
        "workers",
        "notes",
        "delays",
        "delay_hours",
        "project_title",
        "author_role",
        "photos",
    }
    assert data["author_role"] == "owner"
    assert data["workers"] == 7
    blob = public.text
    for secret in ("Ерлан", "Сатыбалды", "author_id", "owner@demo", "+7 701", "share_token", "Талгарский"):
        assert secret not in blob
    assert data["photos"][0]["url"].startswith("/v1/public/files/")
    assert original_id not in data["photos"][0]["url"]
    assert set(data["photos"][0]) == {"url"}

    original = store.get_upload(original_id)
    assert original is not None and original.kind == "original"
    disk = resolve_stored_file(original.kind, original.name).read_bytes()
    open_original = client.get(photo["original_url"])
    assert open_original.status_code == 401
    owned = client.get(photo["original_url"], headers=_auth(owner))
    assert owned.status_code == 200
    assert owned.content == disk
    assert b"SECRET-GPS-99" not in owned.content

    leaked = client.get(f"/v1/public/files/{original_id}?t={token}")
    assert leaked.status_code == 404
    assert "noindex" in leaked.headers["x-robots-tag"]
    cleaned = client.get(data["photos"][0]["url"])
    assert cleaned.status_code == 200
    assert cleaned.headers["content-type"].startswith("image/jpeg")
    assert "noindex" in cleaned.headers["x-robots-tag"]
    assert cleaned.content != disk
    assert cleaned.content != raw
    assert b"SECRET-GPS-99" not in cleaned.content
    assert len(Image.open(io.BytesIO(cleaned.content)).getexif()) == 0

    log_row = store.daily_logs[log["id"]]
    log_row.share_expires_at = "2000-01-01T00:00:00+00:00"
    store.daily_logs[log_row.id] = log_row
    expired = client.get(f"/v1/public/daily/{token}")
    assert expired.status_code == 410
    assert "noindex" in expired.headers["x-robots-tag"]
    expired_file = client.get(data["photos"][0]["url"])
    assert expired_file.status_code == 410

    renewed = _share(owner, log["id"], 90)
    assert renewed.status_code == 200, renewed.text
    fresh = renewed.json()["data"]["token"]
    assert fresh and fresh != token
    assert client.get(f"/v1/public/daily/{token}").status_code == 404
    assert client.get(f"/v1/public/daily/{fresh}").status_code == 200

    revoked = client.delete(f"/v1/site/daily/{log['id']}/share", headers=_auth(owner))
    assert revoked.status_code == 200
    gone = client.get(f"/v1/public/daily/{fresh}")
    assert gone.status_code == 404
    assert "noindex" in gone.headers["x-robots-tag"]
    unknown = client.get("/v1/public/daily/" + "a" * 40)
    assert unknown.status_code == 404


def test_staff_payload_names_the_author_and_the_public_link_does_not():
    from types import SimpleNamespace

    from app.shares import member_daily, public_daily
    from app.site_models import DailyLog, Project

    log = DailyLog(
        id="dl-foreman",
        project_id="pr-yard",
        day="2026-10-19",
        author_id="u-foreman",
        author_role="foreman",
        notes="Кладка цоколя",
    )
    project = Project(id="pr-yard", slug="yard", title="Дом на Наурызбая", owner_id="u-owner")
    person = SimpleNamespace(full_name="Айгуль Тестова", role="foreman")
    staff = member_daily(log, lookup=lambda uid: person if uid == "u-foreman" else None)
    assert staff["author_name"] == "Айгуль Тестова"
    public = public_daily(log, project, "public-token", lambda uid: person)
    assert "author_name" not in public
    assert public["author_role"] == "foreman"
    assert "Айгуль" not in str(public)
    assert "Тестова" not in str(public)
