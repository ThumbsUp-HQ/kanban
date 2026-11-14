"""Capability bitmask evaluator and On-Behalf-Of (OBO) delegation logic (S3.2)."""

from __future__ import annotations

from enum import IntFlag
from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from database.models import (
    EffectiveResourceAccess,
    ObjectRecord,
    Principal,
    PrincipalGroupClosure,
)
from kanban.api.problems import ProblemException, not_found

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext


class Capability(IntFlag):
    """Granular capability bitmask matching S3.2 / KB-P1-13 bit positions."""

    NONE = 0
    VIEW = 1 << 0  # 1
    COMMENT = 1 << 1  # 2
    EDIT = 1 << 2  # 4
    TRANSITION = 1 << 3  # 8
    LINK = 1 << 4  # 16
    SHARE = 1 << 5  # 32
    ADMIN = 1 << 6  # 64
    DELETE = 1 << 7  # 128
    ALL = 0xFF  # 255


SCOPE_CAPABILITY_MAP: dict[str, Capability] = {
    "session": Capability.ALL,
    "read": Capability.VIEW,
    "agent:read": Capability.VIEW,
    "docs:read": Capability.VIEW,
    "admin:read": Capability.VIEW,
    "comment": Capability.VIEW | Capability.COMMENT,
    "write": Capability.VIEW
    | Capability.COMMENT
    | Capability.EDIT
    | Capability.TRANSITION
    | Capability.LINK,
    "agent:write": Capability.VIEW
    | Capability.COMMENT
    | Capability.EDIT
    | Capability.TRANSITION
    | Capability.LINK,
    "docs:write": Capability.VIEW
    | Capability.COMMENT
    | Capability.EDIT
    | Capability.TRANSITION
    | Capability.LINK,
    "share": Capability.VIEW | Capability.SHARE,
    "admin:write": Capability(Capability.ALL & ~Capability.DELETE),
    "admin:destructive": Capability.ALL,
}

_ORDERED_CAPABILITIES: tuple[tuple[Capability, str], ...] = (
    (Capability.VIEW, "VIEW"),
    (Capability.COMMENT, "COMMENT"),
    (Capability.EDIT, "EDIT"),
    (Capability.TRANSITION, "TRANSITION"),
    (Capability.LINK, "LINK"),
    (Capability.SHARE, "SHARE"),
    (Capability.ADMIN, "ADMIN"),
    (Capability.DELETE, "DELETE"),
)


def parse_token_scope_mask(token_scopes: Sequence[str]) -> Capability:
    """Parse a sequence of token scopes into an additive capability mask.

    Unknown or empty scopes fail closed and contribute Capability.NONE.
    """
    mask = Capability.NONE
    for scope in token_scopes:
        if scope in SCOPE_CAPABILITY_MAP:
            mask |= SCOPE_CAPABILITY_MAP[scope]
    return mask


def capabilities_to_names(caps: Capability) -> list[str]:
    """Convert an active capability bitmask into canonical uppercase capability names."""
    return [name for cap, name in _ORDERED_CAPABILITIES if cap in caps]


async def _check_ephemeral_confinement(
    session: AsyncSession,
    ephemeral_project_id: uuid.UUID,
    object_id: uuid.UUID,
) -> bool:
    """Verify that the object is confined to the ephemeral project."""
    obj_stmt = select(ObjectRecord.project_id, ObjectRecord.object_type).where(
        ObjectRecord.id == object_id
    )
    obj_row = (await session.execute(obj_stmt)).first()
    if obj_row is None:
        return False
    proj_id, obj_type = obj_row[0], obj_row[1]
    if str(obj_type) == "project":
        return bool(object_id == ephemeral_project_id)
    return bool(proj_id == ephemeral_project_id)


async def _is_principal_active(session: AsyncSession, principal_id: uuid.UUID) -> bool:
    """Check whether a principal exists and has ACTIVE status."""
    stmt = select(Principal.status).where(Principal.id == principal_id)
    status = (await session.execute(stmt)).scalar_one_or_none()
    return status == "ACTIVE"


async def evaluate_capabilities(
    session: AsyncSession,
    principal_ctx: PrincipalContext,
    object_id: uuid.UUID,
) -> Capability:
    """Evaluate effective capabilities enforcing explicit-deny precedence and OBO intersection.

    S3.2:
    - Human or Autonomous Agent:
        EffectivePerms(u, r) = _principal_mask(u, r) & parse_token_scope_mask(token_scopes)
    - Delegated User Agent (OBO):
        EffectivePerms(a_obo(u), r) = (
            _principal_mask(u, r) & _principal_mask(a, r) & parse_token_scope_mask(t)
        )
    """
    # 0. Enforce ephemeral project confinement if ephemeral_project_id is set
    if principal_ctx.ephemeral_project_id is not None and not await _check_ephemeral_confinement(
        session, principal_ctx.ephemeral_project_id, object_id
    ):
        return Capability.NONE

    # 1. Verify human principal exists and is ACTIVE
    if not await _is_principal_active(session, principal_ctx.principal_id):
        return Capability.NONE

    # 2. If OBO delegated agent, verify agent principal exists and is ACTIVE
    if principal_ctx.agent_principal_id is not None and not await _is_principal_active(
        session, principal_ctx.agent_principal_id
    ):
        return Capability.NONE

    # 3. Helper to aggregate effective perms across principal + group closure
    async def _principal_mask(p_id: uuid.UUID) -> Capability:
        ancestor_subq = select(PrincipalGroupClosure.ancestor_group_id).where(
            PrincipalGroupClosure.member_id == p_id
        )
        all_principals = select(text("cast(:target_p_id as uuid)")).union(ancestor_subq)

        stmt = select(
            func.coalesce(func.bit_or(EffectiveResourceAccess.allow_mask), 0),
            func.coalesce(func.bit_or(EffectiveResourceAccess.deny_mask), 0),
        ).where(
            EffectiveResourceAccess.object_id == object_id,
            EffectiveResourceAccess.principal_id.in_(all_principals),
        )

        row = (await session.execute(stmt, {"target_p_id": p_id})).one()
        allow_mask: int = row[0]
        deny_mask: int = row[1]
        # Explicit Deny Precedence: any DENY bit on the principal or any ancestor group clears it
        return Capability(allow_mask & (~deny_mask))

    token_mask = parse_token_scope_mask(principal_ctx.token_scopes)
    if token_mask == Capability.NONE:
        return Capability.NONE

    human_mask = await _principal_mask(principal_ctx.principal_id)

    if principal_ctx.agent_principal_id is None:
        return Capability(human_mask & token_mask)

    agent_mask = await _principal_mask(principal_ctx.agent_principal_id)
    return Capability(human_mask & agent_mask & token_mask)


async def require_capability(
    session: AsyncSession,
    principal_ctx: PrincipalContext,
    object_id: uuid.UUID,
    required: Capability,
) -> Capability:
    """Enforce required capability with S3.4 anti-enumeration 404 discipline.

    - If caller lacks VIEW: raises 404 NOT_FOUND (never 403, preventing object existence leaks).
    - If caller holds VIEW but lacks required: raises 403 INSUFFICIENT_CAPABILITY.
    - Returns effective capabilities for serializer reuse.
    """
    caps = await evaluate_capabilities(session, principal_ctx, object_id)

    if Capability.VIEW not in caps:
        not_found()

    if (caps & required) != required:
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail=None,
        )

    return caps
