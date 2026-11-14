# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""RFC 8628 Headless CLI Device Authorization Flow engine (KB-P4-16)."""

from __future__ import annotations

import logging
import re
import secrets
import time
import uuid  # noqa: TC003  # Runtime import required for Pydantic / dataclass type annotations
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models.oauth import (
    OAuthClient,
    OAuthDeviceCode,
    OAuthGrant,
)
from kanban.api.problems import ProblemException
from kanban.oauth.server import (
    SURFACE_SCOPES,
    OAuth2Error,
    hash_token,
    parse_surface_from_resource,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_logger: Final[logging.Logger] = logging.getLogger(__name__)

# Base-20 consonant-safe alphabet (RFC 8628 section 6.1 recommendation)
# Avoids vowels (A, E, I, O, U) and ambiguous characters (0, 1, 8, O, I).
BASE20_ALPHABET: Final[str] = "BCDFGHJKLMNPQRSTVWXZ"
USER_CODE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[" + BASE20_ALPHABET + r"]{4}-[" + BASE20_ALPHABET + r"]{4}$"
)

RAW_USER_CODE_LEN: Final[int] = 8
DEVICE_CODE_TTL_SECONDS: Final[int] = 600
DEFAULT_POLL_INTERVAL_SECONDS: Final[int] = 5
MAX_INVALID_ATTEMPTS: Final[int] = 5
RATE_LIMIT_WINDOW_SECONDS: Final[int] = 300

# In-memory rate limiting tracking for invalid user code submissions: key -> timestamps
_failed_attempts: Final[dict[str, list[float]]] = {}


def generate_device_code() -> str:
    """Generate a high-entropy URL-safe device code."""
    return secrets.token_urlsafe(32)


def generate_user_code() -> str:
    """Generate an 8-character user code formatted as XXXX-XXXX in Base-20 consonant alphabet."""
    part1 = "".join(secrets.choice(BASE20_ALPHABET) for _ in range(4))
    part2 = "".join(secrets.choice(BASE20_ALPHABET) for _ in range(4))
    return f"{part1}-{part2}"


def normalize_user_code(raw_code: str) -> str:
    """Normalize user input: strip whitespace, hyphens, uppercase, and format as XXXX-XXXX."""
    cleaned = raw_code.strip().replace("-", "").replace(" ", "").upper()
    if len(cleaned) == RAW_USER_CODE_LEN:
        return f"{cleaned[:4]}-{cleaned[4:]}"
    return raw_code.strip().upper()


def is_rate_limited(key: str) -> bool:
    """Check if the given IP/session key has exceeded 5 failed attempts in the last 300s."""
    now = time.time()
    attempts = _failed_attempts.setdefault(key, [])
    attempts[:] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
    return len(attempts) >= MAX_INVALID_ATTEMPTS


def record_failed_attempt(key: str) -> None:
    """Record a failed user code attempt for brute-force defense."""
    now = time.time()
    attempts = _failed_attempts.setdefault(key, [])
    attempts[:] = [t for t in attempts if now - t < RATE_LIMIT_WINDOW_SECONDS]
    attempts.append(now)


def clear_failed_attempts(key: str) -> None:
    """Reset failed attempts upon successful code verification."""
    _failed_attempts.pop(key, None)


def reset_rate_limits() -> None:
    """Reset all rate limiting state (used for testing)."""
    _failed_attempts.clear()


@dataclass(frozen=True, slots=True)
class DeviceAuthorizationResult:
    """Response returned to headless CLI client upon initiating device flow."""

    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class DeviceCodeInfo:
    """Information displayed on user consent verification screen."""

    user_code: str
    client_name: str
    client_id: str
    resource: str
    surface: str
    requested_scopes: list[str]
    allowed_projects: list[uuid.UUID] | None
    expires_at: datetime


async def create_device_authorization(  # noqa: PLR0913
    session: AsyncSession,
    *,
    client_id_str: str,
    resource: str,
    scope_str: str | None,
    base_url: str,
    workspace_id: uuid.UUID | None = None,
) -> DeviceAuthorizationResult:
    """Create a new RFC 8628 device authorization request."""
    # 1. Lookup client
    stmt_client = select(OAuthClient).where(OAuthClient.client_id == client_id_str)
    client = (await session.execute(stmt_client)).scalar_one_or_none()
    if client is None or client.status != "active":
        err = "invalid_client"
        desc = "Client not found or not active"
        raise OAuth2Error(err, desc, 400)

    # 2. Determine target surface and validate scopes
    surface = parse_surface_from_resource(resource, base_url)
    allowed_scopes = SURFACE_SCOPES[surface]

    if scope_str:
        requested_scopes = [s for s in scope_str.split() if s in allowed_scopes]
    else:
        requested_scopes = list(allowed_scopes)

    if not requested_scopes:
        requested_scopes = [allowed_scopes[0]]

    # 3. Determine workspace
    ws_id = client.workspace_id or workspace_id

    # 4. Generate random device code and unique user code
    device_code = generate_device_code()
    device_code_sha = hash_token(device_code)

    user_code = generate_user_code()
    # Ensure user_code uniqueness
    for _ in range(5):
        stmt_check = select(OAuthDeviceCode).where(OAuthDeviceCode.user_code == user_code)
        if (await session.execute(stmt_check)).scalar_one_or_none() is None:
            break
        user_code = generate_user_code()

    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=DEVICE_CODE_TTL_SECONDS)

    record = OAuthDeviceCode(
        device_code_sha256=device_code_sha,
        user_code=user_code,
        client_id=client.id,
        workspace_id=ws_id,
        resource=resource,
        surface=surface,
        requested_scopes=requested_scopes,
        status="pending",
        created_at=now,
        expires_at=expires_at,
        interval_sec=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    session.add(record)
    await session.commit()

    verif_uri = f"{base_url}/activate"
    verif_uri_complete = f"{base_url}/activate?user_code={user_code}"

    return DeviceAuthorizationResult(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verif_uri,
        verification_uri_complete=verif_uri_complete,
        expires_in=DEVICE_CODE_TTL_SECONDS,
        interval=DEFAULT_POLL_INTERVAL_SECONDS,
    )


async def poll_device_code(  # noqa: C901, PLR0915
    session: AsyncSession,
    *,
    device_code: str,
    client_id_str: str,
) -> OAuthGrant:
    """Poll device code verification status per RFC 8628 section 3.5."""
    if not device_code:
        err = "invalid_request"
        desc = "device_code parameter required"
        raise OAuth2Error(err, desc, 400)

    device_sha = hash_token(device_code)
    stmt = (
        select(OAuthDeviceCode, OAuthClient)
        .join(OAuthClient, OAuthClient.id == OAuthDeviceCode.client_id)
        .where(OAuthDeviceCode.device_code_sha256 == device_sha)
    )
    res = (await session.execute(stmt)).first()
    if res is None:
        err = "invalid_grant"
        desc = "Invalid device code"
        raise OAuth2Error(err, desc, 400)

    code_record, client_record = res

    if client_record.client_id != client_id_str:
        err = "invalid_grant"
        desc = "client_id mismatch"
        raise OAuth2Error(err, desc, 400)

    now = datetime.now(UTC)

    # Check expiration
    if code_record.expires_at <= now or code_record.status == "expired":
        if code_record.status != "expired":
            code_record.status = "expired"
            await session.commit()
        err = "expired_token"
        desc = "Device code has expired"
        raise OAuth2Error(err, desc, 400)

    # Check polling interval (RFC 8628 section 3.5)
    if code_record.last_polled_at is not None:
        elapsed = (now - code_record.last_polled_at).total_seconds()
        if elapsed < code_record.interval_sec:
            # Polling faster than interval: increment required interval by 5s and raise slow_down
            code_record.interval_sec += 5
            code_record.last_polled_at = now
            await session.commit()
            err = "slow_down"
            desc = f"Polling too rapidly. Interval increased to {code_record.interval_sec} seconds."
            raise OAuth2Error(err, desc, 400)

    code_record.last_polled_at = now

    # Check status
    if code_record.status == "denied":
        await session.commit()
        err = "access_denied"
        desc = "User denied authorization"
        raise OAuth2Error(err, desc, 400)

    if code_record.status == "pending":
        await session.commit()
        err = "authorization_pending"
        desc = "Authorization is pending user approval"
        raise OAuth2Error(err, desc, 400)

    if code_record.status == "approved":
        if code_record.approved_grant_id is None:
            err = "invalid_grant"
            desc = "Missing approved grant reference"
            raise OAuth2Error(err, desc, 400)

        grant = await session.get(OAuthGrant, code_record.approved_grant_id)
        if grant is None or grant.revoked_at is not None:
            err = "invalid_grant"
            desc = "Approved grant is invalid or revoked"
            raise OAuth2Error(err, desc, 400)

        # Mark consumed so device_code cannot be polled again
        code_record.status = "expired"
        await session.commit()
        return grant

    err = "invalid_grant"
    desc = f"Invalid device code state: {code_record.status}"
    raise OAuth2Error(err, desc, 400)


async def get_device_code_info(
    session: AsyncSession,
    raw_user_code: str,
    *,
    rate_limit_key: str,
) -> DeviceCodeInfo:
    """Validate user code and retrieve metadata for the consent screen."""
    if is_rate_limited(rate_limit_key):
        msg = "Too many invalid code verification attempts. Please wait 5 minutes."
        raise ProblemException(
            code="RATE_LIMIT_EXCEEDED",
            status=429,
            title="Too Many Attempts",
            detail=msg,
        )

    norm_code = normalize_user_code(raw_user_code)
    if not USER_CODE_PATTERN.match(norm_code):
        record_failed_attempt(rate_limit_key)
        msg = "User code must match format XXXX-XXXX using consonant alphabet."
        raise ProblemException(
            code="INVALID_USER_CODE",
            status=400,
            title="Invalid User Code",
            detail=msg,
        )

    now = datetime.now(UTC)
    stmt = (
        select(OAuthDeviceCode, OAuthClient)
        .join(OAuthClient, OAuthClient.id == OAuthDeviceCode.client_id)
        .where(OAuthDeviceCode.user_code == norm_code)
    )
    res = (await session.execute(stmt)).first()
    if res is None:
        record_failed_attempt(rate_limit_key)
        msg = "No device authorization request found for this code."
        raise ProblemException(
            code="NOT_FOUND",
            status=404,
            title="Device Code Not Found",
            detail=msg,
        )

    code_record, client_record = res

    if code_record.expires_at <= now or code_record.status == "expired":
        if code_record.status != "expired":
            code_record.status = "expired"
            await session.commit()
        msg = "This device code has expired. Please initiate a new login from the CLI."
        raise ProblemException(
            code="EXPIRED_CODE",
            status=410,
            title="Device Code Expired",
            detail=msg,
        )

    if code_record.status != "pending":
        msg = f"This device code has already been {code_record.status}."
        raise ProblemException(
            code="ALREADY_PROCESSED",
            status=409,
            title="Device Code Already Processed",
            detail=msg,
        )

    # Valid lookup; do not clear failed attempts yet until submission or pass
    return DeviceCodeInfo(
        user_code=code_record.user_code,
        client_name=client_record.client_name,
        client_id=client_record.client_id,
        resource=code_record.resource,
        surface=code_record.surface,
        requested_scopes=code_record.requested_scopes,
        allowed_projects=code_record.allowed_projects,
        expires_at=code_record.expires_at,
    )


async def activate_device_code(  # noqa: C901, PLR0913, PLR0915
    session: AsyncSession,
    *,
    raw_user_code: str,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    approved: bool,
    allowed_scopes: list[str] | None,
    allowed_projects: list[uuid.UUID] | None,
    rate_limit_key: str,
    is_aal2: bool = False,
) -> OAuthGrant | None:
    """Process user consent decision on the /activate screen."""
    if is_rate_limited(rate_limit_key):
        msg = "Too many invalid code verification attempts. Please wait 5 minutes."
        raise ProblemException(
            code="RATE_LIMIT_EXCEEDED",
            status=429,
            title="Too Many Attempts",
            detail=msg,
        )

    norm_code = normalize_user_code(raw_user_code)
    if not USER_CODE_PATTERN.match(norm_code):
        record_failed_attempt(rate_limit_key)
        msg = "User code must match format XXXX-XXXX using consonant alphabet."
        raise ProblemException(
            code="INVALID_USER_CODE",
            status=400,
            title="Invalid User Code",
            detail=msg,
        )

    now = datetime.now(UTC)
    stmt = (
        select(OAuthDeviceCode, OAuthClient)
        .join(OAuthClient, OAuthClient.id == OAuthDeviceCode.client_id)
        .where(OAuthDeviceCode.user_code == norm_code)
    )
    res = (await session.execute(stmt)).first()
    if res is None:
        record_failed_attempt(rate_limit_key)
        msg = "No device authorization request found for this code."
        raise ProblemException(
            code="NOT_FOUND",
            status=404,
            title="Device Code Not Found",
            detail=msg,
        )

    code_record, client_record = res

    if code_record.expires_at <= now or code_record.status == "expired":
        if code_record.status != "expired":
            code_record.status = "expired"
            await session.commit()
        msg = "This device code has expired. Please initiate a new login from the CLI."
        raise ProblemException(
            code="EXPIRED_CODE",
            status=410,
            title="Device Code Expired",
            detail=msg,
        )

    if code_record.status != "pending":
        msg = f"This device code has already been {code_record.status}."
        raise ProblemException(
            code="ALREADY_PROCESSED",
            status=409,
            title="Device Code Already Processed",
            detail=msg,
        )

    # Success: clear failed attempts
    clear_failed_attempts(rate_limit_key)

    if not approved:
        code_record.status = "denied"
        await session.commit()
        return None

    # Enforce AAL2 Gate if resource targets /mcp/admin
    is_admin_target = code_record.surface == "admin" or "/mcp/admin" in code_record.resource
    if is_admin_target and not is_aal2:
        msg = "Device approval for /mcp/admin requires AAL2 Passkey or TOTP verification."
        raise ProblemException(
            code="AAL2_REQUIRED",
            status=403,
            title="AAL2 Step-Up Required",
            detail=msg,
        )

    # Filter and narrow scopes
    valid_surface_scopes = SURFACE_SCOPES[code_record.surface]
    if allowed_scopes:
        final_scopes = [s for s in allowed_scopes if s in valid_surface_scopes]
    else:
        final_scopes = list(code_record.requested_scopes)

    if not final_scopes:
        final_scopes = [valid_surface_scopes[0]]

    # Narrow projects
    final_projects = (
        allowed_projects if allowed_projects is not None else code_record.allowed_projects
    )

    grant = OAuthGrant(
        workspace_id=workspace_id,
        principal_id=principal_id,
        client_id=client_record.id,
        surface=code_record.surface,
        scopes=final_scopes,
        allowed_projects=final_projects,
    )
    session.add(grant)
    await session.flush()

    code_record.status = "approved"
    code_record.approved_grant_id = grant.id
    code_record.approved_by_user_id = principal_id
    code_record.approved_scopes = final_scopes
    if final_projects is not None:
        code_record.allowed_projects = final_projects

    await session.commit()
    return grant
