import os

from pydantic import BaseModel

_SECURE_ENVS = frozenset({"demo", "production"})


def current_env() -> str:
    return os.getenv("ANYQ_ENV", "development").strip().lower()


def demo_mode() -> bool:
    """Fictional seed and illustrations. Off unless ANYQ_DEMO_MODE is explicitly on."""
    return os.getenv("ANYQ_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def secure_env() -> bool:
    """demo follows production for secrets, CORS, cookies, docs, and db.json.

    SQLite and ANYQ_DEMO_MODE stay available in demo. Schema startup stays on
    production only so a demo process can create a local SQLite file.
    """
    return current_env() in _SECURE_ENVS


def production_env() -> bool:
    return current_env() == "production"


def secure_cookies() -> bool:
    return secure_env()


def session_cookie_params() -> dict[str, object]:
    """Cookie flags for a session cookie. Secure is on for demo and production."""
    return {"httponly": True, "secure": secure_cookies(), "samesite": "lax"}


def api_docs_urls() -> dict[str, str | None]:
    """Swagger stays off in production and demo. Development still serves /docs.

    PR #16 can keep calling this instead of checking production on its own.
    """
    if secure_env():
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


def resolve_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if secure_env() and "*" in raw:
        raise RuntimeError("CORS_ORIGINS must not contain *")
    items = [part.strip() for part in raw.split(",") if part.strip()]
    if secure_env() and not items:
        raise RuntimeError("CORS_ORIGINS must be set")
    if not items:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return items


def assert_demo_password_policy() -> None:
    """ANYQ_DEMO_PASSWORD may be set for demo and must be empty in production.

    The message names the variable and does not include its value.
    """
    password = os.getenv("ANYQ_DEMO_PASSWORD", "").strip()
    if production_env() and password:
        raise RuntimeError("ANYQ_DEMO_PASSWORD must be empty when ANYQ_ENV=production")


class Settings(BaseModel):
    app_name: str = "SuperAPP API"
    version: str = "0.1.0"
    database_url: str | None = os.getenv("DATABASE_URL")
    anyq_env: str = os.getenv("ANYQ_ENV", "development")
    demo_mode: bool = demo_mode()
    cors_origins: list[str] = resolve_cors_origins()
    # Current Kazakhstan VAT. KS acts keep the date-based rate in tax.py.
    vat_rate: float = float(os.getenv("ANYQ_VAT_RATE", "0.16"))
    # An offer this far above the website reference is flagged. It is not a saving.
    overprice_threshold: float = float(os.getenv("ANYQ_OVERPRICE_THRESHOLD", "0.15"))


settings = Settings()
