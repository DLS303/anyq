from pydantic import BaseModel
import os


class Settings(BaseModel):
    app_name: str = "SuperAPP API"
    version: str = "0.1.0"
    database_url: str | None = os.getenv("DATABASE_URL")
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
