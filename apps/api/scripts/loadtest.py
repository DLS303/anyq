"""Concurrent read/write probe for the main API.

    python scripts/loadtest.py --base http://127.0.0.1:8010 --users 50 --rounds 2

Prints one JSON object with p50/p95 milliseconds per endpoint and overall.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


async def _hit(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> tuple[str, float, int, httpx.Response]:
    started = time.perf_counter()
    response = await client.request(method, path, **kwargs)
    elapsed = (time.perf_counter() - started) * 1000
    return path, elapsed, response.status_code, response


async def _user(client: httpx.AsyncClient, index: int, rounds: int) -> list[tuple[str, float, int]]:
    samples: list[tuple[str, float, int]] = []
    for _ in range(rounds):
        email = f"load-{index}-{uuid.uuid4().hex[:8]}@example.com"
        password = "secret12"
        body = {
            "email": email,
            "password": password,
            "full_name": "Load Tester",
            "phone": "+77001234567",
            "company": f"Load LLP {index}",
            "company_bin": f"{(index * 97 + int(uuid.uuid4().hex[:6], 16)) % 10**12:012d}",
            "city": "Almaty",
            "role": "buyer",
            "consent_offer_pd": True,
        }
        for path in (
            "/health",
            "/v1/plots?limit=24&offset=0",
            "/v1/materials?limit=24&offset=0",
            "/v1/specialists?limit=24&offset=0",
        ):
            path_name, elapsed, status, _response = await _hit(client, "GET", path)
            samples.append((path_name.split("?", 1)[0], elapsed, status))
        _path, elapsed, status, _response = await _hit(client, "POST", "/v1/auth/register", json=body)
        samples.append(("/v1/auth/register", elapsed, status))
        _path, elapsed, status, response = await _hit(
            client,
            "POST",
            "/v1/auth/login",
            json={"email": email, "password": password, "consent_offer_pd": True},
        )
        samples.append(("/v1/auth/login", elapsed, status))
        if status == 200:
            token = response.json()["data"]["token"]
            headers = {"Authorization": f"Bearer {token}"}
            _path, elapsed, me_status, _response = await _hit(client, "GET", "/v1/auth/me", headers=headers)
            samples.append(("/v1/auth/me", elapsed, me_status))
    return samples


async def run(base: str, users: int, rounds: int) -> dict:
    timeout = httpx.Timeout(30.0)
    limits = httpx.Limits(max_connections=users, max_keepalive_connections=users)
    async with httpx.AsyncClient(base_url=base, timeout=timeout, limits=limits) as client:
        batches = await asyncio.gather(*[_user(client, index, rounds) for index in range(users)])
    flat = [row for batch in batches for row in batch]
    by_path: dict[str, list[float]] = {}
    errors = 0
    for path, elapsed, status in flat:
        by_path.setdefault(path, []).append(elapsed)
        if status >= 400:
            errors += 1
    endpoints = {}
    for path, values in sorted(by_path.items()):
        endpoints[path] = {
            "n": len(values),
            "p50_ms": round(_pct(values, 50), 2),
            "p95_ms": round(_pct(values, 95), 2),
            "mean_ms": round(statistics.fmean(values), 2) if values else 0,
        }
    all_values = [row[1] for row in flat]
    return {
        "users": users,
        "rounds": rounds,
        "requests": len(flat),
        "errors": errors,
        "p50_ms": round(_pct(all_values, 50), 2),
        "p95_ms": round(_pct(all_values, 95), 2),
        "endpoints": endpoints,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8010")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args()
    report = asyncio.run(run(args.base, args.users, args.rounds))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
