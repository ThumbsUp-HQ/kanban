"""Media proxy endpoint protecting against SSRF and IP leakage (S5.4, S10.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Response
from starlette.requests import Request  # noqa: TC002

from kanban.api.deps import PrincipalContext, get_principal
from kanban.api.problems import ProblemException
from kanban.media_proxy.service import MediaProxyService
from kanban.media_proxy.signing import validate_external_image_url, verify_media_proxy_url
from kanban.security.keys import load_key_material
from kanban.security.ratelimit import MEDIA_PROXY_PRINCIPAL, rate_limited

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kanban.security.keys import KeyMaterial

router = APIRouter(tags=["media-proxy"])


async def _media_proxy_principal_key(request: Request) -> Sequence[str]:
    """Extract authenticated principal ID for rate limit keying."""
    caller = await get_principal(request)
    request.state.caller_principal = caller
    return [str(caller.principal_id)]


_media_rate_limit_dep = rate_limited(
    MEDIA_PROXY_PRINCIPAL,
    key_func=_media_proxy_principal_key,
)


@router.get(
    "/media-proxy",
    summary="Cookieless SSRF-defended external media proxy",
    dependencies=[Depends(_media_rate_limit_dep)],
)
async def get_media_proxy(
    request: Request,
    u: Annotated[str, Query(description="Target external HTTPS image URL")],
    sig: Annotated[str, Query(description="HMAC-SHA256 signature for media URL")],
) -> Response:
    """Retrieve external Markdown image over DNS-pinned cookieless socket.

    Requires authenticated principal and enforces MEDIA_PROXY_PRINCIPAL rate limits.
    Validates HMAC signature before URL parsing or DNS lookup.
    """
    caller: PrincipalContext = getattr(
        request.state, "caller_principal", None
    ) or await get_principal(request)

    key_mat: KeyMaterial | None = getattr(request.app.state, "key_material", None)
    if key_mat is None:
        key_mat = load_key_material()

    # S5.4: Validate HMAC signature BEFORE URL parsing or DNS lookup
    if not verify_media_proxy_url(u, sig, key_mat):
        msg = "Missing or invalid HMAC signature for media proxy URL"
        raise ProblemException(
            code="INVALID_SIGNATURE",
            status=403,
            title="Invalid Signature",
            detail=msg,
        )

    # Validate external image URL format and boundaries
    validate_external_image_url(u)

    service: MediaProxyService = getattr(
        request.app.state, "media_proxy_service", None
    ) or MediaProxyService(air_gap_checker=getattr(request.app.state, "air_gap_checker", None))

    content_type, body_bytes, extra_headers = await service.fetch_proxy_media(
        u, workspace_id=caller.workspace_id
    )

    response_headers = {
        "content-type": content_type,
        "content-length": str(len(body_bytes)),
        "x-content-type-options": "nosniff",
        "content-security-policy": "default-src 'none'; sandbox",
        "cross-origin-resource-policy": "same-origin",
        "referrer-policy": "no-referrer",
    }
    response_headers.update(extra_headers)

    return Response(
        content=body_bytes,
        status_code=200,
        media_type=content_type,
        headers=response_headers,
    )
