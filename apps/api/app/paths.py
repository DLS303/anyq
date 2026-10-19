import os
from pathlib import Path
from uuid import uuid4

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
    if kind in ("original", "voice", "drawing_pdf", "markup_photo"):
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


def stage_upload(kind: str, data: bytes) -> tuple[str, Path]:
    """Write bytes to a temp file. The storage key is generated here, not from a client id."""
    root = kind_root(kind)
    key = f"{uuid4().hex}.pdf" if kind == "drawing_pdf" else uuid4().hex
    tmp = root / f".part-{uuid4().hex}"
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        view = memoryview(data)
        written = 0
        while written < len(view):
            written += os.write(fd, view[written:])
    except Exception:
        os.close(fd)
        os.unlink(tmp)
        raise
    os.close(fd)
    return key, tmp


def publish_upload(kind: str, key: str, tmp: Path) -> Path:
    """Move a staged file into place after commit. An existing name is left untouched."""
    dest = resolve_stored_file(kind, key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(tmp, dest)
    except FileExistsError:
        discard_upload(tmp)
        raise
    discard_upload(tmp)
    return dest


def discard_upload(tmp: Path | None) -> None:
    if tmp is None:
        return
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
