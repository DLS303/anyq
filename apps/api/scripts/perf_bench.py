"""Time the main read endpoints on a throwaway database.

    python scripts/perf_bench.py

Prints one JSON object with p50/p95 milliseconds. Uses a temporary SQLite
file and never reads or writes data/db.json.
"""

from __future__ import annotations

import json
import os
import statistics
import tempfile
import time
from pathlib import Path


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def _prepare() -> None:
    root = Path(tempfile.mkdtemp(prefix="anyq-perf-"))
    os.environ["ANYQ_ENV"] = "development"
    os.environ["ANYQ_DEMO_MODE"] = "0"
    os.environ["ANYQ_DEMO_PASSWORD"] = ""
    os.environ["JWT_SECRET"] = "perf-only-secret-value-with-32-characters"
    os.environ["LOGIN_HASH_SECRET"] = "perf-only-login-hash-secret-value-32ch"
    os.environ.pop("DATABASE_URL", None)
    os.environ["ANYQ_DB_PATH"] = str(root / "db.json")
    os.environ["ANYQ_UPLOADS_DIR"] = str(root / "uploads")
    os.environ["CORS_ORIGINS"] = "http://localhost:3000"


def main() -> None:
    _prepare()
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from fastapi.testclient import TestClient

    from app.authutil import hash_password
    from app.main import app
    from app.schemas import User
    from app.site_models import RFI, BudgetLine, PunchItem
    from app.store import store

    owner = User(
        id="u-perf",
        email="perf-owner@example.com",
        full_name="Perf Owner",
        role="owner",
        phone="+77001110000",
        company="Perf LLP",
        company_bin="123456789012",
    )
    store._index_user(owner)
    store.credentials[owner.id] = hash_password("secret12")
    projects = []
    for index in range(40):
        projects.append(store.create_project(owner, f"Объект {index:02d} корпус", f"Алматы, улица {index}"))
    for index, project in enumerate(projects):
        for line in range(8):
            item = BudgetLine(
                id=f"bl-{index}-{line}",
                project_id=project.id,
                code=f"{line}",
                title="Материалы",
                budget_kzt=100_000 + line,
                committed_kzt=20_000,
                actual_kzt=10_000,
            )
            store.budget_lines[item.id] = item
        if index % 3 == 0:
            punch = PunchItem(
                id=f"pu-{index}",
                project_id=project.id,
                title="Открытый пункт",
                location="ось",
                trade="ТБ",
                status="open",
                assignee_id=owner.id,
            )
            store.punches[punch.id] = punch
            rfi = RFI(
                id=f"rfi-{index}",
                project_id=project.id,
                number=f"RFI-{index}",
                title="Вопрос",
                question="Уточнить отметку",
                answer="",
                status="open",
                assignee_id=owner.id,
                drawing="",
                created_at="2026-10-01T00:00:00+00:00",
            )
            store.rfis[rfi.id] = rfi
    store._save()
    focus = projects[0].id

    client = TestClient(app)
    login = client.post(
        "/v1/auth/login",
        json={"email": owner.email, "password": "secret12", "consent_offer_pd": True},
        headers={"User-Agent": "anyq-perf"},
    )
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
    paths = {
        "/health": None,
        "/v1/plots?limit=24&offset=0": None,
        "/v1/materials?limit=24&offset=0": None,
        "/v1/site/projects": headers,
        f"/v1/site/projects/{focus}/bundle": headers,
        f"/v1/site/projects/{focus}/object-budget": headers,
        f"/v1/procurement/projects/{focus}/requests": headers,
    }
    samples: dict[str, list[float]] = {path.split("?", 1)[0]: [] for path in paths}
    for _ in range(3):
        for path, hdrs in paths.items():
            client.get(path, headers=hdrs)
    for _ in range(21):
        for path, hdrs in paths.items():
            started = time.perf_counter()
            response = client.get(path, headers=hdrs)
            elapsed = (time.perf_counter() - started) * 1000
            response.raise_for_status()
            samples[path.split("?", 1)[0]].append(elapsed)
    endpoints = {}
    for path, values in samples.items():
        endpoints[path] = {
            "n": len(values),
            "p50_ms": round(_pct(values, 50), 2),
            "p95_ms": round(_pct(values, 95), 2),
            "mean_ms": round(statistics.fmean(values), 2) if values else 0,
        }
    print(json.dumps({"projects": len(projects), "budget_lines": len(store.budget_lines), "endpoints": endpoints}, ensure_ascii=False))


if __name__ == "__main__":
    main()
