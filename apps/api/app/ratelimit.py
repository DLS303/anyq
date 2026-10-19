"""Login failure window stored in the database and shared by every worker."""

from __future__ import annotations

import threading
import time

from sqlalchemy import delete, func, select

from app.sql_backend import LoginFailure


class RateLimited(Exception):
    def __init__(self) -> None:
        super().__init__("Слишком много попыток входа. Повторите через 10 минут")


class LoginRateLimiter:
    def __init__(self, limit: int = 5, window_s: int = 600) -> None:
        self.limit = limit
        self.window_s = window_s

    def _session(self):
        from app.store import store

        return store._sql.factory()

    def _key(self, account: str, ip: str) -> tuple[str, str]:
        return (account.strip().lower(), ip or "")

    def reset(self) -> None:
        with self._session() as session:
            session.execute(delete(LoginFailure))
            session.commit()

    def count(self, account: str, ip: str) -> int:
        account_key, ip_key = self._key(account, ip)
        now = time.time()
        with self._session() as session:
            value = session.scalar(
                select(func.count())
                .select_from(LoginFailure)
                .where(
                    LoginFailure.account == account_key,
                    LoginFailure.ip == ip_key,
                    LoginFailure.created_at > now - self.window_s,
                )
            )
            return int(value or 0)

    def check(self, account: str, ip: str) -> None:
        if self.count(account, ip) >= self.limit:
            raise RateLimited()

    def record_failure(self, account: str, ip: str) -> None:
        account_key, ip_key = self._key(account, ip)
        with self._session() as session:
            session.add(
                LoginFailure(account=account_key, ip=ip_key, created_at=time.time())
            )
            session.commit()

    def clear(self, account: str, ip: str) -> None:
        account_key, ip_key = self._key(account, ip)
        with self._session() as session:
            session.execute(
                delete(LoginFailure).where(
                    LoginFailure.account == account_key, LoginFailure.ip == ip_key
                )
            )
            session.commit()


login_limiter = LoginRateLimiter()


class PublicRateLimited(Exception):
    def __init__(self) -> None:
        super().__init__("Слишком много запросов")


class SlidingWindowLimiter:
    """In-memory per-key window. Public reply routes use one instance per process."""

    def __init__(self, limit: int = 30, window_s: int = 60) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str) -> None:
        now = time.monotonic()
        name = key or ""
        with self._lock:
            recent = [
                stamp
                for stamp in self._hits.get(name, [])
                if now - stamp < self.window_s
            ]
            if len(recent) >= self.limit:
                self._hits[name] = recent
                raise PublicRateLimited()
            recent.append(now)
            self._hits[name] = recent


public_rfi_limiter = SlidingWindowLimiter()
