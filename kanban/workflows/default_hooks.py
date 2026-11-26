# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0912, PLR0915, TC003
"""Default workflow hook template materialization and inheritance helpers."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from database.models.agent_definition import AgentDefinition
from database.models.projects import WorkflowState
from database.models.workflow import DefaultWorkflowHook, WorkflowTransitionHook
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def materialize_default_workflow_hooks(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    skip_existing: bool = True,
) -> list[WorkflowTransitionHook]:
    """Copy enabled default workflow hook templates into a project (copy-on-create inheritance).

    Workspace-scoped templates override system-scoped templates of the same name (case-insensitive).
    Resolves to_state_name and optional from_state_name against the project's workflow states.
    Resolves agent_slug within workspace_id if agent_definition_id is not set.
    """
    # 1. Fetch enabled default templates for system and this workspace
    tpl_stmt = (
        select(DefaultWorkflowHook)
        .where(
            DefaultWorkflowHook.is_enabled.is_(True),
            (DefaultWorkflowHook.scope_kind == "system")
            | (
                (DefaultWorkflowHook.scope_kind == "workspace")
                & (DefaultWorkflowHook.workspace_id == workspace_id)
            ),
        )
        .order_by(DefaultWorkflowHook.sort_rank.asc(), DefaultWorkflowHook.created_at.asc())
    )
    templates = list((await session.execute(tpl_stmt)).scalars().all())
    if not templates:
        return []

    # 2. Workspace templates override system templates of the same name.casefold()
    tpl_map: dict[str, DefaultWorkflowHook] = {}
    for tpl in templates:
        if tpl.scope_kind == "system":
            tpl_map[tpl.name.strip().casefold()] = tpl
    for tpl in templates:
        if tpl.scope_kind == "workspace":
            tpl_map[tpl.name.strip().casefold()] = tpl

    active_templates = sorted(tpl_map.values(), key=lambda t: t.sort_rank)

    # 3. Fetch workflow states for this project
    st_stmt = select(WorkflowState.id, WorkflowState.name).where(
        WorkflowState.project_id == project_id
    )
    states = (await session.execute(st_stmt)).all()
    state_map = {name.strip().casefold(): s_id for s_id, name in states}

    # 4. Fetch existing hooks in project to avoid duplicate names if skip_existing
    existing_names: set[str] = set()
    if skip_existing:
        hook_stmt = select(WorkflowTransitionHook.name).where(
            WorkflowTransitionHook.project_id == project_id
        )
        existing_names = {
            name.strip().casefold() for name in (await session.execute(hook_stmt)).scalars().all()
        }

    created_hooks: list[WorkflowTransitionHook] = []
    for tpl in active_templates:
        clean_name = tpl.name.strip()
        if skip_existing and clean_name.casefold() in existing_names:
            continue

        to_key = tpl.to_state_name.strip().casefold()
        if to_key not in state_map:
            logger.warning(
                "Default hook template '%s' target state '%s' not found in project %s; skipping.",
                tpl.name,
                tpl.to_state_name,
                project_id,
            )
            continue
        to_id = state_map[to_key]

        from_id: uuid.UUID | None = None
        if tpl.from_state_name and tpl.from_state_name.strip() not in ("", "*"):
            from_key = tpl.from_state_name.strip().casefold()
            if from_key not in state_map:
                logger.warning(
                    "Default hook template '%s' from state '%s' not found in project %s; skipping.",
                    tpl.name,
                    tpl.from_state_name,
                    project_id,
                )
                continue
            from_id = state_map[from_key]

        # Resolve hook kind
        resolved_kind: str
        if tpl.hook_kind in ("agent_async", "agent_interceptor"):
            resolved_kind = "agent_interceptor"
        elif tpl.hook_kind in ("wasm_sync", "wasm_validator", "sync_validator", "sync_mutator"):
            resolved_kind = "sync_mutator" if tpl.allowed_mutable_fields else "sync_validator"
        else:
            resolved_kind = "agent_interceptor" if "agent" in tpl.hook_kind else "sync_validator"

        # Resolve agent if needed
        agent_def_id = tpl.agent_definition_id
        if agent_def_id is None and tpl.agent_slug:
            clean_slug = tpl.agent_slug.strip().lstrip("@")
            agent_stmt = select(AgentDefinition.id).where(
                AgentDefinition.workspace_id == workspace_id,
                AgentDefinition.slug == clean_slug,
            )
            agent_def_id = (await session.execute(agent_stmt)).scalar_one_or_none()
            if agent_def_id is None:
                logger.warning(
                    "Default hook template '%s' requires agent slug '%s', "
                    "not found in workspace %s; skipping gracefully.",
                    tpl.name,
                    clean_slug,
                    workspace_id,
                )
                continue

        if resolved_kind == "agent_interceptor" and agent_def_id is None:
            logger.warning(
                "Default hook template '%s' is agent_interceptor but lacks agent_definition; "
                "skipping.",
                tpl.name,
            )
            continue

        wasm_sha = tpl.wasm_module_sha256
        if resolved_kind in ("sync_validator", "sync_mutator") and wasm_sha is None:
            logger.warning(
                "Default hook template '%s' is sync wasm hook but lacks wasm_module_sha256; "
                "skipping.",
                tpl.name,
            )
            continue

        clean_fields = list(tpl.allowed_mutable_fields)

        manifest_sha = compute_hook_manifest_sha256(
            from_state_id=from_id,
            to_state_id=to_id,
            hook_kind=resolved_kind,
            wasm_module_sha256=wasm_sha,
            agent_definition_id=agent_def_id,
            allowed_mutable_fields=clean_fields,
            failure_policy=tpl.failure_policy,
        )

        sort_rank = f"{tpl.sort_rank:016d}"

        hook = WorkflowTransitionHook(
            workspace_id=workspace_id,
            project_id=project_id,
            name=clean_name,
            from_state_id=from_id,
            to_state_id=to_id,
            hook_kind=resolved_kind,
            sort_rank=sort_rank,
            is_enabled=tpl.is_enabled,
            wasm_module_sha256=wasm_sha,
            agent_definition_id=agent_def_id,
            allowed_mutable_fields=clean_fields,
            failure_policy=tpl.failure_policy,
            manifest_sha256=manifest_sha,
            timeout_ms=tpl.timeout_ms,
            max_rework_attempts=tpl.max_rework_attempts,
            inherited_from_template_id=tpl.id,
        )
        session.add(hook)
        created_hooks.append(hook)
        existing_names.add(clean_name.casefold())

    if created_hooks:
        await session.flush()

    return created_hooks
