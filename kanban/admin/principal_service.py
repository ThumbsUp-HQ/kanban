# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Principal and group administration service (KB-P4-09b, S11.4, S3.1)."""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import unquote

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from database.models.agent_definition import AgentDefinition
from database.models.base import RbacRole
from database.models.mcp_api_key import McpApiKey
from database.models.principals import (
    Group,
    Principal,
    PrincipalGroupClosure,
    PrincipalGroupEdge,
    RoleBinding,
    User,
)
from database.models.projects import Project
from database.models.spine import ObjectRecord
from kanban.api.problems import FieldError, ProblemException, not_found
from kanban.auth.cards.lockout import LockoutPreventedError
from kanban.auth.local.hashing import get_auth_pepper, hash_password_sync
from kanban.services.activity import ActivityEventType, record_activity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_HANDLE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,38}$")
_RFC4122_UUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
MAX_PRINCIPAL_NAME_LEN: Final[int] = 120
MAX_PRINCIPALS_LIMIT: Final[int] = 100


def normalize_handle(handle: str) -> str:
    """Normalize and validate a user or agent handle."""
    h = handle.strip().lstrip("@").lower()
    if not _HANDLE_PATTERN.match(h):
        msg = f"Invalid handle format: '{handle}'. Must match ^[a-z0-9][a-z0-9._-]{{1,38}}$"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="handle", message=msg)],
        )
    return h


async def resolve_principal_id(  # noqa: RET503
    session: AsyncSession,
    workspace_id: uuid.UUID,
    ref: str,
) -> uuid.UUID:
    """Resolve a principal reference (@handle, group name, agent slug, or UUID) to a UUID."""
    r = unquote(ref.strip())
    if _RFC4122_UUID_REGEX.match(r):
        uid = uuid.UUID(r)
        stmt = select(Principal.id).where(
            Principal.id == uid,
            Principal.workspace_id == workspace_id,
            Principal.principal_type != "SCRIPT_EPHEMERAL",
        )
        found = (await session.execute(stmt)).scalar_one_or_none()
        if found:
            return found
        not_found()

    # If starts with @, try user canonical key or handle
    clean_ref = r.lstrip("@").lower()
    canonical_key = f"@{clean_ref}"

    # 1. Search objects for user canonical_key
    user_stmt = select(ObjectRecord.id).where(
        ObjectRecord.workspace_id == workspace_id,
        func.lower(ObjectRecord.canonical_key).in_([canonical_key, clean_ref]),
        ObjectRecord.object_type == "user",
        ObjectRecord.deleted_at.is_(None),
    )
    user_id = (await session.execute(user_stmt)).scalar_one_or_none()
    if user_id:
        return user_id

    # 2. Search groups by name
    group_stmt = select(Group.id).where(
        Group.workspace_id == workspace_id,
        func.lower(Group.name) == r.lower(),
    )
    group_id = (await session.execute(group_stmt)).scalar_one_or_none()
    if group_id:
        return group_id

    # 3. Search agent_definitions by slug
    agent_stmt = select(AgentDefinition.principal_id).where(
        AgentDefinition.workspace_id == workspace_id,
        func.lower(AgentDefinition.slug) == clean_ref,
    )
    agent_pid = (await session.execute(agent_stmt)).scalar_one_or_none()
    if agent_pid:
        return agent_pid

    # 4. Search principals by display_name
    p_stmt = select(Principal.id).where(
        Principal.workspace_id == workspace_id,
        func.lower(Principal.display_name) == clean_ref,
        Principal.principal_type != "SCRIPT_EPHEMERAL",
    )
    p_id = (await session.execute(p_stmt)).scalar_one_or_none()
    if p_id:
        return p_id

    not_found()


async def get_principal_detail(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_ref: str,
) -> dict[str, Any]:
    """Retrieve full details for a principal in the workspace."""
    p_id = await resolve_principal_id(session, workspace_id, principal_ref)

    p_stmt = select(Principal).where(
        Principal.id == p_id,
        Principal.workspace_id == workspace_id,
    )
    principal = (await session.execute(p_stmt)).scalar_one_or_none()
    if principal is None or principal.principal_type == "SCRIPT_EPHEMERAL":
        not_found()

    handle: str | None = None
    email: str | None = None

    if principal.principal_type == "USER":
        # Get handle from objects
        obj_stmt = select(ObjectRecord.canonical_key).where(
            ObjectRecord.id == p_id,
            ObjectRecord.object_type == "user",
        )
        ck = (await session.execute(obj_stmt)).scalar_one_or_none()
        handle = ck or f"@{principal.display_name.lower().replace(' ', '')}"

        # Get email
        u_stmt = select(User.email).where(User.id == p_id)
        email = (await session.execute(u_stmt)).scalar_one_or_none()

    elif principal.principal_type == "AGENT":
        a_stmt = select(AgentDefinition.slug).where(AgentDefinition.principal_id == p_id)
        slug = (await session.execute(a_stmt)).scalar_one_or_none()
        handle = f"@{slug}" if slug else f"@{principal.display_name.lower().replace(' ', '')}"

    elif principal.principal_type == "GROUP":
        g_stmt = select(Group.name).where(Group.id == p_id)
        g_name = (await session.execute(g_stmt)).scalar_one_or_none()
        handle = g_name or principal.display_name

    # Retrieve groups via closure
    closure_stmt = (
        select(Group.name)
        .join(PrincipalGroupClosure, PrincipalGroupClosure.ancestor_group_id == Group.id)
        .where(
            PrincipalGroupClosure.member_id == p_id,
            PrincipalGroupClosure.workspace_id == workspace_id,
        )
        .order_by(Group.name)
    )
    groups = list((await session.execute(closure_stmt)).scalars().all())

    # Retrieve role bindings
    rb_stmt = (
        select(RoleBinding, Project.identifier)
        .outerjoin(Project, Project.id == RoleBinding.project_id)
        .where(
            RoleBinding.principal_id == p_id,
            RoleBinding.workspace_id == workspace_id,
        )
    )
    rb_rows = (await session.execute(rb_stmt)).all()
    roles: list[dict[str, Any]] = []
    for rb, prj_ident in rb_rows:
        scope_str = prj_ident if rb.scope_type == "project" and prj_ident else rb.scope_type
        roles.append(
            {
                "role": str(rb.role.value if hasattr(rb.role, "value") else rb.role),
                "scope_type": rb.scope_type,
                "scope": scope_str,
                "project_id": str(rb.project_id) if rb.project_id else None,
            }
        )

    status_str = "active" if principal.status == "ACTIVE" else "deactivated"
    return {
        "id": str(principal.id),
        "principal": handle or principal.display_name,
        "handle": handle,
        "display_name": principal.display_name,
        "type": principal.principal_type,
        "status": status_str,
        "email": email,
        "groups": groups,
        "roles": roles,
        "created_at": principal.created_at.isoformat(),
    }


def _highest_role(user_roles: list[str]) -> str:
    """Return highest role from list of bound roles."""
    for candidate in ("SERVER_ADMIN", "WORKSPACE_ADMIN", "WORKSPACE_MEMBER", "WORKSPACE_GUEST"):
        if candidate in user_roles:
            return candidate
    return user_roles[0] if user_roles else "WORKSPACE_MEMBER"


def _resolve_provider_label(p_kind: str, p_slug: str) -> str:  # noqa: PLR0911
    """Classify provider kind/slug into presentation label."""
    kind = p_kind.upper()
    slug = p_slug.lower()
    if kind == "LOCAL_ADMIN":
        return "LOCAL"
    if "google" in slug:
        return "GOOGLE"
    if "github" in slug:
        return "GITHUB"
    if "active-directory" in slug or slug == "ad" or slug.startswith("ad-") or slug.endswith("-ad"):
        return "ACTIVE_DIRECTORY"
    if kind == "LDAP":
        return "LDAP"
    if kind in ("OIDC", "OAUTH2"):
        return "OAUTH2"
    return kind


async def _enrich_user_principal(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    p: Principal,
) -> tuple[str, str | None, str, str]:
    """Resolve handle, email, highest role, and provider badge for a USER principal."""
    ck_stmt = select(ObjectRecord.canonical_key).where(
        ObjectRecord.id == p.id,
        ObjectRecord.object_type == "user",
    )
    ck = (await session.execute(ck_stmt)).scalar_one_or_none()
    handle = ck or f"@{p.display_name.lower().replace(' ', '')}"

    u_stmt = select(User.email).where(User.id == p.id)
    email = (await session.execute(u_stmt)).scalar_one_or_none()

    rb_stmt = select(RoleBinding.role).where(
        RoleBinding.principal_id == p.id,
        RoleBinding.workspace_id == workspace_id,
    )
    raw_roles = (await session.execute(rb_stmt)).scalars().all()
    user_roles = [str(r.value if hasattr(r, "value") else r) for r in raw_roles]
    role = _highest_role(user_roles)

    ui_stmt = text(
        "SELECT provider_kind, card_slug AS slug "
        "FROM kb_auth.identity_list_for_principal(:p_id) LIMIT 1"
    )
    ui_row = (await session.execute(ui_stmt, {"p_id": p.id})).mappings().first()
    provider = (
        _resolve_provider_label(str(ui_row["provider_kind"]), str(ui_row["slug"]))
        if ui_row
        else "LOCAL"
    )

    return handle, email, role, provider


async def list_principals(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    filter_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List principals in the workspace, omitting SCRIPT_EPHEMERAL."""
    if limit < 1 or limit > MAX_PRINCIPALS_LIMIT:
        msg = f"Limit must be between 1 and {MAX_PRINCIPALS_LIMIT} (got {limit})"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="limit", message=msg)],
        )

    stmt = (
        select(Principal)
        .where(
            Principal.workspace_id == workspace_id,
            Principal.principal_type != "SCRIPT_EPHEMERAL",
        )
        .order_by(Principal.display_name)
        .limit(limit)
    )

    if filter_type is not None:
        ft = filter_type.strip().upper()
        if ft not in ("USER", "GROUP", "AGENT", "SERVICE_PRINCIPAL"):
            msg = (
                f"Invalid filter '{filter_type}'. Must be USER, GROUP, AGENT, or SERVICE_PRINCIPAL"
            )
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="filter", message=msg)],
            )
        stmt = stmt.where(Principal.principal_type == ft)

    principals = list((await session.execute(stmt)).scalars().all())
    result: list[dict[str, Any]] = []

    for p in principals:
        handle = p.display_name
        email: str | None = None
        role: str = "WORKSPACE_MEMBER"
        provider: str = "LOCAL"

        if p.principal_type == "USER":
            handle, email, role, provider = await _enrich_user_principal(session, workspace_id, p)
        elif p.principal_type == "AGENT":
            a_stmt = select(AgentDefinition.slug).where(AgentDefinition.principal_id == p.id)
            slug = (await session.execute(a_stmt)).scalar_one_or_none()
            if slug:
                handle = f"@{slug}"
        elif p.principal_type == "GROUP":
            g_stmt = select(Group.name).where(Group.id == p.id)
            g_name = (await session.execute(g_stmt)).scalar_one_or_none()
            if g_name:
                handle = g_name

        result.append(
            {
                "id": str(p.id),
                "principal": handle,
                "display_name": p.display_name,
                "type": p.principal_type,
                "status": "active" if p.status == "ACTIVE" else "deactivated",
                "email": email,
                "role": role,
                "provider": provider,
            }
        )
    return result


async def provision_user(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    handle: str,
    display_name: str,
    email: str,
    password: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """Provision a new USER principal with object spine and user record."""
    norm_handle = normalize_handle(handle)
    dn = display_name.strip()
    if len(dn) < 1 or len(dn) > MAX_PRINCIPAL_NAME_LEN:
        msg = f"display_name must be between 1 and {MAX_PRINCIPAL_NAME_LEN} characters"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="display_name", message=msg)],
        )

    em = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+$", em):
        msg = f"Invalid email format: '{email}'"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="email", message=msg)],
        )

    canonical_key = f"@{norm_handle}"
    user_id = uuid.uuid4()

    try:
        # 1. Register in objects spine
        await session.execute(
            text(
                "SELECT register_object("
                "  'user'::object_kind, :ws_id, NULL, :ck, :title, :creator_id, :uid"
                ")"
            ),
            {
                "ws_id": workspace_id,
                "ck": canonical_key,
                "title": dn,
                "creator_id": creator_id,
                "uid": user_id,
            },
        )

        # 2. Insert into principals
        principal = Principal(
            id=user_id,
            principal_type="USER",
            workspace_id=workspace_id,
            status="ACTIVE",
            display_name=dn,
        )
        session.add(principal)
        await session.flush()

        # 3. Insert into users
        user = User(
            id=user_id,
            workspace_id=workspace_id,
            email=em,
        )
        session.add(user)
        await session.flush()

        # 4. Bind initial RBAC role
        target_role = role or "WORKSPACE_MEMBER"
        scope_type = "server" if target_role == "SERVER_ADMIN" else "workspace"
        role_binding = RoleBinding(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            principal_id=user_id,
            role=target_role,
            scope_type=scope_type,
        )
        session.add(role_binding)
        await session.flush()

        # 5. Provision local credentials if password provided
        if password:
            pepper = get_auth_pepper()
            pw_hash = hash_password_sync(password, pepper)
            await session.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
            await session.execute(
                text("SELECT kb_auth.local_admin_create(:pid, :username, :hash, 'pepper-v1')"),
                {"pid": user_id, "username": norm_handle, "hash": pw_hash},
            )
            await session.flush()

    except IntegrityError as exc:
        orig_msg = str(exc.orig) if exc.orig else str(exc)
        if "users_ws_email_uq" in orig_msg or "email" in orig_msg:
            msg = f"User with email '{em}' already exists in workspace"
            raise ProblemException(
                code="CONFLICT_IDENTIFIER",
                status=409,
                title="Conflict",
                detail=msg,
                errors=[FieldError(path="email", message=msg)],
            ) from exc
        if "canonical_key" in orig_msg or "objects" in orig_msg:
            msg = f"User with handle '{canonical_key}' already exists in workspace"
            raise ProblemException(
                code="CONFLICT_IDENTIFIER",
                status=409,
                title="Conflict",
                detail=msg,
                errors=[FieldError(path="handle", message=msg)],
            ) from exc
        raise

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.PRINCIPAL_PROVISIONED,
        payload={
            "id": str(user_id),
            "type": "USER",
            "handle": canonical_key,
            "display_name": dn,
            "email": em,
            "role": target_role,
        },
    )

    return {
        "id": str(user_id),
        "principal": canonical_key,
        "type": "USER",
        "handle": canonical_key,
        "display_name": dn,
        "email": em,
        "status": "active",
        "role": target_role,
        "provider": "LOCAL",
    }


async def reset_password(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    principal_id: uuid.UUID,
    password: str,
) -> dict[str, Any]:
    """Reset or initialize local password credential for a principal."""
    p_stmt = select(Principal).where(
        Principal.id == principal_id,
        Principal.workspace_id == workspace_id,
    )
    principal = (await session.execute(p_stmt)).scalar_one_or_none()
    if principal is None or principal.principal_type != "USER":
        not_found()

    pepper = get_auth_pepper()
    pw_hash = hash_password_sync(password, pepper)

    # Check if credential already exists
    cred_stmt = text("SELECT 1 FROM local_admin_credentials WHERE principal_id = :pid")
    exists = (await session.execute(cred_stmt, {"pid": principal_id})).scalar() is not None

    if exists:
        await session.execute(
            text("SELECT kb_auth.local_set_password_hash(:pid, :hash)"),
            {"pid": principal_id, "hash": pw_hash},
        )
    else:
        ck_stmt = select(ObjectRecord.canonical_key).where(
            ObjectRecord.id == principal_id,
            ObjectRecord.object_type == "user",
        )
        ck = (await session.execute(ck_stmt)).scalar_one_or_none()
        username = ck.lstrip("@") if ck else principal.display_name.lower().replace(" ", "")
        await session.execute(text("SET LOCAL app.is_setup_claim = 'true'"))
        await session.execute(
            text("SELECT kb_auth.local_admin_create(:pid, :username, :hash, 'pepper-v1')"),
            {"pid": principal_id, "username": username, "hash": pw_hash},
        )

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.PRINCIPAL_UPDATED,
        payload={"id": str(principal_id), "action": "password_reset"},
    )

    return {"status": "ok", "principal_id": str(principal_id)}


async def provision_group(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    name: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Provision a new GROUP principal."""
    grp_name = name.strip()
    if len(grp_name) < 1 or len(grp_name) > MAX_PRINCIPAL_NAME_LEN:
        msg = f"Group name must be between 1 and {MAX_PRINCIPAL_NAME_LEN} characters"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="name", message=msg)],
        )

    dn = (display_name or grp_name).strip()[:MAX_PRINCIPAL_NAME_LEN]
    group_id = uuid.uuid4()

    try:
        principal = Principal(
            id=group_id,
            principal_type="GROUP",
            workspace_id=workspace_id,
            status="ACTIVE",
            display_name=dn,
        )
        session.add(principal)
        await session.flush()

        group = Group(
            id=group_id,
            principal_type="GROUP",
            workspace_id=workspace_id,
            name=grp_name,
        )
        session.add(group)
        await session.flush()
    except IntegrityError as exc:
        orig_msg = str(exc.orig) if exc.orig else str(exc)
        if "groups_workspace_id_name_key" in orig_msg or "name" in orig_msg:
            msg = f"Group with name '{grp_name}' already exists in workspace"
            raise ProblemException(
                code="CONFLICT_IDENTIFIER",
                status=409,
                title="Conflict",
                detail=msg,
                errors=[FieldError(path="name", message=msg)],
            ) from exc
        raise

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.PRINCIPAL_PROVISIONED,
        payload={"id": str(group_id), "type": "GROUP", "name": grp_name, "display_name": dn},
    )

    return {
        "id": str(group_id),
        "principal": grp_name,
        "type": "GROUP",
        "display_name": dn,
        "status": "active",
        "member_count": 0,
    }


async def provision_agent(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    handle: str,
    display_name: str,
) -> dict[str, Any]:
    """Provision a new AGENT principal and definition."""
    norm_slug = normalize_handle(handle)
    dn = display_name.strip()
    if len(dn) < 1 or len(dn) > MAX_PRINCIPAL_NAME_LEN:
        msg = f"display_name must be between 1 and {MAX_PRINCIPAL_NAME_LEN} characters"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="display_name", message=msg)],
        )

    agent_pid = uuid.uuid4()
    try:
        principal = Principal(
            id=agent_pid,
            principal_type="AGENT",
            workspace_id=workspace_id,
            status="ACTIVE",
            display_name=dn,
        )
        session.add(principal)
        await session.flush()

        agent_def = AgentDefinition(
            workspace_id=workspace_id,
            principal_id=agent_pid,
            slug=norm_slug,
            display_name=dn,
            harness_kind="cli_pipe",
            cli_binary_allowlist_id="agy",
            cli_args_json=[],
        )
        session.add(agent_def)
        await session.flush()
    except IntegrityError as exc:
        orig_msg = str(exc.orig) if exc.orig else str(exc)
        if "agent_definitions_workspace_id_slug_key" in orig_msg or "slug" in orig_msg:
            msg = f"Agent with slug '{norm_slug}' already exists in workspace"
            raise ProblemException(
                code="CONFLICT_IDENTIFIER",
                status=409,
                title="Conflict",
                detail=msg,
                errors=[FieldError(path="handle", message=msg)],
            ) from exc
        raise

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=creator_id,
        event_type=ActivityEventType.PRINCIPAL_PROVISIONED,
        payload={"id": str(agent_pid), "type": "AGENT", "slug": norm_slug, "display_name": dn},
    )

    return {
        "id": str(agent_pid),
        "principal": f"@{norm_slug}",
        "type": "AGENT",
        "slug": norm_slug,
        "display_name": dn,
        "status": "active",
    }


async def update_principal(  # noqa: PLR0913
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    principal_id: uuid.UUID,
    *,
    status: str | None = None,
    display_name: str | None = None,
) -> dict[str, Any]:
    """Update principal status (active/deactivated) or display_name with lockout checks."""
    stmt = (
        select(Principal)
        .where(
            Principal.id == principal_id,
            Principal.workspace_id == workspace_id,
            Principal.principal_type != "SCRIPT_EPHEMERAL",
        )
        .with_for_update()
    )
    principal = (await session.execute(stmt)).scalar_one_or_none()
    if principal is None:
        not_found()

    if display_name is not None:
        dn = display_name.strip()
        if len(dn) < 1 or len(dn) > MAX_PRINCIPAL_NAME_LEN:
            msg = f"display_name must be between 1 and {MAX_PRINCIPAL_NAME_LEN} characters"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="display_name", message=msg)],
            )
        principal.display_name = dn
        await record_activity(
            session,
            workspace_id=workspace_id,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.PRINCIPAL_UPDATED,
            payload={"id": str(principal_id), "display_name": dn},
        )

    if status is not None:
        st = status.strip().lower()
        if st in ("deactivated", "disabled"):
            if principal.status == "ACTIVE":
                # Anti-lockout: verify we are not deactivating the last active SERVER_ADMIN
                admin_count = (
                    await session.execute(
                        text(
                            "SELECT count(DISTINCT rb.principal_id) "
                            "FROM role_bindings rb "
                            "JOIN principals p ON p.id = rb.principal_id "
                            "WHERE rb.role = 'SERVER_ADMIN' "
                            "  AND p.status = 'ACTIVE' "
                            "  AND p.id != :target_id"
                        ),
                        {"target_id": principal_id},
                    )
                ).scalar_one()

                # Does the principal hold SERVER_ADMIN?
                holds_server_admin = (
                    await session.execute(
                        select(func.count(RoleBinding.id)).where(
                            RoleBinding.principal_id == principal_id,
                            RoleBinding.role == RbacRole.SERVER_ADMIN,
                        )
                    )
                ).scalar_one() > 0

                if holds_server_admin and admin_count == 0:
                    raise LockoutPreventedError(
                        layer="db_trigger",
                        detail="Cannot deactivate the last active SERVER_ADMIN.",
                    ).to_problem_exception()

                principal.status = "DISABLED"

                # Synchronously revoke user sessions
                await session.execute(
                    text("SELECT kb_auth.session_revoke_all_for_principal(:p_id)"),
                    {"p_id": principal_id},
                )

                # Synchronously revoke MCP API keys
                await session.execute(
                    update(McpApiKey)
                    .where(
                        McpApiKey.principal_id == principal_id,
                        McpApiKey.revoked_at.is_(None),
                    )
                    .values(revoked_at=func.clock_timestamp())
                )

                await record_activity(
                    session,
                    workspace_id=workspace_id,
                    actor_principal_id=actor_id,
                    event_type=ActivityEventType.PRINCIPAL_DEACTIVATED,
                    payload={"id": str(principal_id), "status": "deactivated"},
                )

        elif st == "active":
            if principal.status == "DISABLED":
                principal.status = "ACTIVE"
                await record_activity(
                    session,
                    workspace_id=workspace_id,
                    actor_principal_id=actor_id,
                    event_type=ActivityEventType.PRINCIPAL_REACTIVATED,
                    payload={"id": str(principal_id), "status": "active"},
                )
        else:
            msg = f"Invalid status '{status}'. Must be active or deactivated"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="status", message=msg)],
            )

    await session.flush()
    return await get_principal_detail(session, workspace_id, str(principal_id))


async def add_group_member(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    group_id: uuid.UUID,
    member_id: uuid.UUID,
) -> dict[str, Any]:
    """Add a principal (user, group, agent) to a group, enforcing depth and cycle guards."""
    if group_id == member_id:
        msg = "A group cannot be a member of itself"
        raise ProblemException(
            code="GROUP_CYCLE_REJECTED",
            status=409,
            title="Group Cycle Rejected",
            detail=msg,
            type_uri="urn:kanban:problem:group-cycle-rejected",
        )

    # Verify group exists and is GROUP
    grp = (
        await session.execute(
            select(Group).where(Group.id == group_id, Group.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if grp is None:
        not_found()

    # Verify member exists in workspace
    mbr = (
        await session.execute(
            select(Principal).where(
                Principal.id == member_id,
                Principal.workspace_id == workspace_id,
                Principal.principal_type != "SCRIPT_EPHEMERAL",
            )
        )
    ).scalar_one_or_none()
    if mbr is None:
        not_found()

    try:
        edge = PrincipalGroupEdge(
            group_id=group_id,
            member_id=member_id,
            workspace_id=workspace_id,
        )
        session.add(edge)
        await session.flush()
    except (DBAPIError, IntegrityError) as exc:
        msg_str = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
        if "GROUP_CYCLE_REJECTED" in msg_str:
            raise ProblemException(
                code="GROUP_CYCLE_REJECTED",
                status=409,
                title="Group Cycle Rejected",
                detail="Adding member would introduce a cyclic group dependency.",
                type_uri="urn:kanban:problem:group-cycle-rejected",
            ) from exc
        if "GROUP_DEPTH_EXCEEDED" in msg_str:
            raise ProblemException(
                code="GROUP_DEPTH_EXCEEDED",
                status=422,
                title="Group Depth Exceeded",
                detail="Group nesting depth cannot exceed 8 levels.",
                type_uri="urn:kanban:problem:group-depth-exceeded",
            ) from exc
        if "already exists" in msg_str or "duplicate key" in msg_str:
            # Already a member - idempotent
            return {"status": "ok", "group_id": str(group_id), "member_id": str(member_id)}
        raise

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=actor_id,
        event_type=ActivityEventType.GROUP_MEMBER_ADDED,
        payload={"group_id": str(group_id), "member_id": str(member_id)},
    )
    return {"status": "member_added", "group_id": str(group_id), "member_id": str(member_id)}


async def remove_group_member(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    group_id: uuid.UUID,
    member_id: uuid.UUID,
) -> dict[str, Any]:
    """Remove a principal from a group."""
    del_stmt = delete(PrincipalGroupEdge).where(
        PrincipalGroupEdge.group_id == group_id,
        PrincipalGroupEdge.member_id == member_id,
        PrincipalGroupEdge.workspace_id == workspace_id,
    )
    res = await session.execute(del_stmt)
    await session.flush()

    if res.rowcount and res.rowcount > 0:
        await record_activity(
            session,
            workspace_id=workspace_id,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.GROUP_MEMBER_REMOVED,
            payload={"group_id": str(group_id), "member_id": str(member_id)},
        )
    return {"status": "member_removed", "group_id": str(group_id), "member_id": str(member_id)}


async def bind_role(  # noqa: C901, PLR0912, PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    principal_id: uuid.UUID,
    role_name: str,
    scope_type: str,
    project_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Bind an RBAC role to a principal at server, workspace, or project scope."""
    # Validate principal
    p_stmt = select(Principal).where(
        Principal.id == principal_id,
        Principal.workspace_id == workspace_id,
        Principal.principal_type != "SCRIPT_EPHEMERAL",
    )
    principal = (await session.execute(p_stmt)).scalar_one_or_none()
    if principal is None:
        not_found()

    st = scope_type.strip().lower()
    if st not in ("server", "workspace", "project"):
        msg = f"Invalid scope_type '{scope_type}'. Must be server, workspace, or project"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="scope_type", message=msg)],
        )

    norm_role = role_name.strip().upper()
    try:
        rbac_role = RbacRole[norm_role]
    except KeyError as exc:
        msg = f"Invalid role '{role_name}'. Allowed roles: {[r.name for r in RbacRole]}"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="role", message=msg)],
        ) from exc

    # Enforce scope and role constraints
    if st == "server":
        if rbac_role != RbacRole.SERVER_ADMIN or project_id is not None:
            msg = "server scope only allows SERVER_ADMIN and project_id must be null"
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="role", message=msg)],
            )
    elif st == "workspace":
        if (
            rbac_role
            not in (
                RbacRole.WORKSPACE_ADMIN,
                RbacRole.WORKSPACE_MEMBER,
                RbacRole.WORKSPACE_GUEST,
            )
            or project_id is not None
        ):
            msg = (
                "workspace scope requires WORKSPACE_ADMIN, WORKSPACE_MEMBER, "
                "or WORKSPACE_GUEST with null project_id"
            )
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail=msg,
                errors=[FieldError(path="role", message=msg)],
            )
    elif st == "project" and (
        project_id is None
        or rbac_role
        not in (
            RbacRole.PROJECT_ADMIN,
            RbacRole.MEMBER,
            RbacRole.VIEWER,
        )
    ):
        msg = "project scope requires project_id and role PROJECT_ADMIN, MEMBER, or VIEWER"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="project_id", message=msg)],
        )

    # Block non-SERVER_ADMIN from granting SERVER_ADMIN role
    if rbac_role == RbacRole.SERVER_ADMIN:
        admin_check = await session.execute(
            text("SELECT app_principal_has_role(NULL, ARRAY['SERVER_ADMIN'])")
        )
        is_sa = bool(admin_check.scalar())
        if not is_sa:
            actor_check = await session.execute(
                select(RoleBinding).where(
                    RoleBinding.principal_id == actor_id,
                    RoleBinding.role == RbacRole.SERVER_ADMIN,
                )
            )
            is_sa = actor_check.scalar_one_or_none() is not None
        if not is_sa:
            raise ProblemException(
                code="INSUFFICIENT_CAPABILITY",
                status=403,
                title="Insufficient Capability",
                detail="Only SERVER_ADMIN can grant SERVER_ADMIN role.",
            )

    # Check project exists in workspace if project scope
    if project_id is not None:
        prj_stmt = select(Project).where(
            Project.id == project_id, Project.workspace_id == workspace_id
        )
        if (await session.execute(prj_stmt)).scalar_one_or_none() is None:
            not_found()

    # Check for existing binding
    existing_stmt = select(RoleBinding).where(
        RoleBinding.workspace_id == workspace_id,
        RoleBinding.principal_id == principal_id,
        RoleBinding.role == rbac_role,
        RoleBinding.scope_type == st,
        RoleBinding.project_id == project_id,
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        return {
            "status": "already_bound",
            "principal_id": str(principal_id),
            "role": norm_role,
            "scope": st,
        }

    binding = RoleBinding(
        workspace_id=workspace_id,
        principal_id=principal_id,
        role=rbac_role,
        scope_type=st,
        project_id=project_id,
    )
    session.add(binding)
    await session.flush()

    await record_activity(
        session,
        workspace_id=workspace_id,
        actor_principal_id=actor_id,
        event_type=ActivityEventType.ROLE_BOUND,
        payload={
            "principal_id": str(principal_id),
            "role": norm_role,
            "scope_type": st,
            "project_id": str(project_id) if project_id else None,
        },
    )

    return {
        "status": "role_bound",
        "principal_id": str(principal_id),
        "role": norm_role,
        "scope": st,
        "project_id": str(project_id) if project_id else None,
    }


async def unbind_role(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID,
    principal_id: uuid.UUID,
    role_name: str,
    scope_type: str,
    project_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Unbind an RBAC role from a principal with anti-lockout protection."""
    norm_role = role_name.strip().upper()
    try:
        rbac_role = RbacRole[norm_role]
    except KeyError as exc:
        msg = f"Invalid role '{role_name}'"
        raise ProblemException(
            code="VALIDATION_FAILED",
            status=422,
            title="Validation Failed",
            detail=msg,
            errors=[FieldError(path="role", message=msg)],
        ) from exc

    st = scope_type.strip().lower()

    # Anti-lockout: verify we are not unbinding the last SERVER_ADMIN
    if rbac_role == RbacRole.SERVER_ADMIN and st == "server":
        admin_count = (
            await session.execute(
                text(
                    "SELECT count(DISTINCT rb.principal_id) "
                    "FROM role_bindings rb "
                    "JOIN principals p ON p.id = rb.principal_id "
                    "WHERE rb.role = 'SERVER_ADMIN' "
                    "  AND p.status = 'ACTIVE' "
                    "  AND (p.id != :target_id OR rb.scope_type != 'server')"
                ),
                {"target_id": principal_id},
            )
        ).scalar_one()
        if admin_count == 0:
            raise LockoutPreventedError(
                layer="db_trigger",
                detail="Cannot unbind the last active SERVER_ADMIN role binding.",
            ).to_problem_exception()

    stmt = delete(RoleBinding).where(
        RoleBinding.workspace_id == workspace_id,
        RoleBinding.principal_id == principal_id,
        RoleBinding.role == rbac_role,
        RoleBinding.scope_type == st,
        RoleBinding.project_id == project_id,
    )
    res = await session.execute(stmt)
    await session.flush()

    if res.rowcount and res.rowcount > 0:
        await record_activity(
            session,
            workspace_id=workspace_id,
            actor_principal_id=actor_id,
            event_type=ActivityEventType.ROLE_UNBOUND,
            payload={
                "principal_id": str(principal_id),
                "role": norm_role,
                "scope_type": st,
                "project_id": str(project_id) if project_id else None,
            },
        )

    return {
        "status": "role_unbound",
        "principal_id": str(principal_id),
        "role": norm_role,
        "scope": st,
    }
