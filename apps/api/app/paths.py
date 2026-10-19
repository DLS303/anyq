import logging
import os
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

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


def write_exclusive_temp(kind: str, data: bytes) -> Path:
    """Write bytes to a new temp file. The name is a server uuid, never a client id."""
    root = kind_root(kind)
    path = root / f".tmp-{uuid4().hex}"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
    except Exception:
        os.close(fd)
        os.unlink(path)
        raise
    os.close(fd)
    return path


def discard_temp(path: Path | None) -> None:
    if path is None:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        return


def publish_exclusive(kind: str, tmp: Path, storage_key: str) -> Path:
    """Publish a temp file after commit. An existing object is left unchanged."""
    if not storage_key or storage_key.startswith(".") or "/" in storage_key or "\\" in storage_key:
        discard_temp(tmp)
        raise ValueError("bad storage key")
    final = resolve_stored_file(kind, storage_key)
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(tmp, final)
    except FileExistsError as exc:
        discard_temp(tmp)
        logger.warning("stored object already exists")
        raise FileExistsError("stored object already exists") from exc
    os.unlink(tmp)
    return final
