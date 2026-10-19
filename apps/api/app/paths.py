import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def uploads_dir() -> Path:
    override = os.getenv("ANYQ_UPLOADS_DIR", "").strip()
    path = Path(override) if override else REPO_ROOT / "data" / "uploads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_root() -> Path:
    override = os.getenv("ANYQ_DATA_DIR", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return uploads_dir().parent


def kind_root(kind: str) -> Path:
    if kind in ("original", "voice"):
        path = media_root() / "private"
    elif kind == "public":
        path = media_root() / "public"
    else:
        return uploads_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_stored_file(kind: str, name: str) -> Path:
    """Resolve a stored file and reject paths that leave the kind directory."""
    rel = Path(name)
    if not name or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("bad path")
    root = kind_root(kind).resolve()
    path = (root / rel).resolve()
    if path == root or root not in path.parents:
        raise ValueError("bad path")
    return path


def write_stored_file(kind: str, name: str, data: bytes) -> Path:
    path = resolve_stored_file(kind, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
