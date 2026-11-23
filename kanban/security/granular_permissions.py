# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Granular RBAC 30-permission engine, multi-role label evaluation, and enforcement.

(KB-GRANULAR-RBAC, KAN-83).
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import select, text

from database.models import (
    Principal,
    PrincipalGroupClosure,
    PrincipalRoleLabel,
    RbacRoleModel,
    RbacRolePermission,
    ResourceAclEntry,
    RoleBinding,
)
from kanban.api.problems import ProblemException, not_found
from kanban.security.permissions import Capability

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext


class GranularPermission(StrEnum):
    """Canonical 30 granular permission keys across workspace, issue, and field tiers."""

    # Workspace Tier (8)
    WORKSPACE_CREATE = "workspace:create"
    WORKSPACE_EDIT_SETTINGS = "workspace:edit_settings"
    WORKSPACE_MANAGE_MEMBERS = "workspace:manage_members"
    WORKSPACE_MANAGE_GROUPS = "workspace:manage_groups"
    WORKSPACE_CREATE_ROLE = "workspace:create_role"
    WORKSPACE_CREATE_PROJECT = "workspace:create_project"
    WORKSPACE_MANAGE_TRASH = "workspace:manage_trash"
    WORKSPACE_MANAGE_MCP_KEYS = "workspace:manage_mcp_keys"

    # Issue Tier (10)
    ISSUE_CREATE = "issue:create"
    ISSUE_VIEW = "issue:view"
    ISSUE_COMMENT = "issue:comment"
    ISSUE_TRANSITION = "issue:transition"
    ISSUE_MOVE_RANK = "issue:move_rank"
    ISSUE_LINK = "issue:link"
    ISSUE_COPY = "issue:copy"
    ISSUE_ARCHIVE = "issue:archive"
    ISSUE_DELETE = "issue:delete"
    ISSUE_MANAGE_ACL = "issue:manage_acl"

    # Field Tier (12)
    FIELD_MODIFY_SUMMARY = "field:modify_summary"
    FIELD_MODIFY_DESCRIPTION = "field:modify_description"
    FIELD_MODIFY_STATE = "field:modify_state"
    FIELD_MODIFY_PRIORITY = "field:modify_priority"
    FIELD_MODIFY_ASSIGNEES = "field:modify_assignees"
    FIELD_MODIFY_LABELS = "field:modify_labels"
    FIELD_MODIFY_DATES = "field:modify_dates"
    FIELD_MODIFY_CYCLE = "field:modify_cycle"
    FIELD_MODIFY_MODULES = "field:modify_modules"
    FIELD_MODIFY_PARENT = "field:modify_parent"
    FIELD_MODIFY_CUSTOM_FIELDS = "field:modify_custom_fields"
    FIELD_ATTACH_FILES = "field:attach_files"


WORKSPACE_PERMISSIONS: frozenset[str] = frozenset(
    {
        GranularPermission.WORKSPACE_CREATE.value,
        GranularPermission.WORKSPACE_EDIT_SETTINGS.value,
        GranularPermission.WORKSPACE_MANAGE_MEMBERS.value,
        GranularPermission.WORKSPACE_MANAGE_GROUPS.value,
        GranularPermission.WORKSPACE_CREATE_ROLE.value,
        GranularPermission.WORKSPACE_CREATE_PROJECT.value,
        GranularPermission.WORKSPACE_MANAGE_TRASH.value,
        GranularPermission.WORKSPACE_MANAGE_MCP_KEYS.value,
    }
)

ISSUE_PERMISSIONS: frozenset[str] = frozenset(
    {
        GranularPermission.ISSUE_CREATE.value,
        GranularPermission.ISSUE_VIEW.value,
        GranularPermission.ISSUE_COMMENT.value,
        GranularPermission.ISSUE_TRANSITION.value,
        GranularPermission.ISSUE_MOVE_RANK.value,
        GranularPermission.ISSUE_LINK.value,
        GranularPermission.ISSUE_COPY.value,
        GranularPermission.ISSUE_ARCHIVE.value,
        GranularPermission.ISSUE_DELETE.value,
        GranularPermission.ISSUE_MANAGE_ACL.value,
    }
)

FIELD_PERMISSIONS: frozenset[str] = frozenset(
    {
        GranularPermission.FIELD_MODIFY_SUMMARY.value,
        GranularPermission.FIELD_MODIFY_DESCRIPTION.value,
        GranularPermission.FIELD_MODIFY_STATE.value,
        GranularPermission.FIELD_MODIFY_PRIORITY.value,
        GranularPermission.FIELD_MODIFY_ASSIGNEES.value,
        GranularPermission.FIELD_MODIFY_LABELS.value,
        GranularPermission.FIELD_MODIFY_DATES.value,
        GranularPermission.FIELD_MODIFY_CYCLE.value,
        GranularPermission.FIELD_MODIFY_MODULES.value,
        GranularPermission.FIELD_MODIFY_PARENT.value,
        GranularPermission.FIELD_MODIFY_CUSTOM_FIELDS.value,
        GranularPermission.FIELD_ATTACH_FILES.value,
    }
)

ALL_PERMISSIONS: frozenset[str] = WORKSPACE_PERMISSIONS | ISSUE_PERMISSIONS | FIELD_PERMISSIONS

# Map field permissions to issue response editable_field property names
FIELD_PERMISSION_PROPERTY_MAP: dict[str, str] = {
    GranularPermission.FIELD_MODIFY_SUMMARY.value: "summary",
    GranularPermission.FIELD_MODIFY_DESCRIPTION.value: "description",
    GranularPermission.FIELD_MODIFY_STATE.value: "state",
    GranularPermission.FIELD_MODIFY_PRIORITY.value: "priority",
    GranularPermission.FIELD_MODIFY_ASSIGNEES.value: "assignees",
    GranularPermission.FIELD_MODIFY_LABELS.value: "labels",
    GranularPermission.FIELD_MODIFY_DATES.value: "dates",
    GranularPermission.FIELD_MODIFY_CYCLE.value: "cycle",
    GranularPermission.FIELD_MODIFY_MODULES.value: "modules",
    GranularPermission.FIELD_MODIFY_PARENT.value: "parent",
    GranularPermission.FIELD_MODIFY_CUSTOM_FIELDS.value: "custom_fields",
    GranularPermission.FIELD_ATTACH_FILES.value: "attachments",
}

DEFAULT_BUILTIN_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "SERVER_ADMIN": ALL_PERMISSIONS,
    "system-admin": ALL_PERMISSIONS,
    "WORKSPACE_ADMIN": ALL_PERMISSIONS - {GranularPermission.WORKSPACE_CREATE.value},
    "workspace-admin": ALL_PERMISSIONS - {GranularPermission.WORKSPACE_CREATE.value},
    "PROJECT_ADMIN": ISSUE_PERMISSIONS | FIELD_PERMISSIONS,
    "project-admin": ISSUE_PERMISSIONS | FIELD_PERMISSIONS,
    "WORKSPACE_MEMBER": frozenset(
        {
            GranularPermission.ISSUE_CREATE.value,
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
            GranularPermission.ISSUE_TRANSITION.value,
            GranularPermission.ISSUE_MOVE_RANK.value,
            GranularPermission.ISSUE_LINK.value,
            GranularPermission.ISSUE_COPY.value,
        }
    )
    | FIELD_PERMISSIONS,
    "MEMBER": frozenset(
        {
            GranularPermission.ISSUE_CREATE.value,
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
            GranularPermission.ISSUE_TRANSITION.value,
            GranularPermission.ISSUE_MOVE_RANK.value,
            GranularPermission.ISSUE_LINK.value,
            GranularPermission.ISSUE_COPY.value,
        }
    )
    | FIELD_PERMISSIONS,
    "users": frozenset(
        {
            GranularPermission.ISSUE_CREATE.value,
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
            GranularPermission.ISSUE_TRANSITION.value,
            GranularPermission.ISSUE_MOVE_RANK.value,
            GranularPermission.ISSUE_LINK.value,
            GranularPermission.ISSUE_COPY.value,
        }
    )
    | FIELD_PERMISSIONS,
    "VIEWER": frozenset(
        {
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
        }
    ),
    "viewer": frozenset(
        {
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
        }
    ),
    "WORKSPACE_GUEST": frozenset(
        {
            GranularPermission.ISSUE_VIEW.value,
        }
    ),
    "guest": frozenset(
        {
            GranularPermission.ISSUE_VIEW.value,
        }
    ),
}


async def _is_principal_active(session: AsyncSession, principal_id: uuid.UUID) -> bool:
    stmt = select(Principal.status).where(Principal.id == principal_id)
    status = (await session.execute(stmt)).scalar_one_or_none()
    return status == "ACTIVE"


async def _get_principal_closure_ids(
    session: AsyncSession,
    principal_id: uuid.UUID,
) -> set[uuid.UUID]:
    subq = select(PrincipalGroupClosure.ancestor_group_id).where(
        PrincipalGroupClosure.member_id == principal_id
    )
    ancestors = (await session.execute(subq)).scalars().all()
    return {principal_id, *ancestors}


async def _evaluate_single_principal_permissions(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    principal_id: uuid.UUID,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
) -> set[str]:
    """Resolve additive union of granular permissions for a single principal."""
    if not await _is_principal_active(session, principal_id):
        return set()

    pset = await _get_principal_closure_ids(session, principal_id)
    granted: set[str] = set()

    # 1. System role bindings
    rb_stmt = select(RoleBinding).where(
        RoleBinding.principal_id.in_(pset),
        RoleBinding.workspace_id == workspace_id,
    )
    role_bindings = (await session.execute(rb_stmt)).scalars().all()

    for rb in role_bindings:
        role_str = str(rb.role.value if hasattr(rb.role, "value") else rb.role)
        if role_str == "SERVER_ADMIN":
            return set(ALL_PERMISSIONS)
        if role_str == "WORKSPACE_ADMIN":
            granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS["WORKSPACE_ADMIN"]
        elif role_str == "PROJECT_ADMIN":
            if rb.project_id is None or project_id is None or rb.project_id == project_id:
                granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS["PROJECT_ADMIN"]
        elif role_str in ("WORKSPACE_MEMBER", "MEMBER"):
            if rb.project_id is None or project_id is None or rb.project_id == project_id:
                granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS["WORKSPACE_MEMBER"]
        elif role_str == "VIEWER":
            if rb.project_id is None or project_id is None or rb.project_id == project_id:
                granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS["VIEWER"]
        elif role_str == "WORKSPACE_GUEST":
            granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS["WORKSPACE_GUEST"]

    # 2. Custom role permissions via principal_role_labels and rbac_role_permissions
    prl_stmt = (
        select(RbacRolePermission.permission_key, RbacRoleModel.system_role, RbacRoleModel.slug)
        .select_from(PrincipalRoleLabel)
        .join(RbacRoleModel, RbacRoleModel.id == PrincipalRoleLabel.role_id)
        .join(RbacRolePermission, RbacRolePermission.role_id == RbacRoleModel.id)
        .where(
            PrincipalRoleLabel.principal_id.in_(pset),
            PrincipalRoleLabel.workspace_id == workspace_id,
            (
                PrincipalRoleLabel.project_id.is_(None)
                | (PrincipalRoleLabel.project_id == project_id)
            ),
            RbacRolePermission.effect == "ALLOW",
            (
                RbacRolePermission.project_id.is_(None)
                | (RbacRolePermission.project_id == project_id)
            ),
        )
    )
    for perm_key, _sys_role, _slug in (await session.execute(prl_stmt)).all():
        granted.add(perm_key)

    # 3. Direct role labels (including built-ins attached via label)
    label_roles_stmt = (
        select(RbacRoleModel)
        .join(PrincipalRoleLabel, PrincipalRoleLabel.role_id == RbacRoleModel.id)
        .where(
            PrincipalRoleLabel.principal_id.in_(pset),
            PrincipalRoleLabel.workspace_id == workspace_id,
            (
                PrincipalRoleLabel.project_id.is_(None)
                | (PrincipalRoleLabel.project_id == project_id)
            ),
        )
    )
    for role_obj in (await session.execute(label_roles_stmt)).scalars().all():
        if role_obj.slug in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
            granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS[role_obj.slug]
        if role_obj.system_role in DEFAULT_BUILTIN_ROLE_PERMISSIONS:
            granted |= DEFAULT_BUILTIN_ROLE_PERMISSIONS[role_obj.system_role]

    # 4. Direct resource ACL entries on target project or object
    acl_targets = [tid for tid in (project_id, object_id) if tid is not None]
    if acl_targets:
        acl_stmt = select(ResourceAclEntry.capability_mask, ResourceAclEntry.effect).where(
            ResourceAclEntry.workspace_id == workspace_id,
            ResourceAclEntry.principal_id.in_(pset),
            ResourceAclEntry.object_id.in_(acl_targets),
        )
        allow_mask = 0
        deny_mask = 0
        for mask_val, effect_val in (await session.execute(acl_stmt)).all():
            if effect_val == "ALLOW":
                allow_mask |= int(mask_val)
            elif effect_val == "DENY":
                deny_mask |= int(mask_val)
        eff_mask = allow_mask & (~deny_mask)
        if eff_mask & Capability.VIEW:
            granted.add(GranularPermission.ISSUE_VIEW.value)
        if eff_mask & Capability.COMMENT:
            granted.add(GranularPermission.ISSUE_COMMENT.value)
        if eff_mask & Capability.EDIT:
            granted |= FIELD_PERMISSIONS | {
                GranularPermission.ISSUE_CREATE.value,
                GranularPermission.ISSUE_MOVE_RANK.value,
                GranularPermission.ISSUE_COPY.value,
            }
        if eff_mask & Capability.TRANSITION:
            granted |= {
                GranularPermission.ISSUE_TRANSITION.value,
                GranularPermission.FIELD_MODIFY_STATE.value,
            }
        if eff_mask & Capability.LINK:
            granted.add(GranularPermission.ISSUE_LINK.value)
        if eff_mask & Capability.SHARE:
            granted.add(GranularPermission.ISSUE_MANAGE_ACL.value)
        if eff_mask & Capability.DELETE:
            granted |= {
                GranularPermission.ISSUE_DELETE.value,
                GranularPermission.ISSUE_ARCHIVE.value,
            }

    return granted


def _filter_permissions_by_token_scope(
    permissions: set[str],
    token_scopes: tuple[str, ...],
) -> set[str]:
    """Narrow permissions if token scopes restrict access."""
    if not token_scopes:
        return permissions

    if "session" in token_scopes or "admin:destructive" in token_scopes:
        return permissions

    filtered = set()
    has_read = "read" in token_scopes or "agent:read" in token_scopes or "docs:read" in token_scopes
    has_write = (
        "write" in token_scopes or "agent:write" in token_scopes or "docs:write" in token_scopes
    )
    has_comment = "comment" in token_scopes
    has_share = "share" in token_scopes
    has_admin_write = "admin:write" in token_scopes

    for perm in permissions:
        if has_read and perm == GranularPermission.ISSUE_VIEW.value:
            filtered.add(perm)
        if has_comment and perm in (
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_COMMENT.value,
        ):
            filtered.add(perm)
        if has_write and (perm in ISSUE_PERMISSIONS or perm in FIELD_PERMISSIONS):
            filtered.add(perm)
        if has_share and perm in (
            GranularPermission.ISSUE_VIEW.value,
            GranularPermission.ISSUE_MANAGE_ACL.value,
        ):
            filtered.add(perm)
        if has_admin_write and perm != GranularPermission.ISSUE_DELETE.value:
            filtered.add(perm)

    return filtered


def _filter_permissions_by_boundary(
    permissions: set[str],
    credential_boundary: object | None,
) -> set[str]:
    """Narrow permissions if credential boundary limits capability bitmask."""
    if credential_boundary is None:
        return permissions

    mask = getattr(credential_boundary, "capability_mask", None)
    if mask is None:
        return permissions

    filtered = set()
    for perm in permissions:
        if (
            (perm == GranularPermission.ISSUE_VIEW.value and (mask & Capability.VIEW))
            or (perm == GranularPermission.ISSUE_COMMENT.value and (mask & Capability.COMMENT))
            or (perm in FIELD_PERMISSIONS and (mask & Capability.EDIT))
            or (
                perm == GranularPermission.ISSUE_TRANSITION.value and (mask & Capability.TRANSITION)
            )
            or (perm == GranularPermission.ISSUE_LINK.value and (mask & Capability.LINK))
            or (perm == GranularPermission.ISSUE_MANAGE_ACL.value and (mask & Capability.SHARE))
            or (
                perm
                in (
                    GranularPermission.ISSUE_DELETE.value,
                    GranularPermission.ISSUE_ARCHIVE.value,
                )
                and (mask & Capability.DELETE)
            )
            or (perm in WORKSPACE_PERMISSIONS and (mask & Capability.ADMIN))
            or perm not in (ISSUE_PERMISSIONS | FIELD_PERMISSIONS | WORKSPACE_PERMISSIONS)
        ):
            filtered.add(perm)

    return filtered


async def evaluate_granular_permissions(
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    object_id: uuid.UUID | None = None,
) -> set[str]:
    """Evaluate full additive union of granular permissions for caller context."""
    # SERVER_ADMIN has universal access
    is_server_admin = getattr(caller, "is_server_admin", False)
    if not is_server_admin:
        try:
            stmt = text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
            res = await session.execute(stmt)
            is_server_admin = bool(res.scalar_one())
        except Exception:  # noqa: BLE001
            is_server_admin = False

    if is_server_admin:
        return set(ALL_PERMISSIONS)

    # 1. Base human permissions
    perms = await _evaluate_single_principal_permissions(
        session, caller.principal_id, workspace_id, project_id, object_id
    )

    # 2. OBO Delegated Agent intersection
    if caller.agent_principal_id is not None:
        agent_perms = await _evaluate_single_principal_permissions(
            session, caller.agent_principal_id, workspace_id, project_id, object_id
        )
        perms = perms & agent_perms

    # 3. Token scopes filtering
    if caller.token_scopes:
        perms = _filter_permissions_by_token_scope(perms, caller.token_scopes)

    # 4. Credential boundary filtering
    if caller.credential_boundary is not None:
        perms = _filter_permissions_by_boundary(perms, caller.credential_boundary)

    return perms


async def require_permissions(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    caller: PrincipalContext,
    workspace_id: uuid.UUID,
    required: set[str] | str,
    project_id: uuid.UUID | None = None,
    object_readable: bool = True,  # noqa: FBT001, FBT002
    object_id: uuid.UUID | None = None,
    error_code: str = "INSUFFICIENT_PERMISSION",
) -> set[str]:
    """Enforce required granular permissions with S3.4 anti-enumeration 404 discipline."""
    req_set = {required} if isinstance(required, str) else set(required)

    if not object_readable:
        not_found()

    perms = await evaluate_granular_permissions(
        session, caller, workspace_id, project_id, object_id
    )
    missing = req_set - perms

    if missing:
        if GranularPermission.ISSUE_VIEW.value in missing and not object_readable:
            not_found()

        missing_list = sorted(missing)
        raise ProblemException(
            code=error_code,
            status=403,
            title="Insufficient Permission"
            if error_code == "INSUFFICIENT_PERMISSION"
            else "Insufficient Capability",
            detail=f"Missing required permission(s): {', '.join(missing_list)}",
            extra={"missing_permissions": missing_list},
        )

    return perms
