"""Keep reply-link tokens out of application logs."""

from __future__ import annotations

import logging
import re

_TOKEN_PATH = re.compile(r"((?:/v1/public/(?:rfi|material)/|/[a-z]{2}/r/(?:rfi|material)/))[^/?\s\"']+")
_INSTALLED = False


def redact_text(value: str) -> str:
    return _TOKEN_PATH.sub(r"\1[redacted]", value)


class TokenRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(redact_text(item) if isinstance(item, str) else item for item in args)
        elif isinstance(args, dict):
            record.args = {key: redact_text(item) if isinstance(item, str) else item for key, item in args.items()}
        return True


def install_token_log_filter() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    redactor = TokenRedactingFilter()
    for name in ("", "uvicorn", "uvicorn.access", "uvicorn.error", "gunicorn", "gunicorn.access", "gunicorn.error"):
        logging.getLogger(name).addFilter(redactor)
    _INSTALLED = True
