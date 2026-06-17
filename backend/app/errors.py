"""Application error types and FastAPI exception handlers.

Centralizing these keeps HTTP responses uniform and avoids leaking internal detail
(stack traces, which user/tenant existed, etc.) to clients.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base application error with an HTTP status and a safe client message."""

    status_code: int = 400
    message: str = "Request could not be processed."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class AuthenticationError(AppError):
    status_code = 401
    message = "Authentication required."


class AuthorizationError(AppError):
    status_code = 403
    message = "You do not have permission to perform this action."


class ConflictError(AppError):
    status_code = 409
    message = "The request conflicts with existing state."


class NotFoundError(AppError):
    status_code = 404
    message = "The requested resource was not found."


class LLMRoutingError(AppError):
    """Raised when policy requires a self-hosted model for a document but none is
    configured. Fail-closed: sensitive content is never sent to the cloud as a fallback.
    Surfaced as 503 so the operator fixes the deployment rather than the user retrying."""

    status_code = 503
    message = "A self-hosted model is required for this content but is not available."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if isinstance(exc, AuthenticationError):
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
            headers=headers,
        )
