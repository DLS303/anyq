"""Run stored photos through the image pipeline.

Dry-run by default. Pass --execute to rewrite originals without metadata and
refresh the matching public copy when a daily report already has one.
"""

from __future__ import annotations

import argparse

from app.media import process_upload, strip_image
from app.paths import resolve_stored_file, write_stored_file
from app.store import store


def _plan() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for item in store.files.values():
        if item.kind not in ("upload", "original"):
            continue
        try:
            path = resolve_stored_file(item.kind, item.name)
        except ValueError:
            rows.append((item.id, item.kind, "skip-path"))
            continue
        if not path.is_file():
            rows.append((item.id, item.kind, "missing"))
            continue
        rows.append((item.id, item.kind, "clean"))
    return rows


def execute() -> int:
    changed = 0
    originals = [item for item in store.files.values() if item.kind == "original"]
    for item in originals:
        try:
            path = resolve_stored_file(item.kind, item.name)
        except ValueError:
            continue
        if not path.is_file():
            continue
        processed = process_upload(path.read_bytes())
        write_stored_file("original", item.name, processed.original)
        log = store.daily_logs.get(item.daily_log_id or "")
        if log:
            match = next((photo for photo in log.photos if photo.original_id == item.id), None)
            if match:
                write_stored_file("public", f"{log.project_id}/{match.public_id}.jpg", processed.public)
        changed += 1
    uploads = [item for item in store.files.values() if item.kind == "upload"]
    for item in uploads:
        try:
            path = resolve_stored_file(item.kind, item.name)
        except ValueError:
            continue
        if not path.is_file():
            continue
        try:
            clean, _content_type, _suffix = strip_image(path.read_bytes())
        except ValueError:
            continue
        path.write_bytes(clean)
        changed += 1
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description="Reprocess stored photos")
    parser.add_argument("--execute", action="store_true", help="Rewrite files. Default is dry-run.")
    args = parser.parse_args()
    plan = _plan()
    for file_id, kind, action in plan:
        print(f"{action}\t{kind}\t{file_id}")
    print(f"files={len(plan)} execute={args.execute}")
    if args.execute:
        print(f"rewritten={execute()}")


if __name__ == "__main__":
    main()
