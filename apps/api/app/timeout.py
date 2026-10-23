"""Stop a request that never finishes so a worker cannot hang."""

from __future__ import annotations

import asyncio

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTimeoutMiddleware:
    def __init__(self, app: ASGIApp, seconds: float = 45) -> None:
        self.app = app
        self.seconds = seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, receive, track), timeout=self.seconds)
        except TimeoutError:
            if started:
                return
            response = JSONResponse({"ok": False, "detail": "timeout"}, status_code=504)
            await response(scope, receive, send)
