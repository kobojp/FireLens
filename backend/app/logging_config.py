from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .config import get_log_dir

LOGGER_NAME = "firelens"
LOG_FILENAME = "firelens.log"


def configure_logging() -> Path:
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / LOG_FILENAME
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    resolved = path.resolve()
    for handler in logger.handlers:
        if (
            isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename).resolve() == resolved
        ):
            return path
    handler = RotatingFileHandler(
        path,
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    return path


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    configure_logging()
    full_name = name if name.startswith("firelens") else f"firelens.{name}"
    logger = logging.getLogger(full_name)
    logger.setLevel(logging.INFO)
    return logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.monotonic()
        logger = get_logger("firelens.http")
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request failed method=%s path=%s", request.method, request.url.path)
            raise
        if request.url.path.startswith("/api/"):
            elapsed_ms = int((time.monotonic() - started) * 1000)
            logger.info(
                "request method=%s path=%s status=%s elapsed_ms=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
        return response
