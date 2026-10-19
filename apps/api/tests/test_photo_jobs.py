import io
import threading
import time

from fastapi.testclient import TestClient
from PIL import Image

from app.authutil import hash_password
from app.main import app
from app.media import process_upload
from app.store import store

client = TestClient(app)


def _jpeg() -> bytes:
    img = Image.new("RGB", (32, 32), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _owner() -> str:
    store.credentials["u-owner"] = hash_password("owner-photo-pass")
    res = client.post(
        "/v1/auth/login",
        json={"email": "owner@demo.superapp", "password": "owner-photo-pass", "consent_offer_pd": True},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["token"]


def _log(token: str) -> str:
    res = client.post(
        "/v1/site/projects/pr-besagash/daily",
        json={"day": "2026-10-19", "weather": "clear", "workers": 2, "notes": "photo job"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["id"]


def test_blur_runs_on_a_pool_thread(monkeypatch):
    seen: dict[str, str] = {}

    def wrapped(raw: bytes):
        seen["thread"] = threading.current_thread().name
        return process_upload(raw)

    monkeypatch.setattr("app.photo_jobs.process_upload", wrapped)
    token = _owner()
    log_id = _log(token)
    uploaded = client.post(
        f"/v1/site/daily/{log_id}/photos",
        files=[("files", ("shot.jpg", _jpeg(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 200, uploaded.text
    added = uploaded.json()["data"]["added"][0]
    assert added["status"] == "done"
    assert seen["thread"].startswith("photo")
    job = client.get(f"/v1/site/photos/jobs/{added['job_id']}", headers={"Authorization": f"Bearer {token}"})
    assert job.status_code == 200
    assert job.json()["data"]["status"] == "done"


def test_photo_job_times_out(monkeypatch):
    def slow(raw: bytes):
        time.sleep(0.4)
        return process_upload(raw)

    monkeypatch.setattr("app.photo_jobs.process_upload", slow)
    monkeypatch.setenv("ANYQ_PHOTO_TIMEOUT", "0.05")
    token = _owner()
    log_id = _log(token)
    uploaded = client.post(
        f"/v1/site/daily/{log_id}/photos",
        files=[("files", ("shot.jpg", _jpeg(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert uploaded.status_code == 408, uploaded.text
