import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time

from app.config import secure_env

_cached_secret: str | None = None


def reset_secret_cache() -> None:
    global _cached_secret
    _cached_secret = None


def load_secret() -> str:
    global _cached_secret
    if _cached_secret:
        return _cached_secret
    secret = (os.getenv("JWT_SECRET") or os.getenv("SUPERAPP_SECRET") or "").strip()
    if secure_env():
        if len(secret) < 32:
            raise RuntimeError("JWT_SECRET must be set to at least 32 characters when ANYQ_ENV is demo or production")
        _cached_secret = secret
        return _cached_secret
    if len(secret) < 16:
        secret = secrets.token_urlsafe(32)
    _cached_secret = secret
    return _cached_secret


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _, _hx = stored.partition("$")
    if not salt or not _hx:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def make_token(user_id: str, ttl: int = 60 * 60 * 24 * 14) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + ttl}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(load_secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def read_token(token: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        expect = hmac.new(load_secret().encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expect, sig):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return str(payload.get("sub") or "")
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return None
