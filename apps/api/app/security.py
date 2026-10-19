"""Response headers shared by every API route, including the docs UI."""

from __future__ import annotations

# Swagger and ReDoc load from jsDelivr. JSON routes do not execute those scripts.
API_CSP = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; "
    "font-src 'self' data:; "
    "worker-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'self'; "
    "object-src 'none'"
)

# First week uses a one-day max-age. A longer lifetime waits until HTTPS is stable.
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("strict-transport-security", "max-age=86400"),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("x-frame-options", "DENY"),
    ("content-security-policy", API_CSP),
)


class PublicRobotsMiddleware:
    """Public report routes stay out of search indexes, including error responses."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/v1/public/"):
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                existing = {name.lower() for name, _value in headers}
                extra = (
                    (b"x-robots-tag", b"noindex, nofollow"),
                    (b"cache-control", b"private, max-age=300"),
                )
                for name, value in extra:
                    if name not in existing:
                        headers.append((name, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                existing = {name.lower() for name, _value in headers}
                for name, value in SECURITY_HEADERS:
                    raw = name.lower().encode()
                    if raw not in existing:
                        headers.append((raw, value.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
