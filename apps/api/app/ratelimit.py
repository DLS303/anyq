"""In-memory login failure window. Each worker keeps its own window."""

from __future__ import annotations

import time
from threading import Lock


class RateLimited(Exception):
    def __init__(self) -> None:
        super().__init__("Слишком много попыток входа. Повторите через 10 минут")


class LoginRateLimiter:
    def __init__(self, limit: int = 5, window_s: int = 600) -> None:
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[tuple[str, str], list[float]] = {}
        self._lock = Lock()

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def _key(self, account: str, ip: str) -> tuple[str, str]:
        return (account.strip().lower(), ip or "")

    def _fresh(self, key: tuple[str, str], now: float) -> list[float]:
        stamps = [stamp for stamp in self._failures.get(key, []) if now - stamp < self.window_s]
        if stamps:
            self._failures[key] = stamps
        else:
            self._failures.pop(key, None)
        return stamps

    def check(self, account: str, ip: str) -> None:
        now = time.time()
        with self._lock:
            if len(self._fresh(self._key(account, ip), now)) >= self.limit:
                raise RateLimited()

    def record_failure(self, account: str, ip: str) -> None:
        now = time.time()
        key = self._key(account, ip)
        with self._lock:
            stamps = self._fresh(key, now)
            stamps.append(now)
            self._failures[key] = stamps

    def clear(self, account: str, ip: str) -> None:
        with self._lock:
            self._failures.pop(self._key(account, ip), None)


login_limiter = LoginRateLimiter()
