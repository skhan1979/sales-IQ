"""
Sales IQ - Error Handling Middleware
Day 19: Standardized error responses, structured error format,
        friendly messages for common failure modes.
"""

import traceback
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import IntegrityError, DBAPIError

logger = logging.getLogger("salesiq.errors")


# ═══════════════════════════════════════════
# Structured error response format
# ═══════════════════════════════════════════

def build_error_response(
    status_code: int,
    error_type: str,
    message: str,
    details: dict | list | None = None,
    request_id: str | None = None,
) -> dict:
    """Build a consistent error response envelope."""
    body = {
        "error": {
            "type": error_type,
            "status": status_code,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    if details:
        body["error"]["details"] = details
    if request_id:
        body["error"]["request_id"] = request_id
    return body


# ═══════════════════════════════════════════
# Friendly messages for common DB errors
# ═══════════════════════════════════════════

DB_ERROR_MESSAGES = {
    "UniqueViolationError": "A record with the same unique value already exists.",
    "ForeignKeyViolationError": "Referenced record not found. Ensure related data exists.",
    "NotNullViolationError": "A required field is missing.",
    "CheckViolationError": "A data validation rule was violated.",
}


def classify_db_error(exc: Exception) -> tuple[int, str, str]:
    """Classify a database exception into user-friendly error info."""
    exc_str = str(exc)

    for error_class, friendly_msg in DB_ERROR_MESSAGES.items():
        if error_class in exc_str:
            return status.HTTP_409_CONFLICT, "database_conflict", friendly_msg

    return (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "database_error",
        "A database error occurred. Please try again.",
    )


# ═══════════════════════════════════════════
# Exception handler registration
# ═══════════════════════════════════════════

def register_error_handlers(app: FastAPI):
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions (404, 403, 401, etc.)."""
        request_id = getattr(request.state, "request_id", None)
        body = build_error_response(
            status_code=exc.status_code,
            error_type="http_error",
            message=str(exc.detail),
            request_id=request_id,
        )
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors with detailed field info."""
        request_id = getattr(request.state, "request_id", None)

        # Parse validation errors into a friendlier format
        field_errors = []
        for error in exc.errors():
            loc = " -> ".join(str(l) for l in error.get("loc", []))
            field_errors.append({
                "field": loc,
                "message": error.get("msg", "Invalid value"),
                "type": error.get("type", "value_error"),
            })

        body = build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_type="validation_error",
            message=f"Request validation failed: {len(field_errors)} error(s)",
            details=field_errors,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=body,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        """Handle database integrity violations (duplicates, FK, etc.)."""
        request_id = getattr(request.state, "request_id", None)
        code, error_type, message = classify_db_error(exc)

        logger.warning(f"DB IntegrityError [{request_id}]: {exc}")

        body = build_error_response(
            status_code=code,
            error_type=error_type,
            message=message,
            request_id=request_id,
        )
        return JSONResponse(status_code=code, content=body)

    @app.exception_handler(DBAPIError)
    async def dbapi_error_handler(request: Request, exc: DBAPIError):
        """Handle low-level database errors."""
        request_id = getattr(request.state, "request_id", None)
        code, error_type, message = classify_db_error(exc)

        logger.error(f"DB Error [{request_id}]: {exc}")

        body = build_error_response(
            status_code=code,
            error_type=error_type,
            message=message,
            request_id=request_id,
        )
        return JSONResponse(status_code=code, content=body)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Catch-all handler for unhandled exceptions."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            f"Unhandled exception [{request_id}]: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )

        body = build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_type="internal_error",
            message="An internal error occurred. Please try again or contact support.",
            details={"exception": type(exc).__name__} if logger.isEnabledFor(logging.DEBUG) else None,
            request_id=request_id,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body,
        )
