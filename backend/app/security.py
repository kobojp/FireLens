from __future__ import annotations

import os
import secrets
from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

COOKIE_NAME = "firelens_session"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _loopback_origin(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


class DesktopSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.enabled = os.environ.get("FIRELENS_DESKTOP_SECURE") == "1"
        self.token = secrets.token_urlsafe(32)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            self.enabled
            and request.url.path.startswith("/api/")
            and request.method.upper() in MUTATING_METHODS
        ):
            origin = request.headers.get("origin")
            if origin and not _loopback_origin(origin):
                return JSONResponse({"detail": "已阻擋非本機來源的寫入要求"}, status_code=403)
            if request.cookies.get(COOKIE_NAME) != self.token:
                return JSONResponse({"detail": "FireLens 工作階段驗證失敗"}, status_code=403)
        response = await call_next(request)
        if self.enabled:
            response.set_cookie(
                COOKIE_NAME,
                self.token,
                httponly=True,
                samesite="strict",
                secure=False,
                path="/",
            )
        return response
