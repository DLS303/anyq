import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def uploads_dir() -> Path:
    override = os.getenv("ANYQ_UPLOADS_DIR", "").strip()
    path = Path(override) if override else REPO_ROOT / "data" / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path
