"""Capability bitmask evaluator and On-Behalf-Of (OBO) delegation logic (S3.2)."""

from __future__ import annotations

from enum import IntFlag
from typing import TYPE_CHECKING, Any

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


def compute_effective_capabilities(
    rbac_caps: object,
    caller: PrincipalContext | None = None,
    project_id: uuid.UUID | str | None = None,
) -> object:
    """Compute effective capabilities enforcing CredentialBoundary.

    When caller.credential_boundary is present:
    - If project_id is checked and not boundary.allows_project(project_id), return frozenset()
      (deny all access to projects outside project_allowlist).
    - Otherwise intersect the resolved RBAC capabilities with
      boundary.effective_capabilities(rbac_caps).
    """
    actual_caller: Any = caller
    actual_caps = rbac_caps
    if hasattr(rbac_caps, "credential_boundary") and not hasattr(caller, "credential_boundary"):
        actual_caller = rbac_caps
        actual_caps = caller

    boundary = getattr(actual_caller, "credential_boundary", None) if actual_caller else None
    if boundary is None:
        if isinstance(actual_caps, (set, frozenset, list, tuple)):
            return frozenset(actual_caps)
        return actual_caps

    if project_id is not None and not boundary.allows_project(project_id):
        from kanban.security.boundary import EmptyCapabilitySet  # noqa: PLC0415

        return EmptyCapabilitySet()

    return boundary.effective_capabilities(actual_caps)


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


async def _check_boundary_project_allowlist(
    session: AsyncSession,
    boundary: object,
    object_id: uuid.UUID,
) -> bool:
    """Verify that the object is permitted under the boundary's project allowlist."""
    obj_stmt = select(ObjectRecord.project_id, ObjectRecord.object_type).where(
        ObjectRecord.id == object_id
    )
    obj_row = (await session.execute(obj_stmt)).first()
    if obj_row is not None:
        proj_id, obj_type = obj_row[0], obj_row[1]
        target_proj_id = object_id if str(obj_type) == "project" else proj_id
        allows_project_fn = getattr(boundary, "allows_project", None)
        if (
            target_proj_id is not None
            and callable(allows_project_fn)
            and not allows_project_fn(target_proj_id)
        ):
            return False
    return True


async def _is_principal_active(session: AsyncSession, principal_id: uuid.UUID) -> bool:
    """Check whether a principal exists and has ACTIVE status."""
    stmt = select(Principal.status).where(Principal.id == principal_id)
    status = (await session.execute(stmt)).scalar_one_or_none()
    return status == "ACTIVE"


async def evaluate_capabilities(  # noqa: PLR0911
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

    # 0b. Enforce CredentialBoundary project allowlist
    if (
        principal_ctx.credential_boundary is not None
        and not await _check_boundary_project_allowlist(
            session, principal_ctx.credential_boundary, object_id
        )
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
        base_caps = Capability(human_mask & token_mask)
    else:
        agent_mask = await _principal_mask(principal_ctx.agent_principal_id)
        base_caps = Capability(human_mask & agent_mask & token_mask)

    if principal_ctx.credential_boundary is not None:
        return Capability(base_caps & principal_ctx.credential_boundary.capability_mask)
    return base_caps


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
        missing_mask = required & ~caps
        missing_caps = [name for cap, name in _ORDERED_CAPABILITIES if cap in missing_mask]
        cap_names = ", ".join(missing_caps) if missing_caps else str(required)

        if missing_mask & (Capability.ADMIN | Capability.DELETE | Capability.SHARE):
            role_hint = "requires Project Admin, Workspace Admin, or Server Admin role"
        elif missing_mask & (
            Capability.EDIT | Capability.COMMENT | Capability.TRANSITION | Capability.LINK
        ):
            role_hint = (
                "requires Project Member, Project Admin, Workspace Admin, or Server Admin role"
            )
        elif missing_mask & Capability.VIEW:
            role_hint = (
                "requires Project Viewer, Project Member, Project Admin, "
                "Workspace Admin, or Server Admin role"
            )
        else:
            role_hint = "requires Project Admin, Workspace Admin, or Server Admin role"

        detail = f"Missing required capability: {cap_names} ({role_hint})."
        raise ProblemException(
            code="INSUFFICIENT_CAPABILITY",
            status=403,
            title="Insufficient Capability",
            detail=detail,
        )

    return caps
