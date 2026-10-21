import asyncio

from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from app.authutil import hash_password
from app.compress import CompressMiddleware
from app.main import app
from app.schemas import User
from app.store import store
from app.timeout import RequestTimeoutMiddleware

client = TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner() -> str:
    user = User(
        id="u-perf-page",
        email="perf-page@example.com",
        full_name="Perf Page",
        role="owner",
        phone="+77001110001",
        company="Perf Page LLP",
        company_bin="123456789013",
    )
    if user.email not in store.users:
        store._index_user(user)
        store.credentials[user.id] = hash_password("secret12")
    login = client.post(
        "/v1/auth/login",
        json={"email": user.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-test"},
    )
    assert login.status_code == 200, login.text
    return login.json()["data"]["token"]


def test_project_list_can_page():
    token = _owner()
    created = client.post(
        "/v1/site/projects",
        json={"title": "Страница объектов", "address": "Алматы"},
        headers=_auth(token),
    )
    assert created.status_code == 200, created.text
    full = client.get("/v1/site/projects", headers=_auth(token))
    page = client.get("/v1/site/projects?limit=1&offset=0", headers=_auth(token))
    assert full.status_code == 200
    assert page.status_code == 200
    assert page.json()["total"] == len(full.json()["data"])
    assert page.json()["total"] >= 1
    assert len(page.json()["data"]) == 1
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 0


def test_brotli_for_clients_that_ask():
    response = client.get("/openapi.json", headers={"Accept-Encoding": "br"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "br"
    assert "openapi" in response.json()


def test_gzip_for_clients_that_ask():
    response = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.headers.get("content-encoding") == "gzip"
    assert "openapi" in response.json()


def test_request_timeout_answers():
    async def slow(scope, receive, send):
        await asyncio.sleep(1)
        response = PlainTextResponse("late")
        await response(scope, receive, send)

    wrapped = RequestTimeoutMiddleware(CompressMiddleware(slow), seconds=0.05)
    timed = TestClient(wrapped)
    response = timed.get("/")
    assert response.status_code == 504
    assert response.json()["detail"] == "timeout"
