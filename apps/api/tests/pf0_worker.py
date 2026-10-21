"""One worker for the company-key and first-flag races. Fresh process, shared database."""

import json
import os
import sys
import time
from pathlib import Path


def _register(email: str, bin_no: str, dest: str) -> None:
    from app.schemas import RegisterBody
    from app.store import store

    user, _token = store.register(
        RegisterBody(
            email=email,
            password="secret12",
            full_name="Race User",
            phone="+77001112233",
            company="Race LLP",
            company_bin=bin_no,
            city="Almaty",
            role="buyer",
            consent_offer_pd=True,
        ),
        ip="127.0.0.1",
        user_agent="anyq-test",
    )
    Path(dest).write_text(
        json.dumps(
            {"id": user.id, "key": user.company_key, "review": user.company_review}
        ),
        encoding="utf-8",
    )


def _flag(company_id: str, dest: str) -> None:
    from fastapi import HTTPException

    from app.company_features import set_feature

    try:
        set_feature(company_id, "offline", True, "u-race", row_version=0)
        code = 200
    except HTTPException as exc:
        code = exc.status_code
    Path(dest).write_text(json.dumps({"code": code}), encoding="utf-8")


def _wait(path: str) -> None:
    deadline = time.time() + 45
    while time.time() < deadline:
        if Path(path).exists():
            return
        time.sleep(0.02)
    raise SystemExit(f"timed out waiting for {path}")


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ["ANYQ_DEMO_MODE"] = "0"
    kind = sys.argv[1]
    dest, ready, start = sys.argv[-3], sys.argv[-2], sys.argv[-1]
    if kind == "register":
        from app.store import store

        assert store.users_by_id is not None
        Path(ready).write_text("ready", encoding="utf-8")
        _wait(start)
        _register(sys.argv[2], sys.argv[3], dest)
        return
    if kind == "flag":
        from app.store import store

        assert store.users_by_id is not None
        Path(ready).write_text("ready", encoding="utf-8")
        _wait(start)
        _flag(sys.argv[2], dest)
        return
    raise SystemExit(f"unknown worker {kind}")


if __name__ == "__main__":
    main()
