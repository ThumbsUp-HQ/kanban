# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Custom OpenAPI specification builder and enricher (KAN-57)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi.openapi.utils import get_openapi

from kanban.api.problems import Problem
from kanban.ops.build_info import (
    compute_openapi_bundle_hash,
    resolve_git_commit,
    resolve_platform_version,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

PUBLIC_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/.well-known/openid-configuration",
        "/healthz",
        "/readyz",
        "/api/v1/health",
        "/api/v1/healthz",
        "/api/v1/system/platform-summary",
        "/api/v1/system/summary",
        "/api/v1/system/about",
        "/api/v1/auth/cards",
        "/api/v1/auth/session",
        "/api/v1/auth/local/login",
        "/api/v1/oauth/device/activate",
        "/api/v1/oauth/device/info",
        "/.well-known/oauth-authorization-server",
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/{subpath:path}",
        "/oauth/authorize",
        "/oauth/authorize/decision",
        "/oauth/device/authorize",
        "/oauth/jwks.json",
        "/oauth/register",
        "/oauth/revoke",
        "/oauth/token",
    }
)

PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/v1/setup/",
    "/api/v1/auth/cards/",
    "/api/v1/auth/ldap/",
    "/api/v1/auth/oidc/",
    "/api/v1/auth/webauthn/authenticate/",
)


def _is_public_route(path: str) -> bool:
    """Return True if route does not require prior authentication."""
    if path in PUBLIC_EXACT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _register_security_schemes(security_schemes: dict[str, Any]) -> None:
    """Register canonical security schemes in OpenAPI components."""
    security_schemes["SessionCookieAuth"] = {
        "type": "apiKey",
        "in": "cookie",
        "name": "__Host-kb_session",
        "description": "Session cookie authentication",
    }
    security_schemes["CsrfHeaderAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-CSRF-Token",
        "description": "Anti-CSRF header token for state-changing requests",
    }
    security_schemes["BearerTokenAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "description": "Bearer token authentication (JWT / kb_agt_* / kb_doc_* / kb_adm_*)",
    }


def _fix_problem_schema_refs(obj: object) -> None:
    """Recursively rewrite #/$defs/FieldError to #/components/schemas/FieldError."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == "$ref" and v == "#/$defs/FieldError":
                obj[k] = "#/components/schemas/FieldError"
            else:
                _fix_problem_schema_refs(v)
    elif isinstance(obj, list):
        for item in obj:
            _fix_problem_schema_refs(item)


def _register_problem_schemas(
    schemas: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Register ProblemDetails schemas and return 401, 412, and 429 response structures."""
    problem_schema = Problem.model_json_schema()
    defs = problem_schema.pop("$defs", {})
    if "FieldError" in defs:
        schemas["FieldError"] = defs["FieldError"]

    _fix_problem_schema_refs(problem_schema)
    problem_schema["title"] = "ProblemDetails"
    schemas["ProblemDetails"] = problem_schema

    ref_payload = {
        "schema": {"$ref": "#/components/schemas/ProblemDetails"},
    }
    problem_401 = {
        "description": "Unauthorized - authentication required",
        "content": {"application/problem+json": ref_payload},
    }
    problem_412 = {
        "description": "Precondition Failed - ETag, If-Match, or blast hash mismatch",
        "content": {"application/problem+json": ref_payload},
    }
    problem_429 = {
        "description": "Too Many Requests - rate limit exceeded",
        "content": {"application/problem+json": ref_payload},
    }
    return problem_401, problem_412, problem_429


def _has_precondition_header(operation: dict[str, Any], path: str) -> bool:
    """Return True if endpoint specifies ETag, If-Match, or state-changing hash checks."""
    for param in operation.get("parameters", []):
        p_in = param.get("in")
        p_name = param.get("name", "").lower()
        if p_in == "header" and p_name in (
            "if-match",
            "kb-blast-hash",
            "if_match",
            "kb_blast_hash",
        ):
            return True
    return (
        "/delete" in path
        or "/trash" in path
        or "/transitions" in path
        or "/states" in path
        or "/versions/" in path
        or path.startswith("/api/v1/admin/destructive")
    )


RATE_LIMITED_EXACT_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/auth/local/login",
        "/api/v1/auth/setup/claim",
        "/api/v1/setup/claim",
        "/api/v1/media-proxy",
        "/oauth/register",
        "/api/v1/oauth/device/activate",
        "/api/v1/oauth/device/info",
    }
)


def _is_rate_limited_route(path: str) -> bool:
    """Return True if endpoint enforces deliberate rate-limiting policies."""
    if path in RATE_LIMITED_EXACT_PATHS:
        return True
    return (
        path.startswith(("/api/v1/auth/webauthn/", "/api/v1/auth/mfa/"))
        or "/attachments" in path
        or (path.startswith("/api/v1/custom-fields/") and path.endswith("/execute"))
    )


def _enrich_operation(
    path: str,
    method: str,
    operation: dict[str, Any],
    problem_responses: dict[str, dict[str, Any]],
) -> None:
    """Enrich a single operation with security and RFC 7807 problem responses."""
    is_unsafe = method in ("post", "put", "patch", "delete")
    if _is_public_route(path):
        operation["security"] = []
    else:
        if is_unsafe:
            operation["security"] = [
                {"SessionCookieAuth": [], "CsrfHeaderAuth": []},
                {"BearerTokenAuth": []},
            ]
        else:
            operation["security"] = [
                {"SessionCookieAuth": []},
                {"BearerTokenAuth": []},
            ]
        responses = operation.setdefault("responses", {})
        if "401" not in responses:
            responses["401"] = problem_responses["401"]

    if _has_precondition_header(operation, path):
        responses = operation.setdefault("responses", {})
        if "412" not in responses:
            responses["412"] = problem_responses["412"]

    if _is_rate_limited_route(path):
        responses = operation.setdefault("responses", {})
        if "429" not in responses:
            responses["429"] = problem_responses["429"]


def _enrich_paths(
    openapi_schema: dict[str, Any],
    problem_responses: dict[str, dict[str, Any]],
) -> None:
    """Iterate all paths and methods in OpenAPI schema and apply enrichment."""
    allowed_methods = {"get", "post", "put", "patch", "delete", "options", "head"}
    for path, path_item in openapi_schema.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method not in allowed_methods or not isinstance(operation, dict):
                continue
            _enrich_operation(
                path,
                method,
                operation,
                problem_responses,
            )


def build_custom_openapi(app: FastAPI) -> dict[str, Any]:
    """Generate and return canonical OpenAPI schema with security, problems, and build info."""
    platform_ver = resolve_platform_version()
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version or platform_ver,
        openapi_version=app.openapi_version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
    )

    components = openapi_schema.setdefault("components", {})
    schemas = components.setdefault("schemas", {})
    security_schemes = components.setdefault("securitySchemes", {})

    _register_security_schemes(security_schemes)

    openapi_schema["security"] = [
        {"SessionCookieAuth": [], "CsrfHeaderAuth": []},
        {"BearerTokenAuth": []},
    ]

    p401, p412, p429 = _register_problem_schemas(schemas)
    _enrich_paths(
        openapi_schema,
        {"401": p401, "412": p412, "429": p429},
    )

    info = openapi_schema.setdefault("info", {})
    info["version"] = platform_ver
    info["x-build-commit"] = resolve_git_commit()
    info["x-openapi-bundle-hash"] = compute_openapi_bundle_hash(openapi_schema)

    return openapi_schema


def setup_custom_openapi(app: FastAPI) -> None:
    """Attach custom OpenAPI generator to FastAPI application instance."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        app.openapi_schema = build_custom_openapi(app)
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
