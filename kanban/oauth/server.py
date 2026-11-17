# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""OAuth 2.1 authorization server core logic, PKCE, codes & consent (KB-P4-02b)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import logging
import os
import time
import uuid  # noqa: TC003
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

from sqlalchemy import update
from starlette.responses import HTMLResponse

from database.models.oauth import (
    OAuthGrant,
    OAuthRefreshToken,
)
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from starlette.requests import Request

_logger: Final[logging.Logger] = logging.getLogger(__name__)

CODE_TTL_SECONDS: Final[int] = 300
REFRESH_TOKEN_TTL_DAYS: Final[int] = 30
MAX_REDIRECT_URIS: Final[int] = 5
MIN_CODE_VERIFIER_LEN: Final[int] = 43
MAX_CODE_VERIFIER_LEN: Final[int] = 128
MAX_REGISTRATIONS_PER_IP_HOUR: Final[int] = 100

SURFACE_SCOPES: Final[dict[str, list[str]]] = {
    "agent": ["agent:read", "agent:write"],
    "docs": ["docs:read", "docs:write"],
    "admin": ["admin:read", "admin:write", "admin:destructive"],
}


class OAuth2Error(Exception):
    """RFC 6749 OAuth 2.0 error with error code and description."""

    def __init__(
        self,
        error: str,
        description: str,
        status_code: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize OAuth2 error with RFC 6749 code and human description."""
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code
        self.headers = headers or {}


def hash_token(token: str) -> bytes:
    """Compute SHA-256 digest of token string."""
    return hashlib.sha256(token.encode("ascii")).digest()


def verify_pkce_s256(code_verifier: str, code_challenge: str) -> bool:
    """Verify PKCE S256 code_verifier against code_challenge in constant time."""
    if not (MIN_CODE_VERIFIER_LEN <= len(code_verifier) <= MAX_CODE_VERIFIER_LEN):
        return False
    try:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        calculated = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return hmac.compare_digest(calculated, code_challenge)
    except (UnicodeError, ValueError):
        return False


def validate_redirect_uri(redirect_uri: str, registered_uris: list[str]) -> bool:
    """Validate redirect URI via exact string match against registered URIs."""
    return redirect_uri in registered_uris


def validate_registration_redirect_uris(uris: list[str]) -> None:
    """Validate client redirect URIs meet RFC 7591 / OAuth 2.1 constraints."""
    err = "invalid_redirect_uri"
    if not uris:
        raise OAuth2Error(err, "At least one redirect_uri required", 400)
    if len(uris) > MAX_REDIRECT_URIS:
        raise OAuth2Error(
            err,
            f"Maximum {MAX_REDIRECT_URIS} redirect URIs permitted",
            400,
        )

    for uri in uris:
        parsed = urlparse(uri)
        if parsed.fragment:
            raise OAuth2Error(err, f"Redirect URI {uri!r} must not contain a fragment", 400)
        if parsed.username or parsed.password:
            raise OAuth2Error(err, f"Redirect URI {uri!r} must not contain userinfo", 400)
        if parsed.scheme == "https":
            continue
        if parsed.scheme == "http" and (
            parsed.hostname in ("127.0.0.1", "localhost", "::1", "[::1]")
            or parsed.netloc.startswith("::1")
            or parsed.netloc.startswith("[::1]")
        ):
            continue
        raise OAuth2Error(
            err,
            f"Redirect URI {uri!r} must use HTTPS or loopback HTTP (127.0.0.1/localhost/::1)",
            400,
        )


def resolve_public_base_url(request: Request | None = None) -> str:
    """Resolve canonical public base URL from settings, proxy headers, or request base URL."""
    env_origin = os.environ.get("KANBAN_PUBLIC_ORIGIN", "").strip()
    if env_origin:
        return env_origin.rstrip("/")

    if request is not None:
        proto = request.headers.get("x-forwarded-proto")
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if proto and host:
            return f"{proto}://{host}".rstrip("/")
        if host:
            has_url = hasattr(request, "url")
            scheme = request.url.scheme if has_url and request.url.scheme else "http"
            return f"{scheme}://{host}".rstrip("/")
        if hasattr(request, "base_url"):
            return str(request.base_url).rstrip("/")

    return "http://localhost:8000"


def parse_resource_target(
    resource: str,
    base_url: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Parse resource indicator URL into (surface, workspace_slug, project_key).

    Supports:
        - /mcp
        - /mcp/w/{workspace_slug}
        - /mcp/w/{workspace_slug}/p/{project_key}
        - /mcp/{surface}
        - /mcp/{surface}/w/{workspace_slug}
        - /mcp/{surface}/w/{workspace_slug}/p/{project_key}
    Default surface is 'agent' when omitted.
    """
    del base_url
    clean_res = resource.rstrip("/")
    parsed = urlparse(clean_res)
    path = (parsed.path or clean_res).rstrip("/")

    if not path.startswith("/"):
        path = "/" + path

    # Check for /mcp base
    target_err = "invalid_target"
    idx = path.find("/mcp")
    if idx == -1:
        raise OAuth2Error(
            target_err,
            f"Resource {resource!r} must target /mcp/agent, /mcp/docs, or /mcp/admin",
            400,
        )

    subpath = path[idx + len("/mcp") :].strip("/")
    segments = [s for s in subpath.split("/") if s]

    surface = "agent"
    ws_slug: str | None = None
    proj_key: str | None = None

    if not segments:
        # Bare /mcp -> surface 'agent'
        return surface, None, None

    if segments[0] in ("agent", "docs", "admin"):
        surface = segments[0]
        segments = segments[1:]

    if segments:
        if segments[0] == "w" and len(segments) >= 2:  # noqa: PLR2004
            ws_slug = segments[1]
            if len(segments) >= 4 and segments[2] == "p":  # noqa: PLR2004
                proj_key = segments[3]
        else:
            raise OAuth2Error(
                target_err,
                f"Resource {resource!r} has invalid target scope segments",
                400,
            )

    return surface, ws_slug, proj_key


def parse_surface_from_resource(resource: str, base_url: str | None = None) -> str:
    """Extract surface ('agent', 'docs', 'admin') from resource URL."""
    surface, _, _ = parse_resource_target(resource, base_url)
    return surface


class RegistrationRateLimiter:
    """In-memory rate limiter for dynamic client registration (100/IP/hr)."""

    def __init__(
        self,
        limit: int = MAX_REGISTRATIONS_PER_IP_HOUR,
        window_s: float = 3600.0,
    ) -> None:
        """Initialize registration sliding window rate limiter."""
        self._limit = limit
        self._window_s = window_s
        self._history: dict[str, list[float]] = {}

    def check(self, ip: str) -> bool:
        """Check if inbound client IP is within registration rate budget."""
        now = time.time()
        cutoff = now - self._window_s
        timestamps = self._history.setdefault(ip, [])
        self._history[ip] = [t for t in timestamps if t > cutoff]
        if len(self._history[ip]) >= self._limit:
            return False
        self._history[ip].append(now)
        return True


_registration_limiter = RegistrationRateLimiter()


def check_registration_rate_limit(ip: str) -> None:
    """Check IP registration rate limit or raise 429."""
    if not _registration_limiter.check(ip):
        err = "rate_limit_exceeded"
        raise OAuth2Error(
            err,
            "Registration rate limit exceeded for this IP. Retry in 1 hour.",
            429,
        )




async def revoke_grant_family(
    session: AsyncSession,
    grant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_principal_id: uuid.UUID | None = None,
) -> None:
    """Revoke an OAuth grant and all associated refresh tokens and active access tokens."""
    now = datetime.now(UTC)

    # 1. Mark grant revoked
    stmt_grant = (
        update(OAuthGrant)
        .where(OAuthGrant.id == grant_id, OAuthGrant.workspace_id == workspace_id)
        .values(revoked_at=now)
    )
    await session.execute(stmt_grant)

    # 2. Mark all refresh tokens revoked
    stmt_rt = (
        update(OAuthRefreshToken)
        .where(
            OAuthRefreshToken.grant_id == grant_id,
            OAuthRefreshToken.workspace_id == workspace_id,
            OAuthRefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(stmt_rt)

    # 3. Record audit activity
    if actor_principal_id is not None:
        await record_activity(
            session,
            workspace_id=workspace_id,
            object_id=None,
            actor_principal_id=actor_principal_id,
            event_type=ActivityEventType.MCP_OAUTH_GRANT_REVOKED,
            payload={
                "grant_id": str(grant_id),
                "revoked_at": now.isoformat(),
            },
        )


SCOPE_DESCRIPTIONS: Final[dict[str, str]] = {
    "agent:read": "Read-only access to boards, tickets, stickies, and issues",
    "agent:write": "Read and write access to tickets, comments, stickies, and workflows",
    "docs:read": "Read-only access to documents and knowledge spaces",
    "docs:write": "Read and write access to documents, stickies, and knowledge bases",
    "admin:read": "Read-only access to system users, audit logs, and settings",
    "admin:write": "Administrative write access to policies and configurations",
    "admin:destructive": "Full destructive administrative control (purge and hard delete)",
}


def render_consent_screen(  # noqa: PLR0913
    *,
    client_name: str,
    redirect_uri: str,
    surface: str,
    requested_scopes: list[str],
    state: str,
    code_challenge: str,
    code_challenge_method: str,
    resource: str,
    client_id: str,
    csrf_token: str,
    available_projects: list[tuple[uuid.UUID, str]] | None = None,
    principal_display: str | None = None,
) -> HTMLResponse:
    """Render server-rendered accessible OAuth 2.1 consent and approval screen."""
    parsed_redirect = urlparse(redirect_uri)
    host_display = html.escape(parsed_redirect.netloc or redirect_uri)
    safe_client_name = html.escape(client_name)
    safe_surface = html.escape(surface.upper())
    safe_resource = html.escape(resource)
    safe_principal = html.escape(principal_display) if principal_display else None

    # Scope checkboxes with human-readable descriptions
    scope_rows = []
    for sc in requested_scopes:
        safe_sc = html.escape(sc)
        desc = html.escape(SCOPE_DESCRIPTIONS.get(sc, "Access to requested capability"))
        scope_rows.append(
            f'<label class="scope-item">'
            f'<input type="checkbox" name="scopes" value="{safe_sc}" checked /> '
            f'<span class="scope-info">'
            f'<span class="scope-name">{safe_sc}</span>'
            f'<span class="scope-desc">{desc}</span>'
            f"</span>"
            f"</label>"
        )
    scopes_html = "\n".join(scope_rows)

    # Project scope selector
    project_options = ['<option value="__ALL__">All Accessible Projects</option>']
    if available_projects:
        for p_id, p_name in available_projects:
            safe_p_id = html.escape(str(p_id))
            safe_p_name = html.escape(p_name)
            project_options.append(f'<option value="{safe_p_id}">{safe_p_name}</option>')
    projects_html = "\n".join(project_options)

    principal_badge_html = (
        f'<div class="user-badge">Signed in as <strong>{safe_principal}</strong></div>'
        if safe_principal
        else ""
    )

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Authorize {safe_client_name} - Kanban</title>
  <style>
    :root {{
      --bg: #0f172a;
      --card-bg: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --danger: #ef4444;
      --danger-hover: #dc2626;
      --badge-bg: #1e3a8a;
      --badge-text: #93c5fd;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 1rem;
    }}
    .consent-card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      max-width: 480px;
      width: 100%;
      padding: 2rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .header {{ text-align: center; margin-bottom: 1.5rem; }}
    .app-title {{ font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem; }}
    .host-badge {{
      display: inline-block;
      font-size: 0.8125rem;
      color: var(--text-muted);
      background: #090d16;
      padding: 0.25rem 0.625rem;
      border-radius: 6px;
      border: 1px solid var(--border);
    }}
    .user-badge {{
      text-align: center;
      font-size: 0.8125rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
    }}
    .user-badge strong {{
      color: var(--text);
    }}
    .surface-banner {{
      background: var(--badge-bg);
      color: var(--badge-text);
      padding: 0.5rem 0.75rem;
      border-radius: 6px;
      font-size: 0.875rem;
      font-weight: 600;
      margin-bottom: 1.25rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .section-title {{
      font-size: 0.875rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 0.5rem;
    }}
    .scope-list {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      margin-bottom: 1.25rem;
      background: #151f30;
      padding: 0.75rem;
      border-radius: 8px;
    }}
    .scope-item {{
      display: flex;
      align-items: flex-start;
      gap: 0.5rem;
      font-size: 0.875rem;
      cursor: pointer;
    }}
    .scope-info {{
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }}
    .scope-name {{ font-family: monospace; color: #cbd5e1; font-weight: 600; }}
    .scope-desc {{ font-size: 0.75rem; color: var(--text-muted); }}
    .project-selector {{ margin-bottom: 1.5rem; }}
    .project-selector select {{
      width: 100%;
      padding: 0.5rem;
      background: #151f30;
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 0.875rem;
    }}
    .actions {{ display: flex; gap: 0.75rem; }}
    .btn {{
      flex: 1;
      padding: 0.75rem;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.9375rem;
      cursor: pointer;
      border: none;
      text-align: center;
      text-decoration: none;
    }}
    .btn-approve {{ background: var(--primary); color: white; }}
    .btn-approve:hover {{ background: var(--primary-hover); }}
    .btn-deny {{ background: #334155; color: var(--text); }}
    .btn-deny:hover {{ background: #475569; }}
  </style>
</head>
<body>
  <div class="consent-card">
    <div class="header">
      <h1 class="app-title">Authorize {safe_client_name}</h1>
      <span class="host-badge">Redirects to {host_display}</span>
      {principal_badge_html}
    </div>

    <div class="surface-banner">
      <span>Target MCP Surface</span>
      <span>{safe_surface}</span>
    </div>

    <form method="POST" action="/oauth/authorize/decision">
      <input type="hidden" name="client_id" value="{html.escape(client_id)}" />
      <input type="hidden" name="redirect_uri" value="{html.escape(redirect_uri)}" />
      <input type="hidden" name="resource" value="{safe_resource}" />
      <input type="hidden" name="code_challenge" value="{html.escape(code_challenge)}" />
      <input type="hidden" name="code_challenge_method"
             value="{html.escape(code_challenge_method)}" />
      <input type="hidden" name="state" value="{html.escape(state)}" />
      <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}" />

      <div class="section-title">Requested Permissions</div>
      <div class="scope-list">
        {scopes_html}
      </div>

      <div class="project-selector">
        <div class="section-title">Project Scope</div>
        <select name="allowed_project_id">
          {projects_html}
        </select>
      </div>

      <div class="actions">
        <button type="submit" name="action" value="deny" class="btn btn-deny">Deny</button>
        <button type="submit" name="action" value="approve" class="btn btn-approve">Approve</button>
      </div>
    </form>
  </div>
</body>
</html>
"""
    return HTMLResponse(
        html_content,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )
