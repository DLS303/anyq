import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from app.paths import REPO_ROOT

PD_VERSION = os.getenv("LEGAL_PD_VERSION", "2026-10-18").strip() or "2026-10-18"
PRIVACY_VERSION = os.getenv("LEGAL_PRIVACY_VERSION", "2026-10-18").strip() or "2026-10-18"
AI_VERSION = os.getenv("LEGAL_AI_VERSION", "2026-10-19").strip() or "2026-10-19"


@dataclass(frozen=True)
class LegalDocument:
    key: str
    version: str
    sha256: str


def legal_dir() -> Path:
    override = os.getenv("LEGAL_DIR", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "apps" / "web" / "content" / "legal"


def _file_sha256(name: str) -> str:
    path = legal_dir() / name
    data = path.read_bytes() if path.is_file() else b""
    return hashlib.sha256(data).hexdigest()


def pd_consent_text() -> bytes:
    path = legal_dir() / "pd-consent.ru.md"
    if not path.is_file():
        return b""
    return path.read_bytes()


def pd_sha256() -> str:
    return hashlib.sha256(pd_consent_text()).hexdigest()


def offer_pd_document() -> LegalDocument:
    return LegalDocument("offer_pd", PD_VERSION, pd_sha256())


def privacy_document() -> LegalDocument:
    return LegalDocument("privacy", PRIVACY_VERSION, _file_sha256("privacy.ru.md"))


def ai_document() -> LegalDocument:
    return LegalDocument("ai", AI_VERSION, _file_sha256("ai-consent.ru.md"))


def consent_documents() -> list[LegalDocument]:
    return [offer_pd_document(), privacy_document(), ai_document()]
