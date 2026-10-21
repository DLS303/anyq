"""Login failure window stored in the database and shared by every worker."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import time

from sqlalchemy import delete, func, select

from app.sql_backend import LoginFailure

_RETENTION_S = 86_400
_dev_secret: str | None = None


def production_login_secret_required() -> bool:
    """Production refuses to start without LOGIN_HASH_SECRET. Demo and development do not."""
    anyq = os.getenv("ANYQ_ENV", "development").strip().lower()
    app_env = os.getenv("APP_ENV", "").strip().lower()
    return anyq == "production" or app_env in {"prod", "production"}


def login_hash_secret() -> str:
    """HMAC key for login windows. Production requires LOGIN_HASH_SECRET."""
    secret = (os.getenv("LOGIN_HASH_SECRET") or "").strip()
    if production_login_secret_required():
        if len(secret) < 32:
            raise RuntimeError(
                "LOGIN_HASH_SECRET must be set to at least 32 characters when ANYQ_ENV=production or APP_ENV=prod"
            )
        return secret
    if len(secret) >= 16:
        return secret
    global _dev_secret
    if not _dev_secret:
        _dev_secret = secrets.token_urlsafe(32)
    return _dev_secret


def require_login_hash_secret() -> None:
    """Fail at process start in production. Demo and development keep the previous behaviour."""
    if production_login_secret_required():
        login_hash_secret()


class RateLimited(Exception):
    def __init__(self) -> None:
        super().__init__("Слишком много попыток входа. Повторите через 10 минут")


def _ip_bucket(ip: str) -> str:
    raw = (ip or "").strip()
    if not raw:
        return ""
    try:
        addr = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return raw
    if isinstance(addr, ipaddress.IPv4Address):
        parts = str(addr).split(".")
        return ".".join([*parts[:3], "0"])
    network = ipaddress.ip_network(f"{addr}/64", strict=False)
    return str(network.network_address)


def login_key(account: str, ip: str) -> str:
    material = f"{account.strip().lower()}|{_ip_bucket(ip)}"
    return hmac.new(login_hash_secret().encode(), material.encode(), hashlib.sha256).hexdigest()


class LoginRateLimiter:
    def __init__(self, limit: int = 5, window_s: int = 600, prefix: str = "") -> None:
        self.limit = limit
        self.window_s = window_s
        self.prefix = prefix

    def _account(self, account: str) -> str:
        return f"{self.prefix}{account}" if self.prefix else account

    def _session(self):
        from app.store import store

        return store._sql.factory()

    def _purge(self, session, now: float) -> None:
        session.execute(delete(LoginFailure).where(LoginFailure.created_at < now - _RETENTION_S))

    def reset(self) -> None:
        with self._session() as session:
            session.execute(delete(LoginFailure))
            session.commit()

    def count(self, account: str, ip: str) -> int:
        key = login_key(self._account(account), ip)
        now = time.time()
        with self._session() as session:
            value = session.scalar(
                select(func.count())
                .select_from(LoginFailure)
                .where(LoginFailure.key_hash == key, LoginFailure.created_at > now - self.window_s)
            )
            return int(value or 0)

    def check(self, account: str, ip: str) -> None:
        now = time.time()
        with self._session() as session:
            self._purge(session, now)
            session.commit()
        if self.count(account, ip) >= self.limit:
            raise RateLimited()

    def record_failure(self, account: str, ip: str) -> None:
        now = time.time()
        with self._session() as session:
            self._purge(session, now)
            session.add(LoginFailure(key_hash=login_key(self._account(account), ip), created_at=now))
            session.commit()

    def clear(self, account: str, ip: str) -> None:
        key = login_key(self._account(account), ip)
        with self._session() as session:
            session.execute(delete(LoginFailure).where(LoginFailure.key_hash == key))
            session.commit()


login_limiter = LoginRateLimiter()
signup_limiter = LoginRateLimiter(prefix="signup:")
