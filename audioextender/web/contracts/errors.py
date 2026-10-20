"""Backward-compatible HTTP error contracts for the web application."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, Literal

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from audioextender.core.exceptions import AudioExtenderError

ErrorCategory = Literal["validation", "not_found", "unavailable", "conflict", "canceled", "unexpected"]


@dataclass(frozen=True)
class ApiError:
    """Stable machine-readable error metadata added beside legacy ``detail``."""

    code: str
    category: ErrorCategory
    message: str
    retryable: bool = False


def classify_status(status_code: int) -> tuple[str, ErrorCategory, bool]:
    """Map HTTP status codes to the public error vocabulary."""
    if status_code == 404:
        return "not_found", "not_found", False
    if status_code in {408, 423, 429, 502, 503, 504}:
        return "resource_unavailable", "unavailable", True
    if status_code == 409:
        return "conflict", "conflict", False
    if status_code == 499:
        return "canceled", "canceled", False
    if status_code in {400, 405, 413, 415, 422}:
        return "validation_error", "validation", False
    if status_code >= 500:
        return "internal_error", "unexpected", status_code != 501
    return "request_failed", "unexpected", False


def error_message(detail: Any, fallback: str) -> str:
    """Extract a safe human message while leaving the legacy detail untouched."""
    if isinstance(detail, str) and detail:
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message:
            return message
    return fallback


def error_response(status_code: int, detail: Any, *, headers: Mapping[str, str] | None = None) -> JSONResponse:
    """Return the legacy FastAPI detail plus a normalized error companion."""
    default_code, category, retryable = classify_status(status_code)
    explicit_code = detail.get("code") if isinstance(detail, dict) else None
    code = explicit_code if isinstance(explicit_code, str) and explicit_code else default_code
    problem = ApiError(
        code=code,
        category=category,
        message=error_message(detail, "The request could not be completed."),
        retryable=retryable,
    )
    response_headers = dict(headers or {})
    response_headers.setdefault("X-AudioExtender-Error-Code", problem.code)
    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder({"detail": detail, "error": asdict(problem)}),
        headers=response_headers,
    )


def install_error_handlers(application: FastAPI, *, logger: logging.Logger | None = None) -> FastAPI:
    """Install the single delivery-boundary mapping for expected and unexpected errors."""
    error_logger = logger or logging.getLogger("uvicorn.error")

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exception: StarletteHTTPException) -> JSONResponse:
        return error_response(exception.status_code, exception.detail, headers=exception.headers)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exception: RequestValidationError) -> JSONResponse:
        return error_response(422, exception.errors())

    @application.exception_handler(AudioExtenderError)
    async def handle_domain_error(request: Request, exception: AudioExtenderError) -> JSONResponse:
        error_logger.info(
            "Expected API domain failure",
            extra={"api_error": {"path": request.url.path, "type": type(exception).__name__}},
        )
        return error_response(400, str(exception))

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
        error_logger.exception(
            "Unexpected API failure",
            extra={"api_error": {"path": request.url.path, "type": type(exception).__name__}},
        )
        return error_response(500, "An unexpected error occurred. Try again or review the application logs.")

    return application
