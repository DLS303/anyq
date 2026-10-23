"""Gates that answer before a route reads or validates the body."""

import os

from fastapi.responses import JSONResponse

REGISTER_PATHS = {"/v1/auth/register"}
_DOC_PATHS = {"/docs", "/redoc", "/openapi.json"}


def registration_enabled() -> bool:
    """Public sign-up stays closed unless REGISTRATION_ENABLED is exactly 1."""
    return os.getenv("REGISTRATION_ENABLED", "").strip() == "1"


def production_env() -> bool:
    return os.getenv("ANYQ_ENV", "development").strip().lower() == "production"


def _normalized(path: str) -> str:
    trimmed = path.rstrip("/")
    return trimmed or "/"


class PublicSurfaceMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        normalized = _normalized(path)
        if scope.get("method") == "POST" and normalized in REGISTER_PATHS and not registration_enabled():
            response = JSONResponse(status_code=403, content={"detail": "Регистрация недоступна"})
            await response(scope, receive, send)
            return
        hidden_docs = production_env() and (
            normalized in _DOC_PATHS or path.startswith(("/docs/", "/redoc/"))
        )
        if hidden_docs:
            response = JSONResponse(status_code=404, content={"detail": "Not Found"})
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
