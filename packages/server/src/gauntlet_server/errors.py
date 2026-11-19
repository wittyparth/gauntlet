"""The error envelope (contracts section 9): {"error": {"code", "message", "detail"}}."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

__all__ = ["ApiError", "ErrorEnvelope", "install_errors", "not_found"]

log = logging.getLogger("gauntlet.api")

_CODES = {401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.detail = status, code, message, detail


def not_found(what: str, id: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} {id!r} not found")


def _body(code: str, message: str, detail: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail}}


class ErrorEnvelope:
    """Pydantic-free marker used to document the envelope in OpenAPI."""

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "detail": {},
                },
                "required": ["code", "message"],
            }
        },
        "required": ["error"],
    }


class _RequestId(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


def install_errors(app: FastAPI) -> None:
    app.add_middleware(_RequestId)

    @app.exception_handler(ApiError)
    async def _api(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.detail), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODES.get(exc.status_code, "error")
        return JSONResponse(
            _body(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
        return JSONResponse(_body("validation_error", "invalid request", detail), status_code=422)

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        rid = getattr(request.state, "request_id", "-")
        log.exception("unhandled error (request %s)", rid)
        return JSONResponse(_body("internal", "internal error"), status_code=500)
