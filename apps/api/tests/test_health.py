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


def _two_revision_scripts(tmp_path: Path):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "001_ancestor.py").write_text(
        'revision = "001"\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n\n'
        "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
        encoding="utf-8",
    )
    (versions / "002_head.py").write_text(
        'revision = "002"\ndown_revision = "001"\nbranch_labels = None\ndepends_on = None\n\n'
        "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
        encoding="utf-8",
    )
    cfg = Config()
    cfg.set_main_option("script_location", str(tmp_path))
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(cfg)


def test_schema_head_ancestor_and_unknown(tmp_path, monkeypatch):
    script = _two_revision_scripts(tmp_path)
    monkeypatch.setattr(health_router, "_script_directory", lambda: script)

    _set_db_revision("002")
    at_head = client.get("/v1/health/ready")
    assert at_head.status_code == 200, at_head.text
    assert at_head.json() == {"ok": True}
    assert "002" not in at_head.text

    _set_db_revision("001")
    older = client.get("/v1/health/ready")
    assert older.status_code == 503
    assert older.json() == {"ok": False, "checks": ["schema"]}
    assert "001" not in older.text

    _set_db_revision("future001")
    newer = client.get("/v1/health/ready")
    assert newer.status_code == 200, newer.text
    assert newer.json() == {"ok": True}
    assert "future001" not in newer.text
    _stamp_head()


def _revision_scripts(tmp_path: Path, revisions: list[tuple[str, str | None]]):
    versions = tmp_path / "versions"
    versions.mkdir()
    for revision, down in revisions:
        down_src = "None" if down is None else f'"{down}"'
        (versions / f"{revision}.py").write_text(
            f'revision = "{revision}"\ndown_revision = {down_src}\n'
            "branch_labels = None\ndepends_on = None\n\n"
            "def upgrade():\n    pass\n\ndef downgrade():\n    pass\n",
            encoding="utf-8",
        )
    cfg = Config()
    cfg.set_main_option("script_location", str(tmp_path))
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(cfg)


def test_schema_two_heads_and_unknown_ahead(tmp_path, monkeypatch):
    script = _revision_scripts(tmp_path, [("a1", None), ("b1", None)])
    monkeypatch.setattr(health_router, "_script_directory", lambda: script)
    assert set(script.get_heads()) == {"a1", "b1"}

    _set_db_revisions("a1", "b1")
    both = client.get("/v1/health/ready")
    assert both.status_code == 200, both.text
    assert both.json() == {"ok": True}

    _set_db_revisions("a1")
    missing = client.get("/v1/health/ready")
    assert missing.status_code == 503
    assert missing.json() == {"ok": False, "checks": ["schema"]}
    assert "a1" not in missing.text
    assert "b1" not in missing.text

    _set_db_revisions("a1", "zz")
    ahead = client.get("/v1/health/ready")
    assert ahead.status_code == 200, ahead.text
    assert ahead.json() == {"ok": True}
    assert "zz" not in ahead.text
    _stamp_head()


def test_head_applied_when_database_revision_descends_from_it(tmp_path):
    script = _revision_scripts(tmp_path, [("a1", None), ("a2", "a1"), ("b1", None)])
    assert health_router._head_applied(script, "a1", {"a2"}) is True
    assert health_router._head_applied(script, "a2", {"a1"}) is False
    assert health_router._schema_matches(script, {"a2", "b1"}) is True
    assert health_router._schema_matches(script, {"a1", "b1"}) is False


def test_schema_match_rejects_revision_prefixes(tmp_path, monkeypatch):
    script = _revision_scripts(tmp_path, [("20261019_0001", None), ("headb", "20261019_0001")])
    monkeypatch.setattr(health_router, "_script_directory", lambda: script)
    assert script.get_revision("2026").revision == "20261019_0001"
    assert "2026" not in {revision.revision for revision in script.walk_revisions()}

    _set_db_revision("2026")
    prefixed = client.get("/v1/health/ready")
    assert prefixed.status_code == 200, prefixed.text
    assert prefixed.json() == {"ok": True}
    assert "2026" not in prefixed.text
    assert "20261019_0001" not in prefixed.text

    _set_db_revision("20261019_0001")
    older = client.get("/v1/health/ready")
    assert older.status_code == 503
    assert older.json() == {"ok": False, "checks": ["schema"]}
    assert "20261019_0001" not in older.text
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
    from sqlalchemy.engine import make_url

    engine = health_router._probe_engine
    assert engine.pool.__class__ is health_router.NullPool
    params = inspect.getclosurevars(engine.pool._creator).nonlocals["cparams"]
    expected = health_router._probe_connect_args(store._sql.url)
    for key, value in expected.items():
        assert params[key] == value
    assert engine.url == make_url(store._sql.url)

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


def test_production_docs_return_404(tmp_path):
    code = """
import os
from sqlalchemy import create_engine
from app.sql_backend import Base, resolve_database_url

engine = create_engine(resolve_database_url())
Base.metadata.create_all(engine)
engine.dispose()

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
