import os
import tempfile
from pathlib import Path

import pytest

_root = Path(tempfile.mkdtemp(prefix="anyq-test-"))
os.environ["ANYQ_ENV"] = "development"
os.environ["JWT_SECRET"] = "test-only-secret-value-with-32-characters"
os.environ["ANYQ_DB_PATH"] = str(_root / "db.json")
os.environ["ANYQ_UPLOADS_DIR"] = str(_root / "uploads")
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ANYQ_DEMO_PASSWORD"] = ""
os.environ["ANYQ_DEMO_MODE"] = "1"


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.ratelimit import login_limiter

    login_limiter.reset()
    yield
    login_limiter.reset()
