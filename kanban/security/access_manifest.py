"""Anti-enumeration access manifest serializer and visibility boundary engine (S3.4)."""

from __future__ import annotations

import re
import uuid  # noqa: TC003  # Required at runtime for Pydantic field validation
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select

from database.models import (
    EffectiveResourceAccess,
    Group,
    ObjectKind,
    ObjectRecord,
    Principal,
    PrincipalGroupClosure,
    PrincipalGroupEdge,
    Project,
    ResourceAclEntry,
    RoleBinding,
    User,
    View,
    Workspace,
)
from kanban.api.problems import not_found
from kanban.security.permissions import (
    Capability,
    capabilities_to_names,
    evaluate_capabilities,
    require_capability,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

GrantSourceType = Literal["project_owner", "project_role", "workspace_role", "direct_share"]


@dataclass(frozen=True, slots=True)
class _ManifestContext:
    """Internal grouping of lookup indices and workspace context."""

    caller_ws_id: uuid.UUID
    project_owner_id: uuid.UUID | None
    direct_allow: set[uuid.UUID]
    project_roles: dict[uuid.UUID, str]
    workspace_roles: dict[uuid.UUID, str]


class InheritedScope(BaseModel):
    """Inherited access boundary and naming scope for an object."""

    kind: Literal["private", "project", "workspace"] = Field(
        description="Scoping level for inherited access"
    )
    scope_label: str = Field(description="Display label for inherited scope")
    workspace_id: uuid.UUID = Field(description="Parent workspace identifier")
    workspace_name: str = Field(description="Parent workspace human-readable name")
    project_id: uuid.UUID | None = Field(
        default=None, description="Parent project identifier if scoped"
    )
    project_key: str | None = Field(default=None, description="Project identifier slug if scoped")
    project_name: str | None = Field(default=None, description="Project display name if scoped")


class ManifestUser(BaseModel):
    """User principal sharing representation without email leakage."""

    principal_id: uuid.UUID = Field(description="User principal identifier")
    handle: str = Field(description="Human handle prefixed with @")
    display_name: str = Field(description="User display name")
    capabilities: list[str] = Field(description="Effective active capability names")
    grant_source: GrantSourceType = Field(description="Source of effective permissions")


class ManifestGroup(BaseModel):
    """Group principal sharing representation without raw external DNs."""

    principal_id: uuid.UUID = Field(description="Group principal identifier")
    name: str = Field(description="Group display name")
    member_count: int = Field(description="Total member count within the group")
    external_source: Literal["LDAP", "OIDC"] | None = Field(
        default=None, description="Identity provider sync origin"
    )
    capabilities: list[str] = Field(description="Active capability names")
    grant_source: str = Field(description="Source of group grant")


class ManifestAgent(BaseModel):
    """Agent and automated runner sharing representation."""

    principal_id: uuid.UUID = Field(description="Agent principal identifier")
    display_name: str = Field(description="Agent display name")
    principal_type: Literal["AGENT", "SERVICE_PRINCIPAL"] = Field(
        description="Discriminator for automated principal"
    )
    provider_badge: str | None = Field(default=None, description="Provider or harness badge")
    scope_summary: str = Field(description="Scope description (e.g. Project Scoped)")
    capabilities: list[str] = Field(description="Active capability names")


class ManifestDenyOverride(BaseModel):
    """Explicit restricted override representation."""

    principal_id: uuid.UUID | None = Field(
        default=None, description="Principal identifier (None if redacted)"
    )
    principal_type: str = Field(description="Principal type or UNKNOWN if redacted")
    display_name: str = Field(description="Principal name or '1 Restricted Principal' if redacted")
    redacted: bool = Field(default=False, description="True if principal was redacted")
    denied_capabilities: list[str] = Field(description="List of denied capability names")


class ManifestRedactedEntry(BaseModel):
    """Redacted entry summary for out-of-boundary principals."""

    redacted: bool = Field(default=True, description="Always true for redacted placeholders")
    label: str = Field(description="Summary label (e.g. '1 External Collaborator')")


class AccessManifest(BaseModel):
    """Complete S3.4 access manifest powering the 🛡️ access pill and inspector."""

    pill_label: str = Field(description="Compact header pill label, e.g. 'Project + 2'")
    explicit_grant_count: int = Field(description="Count of explicit direct shares on this object")
    inherited_scope: InheritedScope = Field(description="Inherited scoping metadata")
    users: list[ManifestUser] = Field(default_factory=list, description="In-boundary active users")
    groups: list[ManifestGroup] = Field(
        default_factory=list, description="In-boundary active groups"
    )
    agents: list[ManifestAgent] = Field(
        default_factory=list, description="In-boundary active agents"
    )
    deny_overrides: list[ManifestDenyOverride] = Field(
        default_factory=list, description="Explicit DENY restricted overrides"
    )
    redacted_entries: list[ManifestRedactedEntry] = Field(
        default_factory=list, description="Redacted placeholder entries"
    )
    redacted_count: int = Field(
        default=0, description="Total count of redacted out-of-boundary principals"
    )
    caller_capabilities: list[str] = Field(
        default_factory=list, description="Effective capability names granted to calling principal"
    )
    canonical_key: str | None = Field(
        default=None, description="Canonical display key (e.g. KAN-142)"
    )
    object_type: str | None = Field(
        default=None, description="Type of object (e.g. issue, project)"
    )


_RBAC_ROLE_CAPABILITY_MAP: dict[str, Capability] = {
    "SERVER_ADMIN": Capability.ALL,
    "WORKSPACE_ADMIN": Capability.ALL,
    "PROJECT_ADMIN": Capability.ALL,
    "WORKSPACE_MEMBER": Capability(
        Capability.VIEW
        | Capability.COMMENT
        | Capability.EDIT
        | Capability.TRANSITION
        | Capability.LINK
    ),
    "MEMBER": Capability(
        Capability.VIEW
        | Capability.COMMENT
        | Capability.EDIT
        | Capability.TRANSITION
        | Capability.LINK
    ),
    "VIEWER": Capability(Capability.VIEW | Capability.COMMENT),
    "WORKSPACE_GUEST": Capability.NONE,
}


def _is_out_of_boundary(principal: Principal, ctx: _ManifestContext) -> bool:
    """Determine whether a principal is outside the caller visibility boundary."""
    if principal.workspace_id != ctx.caller_ws_id:
        return True
    if principal.principal_type == "SCRIPT_EPHEMERAL":
        return True
    ws_role = ctx.workspace_roles.get(principal.id)
    pr_role = ctx.project_roles.get(principal.id)
    return ws_role == "WORKSPACE_GUEST" or pr_role == "WORKSPACE_GUEST"


async def _resolve_inherited_scope(
    session: AsyncSession,
    object_rec: ObjectRecord,
    project_rec: Project | None,
    workspace_name: str,
) -> InheritedScope:
    """Resolve inherited scope metadata for the object."""
    if object_rec.object_type == ObjectKind.VIEW:
        view_stmt = select(View.visibility).where(View.id == object_rec.id)
        view_vis = (await session.execute(view_stmt)).scalar_one_or_none()
        if view_vis == "private":
            return InheritedScope(
                kind="private",
                scope_label="Private",
                workspace_id=object_rec.workspace_id,
                workspace_name=workspace_name,
            )

    if project_rec:
        return InheritedScope(
            kind="project",
            scope_label=f"Project: {project_rec.identifier}",
            workspace_id=object_rec.workspace_id,
            workspace_name=workspace_name,
            project_id=project_rec.id,
            project_key=project_rec.identifier,
            project_name=project_rec.name,
        )

    return InheritedScope(
        kind="workspace",
        scope_label=f"Workspace: {workspace_name}",
        workspace_id=object_rec.workspace_id,
        workspace_name=workspace_name,
    )


async def _create_manifest_user(
    session: AsyncSession,
    principal: Principal,
    eff_mask: int,
    ctx: _ManifestContext,
) -> ManifestUser:
    """Build a sanitized ManifestUser record."""
    user_obj = await session.get(ObjectRecord, principal.id)
    if user_obj and user_obj.canonical_key:
        handle = f"@{user_obj.canonical_key.lstrip('@')}"
    else:
        user_row = await session.get(User, principal.id)
        if user_row and user_row.email:
            handle = f"@{user_row.email.split('@')[0]}"
        else:
            handle = f"@{principal.id.hex[:8]}"

    if principal.id == ctx.project_owner_id:
        grant_src: GrantSourceType = "project_owner"
    elif principal.id in ctx.direct_allow:
        grant_src = "direct_share"
    elif principal.id in ctx.project_roles:
        grant_src = "project_role"
    else:
        grant_src = "workspace_role"

    return ManifestUser(
        principal_id=principal.id,
        handle=handle,
        display_name=principal.display_name,
        capabilities=capabilities_to_names(Capability(eff_mask)),
        grant_source=grant_src,
    )


def _create_manifest_agent(
    principal: Principal,
    eff_mask: int,
    ctx: _ManifestContext,
) -> ManifestAgent:
    """Build a sanitized ManifestAgent record."""
    badge_match = re.search(r"\(([^)]+)\)", principal.display_name)
    provider_badge = badge_match.group(1) if badge_match else None

    if principal.id in ctx.direct_allow:
        scope_summary = "Direct Share"
    elif principal.id in ctx.project_roles:
        scope_summary = "Project Scoped"
    else:
        scope_summary = "Workspace Scoped"

    return ManifestAgent(
        principal_id=principal.id,
        display_name=principal.display_name,
        principal_type=principal.principal_type,  # type: ignore[arg-type]
        provider_badge=provider_badge,
        scope_summary=scope_summary,
        capabilities=capabilities_to_names(Capability(eff_mask)),
    )


async def _collect_users_and_agents(
    session: AsyncSession,
    era_rows: list[tuple[EffectiveResourceAccess, Principal]],
    ctx: _ManifestContext,
) -> tuple[list[ManifestUser], list[ManifestAgent], int]:
    """Iterate effective resource access rows and build in-boundary user and agent lists."""
    users: list[ManifestUser] = []
    agents: list[ManifestAgent] = []
    redacted_count = 0
    seen_users: set[uuid.UUID] = set()
    seen_agents: set[uuid.UUID] = set()

    for era, princ in era_rows:
        eff_mask = era.effective_mask or 0
        if _is_out_of_boundary(princ, ctx):
            if eff_mask > 0:
                redacted_count += 1
            continue

        if princ.status != "ACTIVE" or eff_mask <= 0:
            continue

        if princ.principal_type == "USER" and princ.id not in seen_users:
            seen_users.add(princ.id)
            users.append(await _create_manifest_user(session, princ, eff_mask, ctx))
        elif princ.principal_type in ("AGENT", "SERVICE_PRINCIPAL") and princ.id not in seen_agents:
            seen_agents.add(princ.id)
            agents.append(_create_manifest_agent(princ, eff_mask, ctx))

    return users, agents, redacted_count


async def _add_role_groups(
    session: AsyncSession,
    roles: dict[uuid.UUID, str],
    candidates: dict[uuid.UUID, tuple[Group, Principal, str, Capability]],
    grant_source: str,
) -> None:
    """Add eligible groups holding role bindings to candidates map."""
    for p_id, role_val in roles.items():
        if p_id in candidates:
            continue
        p = await session.get(Principal, p_id)
        if p and p.principal_type == "GROUP" and p.status == "ACTIVE":
            g = await session.get(Group, p.id)
            if g:
                caps = _RBAC_ROLE_CAPABILITY_MAP.get(role_val, Capability.NONE)
                candidates[g.id] = (g, p, grant_source, caps)


async def _resolve_group_candidates(
    session: AsyncSession,
    direct_acls: list[ResourceAclEntry],
    ctx: _ManifestContext,
) -> dict[uuid.UUID, tuple[Group, Principal, str, Capability]]:
    """Resolve distinct groups from direct ACLs and role bindings."""
    candidates: dict[uuid.UUID, tuple[Group, Principal, str, Capability]] = {}

    for acl in direct_acls:
        if acl.effect == "ALLOW":
            p = await session.get(Principal, acl.principal_id)
            if p and p.principal_type == "GROUP" and p.status == "ACTIVE":
                g = await session.get(Group, p.id)
                if g:
                    candidates[g.id] = (g, p, "direct_share", Capability(acl.capability_mask))

    await _add_role_groups(session, ctx.project_roles, candidates, "project_role")
    await _add_role_groups(session, ctx.workspace_roles, candidates, "workspace_role")
    return candidates


async def _collect_groups(
    session: AsyncSession,
    direct_acls: list[ResourceAclEntry],
    ctx: _ManifestContext,
) -> tuple[list[ManifestGroup], int]:
    """Collect active in-boundary groups with member counts."""
    candidates = await _resolve_group_candidates(session, direct_acls, ctx)
    groups: list[ManifestGroup] = []
    redacted_count = 0

    for g, p, grant_src, caps in candidates.values():
        if _is_out_of_boundary(p, ctx):
            redacted_count += 1
            continue

        edge_cnt = (
            await session.execute(
                select(func.count(distinct(PrincipalGroupEdge.member_id))).where(
                    PrincipalGroupEdge.group_id == g.id
                )
            )
        ).scalar_one() or 0

        if edge_cnt == 0:
            edge_cnt = (
                await session.execute(
                    select(func.count(distinct(PrincipalGroupClosure.member_id))).where(
                        PrincipalGroupClosure.ancestor_group_id == g.id
                    )
                )
            ).scalar_one() or 0

        groups.append(
            ManifestGroup(
                principal_id=g.id,
                name=g.name,
                member_count=edge_cnt,
                external_source=g.external_source,  # type: ignore[arg-type]
                capabilities=capabilities_to_names(caps),
                grant_source=grant_src,
            )
        )

    return groups, redacted_count


async def _collect_deny_overrides(
    session: AsyncSession,
    direct_deny_acls: list[ResourceAclEntry],
    ctx: _ManifestContext,
) -> list[ManifestDenyOverride]:
    """Collect explicit restricted overrides with out-of-boundary redaction."""
    deny_overrides: list[ManifestDenyOverride] = []

    for d_acl in direct_deny_acls:
        target_p = await session.get(Principal, d_acl.principal_id)
        if not target_p:
            continue

        denied_names = capabilities_to_names(Capability(d_acl.capability_mask))
        if _is_out_of_boundary(target_p, ctx):
            deny_overrides.append(
                ManifestDenyOverride(
                    principal_id=None,
                    principal_type="UNKNOWN",
                    display_name="1 Restricted Principal",
                    redacted=True,
                    denied_capabilities=denied_names,
                )
            )
        else:
            deny_overrides.append(
                ManifestDenyOverride(
                    principal_id=target_p.id,
                    principal_type=target_p.principal_type,
                    display_name=target_p.display_name,
                    redacted=False,
                    denied_capabilities=denied_names,
                )
            )

    return deny_overrides


async def build_access_manifest(
    session: AsyncSession,
    caller: PrincipalContext,
    object_id: uuid.UUID,
) -> AccessManifest:
    """Build the anti-enumeration AccessManifest for an object enforcing S3.4 rules."""
    # 1. Require VIEW capability (raises 404 if unreadable or non-existent)
    await require_capability(session, caller, object_id, Capability.VIEW)

    # 2. Fetch object record
    object_rec = await session.get(ObjectRecord, object_id)
    if object_rec is None:
        not_found()

    # 3. Fetch workspace and project records
    workspace_rec = await session.get(Workspace, object_rec.workspace_id)
    workspace_name = workspace_rec.name if workspace_rec else "Workspace"

    project_rec: Project | None = None
    if object_rec.project_id is not None:
        project_rec = await session.get(Project, object_rec.project_id)

    # 4. Resolve inherited scope and pill label
    inherited_scope = await _resolve_inherited_scope(
        session, object_rec, project_rec, workspace_name
    )

    acl_count_stmt = select(func.count(distinct(ResourceAclEntry.principal_id))).where(
        ResourceAclEntry.object_id == object_id,
        ResourceAclEntry.effect == "ALLOW",
    )
    explicit_grant_count: int = (await session.execute(acl_count_stmt)).scalar_one() or 0

    base_label = (
        "Project"
        if inherited_scope.kind == "project"
        else ("Private" if inherited_scope.kind == "private" else "Workspace")
    )
    if explicit_grant_count > 0:
        pill_label = f"{base_label} + {explicit_grant_count}"
    else:
        pill_label = base_label

    # 5. Project owner identification
    project_owner_id: uuid.UUID | None = None
    if project_rec:
        proj_obj = await session.get(ObjectRecord, project_rec.id)
        if proj_obj:
            project_owner_id = proj_obj.created_by_id

    # 6. Query direct ACL entries and role bindings
    direct_acl_stmt = select(ResourceAclEntry).where(ResourceAclEntry.object_id == object_id)
    direct_acls = list((await session.execute(direct_acl_stmt)).scalars().all())
    direct_allow = {acl.principal_id for acl in direct_acls if acl.effect == "ALLOW"}
    direct_deny_acls = [acl for acl in direct_acls if acl.effect == "DENY"]

    project_roles: dict[uuid.UUID, str] = {}
    if project_rec:
        pr_stmt = select(RoleBinding).where(RoleBinding.project_id == project_rec.id)
        for rb in (await session.execute(pr_stmt)).scalars().all():
            project_roles[rb.principal_id] = str(
                rb.role.value if hasattr(rb.role, "value") else rb.role
            )

    workspace_roles: dict[uuid.UUID, str] = {}
    ws_stmt = select(RoleBinding).where(
        RoleBinding.workspace_id == object_rec.workspace_id,
        RoleBinding.scope_type == "workspace",
    )
    for rb in (await session.execute(ws_stmt)).scalars().all():
        workspace_roles[rb.principal_id] = str(
            rb.role.value if hasattr(rb.role, "value") else rb.role
        )

    ctx = _ManifestContext(
        caller_ws_id=caller.workspace_id,
        project_owner_id=project_owner_id,
        direct_allow=direct_allow,
        project_roles=project_roles,
        workspace_roles=workspace_roles,
    )

    # 7. Query effective resource access
    era_stmt = (
        select(EffectiveResourceAccess, Principal)
        .join(Principal, Principal.id == EffectiveResourceAccess.principal_id)
        .where(EffectiveResourceAccess.object_id == object_id)
    )
    era_rows = list((await session.execute(era_stmt)).all())

    # 8. Collect users, agents, groups, and deny overrides
    users, agents, red_users = await _collect_users_and_agents(
        session,
        era_rows,  # type: ignore[arg-type]
        ctx,
    )

    groups, red_groups = await _collect_groups(session, direct_acls, ctx)

    deny_overrides = await _collect_deny_overrides(session, direct_deny_acls, ctx)

    total_redacted = red_users + red_groups
    redacted_entries: list[ManifestRedactedEntry] = []
    if total_redacted > 0:
        plural = "s" if total_redacted > 1 else ""
        redacted_entries.append(
            ManifestRedactedEntry(
                redacted=True,
                label=f"{total_redacted} External Collaborator{plural}",
            )
        )

    caller_caps = await evaluate_capabilities(session, caller, object_id)
    caller_capabilities = capabilities_to_names(caller_caps)
    canonical_key = object_rec.canonical_key or (
        f"{inherited_scope.project_key}"
        if inherited_scope.project_key
        else str(object_rec.id)[:8]
    )
    object_type = (
        object_rec.object_type.value
        if hasattr(object_rec.object_type, "value")
        else str(object_rec.object_type)
    )

    return AccessManifest(
        pill_label=pill_label,
        explicit_grant_count=explicit_grant_count,
        inherited_scope=inherited_scope,
        users=users,
        groups=groups,
        agents=agents,
        deny_overrides=deny_overrides,
        redacted_entries=redacted_entries,
        redacted_count=total_redacted,
        caller_capabilities=caller_capabilities,
        canonical_key=canonical_key,
        object_type=object_type,
    )
