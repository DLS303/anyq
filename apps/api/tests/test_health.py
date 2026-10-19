import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from alembic import command
from app.config import settings
from app.main import app
from app.routers import health as health_router
from app.store import store

client = TestClient(app)
REPO = Path(__file__).resolve().parents[3]
API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    ini = API_ROOT / "alembic.ini"
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(ini.parent / "alembic"))
    cfg.set_main_option("path_separator", "os")
    return cfg


def _stamp_head() -> None:
    command.stamp(_alembic_config(), "head")


def _drop_alembic_version() -> None:
    with store._sql.engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def test_healthz_is_liveness_only():
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_health_and_version_fields(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("BUILD_TIME", "2026-10-19T00:00:00Z")
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json() == {"ok": True, "version": settings.version}

    version_res = client.get("/v1/version")
    assert version_res.status_code == 200
    assert version_res.json() == {
        "version": settings.version,
        "git_sha": "abc1234",
        "build_time": "2026-10-19T00:00:00Z",
    }


def test_health_and_version_omit_sensitive_fields(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("BUILD_TIME", "2026-10-19T00:00:00Z")
    health_res = client.get("/health")
    version_res = client.get("/v1/version")
    assert set(health_res.json()) == {"ok", "version"}
    assert set(version_res.json()) == {"version", "git_sha", "build_time"}
    blob = (health_res.text + version_res.text).lower()
    for word in ("sqlite", "postgres", "password", "hostname", "traceback", "database_url", "dialect"):
        assert word not in blob


def test_ready_ok_when_dependencies_pass():
    _stamp_head()
    res = client.get("/v1/health/ready")
    assert res.status_code == 200, res.text
    assert res.json() == {"ok": True}
    lowered = res.text.lower()
    assert "20261019_0001" not in res.text
    for word in ("sqlite", "postgres", "dialect", "alembic", "uploads", "traceback"):
        assert word not in lowered


def test_ready_503_when_uploads_dir_is_missing(tmp_path, monkeypatch):
    _stamp_head()
    missing = tmp_path / "absent-volume" / "uploads"
    monkeypatch.setenv("ANYQ_UPLOADS_DIR", str(missing))
    res = client.get("/v1/health/ready")
    assert res.status_code == 503
    assert res.json() == {"ok": False, "checks": ["uploads"]}
    assert not missing.exists()
    assert not missing.parent.exists()
    assert "absent-volume" not in res.text


def test_ready_names_alembic_when_revision_is_not_head():
    _drop_alembic_version()
    res = client.get("/v1/health/ready")
    assert res.status_code == 503
    assert res.json() == {"ok": False, "checks": ["alembic"]}
    assert "20261019_0001" not in res.text
    assert "sqlite" not in res.text.lower()


def test_ready_503_when_database_is_down(monkeypatch):
    secret_host = "db.internal.example"
    secret_path = "/var/lib/anyq/secret-data"
    secret_version = "PostgreSQL 16.4"

    def connect(*_args, **_kwargs):
        raise OperationalError(
            "SELECT 1",
            {},
            Exception(f"could not connect to {secret_host} at {secret_path} version {secret_version}"),
        )

    monkeypatch.setattr(store._sql.engine, "connect", connect)
    live = client.get("/healthz")
    assert live.status_code == 200
    assert live.json() == {"ok": True}
    info = client.get("/health")
    assert info.status_code == 200
    assert set(info.json()) == {"ok", "version"}

    res = client.get("/v1/health/ready")
    assert res.status_code == 503
    assert res.json() == {"ok": False, "checks": ["db", "alembic"]}
    for secret in (secret_host, secret_path, secret_version, "Traceback", "OperationalError", "SELECT"):
        assert secret not in res.text


def test_postgres_probe_uses_select_1_with_two_second_timeout(monkeypatch):
    class Conn:
        def __init__(self):
            self.statements: list[str] = []
            self.dialect = SimpleNamespace(name="postgresql")

        def execute(self, statement, *_args, **_kwargs):
            self.statements.append(str(statement))
            return SimpleNamespace()

        def rollback(self):
            self.statements.append("ROLLBACK")

    class Connect:
        def __init__(self, conn: Conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, *_args):
            return False

    conn = Conn()
    monkeypatch.setattr(store._sql.engine, "connect", lambda: Connect(conn))
    assert health_router._db_ok() is True
    script = "\n".join(conn.statements)
    assert "SET LOCAL statement_timeout = '2s'" in script
    assert "SELECT 1" in script


def test_dev_docs_remain_available():
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["openapi"]
    assert client.get("/redoc").status_code == 200
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["docs"] == "/docs"


def test_production_docs_return_404(tmp_path):
    code = """
import os
from fastapi.testclient import TestClient
from app.main import app

assert os.environ["ANYQ_ENV"] == "production"
assert app.docs_url is None
assert app.redoc_url is None
assert app.openapi_url is None
client = TestClient(app)
live = client.get("/healthz")
assert live.status_code == 200, live.text
assert live.json() == {"ok": True}
for path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
    res = client.get(path)
    assert res.status_code == 404, (path, res.status_code, res.text)
    lowered = res.text.lower()
    assert "swagger" not in lowered
    assert "<html" not in lowered
root = client.get("/")
assert root.status_code == 200, root.text
assert "docs" not in root.json()
assert "/docs" not in root.text
print("docs-hidden")
"""
    env = os.environ.copy()
    env["ANYQ_ENV"] = "production"
    env["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
    env["CORS_ORIGINS"] = "http://localhost:3000"
    env["ANYQ_DB_PATH"] = str(tmp_path / "db.json")
    env["ANYQ_UPLOADS_DIR"] = str(tmp_path / "uploads")
    env["ANYQ_DEMO_PASSWORD"] = ""
    env["ANYQ_DEMO_MODE"] = "0"
    env.pop("DATABASE_URL", None)
    env.pop("ANYQ_DATA_DIR", None)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "docs-hidden" in completed.stdout


def test_caddy_does_not_route_api_docs():
    text = (REPO / "deploy" / "Caddyfile").read_text()
    assert "ANYQ_PUBLIC_DOCS" not in text
    assert 'Permissions-Policy "camera=(self), geolocation=(self), microphone=(self)"' in text
    assert "Content-Security-Policy-Report-Only" in text
    match = re.search(r"handle @api_docs \{(?P<body>.*?)\n\t\}", text, re.DOTALL)
    assert match is not None
    body = match.group("body")
    assert "respond 404" in body
    assert "reverse_proxy" not in body
    assert "handle /docs" not in text
    assert "handle /redoc" not in text
    assert "handle /openapi.json" not in text
    ready = re.search(r"handle /v1/health/ready \{(?P<body>.*?)\n\t\}", text, re.DOTALL)
    assert ready is not None
    assert "respond 404" in ready.group("body")
    assert "reverse_proxy" not in ready.group("body")
    assert text.index("handle /v1/health/ready") < text.index("handle /v1/*")


def test_deploy_uses_readiness_and_build_identity():
    compose = (REPO / "deploy" / "docker-compose.prod.yml").read_text()
    assert "http://127.0.0.1:8010/v1/health/ready" in compose
    assert "8010/healthz" not in compose
    assert "http://127.0.0.1:3000/healthz" in compose
    assert "GIT_SHA:" in compose
    assert "BUILD_TIME:" in compose
    script = (REPO / "deploy" / "deploy.sh").read_text()
    assert '"$base/v1/health/ready"' not in script
    assert "127.0.0.1:8010/v1/health/ready" in script
    assert "docker exec anyq-api" in script
    assert '"$base/v1/version"' in script
    api_docker = (REPO / "apps" / "api" / "Dockerfile").read_text()
    web_docker = (REPO / "apps" / "web" / "Dockerfile").read_text()
    assert "ARG GIT_SHA=" in api_docker
    assert "ARG BUILD_TIME=" in api_docker
    assert "GIT_SHA=${GIT_SHA}" in api_docker
    assert "BUILD_TIME=${BUILD_TIME}" in api_docker
    assert "ARG GIT_SHA=" in web_docker
    assert "GIT_SHA=$GIT_SHA" in web_docker
    web_health = (REPO / "apps" / "web" / "src" / "app" / "healthz" / "route.ts").read_text()
    assert "ok: true" in web_health
