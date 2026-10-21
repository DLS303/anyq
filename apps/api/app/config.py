import os

from pydantic import BaseModel


def demo_mode() -> bool:
    """Fictional seed and illustrations. Off unless ANYQ_DEMO_MODE is explicitly on."""
    return os.getenv("ANYQ_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def registration_enabled() -> bool:
    """Public sign-up. On unless REGISTRATION_ENABLED is explicitly off."""
    raw = os.getenv("REGISTRATION_ENABLED")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


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
    # A price more than this far under the VAT-inclusive median is suspicious.
    price_suspicious_below: float = float(os.getenv("ANYQ_PRICE_SUSPICIOUS_BELOW", "0.5"))
    # Other offers for the same item are taken from this many days.
    price_compare_days: int = int(os.getenv("ANYQ_PRICE_COMPARE_DAYS", "30"))


settings = Settings()
