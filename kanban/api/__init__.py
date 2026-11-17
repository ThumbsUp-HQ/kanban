"""Kanban API package: routing, problems, request context, and security dependencies."""

from typing import Any

from kanban.api.deps import (
    DenyAllResolver,
    PrincipalContext,
    PrincipalResolver,
    get_principal,
    get_rls_session,
)
from kanban.api.problems import (
    PROBLEM_MEDIA_TYPE,
    FieldError,
    Problem,
    ProblemException,
    not_found,
    problem_exception_handler,
    starlette_http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from kanban.api.request_id import RequestIdFilter, RequestIdMiddleware, get_request_id
from kanban.api.timing import TimingFloor, load_or_404, timing_floor

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "DenyAllResolver",
    "FieldError",
    "PrincipalContext",
    "PrincipalResolver",
    "Problem",
    "ProblemException",
    "RequestIdFilter",
    "RequestIdMiddleware",
    "TimingFloor",
    "build_v1_router",
    "get_principal",
    "get_request_id",
    "get_rls_session",
    "load_or_404",
    "not_found",
    "problem_exception_handler",
    "starlette_http_exception_handler",
    "timing_floor",
    "unhandled_exception_handler",
    "validation_exception_handler",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    if name == "build_v1_router":
        from kanban.api.v1 import build_v1_router  # noqa: PLC0415

        return build_v1_router
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
