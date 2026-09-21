import base64
import hashlib
import hmac
import json
import os
import secrets
import time

SECRET = os.getenv("SUPERAPP_SECRET", "superapp-dev-secret-change-me")
DEMO_PASSWORD = "demo123"


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
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def read_token(token: str) -> str | None:
    try:
        body, sig = token.split(".", 1)
        expect = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(expect, sig):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return str(payload.get("sub") or "")
    except Exception:
        return None
