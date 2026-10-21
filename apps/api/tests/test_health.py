import inspect
import os
import re
import subprocess
import sys
import time
from pathlib import Path

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
    _drop_alembic_version()
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


def test_version_returns_short_sha(monkeypatch):
    full = "0123456789ABCDEF0123456789abcdef01234567"
    monkeypatch.setenv("GIT_SHA", full)
    monkeypatch.setenv("BUILD_TIME", "2026-10-21T00:00:00Z")
    res = client.get("/v1/version")
    assert res.status_code == 200
    assert res.json()["git_sha"] == "0123456"
    assert full not in res.text


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
    from app.sql_backend import SCHEMA_HEAD

    _stamp_head()
    res = client.get("/v1/health/ready")
    assert res.status_code == 200, res.text
    assert res.json() == {"ok": True}
    lowered = res.text.lower()
    assert SCHEMA_HEAD not in res.text
    for word in ("sqlite", "postgres", "dialect", "alembic", "uploads", "traceback"):
        assert word not in lowered


def test_ready_alias_matches_v1_health_ready():
    try:
        _stamp_head()
        canonical = client.get("/v1/health/ready")
        alias = client.get("/ready")
        assert canonical.status_code == 200
        assert alias.status_code == canonical.status_code
        assert alias.json() == canonical.json() == {"ok": True}

        _set_db_revision("not-in-this-chain")
        canonical = client.get("/v1/health/ready")
        alias = client.get("/ready")
        assert canonical.status_code == 503
        assert alias.status_code == canonical.status_code
        assert alias.json() == canonical.json()
        assert alias.json() == {"ok": False, "checks": ["schema"]}
    finally:
        _stamp_head()


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


def _set_db_revisions(*revisions: str) -> None:
    with store._sql.engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("DELETE FROM alembic_version"))
        for revision in revisions:
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES (:revision)"), {"revision": revision})


def _set_db_revision(revision: str | None) -> None:
    if revision is None:
        _set_db_revisions()
    else:
        _set_db_revisions(revision)


def test_ready_follows_revision_chain(monkeypatch):
    from alembic.script import ScriptDirectory

    from app.sql_backend import SCHEMA_HEAD, database_revision_ready

    script = ScriptDirectory.from_config(_alembic_config())
    assert script.get_heads() == [SCHEMA_HEAD]
    parent = script.get_revision(SCHEMA_HEAD).down_revision
    assert isinstance(parent, str)
    assert database_revision_ready(SCHEMA_HEAD)
    assert database_revision_ready(SCHEMA_HEAD, expected=parent)
    assert not database_revision_ready(parent)
    assert not database_revision_ready("not-in-this-chain")

    try:
        _stamp_head()
        at_head = client.get("/v1/health/ready")
        assert at_head.status_code == 200, at_head.text
        assert at_head.json() == {"ok": True}
        assert SCHEMA_HEAD not in at_head.text

        _set_db_revision(parent)
        older = client.get("/v1/health/ready")
        assert older.status_code == 503
        assert older.json() == {"ok": False, "checks": ["schema"]}
        assert parent not in older.text

        monkeypatch.setattr("app.sql_backend.SCHEMA_HEAD", parent)
        _stamp_head()
        later = client.get("/v1/health/ready")
        assert later.status_code == 200, later.text
        assert later.json() == {"ok": True}

        monkeypatch.setattr("app.sql_backend.SCHEMA_HEAD", SCHEMA_HEAD)
        _set_db_revision("not-in-this-chain")
        unknown = client.get("/v1/health/ready")
        assert unknown.status_code == 503
        assert unknown.json() == {"ok": False, "checks": ["schema"]}
        assert "not-in-this-chain" not in unknown.text
    finally:
        _stamp_head()


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

    calls = {"n": 0}

    def broken_probe():
        calls["n"] += 1
        raise OperationalError(
            "SELECT 1",
            {},
            Exception(f"could not connect to {secret_host} at {secret_path} version {secret_version}"),
        )

    monkeypatch.setattr(health_router, "_probe_connection", broken_probe)
    res = client.get("/v1/health/ready")
    assert res.status_code == 503
    assert calls["n"] == 1
    assert res.json() == {"ok": False, "checks": ["db"]}
    for secret in (secret_host, secret_path, secret_version, "Traceback", "OperationalError", "SELECT"):
        assert secret not in res.text


def test_probe_uses_private_engine_with_two_second_timeout(monkeypatch):
    engine = health_router._probe_engine
    assert engine.pool.__class__ is health_router.NullPool
    params = inspect.getclosurevars(engine.pool._creator).nonlocals["cparams"]
    if store._sql.url.startswith("sqlite"):
        assert params["timeout"] == 2
    else:
        assert params["connect_timeout"] == 2
    assert engine.url.render_as_string(hide_password=False) == store._sql.url

    def fail_create(*_args, **_kwargs):
        raise AssertionError("probe engine is created per request")

    monkeypatch.setattr(health_router, "create_engine", fail_create)
    calls = {"n": 0}
    real_connect = engine.connect

    def counting_connect(*args, **kwargs):
        calls["n"] += 1
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(engine, "connect", counting_connect)
    _stamp_head()
    res = client.get("/v1/health/ready")
    assert res.status_code == 200, res.text
    assert calls["n"] == 1


def test_probe_works_while_app_pool_is_exhausted():
    _stamp_head()
    engine = store._sql.engine
    previous_timeout = engine.pool._timeout
    engine.pool._timeout = 0.2
    limit = engine.pool.size() + engine.pool._max_overflow
    held = []
    try:
        for _ in range(limit):
            held.append(engine.connect())
        started = time.monotonic()
        res = client.get("/v1/health/ready")
        elapsed = time.monotonic() - started
    finally:
        for conn in held:
            conn.close()
        engine.pool._timeout = previous_timeout
    assert res.status_code == 200, res.text
    assert res.json() == {"ok": True}
    assert elapsed < 2


def test_dev_docs_remain_available():
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["openapi"]
    assert client.get("/redoc").status_code == 200
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["docs"] == "/docs"


def test_ready_503_schema_when_migrations_are_unreadable(monkeypatch):
    def unreadable(*_args, **_kwargs):
        raise OSError("migrations unreadable")

    _set_db_revision("not-in-this-chain")
    monkeypatch.setattr("alembic.script.ScriptDirectory.from_config", unreadable)
    try:
        res = client.get("/v1/health/ready")
        assert res.status_code == 503
        assert res.json() == {"ok": False, "checks": ["schema"]}
        assert "migrations" not in res.text
    finally:
        monkeypatch.undo()
        _stamp_head()


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
    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stdout + upgraded.stderr
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
    assert "@ready path /v1/health/ready /v1/health/ready/*" in text
    ready = re.search(r"handle @ready \{(?P<body>.*?)\n\t\}", text, re.DOTALL)
    assert ready is not None
    assert "respond 404" in ready.group("body")
    assert "reverse_proxy" not in ready.group("body")
    assert text.index("handle @ready") < text.index("handle /v1/*")
    assert "handle /healthz" not in text
    assert "reverse_proxy web:3000" in text


def test_deploy_uses_readiness_and_build_identity():
    compose = (REPO / "deploy" / "docker-compose.prod.yml").read_text()
    assert "http://127.0.0.1:8010/v1/health/ready" in compose
    assert "8010/healthz" not in compose
    assert "http://127.0.0.1:3000/healthz" in compose
    assert "GIT_SHA:" in compose
    assert "BUILD_TIME:" in compose
    assert "container_name: ${ANYQ_API_CONTAINER:-anyq-api}" in compose
    script = (REPO / "deploy" / "deploy.sh").read_text()
    assert '"$base/v1/health/ready"' not in script
    assert "127.0.0.1:8010/v1/health/ready" in script
    assert 'API_CONTAINER="${ANYQ_API_CONTAINER:-anyq-api}"' in script
    assert 'docker exec "$API_CONTAINER"' in script
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
    render = (REPO / "render.yaml").read_text()
    assert "healthCheckPath: /healthz" in render
