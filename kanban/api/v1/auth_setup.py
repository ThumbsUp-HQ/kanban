# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""First-boot setup claim and status API endpoints (KB-P2-12)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Annotated, Final

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.requests import Request  # noqa: TC002
from starlette.responses import JSONResponse

from database.session import RLSContext
from kanban.auth.sessions.cookies import build_set_cookie_header
from kanban.auth.sessions.csrf import build_set_csrf_cookie_header
from kanban.auth.sessions.service import SessionService  # noqa: TC001
from kanban.auth.setup import SetupBootstrapService
from kanban.security.client_ip import resolve_client_ip
from kanban.security.ratelimit import SETUP_CLAIM_IP, rate_limited

if TYPE_CHECKING:
    from collections.abc import Sequence

    from database.session import RLSSessionFactory
    from kanban.security.keys import KeyMaterial
    from kanban.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])

MIN_DISPLAY_NAME_CHARS: Final[int] = 1
MAX_DISPLAY_NAME_CHARS: Final[int] = 120
MIN_PASSWORD_BYTES: Final[int] = 14
MAX_PASSWORD_BYTES: Final[int] = 1024


class SetupStatusResponse(BaseModel):
    """Status indicating whether first-boot setup has been completed."""

    model_config = ConfigDict(extra="forbid")
    initialized: bool = Field(..., description="True if initial administrator exists")


class SetupClaimRequest(BaseModel):
    """Initial administrator provisioning request."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(..., description="First-boot single-use setup claim token")
    username: str = Field(
        ...,
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9._-]{2,62}$",
        description="Lowercase administrator username",
    )
    display_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Display name for administrator account",
    )
    password: str = Field(
        ...,
        min_length=14,
        max_length=1024,
        description="Administrator password (minimum 14 characters)",
    )
    email: str | None = Field(
        default=None,
        max_length=320,
        description="Optional administrator email (defaults to username@local.kanban)",
    )

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        """Validate display name length after trimming whitespace."""
        trimmed = v.strip()
        if not (MIN_DISPLAY_NAME_CHARS <= len(trimmed) <= MAX_DISPLAY_NAME_CHARS):
            msg = "display_name must be between 1 and 120 characters after trimming"
            raise ValueError(msg)
        return trimmed

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """Validate password byte length in UTF-8."""
        utf8_len = len(v.encode("utf-8"))
        if not (MIN_PASSWORD_BYTES <= utf8_len <= MAX_PASSWORD_BYTES):
            msg = "password must be between 14 and 1024 UTF-8 bytes"
            raise ValueError(msg)
        return v


def _get_setup_service(request: Request) -> SetupBootstrapService:
    session_factory: RLSSessionFactory = request.app.state.session_factory
    key_material: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return SetupBootstrapService(session_factory, key_material=key_material, settings=settings)


def _get_session_service(request: Request) -> SessionService:
    service: SessionService | None = getattr(request.app.state, "session_service", None)
    if service is None:
        msg = "SessionService is not configured on application state"
        raise RuntimeError(msg)
    return service


def _resolve_setup_ip_key(request: Request) -> Sequence[str]:
    return [resolve_client_ip(request)]


@router.get("/status", response_model=SetupStatusResponse)
async def get_setup_status(
    request: Request,
    setup_service: Annotated[SetupBootstrapService, Depends(_get_setup_service)],
) -> SetupStatusResponse:
    """Check whether first-boot administrator claiming has occurred."""
    session_factory: RLSSessionFactory = request.app.state.session_factory
    rls_ctx = RLSContext(
        workspace_id=uuid.UUID(int=0),
        principal_id=uuid.UUID(int=0),
    )
    async with session_factory.session(rls_ctx) as session:
        is_init = await setup_service.is_initialized(session)
    return SetupStatusResponse(initialized=is_init)


@router.post(
    "/claim",
    dependencies=[Depends(rate_limited(SETUP_CLAIM_IP, key_func=_resolve_setup_ip_key))],
)
async def claim_setup(
    payload: SetupClaimRequest,
    request: Request,
    setup_service: Annotated[SetupBootstrapService, Depends(_get_setup_service)],
    session_service: Annotated[SessionService, Depends(_get_session_service)],
) -> JSONResponse:
    """Atomically claim instance, provision first SERVER_ADMIN, and require AAL2 enrollment."""
    session_factory: RLSSessionFactory = request.app.state.session_factory
    clean_email = payload.email.strip() if payload.email else f"{payload.username}@local.kanban"

    rls_ctx = RLSContext(
        workspace_id=uuid.UUID(int=0),
        principal_id=uuid.UUID(int=0),
    )

    async with session_factory.session(rls_ctx) as session:
        (
            principal_id_str,
            workspace_id_str,
            local_card_id_str,
        ) = await setup_service.claim_initial_admin(
            session,
            token=payload.token,
            username=payload.username,
            display_name=payload.display_name,
            email=clean_email,
            password=payload.password,
        )
        principal_id = uuid.UUID(principal_id_str)
        workspace_id = uuid.UUID(workspace_id_str)
        local_card_id = uuid.UUID(local_card_id_str)

        # Issue session with mfa_pending=True so new admin is gated to enrollment
        issued = await session_service.create_after_login(
            session,
            principal_id=principal_id,
            workspace_id=workspace_id,
            auth_card_id=local_card_id,
            aal_level=1,
            mfa_pending=True,
        )

    response = JSONResponse(
        status_code=200,
        content={
            "status": "enrollment_required",
            "principal_id": str(principal_id),
            "enrollment_id": str(issued.session_id),
        },
    )

    response.raw_headers.append(
        (
            b"set-cookie",
            build_set_cookie_header(issued.cookie_val, issued.idle_expires_at).encode("latin-1"),
        )
    )
    response.raw_headers.append(
        (
            b"set-cookie",
            build_set_csrf_cookie_header(issued.csrf_token).encode("latin-1"),
        )
    )

    return response
