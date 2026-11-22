# Copyright 2026 Kanban Platform Contributors
"""Authenticated internal HTTP/2 client for communication between MCP and kanban-api."""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, Final, Self

import httpx

from kanban.security.service_auth import create_internal_service_auth_header
from mcp.errors import KbMcpError, McpErrorCode

if TYPE_CHECKING:
    import types

    from starlette.types import ASGIApp

    from mcp.settings import McpSettings

__all__ = [
    "KanbanApiClient",
]

_CONNECT_TIMEOUT_S: Final[float] = 2.0
_READ_TIMEOUT_S: Final[float] = 10.0
_WRITE_TIMEOUT_S: Final[float] = 10.0
_POOL_TIMEOUT_S: Final[float] = 2.0
_DEFAULT_BODY_LIMIT_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MiB

_HTTP_BAD_REQUEST: Final[int] = 400
_HTTP_NOT_FOUND: Final[int] = 404
_HTTP_CONFLICT: Final[int] = 409
_HTTP_PRECONDITION_FAILED: Final[int] = 412
_HTTP_UNPROCESSABLE_ENTITY: Final[int] = 422
_HTTP_TOO_MANY_REQUESTS: Final[int] = 429
_HTTP_SERVER_ERROR_MIN: Final[int] = 500


class KanbanApiClient:
    """Internal HTTP/2 mTLS client connecting MCP server to kanban-api."""

    def __init__(
        self,
        settings: McpSettings,
        *,
        kanban_app: ASGIApp | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize client with mTLS certificates or in-process ASGI transport.

        Raises:
            ValueError: If plaintext http:// base URL is provided in mtls mode,
                or if kanban_app is omitted in standalone_inprocess mode.

        """
        self.settings: Final[McpSettings] = settings
        self.response_body_limit_bytes: Final[int] = settings.response_body_limit_bytes

        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT_S,
            read=_READ_TIMEOUT_S,
            write=_WRITE_TIMEOUT_S,
            pool=_POOL_TIMEOUT_S,
        )

        if settings.mode == "standalone_inprocess":
            if transport is not None:
                active_transport = transport
            elif kanban_app is not None:
                active_transport = httpx.ASGITransport(app=kanban_app)
            else:
                msg = "kanban_app or transport is required in standalone_inprocess mode"
                raise ValueError(msg)
            self._client = httpx.AsyncClient(
                transport=active_transport,
                base_url="http://localhost",
                timeout=timeout,
            )
        else:
            # mTLS mode
            if settings.kanban_api_base_url.startswith("http://"):
                msg = (
                    f"Plaintext http:// base URL is strictly prohibited in mtls mode: "
                    f"'{settings.kanban_api_base_url}'"
                )
                raise ValueError(msg)

            verify: str | bool = (
                str(settings.internal_ca_path) if settings.internal_ca_path else True
            )
            cert = (
                (str(settings.client_cert_path), str(settings.client_key_path))
                if settings.client_cert_path and settings.client_key_path
                else None
            )

            if transport is not None:
                self._client = httpx.AsyncClient(
                    transport=transport,
                    base_url=settings.kanban_api_base_url,
                    timeout=timeout,
                )

            else:
                self._client = httpx.AsyncClient(
                    http2=True,
                    verify=verify,
                    cert=cert,
                    base_url=settings.kanban_api_base_url,
                    timeout=timeout,
                )

        self._csrf_token: str | None = None

    async def aclose(self) -> None:
        """Close the underlying HTTP client session and connections."""
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def _ensure_csrf_token(
        self, req_headers: dict[str, str], method: str, path: str = ""
    ) -> None:
        unsafe_methods = ("POST", "PUT", "PATCH", "DELETE")
        if (
            method.upper() not in unsafe_methods
            or path.startswith("/internal/")
            or "X-CSRF-Token" in req_headers
        ):
            return
        if self._csrf_token is None:
            try:
                csrf_resp = await self._client.get("/api/v1/auth/session")
                if csrf_resp.status_code == httpx.codes.OK:
                    data = csrf_resp.json()
                    if isinstance(data, dict) and "csrf_token" in data:
                        self._csrf_token = str(data["csrf_token"])
                        self._client.cookies.set("__Host-kb_csrf", self._csrf_token)
            except (httpx.HTTPError, ValueError):
                pass
        if self._csrf_token:
            req_headers["X-CSRF-Token"] = self._csrf_token

    async def request(  # noqa: C901, PLR0912, PLR0913
        self,
        method: str,
        path: str,
        *,
        subject_token: str | None = None,
        mcp_session_id: str | None = None,
        json_data: object = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        """Send authenticated internal request with identity forwarding and error mapping."""
        req_headers = dict(headers or {})
        if subject_token:
            req_headers["X-KB-Subject-Token"] = subject_token
        if mcp_session_id:
            req_headers["X-KB-MCP-Session"] = mcp_session_id

        await self._ensure_csrf_token(req_headers, method, path)

        # Forward resolved connection scope headers
        from mcp.context import get_current_mcp_context  # noqa: PLC0415

        ctx = get_current_mcp_context()
        if ctx is not None:
            if ctx.session_id and "X-KB-MCP-Session" not in req_headers:
                req_headers["X-KB-MCP-Session"] = ctx.session_id
            if ctx.connection_scope is not None:
                scope = ctx.connection_scope
                if scope.workspace_slug or scope.workspace_id:
                    req_headers.setdefault(
                        "X-KB-Scope-Workspace", str(scope.workspace_slug or scope.workspace_id)
                    )
                if scope.project_key or scope.project_id:
                    req_headers.setdefault(
                        "X-KB-Scope-Project", str(scope.project_key or scope.project_id)
                    )
                if scope.is_global:
                    req_headers.setdefault("X-KB-Scope-Global", "true")

        try:
            req = self._client.build_request(
                method,
                path,
                json=json_data,
                params=params,
                headers=req_headers,
            )
            if (
                self.settings.mode == "standalone_inprocess"
                and "x-kb-internal-auth" not in req.headers
            ):
                req.headers["X-KB-Internal-Auth"] = create_internal_service_auth_header(
                    principal="mcp-gateway",
                    method=req.method,
                    path=req.url.path,
                    body_bytes=req.content,
                )
            resp = await self._client.send(req, stream=True)
        except httpx.TransportError as exc:
            msg = f"Upstream communication failure: {exc}"
            raise KbMcpError(McpErrorCode.UPSTREAM_UNAVAILABLE, msg) from exc

        body_chunks: list[bytes] = []
        total_bytes = 0
        try:
            async for chunk in resp.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > self.response_body_limit_bytes:
                    await resp.aclose()
                    msg = (
                        f"Response body size ({total_bytes} bytes) exceeds limit of "
                        f"{self.response_body_limit_bytes} bytes"
                    )
                    raise KbMcpError(McpErrorCode.UPSTREAM_ERROR, msg)
                body_chunks.append(chunk)
        finally:
            await resp.aclose()

        body_bytes = b"".join(body_chunks)

        if resp.status_code >= _HTTP_BAD_REQUEST:
            self._map_upstream_error(resp.status_code, body_bytes)

        if not body_bytes:
            return None

        try:
            return json.loads(body_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return body_bytes.decode("utf-8", errors="replace")

    def _map_upstream_error(self, status_code: int, body_bytes: bytes) -> None:
        """Map RFC 7807 problem details or raw HTTP error status to McpErrorCode."""
        problem: dict[str, Any] = {}
        if body_bytes:
            with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                loaded = json.loads(body_bytes.decode("utf-8"))
                if isinstance(loaded, dict):
                    problem = loaded

        prob_type = str(problem.get("type", ""))
        prob_title = str(problem.get("title", ""))
        prob_detail = str(problem.get("detail", ""))
        prob_code = str(problem.get("code", ""))
        prob_hint = problem.get("hint")
        prob_candidates = problem.get("candidates")
        error_message = prob_detail or prob_title or f"Upstream returned HTTP {status_code}"

        mapped_code = self._resolve_error_code(status_code, prob_type, prob_code)
        hint_str = str(prob_hint) if prob_hint is not None else None
        extra_layer = problem.get("layer") or (
            problem["extra"].get("layer") if isinstance(problem.get("extra"), dict) else None
        )
        if extra_layer:
            layer_text = f"layer: {extra_layer}"
            hint_str = f"{hint_str} ({layer_text})" if hint_str else layer_text

        candidates_list = (
            [dict(c) for c in prob_candidates] if isinstance(prob_candidates, list) else None
        )
        prob_blockers = problem.get("blockers")
        blockers_list = [str(b) for b in prob_blockers] if isinstance(prob_blockers, list) else None
        extra_dict: dict[str, Any] = {}
        if "tainted_by" in problem:
            extra_dict["tainted_by"] = problem["tainted_by"]
        elif isinstance(problem.get("extra"), dict) and "tainted_by" in problem["extra"]:
            extra_dict["tainted_by"] = problem["extra"]["tainted_by"]
        if "unauthorized_mentions" in problem:
            extra_dict["unauthorized_mentions"] = problem["unauthorized_mentions"]

        enriched = self._enrich_progressive_disclosure(mapped_code, problem, hint_str, extra_dict)
        raise KbMcpError(
            mapped_code,
            error_message,
            hint=hint_str,
            candidates=candidates_list,
            blockers=blockers_list,
            extra=extra_dict or None,
            field=enriched["field"],
            fix_hint=enriched["fix_hint"],
            cli_example=enriched["cli_example"],
            valid_options=enriched["valid_options"],
            did_you_mean=enriched["did_you_mean"],
            closest_match=enriched["closest_match"],
        )

    @staticmethod
    def _enrich_progressive_disclosure(
        mapped_code: McpErrorCode,
        problem: dict[str, Any],
        hint_str: str | None,
        extra_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract and synthesize self-correcting progressive disclosure error fields."""
        fix_hint = problem.get("fix_hint") or hint_str
        cli_example = problem.get("cli_example")
        raw_options = (
            problem.get("valid_options")
            or problem.get("valid_states")
            or (
                problem["extra"].get("valid_states")
                if isinstance(problem.get("extra"), dict)
                else None
            )
        )
        valid_options = list(raw_options) if isinstance(raw_options, (list, tuple)) else None
        raw_mean = problem.get("did_you_mean")
        did_you_mean = list(raw_mean) if isinstance(raw_mean, (list, tuple)) else None
        raw_closest = problem.get("closest_match")
        closest_match = [dict(c) for c in raw_closest] if isinstance(raw_closest, list) else None

        if mapped_code == McpErrorCode.INVALID_TRANSITION and valid_options:
            opts_str = ", ".join(str(s) for s in valid_options)
            fix_hint = fix_hint or f"Allowed target states: {opts_str}"
            first_opt = valid_options[0]
            cli_example = cli_example or (
                f'kanban-cli-agent transition_ticket --identifier="<key>" --to-state="{first_opt}"'
            )
        elif mapped_code == McpErrorCode.CONFLICT_ETAG:
            current_etag = (
                problem.get("current_etag") or problem.get("etag") or problem.get("fresh_etag")
            )
            if current_etag:
                extra_dict["current_etag"] = str(current_etag)
                fix_hint = (
                    fix_hint or f"Concurrency conflict. Retry with current ETag: {current_etag}"
                )
                cli_example = cli_example or (
                    'kanban-cli-agent update_ticket --identifier="<key>" '
                    f'--if-match="{current_etag}"'
                )
        elif mapped_code == McpErrorCode.ALREADY_PROMOTED:
            target_doc = (
                problem.get("target_doc_key")
                or problem.get("doc_key")
                or problem.get("promoted_to_doc_id")
            )
            if target_doc:
                extra_dict["target_doc_key"] = str(target_doc)
                fix_hint = fix_hint or (
                    f"Sticky has already been promoted to Doc '{target_doc}'. Use update instead."
                )
                cli_example = cli_example or f'kanban-cli-docs update --id="{target_doc}"'
        elif mapped_code in (McpErrorCode.NOT_FOUND, McpErrorCode.SECTION_NOT_FOUND):
            if not fix_hint:
                fix_hint = (
                    "Verify identifier or use search tool to discover valid entities."
                    if mapped_code == McpErrorCode.NOT_FOUND
                    else "Verify section heading or inspect document structure."
                )
            if not cli_example:
                ident = (
                    problem.get("identifier")
                    or problem.get("id")
                    or problem.get("key")
                    or problem.get("doc_id")
                    or problem.get("ticket_id")
                )
                safe_ident = str(ident).replace('"', '\\"') if ident else ""
                if mapped_code == McpErrorCode.SECTION_NOT_FOUND:
                    cli_example = (
                        f'kanban-cli-docs read --id="{safe_ident}"'
                        if safe_ident
                        else 'kanban-cli-docs search --query=""'
                    )
                else:
                    cli_example = (
                        f'kanban-cli-agent search_tickets --query="{safe_ident}"'
                        if safe_ident
                        else 'kanban-cli-agent search_tickets --query=""'
                    )

        return {
            "field": str(problem["field"]) if "field" in problem else None,
            "fix_hint": str(fix_hint) if fix_hint is not None else None,
            "cli_example": str(cli_example) if cli_example is not None else None,
            "valid_options": valid_options,
            "did_you_mean": did_you_mean,
            "closest_match": closest_match,
        }

    @staticmethod
    def _resolve_conflict_code(prob_type: str, prob_code: str) -> McpErrorCode:
        if prob_type.endswith("etag-mismatch"):
            return McpErrorCode.CONFLICT_ETAG
        conflict_map: dict[str, McpErrorCode] = {
            "AMBIGUOUS_IDENTIFIER": McpErrorCode.AMBIGUOUS_IDENTIFIER,
            "ALREADY_PROMOTED": McpErrorCode.ALREADY_PROMOTED,
            "LINK_TYPE_NOT_ALLOWED": McpErrorCode.LINK_TYPE_NOT_ALLOWED,
            "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED": (
                McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED
            ),
            "MENTION_ACCESS_WARNING": McpErrorCode.MENTION_ACCESS_WARNING,
            "LINK_NOT_FLAGGED": McpErrorCode.LINK_NOT_FLAGGED,
            "CREATOR_UNCHANGED": McpErrorCode.CREATOR_UNCHANGED,
            "NOT_ARCHIVED": McpErrorCode.NOT_ARCHIVED,
            "LOCKOUT_PREVENTED": McpErrorCode.LOCKOUT_PREVENTED,
            "PLAN_STALE": McpErrorCode.PLAN_STALE,
            "STATE_IN_USE": McpErrorCode.STATE_IN_USE,
            "PRIORITY_IN_USE": McpErrorCode.PRIORITY_IN_USE,
            "INVALID_TRANSITION": McpErrorCode.INVALID_TRANSITION,
            "INVALID_CYCLE_TRANSITION": McpErrorCode.INVALID_TRANSITION,
            "OPEN_CHILD_BLOCKERS": McpErrorCode.OPEN_CHILD_BLOCKERS,
            "TRANSITION_HELD": McpErrorCode.TRANSITION_HELD,
            "TRANSITION_PENDING": McpErrorCode.TRANSITION_PENDING,
            "GROUP_CYCLE_REJECTED": McpErrorCode.GROUP_CYCLE_REJECTED,
            "GROUP_DEPTH_EXCEEDED": McpErrorCode.GROUP_DEPTH_EXCEEDED,
        }
        if prob_code in conflict_map:
            return conflict_map[prob_code]
        if prob_type.endswith("cross-scope-taint"):
            return McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED
        if prob_type.endswith("mention-access-warning"):
            return McpErrorCode.MENTION_ACCESS_WARNING
        for name, code in conflict_map.items():
            if prob_type.endswith(name.lower().replace("_", "-")):
                return code
        return McpErrorCode.VALIDATION_FAILED

    @staticmethod
    def _resolve_error_code(
        status_code: int,
        prob_type: str,
        prob_code: str = "",
    ) -> McpErrorCode:
        """Determine McpErrorCode from HTTP status and problem type."""
        code_map: dict[str, McpErrorCode] = {
            "AAL2_REQUIRED": McpErrorCode.AAL2_REQUIRED,
            "INSUFFICIENT_PERMISSION": McpErrorCode.INSUFFICIENT_PERMISSION,
            "INSUFFICIENT_CAPABILITY": McpErrorCode.INSUFFICIENT_PERMISSION,
            "MODULES_DISABLED": McpErrorCode.MODULES_DISABLED,
            "SECTION_NOT_FOUND": McpErrorCode.SECTION_NOT_FOUND,
            "TARGET_NOT_FOUND": McpErrorCode.NOT_FOUND,
            "SOURCE_NOT_FOUND": McpErrorCode.NOT_FOUND,
            "ALREADY_PROMOTED": McpErrorCode.ALREADY_PROMOTED,
            "LINK_TYPE_NOT_ALLOWED": McpErrorCode.LINK_TYPE_NOT_ALLOWED,
            "CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED": (
                McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED
            ),
            "MENTION_ACCESS_WARNING": McpErrorCode.MENTION_ACCESS_WARNING,
            "SELF_LINK": McpErrorCode.VALIDATION_FAILED,
            "CREATOR_NOT_ELIGIBLE": McpErrorCode.CREATOR_NOT_ELIGIBLE,
            "LINK_NOT_FLAGGED": McpErrorCode.LINK_NOT_FLAGGED,
            "CREATOR_UNCHANGED": McpErrorCode.CREATOR_UNCHANGED,
            "NOT_ARCHIVED": McpErrorCode.NOT_ARCHIVED,
            "CONFIRM_PHRASE_MISMATCH": McpErrorCode.CONFIRM_PHRASE_MISMATCH,
            "LOCKOUT_PREVENTED": McpErrorCode.LOCKOUT_PREVENTED,
            "KEY_SCOPE_VIOLATION": McpErrorCode.KEY_SCOPE_VIOLATION,
            "CONNECTION_SCOPE_VIOLATION": McpErrorCode.CONNECTION_SCOPE_VIOLATION,
            "CONFLICTING_SCOPE_HEADERS": McpErrorCode.CONFLICTING_SCOPE_HEADERS,
            "NO_STARTED_STATE": McpErrorCode.NO_STARTED_STATE,
            "USE_COMPLETE_WORK": McpErrorCode.USE_COMPLETE_WORK,
            "OPEN_CHILD_BLOCKERS": McpErrorCode.OPEN_CHILD_BLOCKERS,
            "QA_VERDICT_NOT_READY": McpErrorCode.QA_VERDICT_NOT_READY,
            "INVALID_TRANSITION": McpErrorCode.INVALID_TRANSITION,
            "TRANSITION_HELD": McpErrorCode.TRANSITION_HELD,
            "TRANSITION_PENDING": McpErrorCode.TRANSITION_PENDING,
            "GROUP_CYCLE_REJECTED": McpErrorCode.GROUP_CYCLE_REJECTED,
            "GROUP_DEPTH_EXCEEDED": McpErrorCode.GROUP_DEPTH_EXCEEDED,
            "CONFIRMATION_TOKEN_INVALID_OR_EXPIRED": (
                McpErrorCode.CONFIRMATION_TOKEN_INVALID_OR_EXPIRED
            ),
            "TOKEN_CALLER_MISMATCH": McpErrorCode.TOKEN_CALLER_MISMATCH,
            "TOKEN_TARGET_MISMATCH": McpErrorCode.TOKEN_TARGET_MISMATCH,
            "BLAST_RADIUS_CHANGED": McpErrorCode.BLAST_RADIUS_CHANGED,
            "SOFT_TRASH_REQUIRED_FIRST": McpErrorCode.SOFT_TRASH_REQUIRED_FIRST,
            "SERVER_ADMIN_REQUIRED": McpErrorCode.SERVER_ADMIN_REQUIRED,
        }
        if prob_code in code_map:
            return code_map[prob_code]

        suffix_map: dict[str, McpErrorCode] = {
            "aal2-required": McpErrorCode.AAL2_REQUIRED,
            "insufficient-capability": McpErrorCode.INSUFFICIENT_PERMISSION,
            "insufficient-permission": McpErrorCode.INSUFFICIENT_PERMISSION,
            "modules-disabled": McpErrorCode.MODULES_DISABLED,
            "section-not-found": McpErrorCode.SECTION_NOT_FOUND,
            "already-promoted": McpErrorCode.ALREADY_PROMOTED,
            "link-type-not-allowed": McpErrorCode.LINK_TYPE_NOT_ALLOWED,
            "cross-scope-taint": McpErrorCode.CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED,
            "mention-access-warning": McpErrorCode.MENTION_ACCESS_WARNING,
            "creator-not-eligible": McpErrorCode.CREATOR_NOT_ELIGIBLE,
            "link-not-flagged": McpErrorCode.LINK_NOT_FLAGGED,
            "creator-unchanged": McpErrorCode.CREATOR_UNCHANGED,
            "not-archived": McpErrorCode.NOT_ARCHIVED,
            "confirm-phrase-mismatch": McpErrorCode.CONFIRM_PHRASE_MISMATCH,
            "lockout-prevented": McpErrorCode.LOCKOUT_PREVENTED,
            "no-started-state": McpErrorCode.NO_STARTED_STATE,
            "use-complete-work": McpErrorCode.USE_COMPLETE_WORK,
            "open-child-blockers": McpErrorCode.OPEN_CHILD_BLOCKERS,
            "qa-verdict-not-ready": McpErrorCode.QA_VERDICT_NOT_READY,
            "invalid-transition": McpErrorCode.INVALID_TRANSITION,
            "transition-held": McpErrorCode.TRANSITION_HELD,
            "group-cycle-rejected": McpErrorCode.GROUP_CYCLE_REJECTED,
            "group-depth-exceeded": McpErrorCode.GROUP_DEPTH_EXCEEDED,
            "confirmation-token-invalid-or-expired": (
                McpErrorCode.CONFIRMATION_TOKEN_INVALID_OR_EXPIRED
            ),
            "token-caller-mismatch": McpErrorCode.TOKEN_CALLER_MISMATCH,
            "token-target-mismatch": McpErrorCode.TOKEN_TARGET_MISMATCH,
            "blast-radius-changed": McpErrorCode.BLAST_RADIUS_CHANGED,
            "soft-trash-required-first": McpErrorCode.SOFT_TRASH_REQUIRED_FIRST,
            "server-admin-required": McpErrorCode.SERVER_ADMIN_REQUIRED,
        }
        for suffix, err_code in suffix_map.items():
            if prob_type.endswith(suffix):
                return err_code

        direct_map = {
            _HTTP_NOT_FOUND: McpErrorCode.NOT_FOUND,
            _HTTP_PRECONDITION_FAILED: McpErrorCode.CONFLICT_ETAG,
            _HTTP_UNPROCESSABLE_ENTITY: McpErrorCode.VALIDATION_FAILED,
            _HTTP_TOO_MANY_REQUESTS: McpErrorCode.RATE_LIMITED,
        }
        if status_code in direct_map:
            return direct_map[status_code]
        if status_code == _HTTP_CONFLICT:
            return KanbanApiClient._resolve_conflict_code(prob_type, prob_code)
        if status_code >= _HTTP_SERVER_ERROR_MIN:
            return McpErrorCode.UPSTREAM_UNAVAILABLE
        return McpErrorCode.UPSTREAM_ERROR
