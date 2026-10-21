"""Pick brotli or gzip from Accept-Encoding. Small bodies stay plain."""

from __future__ import annotations

import brotli
from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, IdentityResponder
from starlette.types import ASGIApp, Receive, Scope, Send


class _BrotliResponder(IdentityResponder):
    content_encoding = "br"

    def __init__(self, app: ASGIApp, minimum_size: int, quality: int) -> None:
        super().__init__(app, minimum_size)
        self.quality = quality
        self._compressor: brotli.Compressor | None = None

    async def apply_compression(self, body: bytes, *, more_body: bool) -> bytes:
        if self._compressor is None:
            self._compressor = brotli.Compressor(quality=self.quality)
        chunk = self._compressor.process(body)
        if not more_body:
            chunk += self._compressor.finish()
            self._compressor = None
        return chunk


class CompressMiddleware:
    def __init__(self, app: ASGIApp, minimum_size: int = 500, brotli_quality: int = 4) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.brotli_quality = brotli_quality
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        accept = Headers(scope=scope).get("accept-encoding", "").lower()
        if "br" in accept:
            await _BrotliResponder(self.app, self.minimum_size, self.brotli_quality)(scope, receive, send)
            return
        if "gzip" in accept:
            await self.gzip(scope, receive, send)
            return
        await self.app(scope, receive, send)
