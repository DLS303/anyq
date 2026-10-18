import hashlib
import os
from pathlib import Path

from app.paths import REPO_ROOT

PD_VERSION = os.getenv("LEGAL_PD_VERSION", "2026-10-18").strip() or "2026-10-18"


def legal_dir() -> Path:
    override = os.getenv("LEGAL_DIR", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "apps" / "web" / "content" / "legal"


def pd_consent_text() -> bytes:
    path = legal_dir() / "pd-consent.ru.md"
    if not path.is_file():
        return b""
    return path.read_bytes()


def pd_sha256() -> str:
    return hashlib.sha256(pd_consent_text()).hexdigest()
