# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""LDAP group synchronization into workspace groups and closure (S3.1, KB-P2-07)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import delete, select

from database.models.principals import Group, Principal, PrincipalGroupEdge
from kanban.auth.ldap.escape import normalize_dn

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["sync_ldap_groups"]


async def _reconcile_group_nesting_edges(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    group_parent_map: Mapping[str, Sequence[str]],
    canonical_map: dict[str, str],
    group_by_name: dict[str, Group],
) -> None:
    """Reconcile inter-group parent-child nesting edges in principal_group_edges."""
    for child_raw_dn, parent_raw_dns in group_parent_map.items():
        norm_c = normalize_dn(child_raw_dn)
        if norm_c not in canonical_map:
            continue
        c_name = canonical_map[norm_c]
        c_grp = group_by_name.get(c_name)
        if not c_grp:
            continue
        for p_raw_dn in parent_raw_dns:
            norm_p = normalize_dn(p_raw_dn)
            if norm_p not in canonical_map:
                continue
            p_name = canonical_map[norm_p]
            p_grp = group_by_name.get(p_name)
            if not p_grp or p_grp.id == c_grp.id:
                continue
            chk_stmt = select(PrincipalGroupEdge.group_id).where(
                PrincipalGroupEdge.workspace_id == workspace_id,
                PrincipalGroupEdge.member_id == c_grp.id,
                PrincipalGroupEdge.group_id == p_grp.id,
            )
            chk_res = await session.execute(chk_stmt)
            if chk_res.scalar_one_or_none() is None:
                session.add(
                    PrincipalGroupEdge(
                        member_id=c_grp.id,
                        group_id=p_grp.id,
                        workspace_id=workspace_id,
                    )
                )


async def sync_ldap_groups(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    workspace_id: uuid.UUID,
    principal_id: uuid.UUID,
    raw_group_dns: Sequence[str],
    group_dn_map: dict[str, str],
    group_parent_map: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Synchronize user memberships for LDAP mapped groups.

    Normalizes all group DNs and mapping keys per RFC 4514, ensures mapped groups exist,
    adds newly asserted group edges, and removes revoked edges for mapped groups,
    leaving unmapped or non-LDAP group memberships untouched.
    """
    if not group_dn_map:
        return []

    # 1. Canonicalize mapping keys (lowercase normalized RFC 4514 DN -> group name)
    canonical_map: dict[str, str] = {}
    dn_by_group_name: dict[str, str] = {}
    for raw_dn, target_group_name in group_dn_map.items():
        norm_map_dn = normalize_dn(raw_dn)
        clean_name = target_group_name.strip()
        if norm_map_dn and clean_name:
            canonical_map[norm_map_dn] = clean_name
            dn_by_group_name[clean_name] = norm_map_dn

    if not canonical_map:
        return []

    # 2. Normalize raw group DNs asserted by directory
    user_norm_dns = {normalize_dn(d) for d in raw_group_dns if d.strip()}

    # 3. Determine matched desired group names
    desired_group_names = {
        canonical_map[norm_dn] for norm_dn in user_norm_dns if norm_dn in canonical_map
    }

    all_target_names = set(canonical_map.values())

    # 4. Fetch existing groups in this workspace matching target names
    stmt = select(Group).where(
        Group.workspace_id == workspace_id,
        Group.name.in_(all_target_names),
    )
    res = await session.execute(stmt)
    existing_groups = list(res.scalars().all())
    group_by_name: dict[str, Group] = {g.name: g for g in existing_groups}

    # 5. Provision missing groups
    for name in all_target_names:
        if name not in group_by_name:
            new_id = uuid4()
            principal = Principal(
                id=new_id,
                principal_type="GROUP",
                workspace_id=workspace_id,
                status="ACTIVE",
                display_name=name,
            )
            session.add(principal)
            await session.flush()

            group = Group(
                id=new_id,
                principal_type="GROUP",
                workspace_id=workspace_id,
                name=name,
                external_source="LDAP",
                external_id=dn_by_group_name.get(name),
            )
            session.add(group)
            await session.flush()
            group_by_name[name] = group

    all_card_group_ids = {group_by_name[name].id for name in all_target_names}
    desired_group_ids = {group_by_name[name].id for name in desired_group_names}

    # 6. Query existing edges for this principal among card-managed groups
    edge_stmt = select(PrincipalGroupEdge.group_id).where(
        PrincipalGroupEdge.workspace_id == workspace_id,
        PrincipalGroupEdge.member_id == principal_id,
        PrincipalGroupEdge.group_id.in_(all_card_group_ids),
    )
    edge_res = await session.execute(edge_stmt)
    current_edge_group_ids = set(edge_res.scalars().all())

    # 7. Reconcile differences
    to_add = desired_group_ids - current_edge_group_ids
    to_remove = current_edge_group_ids - desired_group_ids

    for gid in to_add:
        session.add(
            PrincipalGroupEdge(
                member_id=principal_id,
                group_id=gid,
                workspace_id=workspace_id,
            )
        )

    if to_remove:
        del_stmt = delete(PrincipalGroupEdge).where(
            PrincipalGroupEdge.workspace_id == workspace_id,
            PrincipalGroupEdge.member_id == principal_id,
            PrincipalGroupEdge.group_id.in_(to_remove),
        )
        await session.execute(del_stmt)

    # 8. Reconcile inter-group nesting edges if group_parent_map provided
    if group_parent_map:
        await _reconcile_group_nesting_edges(
            session,
            workspace_id,
            group_parent_map,
            canonical_map,
            group_by_name,
        )

    await session.flush()

    return sorted(desired_group_names)
