"""Copy data/db.json into the SQL database.

The import is idempotent: a second run updates changed rows and leaves matching
rows in place. ``--dry-run`` prints the same counts and writes nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.sql_backend import (
    LISTS,
    PERSISTED,
    Record,
    SqlRuntime,
    bump_revisions,
    index_values,
    read_json_store,
)


def _iter(raw: dict, users: dict, specs: dict):
    for item in raw.get("users") or []:
        users[str(item["id"])] = type("User", (), item)
        yield "users", str(item["id"]), item
    for item in raw.get("specialists") or []:
        specs[str(item["id"])] = type("Spec", (), item)
    for user_id, password_hash in (raw.get("credentials") or {}).items():
        yield "credentials", str(user_id), {"password_hash": str(password_hash)}
    names = [name for _attr, name in PERSISTED if name not in {"users", "credentials"}]
    names.extend(name for _attr, name in LISTS)
    for name in names:
        rows = raw.get(name) or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        for item in rows:
            if name == "favorites":
                doc_id = f"{item.get('user_id')}:{item.get('plot_id')}"
            elif name == "object_budgets":
                doc_id = str(item.get("project_id") or item.get("id"))
            else:
                doc_id = str(item["id"])
            yield name, doc_id, item


def import_payload(raw: dict, *, dry_run: bool = False, runtime: SqlRuntime | None = None) -> dict:
    own_runtime = runtime is None
    runtime = runtime or SqlRuntime()
    users: dict = {}
    specs: dict = {}
    docs = list(_iter(raw, users, specs))

    class _Bag:
        pass

    bag = _Bag()
    bag.users_by_id = users
    bag.specialists = specs
    collections: dict[str, dict[str, int]] = {}
    session = runtime.factory()
    try:
        for collection, doc_id, payload in docs:
            bucket = collections.setdefault(collection, {"insert": 0, "update": 0, "same": 0})
            stored = json.loads(json.dumps(payload, ensure_ascii=False))
            current = session.get(Record, (collection, doc_id))
            if current is None:
                bucket["insert"] += 1
                if dry_run:
                    continue
                fields = index_values(bag, collection, doc_id, stored)
                session.add(
                    Record(collection=collection, doc_id=doc_id, seq=bucket["insert"], payload=stored, **fields)
                )
                continue
            if current.payload == stored:
                bucket["same"] += 1
                continue
            bucket["update"] += 1
            if dry_run:
                continue
            current.payload = stored
            current.row_version = int(current.row_version or 1) + 1
            current.seq = int(current.seq or 0) + 1
            for field, value in index_values(bag, collection, doc_id, stored).items():
                setattr(current, field, value)
        changed = [name for name, bucket in collections.items() if bucket["insert"] or bucket["update"]]
        if not dry_run and changed:
            bump_revisions(session, set(changed))
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if own_runtime:
            runtime.engine.dispose()
    return {
        "dry_run": dry_run,
        "collections": collections,
        "total": {
            "insert": sum(item["insert"] for item in collections.values()),
            "update": sum(item["update"] for item in collections.values()),
            "same": sum(item["same"] for item in collections.values()),
        },
    }


def import_file(path: Path, *, dry_run: bool = False) -> dict:
    return import_payload(read_json_store(path), dry_run=dry_run)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Import db.json into the SQL database")
    parser.add_argument("path", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    report = import_file(args.path, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
