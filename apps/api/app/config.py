import os

from pydantic import BaseModel


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
    cors_origins: list[str] = resolve_cors_origins()
    # Current Kazakhstan VAT. KS acts keep the date-based rate in tax.py.
    vat_rate: float = float(os.getenv("ANYQ_VAT_RATE", "0.16"))
    # An offer this far above the website reference is flagged. It is not a saving.
    overprice_threshold: float = float(os.getenv("ANYQ_OVERPRICE_THRESHOLD", "0.15"))


settings = Settings()
