import os

from pydantic import BaseModel


def demo_mode() -> bool:
    """Fictional seed and illustrations. Off unless ANYQ_DEMO_MODE is explicitly on."""
    return os.getenv("ANYQ_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def registration_enabled() -> bool:
    """Public registration and confirmation-code delivery. Off unless explicitly enabled."""
    return os.getenv("REGISTRATION_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


DEMO_EMAIL_SUFFIX = "@demo.superapp"
DEMO_EMAIL_REJECTION = "В демо-версии регистрация только для адресов @demo.superapp"
DEMO_PHONE_REJECTION = "В демо-версии телефон не сохраняется. Укажите почту @demo.superapp"


def refuse_stub_code_in_production() -> None:
    """A fixed sign-up code is demo-only. Production must not boot with it set."""
    raw = os.getenv("SIGNUP_STUB_CODE", "").strip()
    if not raw:
        return
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    if env == "production":
        raise RuntimeError("SIGNUP_STUB_CODE must not be set when ANYQ_ENV=production")


def resolve_cors_origins() -> list[str]:
    env = os.getenv("ANYQ_ENV", "development").strip().lower()
    raw = os.getenv("CORS_ORIGINS", "")
    items = [part.strip() for part in raw.split(",") if part.strip()]
    if env == "production" and not items:
        raise RuntimeError("CORS_ORIGINS must be set when ANYQ_ENV=production")
    if not items:
        return ["http://localhost:3000", "http://127.0.0.1:3000"]
    return items


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
    request_timeout_s: float = float(os.getenv("ANYQ_REQUEST_TIMEOUT", "45"))


settings = Settings()
