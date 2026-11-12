"""RFC 7807 problem details specification and non-leaking exception handlers (S3.4)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, NoReturn

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from kanban.api.request_id import get_request_id

if TYPE_CHECKING:
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.requests import Request

logger = logging.getLogger(__name__)

_CODE_REGEX = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
PROBLEM_MEDIA_TYPE = "application/problem+json"


class FieldError(BaseModel):
    """Validation failure on an individual request field without echoing raw user input."""

    path: str = Field(description="JSON dot-separated path to the offending field")
    message: str = Field(description="Human-readable explanation of the validation constraint")


class Problem(BaseModel):
    """Canonical RFC 7807 problem document for the platform."""

    type: str = Field(description="Absolute URI referencing problem definition")
    title: str = Field(description="Short human-readable summary of the problem type")
    status: int = Field(description="HTTP status code")
    code: str = Field(description="Machine-readable error code")
    detail: str | None = Field(
        default=None,
        description="Human-readable explanation specific to this occurrence",
    )
    request_id: str = Field(description="Correlating request identifier")
    errors: list[FieldError] | None = Field(
        default=None,
        description="Field-level validation errors",
    )
    candidates: list[dict[str, str]] | None = Field(
        default=None,
        description="Candidate suggestions when identifier resolution is ambiguous",
    )
    current_etag: str | None = Field(
        default=None,
        description="Current resource ETag on 412 precondition failed",
    )


class ProblemException(Exception):  # noqa: N818
    """Application exception mapped directly to an RFC 7807 Problem document."""

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        code: str,
        status: int,
        title: str,
        detail: str | None = None,
        errors: list[FieldError] | None = None,
        headers: dict[str, str] | None = None,
        *,
        candidates: list[dict[str, str]] | None = None,
        current_etag: str | None = None,
    ) -> None:
        """Initialize problem exception with error code, status, and optional details."""
        if not _CODE_REGEX.match(code):
            msg = f"Invalid problem code: {code!r}. Must match '^[A-Z][A-Z0-9_]{{2,63}}$'."
            raise ValueError(msg)
        super().__init__(title if detail is None else f"{title}: {detail}")
        self.code = code
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors
        self.headers = headers
        self.candidates = candidates
        self.current_etag = current_etag


def not_found() -> NoReturn:
    """Raise canonical 404 Not Found problem document.

    S3.4: 403 MUST NOT be used for object reads; all unreadable or non-existent
    objects return 404 to eliminate enumeration side-channels.
    """
    raise ProblemException(
        code="NOT_FOUND",
        status=404,
        title="Not Found",
        detail=None,
    )


async def problem_exception_handler(
    request: Request,
    exc: ProblemException,
) -> JSONResponse:
    """Format an explicit ProblemException into application/problem+json."""
    del request
    req_id = get_request_id()
    problem = Problem(
        type=f"urn:kanban:problem:{exc.code}",
        title=exc.title,
        status=exc.status,
        code=exc.code,
        detail=exc.detail,
        request_id=req_id,
        errors=exc.errors,
        candidates=exc.candidates,
        current_etag=exc.current_etag,
    )
    response_headers = {"x-request-id": req_id}
    if exc.headers:
        response_headers.update(exc.headers)
    return JSONResponse(
        status_code=exc.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=response_headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Format request validation errors into 422 VALIDATION_FAILED without echoing input."""
    del request
    req_id = get_request_id()
    field_errors: list[FieldError] = []

    for err in exc.errors():
        loc = err.get("loc", ())
        path_segments = [str(elem) for elem in loc if elem != "body"]
        path_str = ".".join(path_segments) if path_segments else "body"
        msg = err.get("msg", "Invalid value")
        # Ensure submitted value is strictly excluded
        field_errors.append(FieldError(path=path_str, message=msg))

    problem = Problem(
        type="urn:kanban:problem:VALIDATION_FAILED",
        title="Validation Failed",
        status=422,
        code="VALIDATION_FAILED",
        detail="Request validation failed",
        request_id=req_id,
        errors=field_errors or None,
    )
    return JSONResponse(
        status_code=422,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers={"x-request-id": req_id},
    )


async def starlette_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Map standard Starlette/FastAPI HTTPExceptions to RFC 7807 problem structure."""
    del request
    req_id = get_request_id()

    code_map = {
        400: ("BAD_REQUEST", "Bad Request"),
        401: ("AUTHENTICATION_REQUIRED", "Authentication Required"),
        403: ("FORBIDDEN", "Forbidden"),
        404: ("NOT_FOUND", "Not Found"),
        405: ("METHOD_NOT_ALLOWED", "Method Not Allowed"),
        409: ("CONFLICT", "Conflict"),
        422: ("VALIDATION_FAILED", "Validation Failed"),
        500: ("INTERNAL_ERROR", "Internal Server Error"),
        501: ("NOT_IMPLEMENTED", "Not Implemented"),
        502: ("BAD_GATEWAY", "Bad Gateway"),
        503: ("SERVICE_UNAVAILABLE", "Service Unavailable"),
    }

    code, default_title = code_map.get(exc.status_code, (f"HTTP_{exc.status_code}", "HTTP Error"))
    detail = None if exc.status_code in (401, 404) else (str(exc.detail) if exc.detail else None)

    problem = Problem(
        type=f"urn:kanban:problem:{code}",
        title=default_title,
        status=exc.status_code,
        code=code,
        detail=detail,
        request_id=req_id,
    )
    response_headers = {"x-request-id": req_id}
    if exc.headers:
        response_headers.update(exc.headers)
    return JSONResponse(
        status_code=exc.status_code,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=response_headers,
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Catch-all handler translating unexpected exceptions into non-leaking 500 INTERNAL_ERROR."""
    del request
    req_id = get_request_id()
    logger.error("Unhandled server exception [request_id=%s]: %s", req_id, exc)

    problem = Problem(
        type="urn:kanban:problem:INTERNAL_ERROR",
        title="Internal Server Error",
        status=500,
        code="INTERNAL_ERROR",
        detail=None,
        request_id=req_id,
    )
    return JSONResponse(
        status_code=500,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers={"x-request-id": req_id},
    )
