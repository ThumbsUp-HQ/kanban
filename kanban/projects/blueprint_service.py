# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Declarative project blueprint engine (S11.4, S7.2, S12.2, KB-P4-10).

Provides declarative plan and apply capabilities for project configurations
including workflow states, custom priorities, labels, modules, WIP limits,
and lifecycle settings.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import delete, func, select, text, update

from database.models import (
    Issue,
    Module,
    ObjectRecord,
    Project,
    ProjectLabel,
    ProjectModuleDefault,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.problems import ProblemException
from kanban.api.v1.schemas.project_config import (
    EXCLUSIVE_GROUP_PATTERN,
    HEX_COLOR_PATTERN,
    MAX_EMOJI_LENGTH,
)
from kanban.security.permissions import Capability, require_capability
from kanban.services.activity import ActivityEventType, record_activity
from kanban.services.projects import (
    _require_project_creator,
    get_project_or_404,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

IDENTIFIER_PATTERN: Final[str] = r"^[A-Z][A-Z0-9]{1,9}$"
MAX_STATES: Final[int] = 30
MAX_PRIORITIES: Final[int] = 10
MAX_LABELS: Final[int] = 200
MAX_MODULES: Final[int] = 100
MAX_DESC_BYTES: Final[int] = 524288

StateGroupName = Literal["backlog", "unstarted", "started", "completed", "cancelled"]


class BlueprintState(BaseModel):
    """Declarative workflow state in a project blueprint."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    group: StateGroupName
    color: str = Field(pattern=HEX_COLOR_PATTERN)
    sort_order: int = 0
    is_default: bool = False
    wip_soft_limit: int | None = Field(default=None, ge=1, le=999)
    wip_hard_limit: int | None = Field(default=None, ge=1, le=999)

    @model_validator(mode="after")
    def _validate_wip(self) -> BlueprintState:
        if (
            self.wip_soft_limit is not None
            and self.wip_hard_limit is not None
            and self.wip_soft_limit > self.wip_hard_limit
        ):
            raise ProblemException(
                code="VALIDATION_FAILED",
                status=422,
                title="Validation Failed",
                detail="wip_soft_limit must be <= wip_hard_limit",
            )
        return self


class BlueprintPriority(BaseModel):
    """Declarative priority level in a project blueprint."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    emoji: str | None = Field(default="", max_length=MAX_EMOJI_LENGTH)
    color: str = Field(default="#64748B", pattern=HEX_COLOR_PATTERN)
    sort_order: int = 0
    is_default: bool = False


class BlueprintLabel(BaseModel):
    """Declarative categorization label in a project blueprint."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    exclusive_group: str | None = Field(default=None, pattern=EXCLUSIVE_GROUP_PATTERN)
    color: str = Field(default="#64748B", pattern=HEX_COLOR_PATTERN)


class BlueprintModule(BaseModel):
    """Declarative module in a project blueprint."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class ProjectBlueprint(BaseModel):
    """Declarative specification of a project configuration."""

    model_config = ConfigDict(extra="forbid")

    identifier: str = Field(pattern=IDENTIFIER_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description_markdown: str = Field(default="", max_length=MAX_DESC_BYTES)
    states: list[BlueprintState] = Field(default_factory=list, max_length=MAX_STATES)
    state_migrations: dict[str, str] = Field(default_factory=dict)
    priorities: list[BlueprintPriority] = Field(default_factory=list, max_length=MAX_PRIORITIES)
    labels: list[BlueprintLabel] = Field(default_factory=list, max_length=MAX_LABELS)
    modules_enabled: bool = False
    modules: list[BlueprintModule] = Field(default_factory=list, max_length=MAX_MODULES)
    default_modules: list[str] = Field(default_factory=list)
    auto_archive_days: int | None = Field(default=None, ge=1, le=365)
    wip_limits: dict[str, dict[str, int]] = Field(default_factory=dict)

    @field_validator("modules", mode="before")
    @classmethod
    def _coerce_modules(cls, val: object) -> object:
        if isinstance(val, list):
            res: list[object] = []
            for item in val:
                if isinstance(item, str):
                    res.append({"name": item})
                else:
                    res.append(item)
            return res
        return val

    @model_validator(mode="after")
    def _validate_blueprint_integrity(self) -> ProjectBlueprint:
        if self.states:
            has_started = any(s.group == "started" for s in self.states)
            has_completed = any(s.group == "completed" for s in self.states)
            if not has_started or not has_completed:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=422,
                    title="Validation Failed",
                    detail="Project must keep at least 1 state in 'started' and 1 in 'completed'",
                )

        # Validate wip_limits
        for state_name, limits in self.wip_limits.items():
            soft = limits.get("soft")
            hard = limits.get("hard")
            if soft is not None and hard is not None and soft > hard:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=422,
                    title="Validation Failed",
                    detail=f"WIP soft limit must be <= hard limit for state '{state_name}'",
                )
        return self


def _canonical_plan_hash(project_ident: str, changes: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash of canonical JSON plan."""
    payload = {
        "changes": changes,
        "project": project_ident,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _slugify_priority(name: str) -> str:
    """Generate safe lowercase ASCII slug for priority label."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.lower().strip()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"pri-{slug}" if slug else "pri"
    return slug[:32]


async def compute_plan(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    blueprint: ProjectBlueprint,
) -> tuple[dict[str, Any], str]:
    """Calculate the declarative diff against the current project configuration."""
    # Look for existing project in caller's workspace
    stmt = select(Project).where(
        Project.workspace_id == caller.workspace_id,
        Project.identifier == blueprint.identifier,
    )
    project = (await session.execute(stmt)).scalar_one_or_none()

    changes: dict[str, Any] = {}

    if project is None:
        # Caller must hold project creation privilege
        await _require_project_creator(session, caller)

        # New project plan
        changes["project"] = {
            "create": True,
            "identifier": blueprint.identifier,
            "name": blueprint.name,
        }

        if blueprint.states:
            changes["states"] = {"create": [s.name for s in blueprint.states]}

        if blueprint.priorities:
            changes["priorities"] = {"create": [p.name for p in blueprint.priorities]}

        if blueprint.labels:
            changes["labels"] = {"create": [lbl.name for lbl in blueprint.labels]}

        if blueprint.modules_enabled:
            changes["modules_enabled"] = {"from": False, "to": True}

        if blueprint.modules:
            changes["modules"] = {"create": [m.name for m in blueprint.modules]}

        if blueprint.default_modules:
            changes["default_modules"] = {"create": list(blueprint.default_modules)}

        if blueprint.auto_archive_days is not None:
            changes["auto_archive_days"] = {"from": None, "to": blueprint.auto_archive_days}

        if blueprint.wip_limits:
            changes["wip_limits"] = {"create": blueprint.wip_limits}

        plan_sha256 = _canonical_plan_hash(blueprint.identifier, changes)
        return changes, plan_sha256

    # Existing project: verify ADMIN capability
    await require_capability(session, caller, project.id, Capability.ADMIN)

    # 1. Project level metadata
    if blueprint.name != project.name:
        changes["name"] = {"from": project.name, "to": blueprint.name}

    if blueprint.auto_archive_days != project.auto_archive_days:
        changes["auto_archive_days"] = {
            "from": project.auto_archive_days,
            "to": blueprint.auto_archive_days,
        }

    if blueprint.modules_enabled != project.modules_enabled:
        changes["modules_enabled"] = {
            "from": project.modules_enabled,
            "to": blueprint.modules_enabled,
        }

    # 2. Workflow states
    states_stmt = (
        select(WorkflowState)
        .where(WorkflowState.project_id == project.id)
        .order_by(WorkflowState.sort_order, WorkflowState.name)
    )
    curr_states = list((await session.execute(states_stmt)).scalars().all())
    curr_state_map = {s.name: s for s in curr_states}
    target_state_names = {s.name for s in blueprint.states}

    states_to_create = [s.name for s in blueprint.states if s.name not in curr_state_map]
    states_to_remove = [s.name for s in curr_states if s.name not in target_state_names]

    # In-use check for removed states
    for state_name in states_to_remove:
        state_obj = curr_state_map[state_name]
        issue_cnt_query = (
            select(func.count(Issue.id))
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .where(
                Issue.state_id == state_obj.id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
        issue_cnt = (await session.execute(issue_cnt_query)).scalar_one()
        if issue_cnt > 0:
            if state_name not in blueprint.state_migrations:
                raise ProblemException(
                    code="STATE_IN_USE",
                    status=409,
                    title="State In Use",
                    detail=(
                        f"State '{state_name}' has {issue_cnt} active issues and requires "
                        "a state migration. Specify state_migrations: "
                        f"{{'{state_name}': '<New State>'}}"
                    ),
                )
            target_mig_state = blueprint.state_migrations[state_name]
            if target_mig_state not in target_state_names:
                raise ProblemException(
                    code="VALIDATION_FAILED",
                    status=422,
                    title="Validation Failed",
                    detail=(
                        f"Migration target state '{target_mig_state}' for '{state_name}' "
                        "does not exist in target blueprint states"
                    ),
                )

    # Check for state updates
    states_to_update: list[str] = []
    for s in blueprint.states:
        if s.name in curr_state_map:
            curr = curr_state_map[s.name]
            wip_override = blueprint.wip_limits.get(s.name, {})
            expected_soft = wip_override.get("soft", s.wip_soft_limit)
            expected_hard = wip_override.get("hard", s.wip_hard_limit)
            if (
                curr.state_group != s.group
                or curr.color_hex != s.color
                or curr.wip_soft_limit != expected_soft
                or curr.wip_hard_limit != expected_hard
            ):
                states_to_update.append(s.name)

    if states_to_create or states_to_remove or states_to_update:
        st_change: dict[str, Any] = {}
        if states_to_create:
            st_change["create"] = states_to_create
        if states_to_update:
            st_change["update"] = states_to_update
        if states_to_remove:
            st_change["remove"] = states_to_remove
            mig_subset = {
                k: v for k, v in blueprint.state_migrations.items() if k in states_to_remove
            }
            if mig_subset:
                st_change["migrate"] = mig_subset
        changes["states"] = st_change

    # 3. Priorities
    pri_stmt = (
        select(ProjectPriority)
        .where(ProjectPriority.project_id == project.id)
        .order_by(ProjectPriority.sort_order)
    )
    curr_pris = list((await session.execute(pri_stmt)).scalars().all())
    curr_pri_map = {p.label: p for p in curr_pris}
    target_pri_names = {p.name for p in blueprint.priorities}

    pri_to_create = [p.name for p in blueprint.priorities if p.name not in curr_pri_map]
    pri_to_remove = [p.label for p in curr_pris if p.label not in target_pri_names]

    # In-use check for removed priorities
    for pri_name in pri_to_remove:
        pri_obj = curr_pri_map[pri_name]
        issue_cnt_query = (
            select(func.count(Issue.id))
            .join(ObjectRecord, ObjectRecord.id == Issue.id)
            .where(
                Issue.project_id == project.id,
                Issue.priority_id == pri_obj.id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
        issue_cnt = (await session.execute(issue_cnt_query)).scalar_one()
        if issue_cnt > 0:
            raise ProblemException(
                code="PRIORITY_IN_USE",
                status=409,
                title="Priority In Use",
                detail=f"Priority '{pri_name}' is in use by {issue_cnt} issues",
            )

    pri_to_update: list[str] = []
    for bp_pri_item in blueprint.priorities:
        if bp_pri_item.name in curr_pri_map:
            curr_item = curr_pri_map[bp_pri_item.name]
            if (curr_item.emoji or "") != (
                bp_pri_item.emoji or ""
            ) or curr_item.color_hex != bp_pri_item.color:
                pri_to_update.append(bp_pri_item.name)

    if pri_to_create or pri_to_remove or pri_to_update:
        pri_change: dict[str, Any] = {}
        if pri_to_create:
            pri_change["create"] = pri_to_create
        if pri_to_update:
            pri_change["update"] = pri_to_update
        if pri_to_remove:
            pri_change["remove"] = pri_to_remove
        changes["priorities"] = pri_change

    # 4. Labels
    lbl_stmt = select(ProjectLabel).where(ProjectLabel.project_id == project.id)
    curr_lbls = list((await session.execute(lbl_stmt)).scalars().all())
    curr_lbl_map = {lbl.name: lbl for lbl in curr_lbls}
    target_lbl_names = {lbl.name for lbl in blueprint.labels}

    lbl_to_create = [lbl.name for lbl in blueprint.labels if lbl.name not in curr_lbl_map]
    lbl_to_remove = [lbl.name for lbl in curr_lbls if lbl.name not in target_lbl_names]
    lbl_to_update = [
        lbl.name
        for lbl in blueprint.labels
        if lbl.name in curr_lbl_map
        and (
            curr_lbl_map[lbl.name].color_hex != lbl.color
            or curr_lbl_map[lbl.name].exclusive_group != lbl.exclusive_group
        )
    ]

    if lbl_to_create or lbl_to_remove or lbl_to_update:
        lbl_change: dict[str, Any] = {}
        if lbl_to_create:
            lbl_change["create"] = lbl_to_create
        if lbl_to_update:
            lbl_change["update"] = lbl_to_update
        if lbl_to_remove:
            lbl_change["remove"] = lbl_to_remove
        changes["labels"] = lbl_change

    # 5. Modules
    mod_stmt = (
        select(Module)
        .join(ObjectRecord, ObjectRecord.id == Module.id)
        .where(
            Module.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
    )
    curr_mods = list((await session.execute(mod_stmt)).scalars().all())
    curr_mod_map = {m.name: m for m in curr_mods}
    target_mod_names = {m.name for m in blueprint.modules}

    mod_to_create = [m.name for m in blueprint.modules if m.name not in curr_mod_map]
    mod_to_remove = [m.name for m in curr_mods if m.name not in target_mod_names]

    if mod_to_create or mod_to_remove:
        mod_change: dict[str, Any] = {}
        if mod_to_create:
            mod_change["create"] = mod_to_create
        if mod_to_remove:
            mod_change["remove"] = mod_to_remove
        changes["modules"] = mod_change

    # 6. Default modules
    def_mod_stmt = (
        select(Module.name)
        .join(ProjectModuleDefault, ProjectModuleDefault.module_id == Module.id)
        .where(ProjectModuleDefault.project_id == project.id)
    )
    curr_def_mod_names = set((await session.execute(def_mod_stmt)).scalars().all())
    target_def_mod_names = set(blueprint.default_modules)

    if curr_def_mod_names != target_def_mod_names:
        changes["default_modules"] = {
            "from": sorted(curr_def_mod_names),
            "to": sorted(target_def_mod_names),
        }

    plan_sha256 = _canonical_plan_hash(blueprint.identifier, changes)
    return changes, plan_sha256


async def apply_blueprint(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    blueprint: ProjectBlueprint,
    plan_sha256: str,
) -> dict[str, Any]:
    """Atomically apply the declarative blueprint if plan_sha256 matches."""
    # Recompute plan to ensure freshness
    changes, current_sha256 = await compute_plan(session, caller, blueprint)

    if plan_sha256 != current_sha256:
        raise ProblemException(
            code="PLAN_STALE",
            status=409,
            title="Plan Stale",
            detail="Project configuration changed since plan was generated",
        )

    # Perform atomic application
    async with session.begin_nested():
        stmt = select(Project).where(
            Project.workspace_id == caller.workspace_id,
            Project.identifier == blueprint.identifier,
        )
        project = (await session.execute(stmt)).scalar_one_or_none()

        project_id: uuid.UUID
        if project is None:
            # Create project
            project_id = (
                await session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('project' AS object_kind), :ws, NULL, :ident, :name, :creator"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "ident": blueprint.identifier,
                        "name": blueprint.name,
                        "creator": caller.principal_id,
                    },
                )
            ).scalar_one()

            project = Project(
                id=project_id,
                workspace_id=caller.workspace_id,
                identifier=blueprint.identifier,
                name=blueprint.name,
                description_markdown=blueprint.description_markdown,
                modules_enabled=blueprint.modules_enabled,
                auto_archive_days=blueprint.auto_archive_days,
            )
            session.add(project)
            await session.flush()

            # Creator ADMIN role binding
            await session.execute(
                text(
                    "INSERT INTO role_bindings (workspace_id, principal_id, role, scope_type,"
                    " project_id) VALUES (:ws, :pid, CAST('PROJECT_ADMIN' AS rbac_role),"
                    " 'project', :proj)"
                ),
                {"ws": caller.workspace_id, "pid": caller.principal_id, "proj": project_id},
            )
        else:
            project_id = project.id
            project.name = blueprint.name
            project.description_markdown = blueprint.description_markdown
            project.modules_enabled = blueprint.modules_enabled
            project.auto_archive_days = blueprint.auto_archive_days
            await session.flush()

        # Handle states
        curr_states_q = select(WorkflowState).where(WorkflowState.project_id == project_id)
        curr_states = list((await session.execute(curr_states_q)).scalars().all())
        curr_state_map = {s.name: s for s in curr_states}

        # Clear is_default first so unique partial index won't conflict
        await session.execute(
            update(WorkflowState)
            .where(WorkflowState.project_id == project_id)
            .values(is_default=False)
        )

        # 1. State creations/updates (before deletions so terminal state guards pass)
        for idx, bp_st in enumerate(blueprint.states):
            wip_override = blueprint.wip_limits.get(bp_st.name, {})
            soft_lim = wip_override.get("soft", bp_st.wip_soft_limit)
            hard_lim = wip_override.get("hard", bp_st.wip_hard_limit)

            if bp_st.name in curr_state_map:
                existing_st = curr_state_map[bp_st.name]
                existing_st.state_group = bp_st.group
                existing_st.color_hex = bp_st.color
                existing_st.sort_order = bp_st.sort_order if bp_st.sort_order != 0 else idx
                existing_st.is_default = bp_st.is_default
                existing_st.wip_soft_limit = soft_lim
                existing_st.wip_hard_limit = hard_lim
            else:
                new_st = WorkflowState(
                    workspace_id=caller.workspace_id,
                    project_id=project_id,
                    name=bp_st.name,
                    state_group=bp_st.group,
                    color_hex=bp_st.color,
                    sort_order=bp_st.sort_order if bp_st.sort_order != 0 else idx,
                    is_default=bp_st.is_default,
                    wip_soft_limit=soft_lim,
                    wip_hard_limit=hard_lim,
                )
                session.add(new_st)
                curr_state_map[bp_st.name] = new_st
        await session.flush()

        # 2. State migrations
        for old_name, new_name in blueprint.state_migrations.items():
            if old_name in curr_state_map and new_name in curr_state_map:
                old_state = curr_state_map[old_name]
                target_state = curr_state_map[new_name]
                await session.execute(
                    update(Issue)
                    .where(Issue.state_id == old_state.id)
                    .values(state_id=target_state.id)
                )
        await session.flush()

        # 3. State deletions
        target_state_names = {st.name for st in blueprint.states}
        for st_row in curr_states:
            if st_row.name not in target_state_names:
                await session.delete(st_row)
        await session.flush()

        # Handle priorities
        curr_pris_q = select(ProjectPriority).where(ProjectPriority.project_id == project_id)
        curr_pris = list((await session.execute(curr_pris_q)).scalars().all())
        curr_pri_map = {pri.label: pri for pri in curr_pris}
        existing_slugs = {pri.slug for pri in curr_pris}

        # Clear is_default first so unique partial index won't conflict
        await session.execute(
            update(ProjectPriority)
            .where(ProjectPriority.project_id == project_id)
            .values(is_default=False)
        )

        for idx, bp_pri in enumerate(blueprint.priorities):
            if bp_pri.name in curr_pri_map:
                existing_pri = curr_pri_map[bp_pri.name]
                existing_pri.emoji = bp_pri.emoji or None
                existing_pri.color_hex = bp_pri.color
                existing_pri.sort_order = bp_pri.sort_order if bp_pri.sort_order != 0 else idx
                existing_pri.is_default = bp_pri.is_default
            else:
                base_slug = _slugify_priority(bp_pri.name)
                slug = base_slug
                if slug in existing_slugs:
                    slug = f"{base_slug[:27]}-{uuid.uuid4().hex[:4]}"
                existing_slugs.add(slug)
                new_pri = ProjectPriority(
                    workspace_id=caller.workspace_id,
                    project_id=project_id,
                    slug=slug,
                    label=bp_pri.name,
                    emoji=bp_pri.emoji or None,
                    color_hex=bp_pri.color,
                    sort_order=bp_pri.sort_order if bp_pri.sort_order != 0 else idx,
                    is_default=bp_pri.is_default,
                )
                session.add(new_pri)
                curr_pri_map[bp_pri.name] = new_pri
        await session.flush()

        target_pri_names = {pri.name for pri in blueprint.priorities}
        for pri_row in curr_pris:
            if pri_row.label not in target_pri_names:
                await session.delete(pri_row)
        await session.flush()

        # Handle labels
        curr_lbls_q = select(ProjectLabel).where(ProjectLabel.project_id == project_id)
        curr_lbls = list((await session.execute(curr_lbls_q)).scalars().all())
        curr_lbl_map = {lbl.name: lbl for lbl in curr_lbls}
        target_lbl_names = {lbl.name for lbl in blueprint.labels}

        for lbl_row in curr_lbls:
            if lbl_row.name not in target_lbl_names:
                await session.delete(lbl_row)
        await session.flush()

        for bp_lbl in blueprint.labels:
            if bp_lbl.name in curr_lbl_map:
                existing_lbl = curr_lbl_map[bp_lbl.name]
                existing_lbl.color_hex = bp_lbl.color
                existing_lbl.exclusive_group = bp_lbl.exclusive_group
            else:
                new_lbl = ProjectLabel(
                    workspace_id=caller.workspace_id,
                    project_id=project_id,
                    name=bp_lbl.name,
                    color_hex=bp_lbl.color,
                    exclusive_group=bp_lbl.exclusive_group,
                )
                session.add(new_lbl)
        await session.flush()

        # Handle modules
        mod_q = (
            select(Module)
            .join(ObjectRecord, ObjectRecord.id == Module.id)
            .where(
                Module.project_id == project_id,
                ObjectRecord.deleted_at.is_(None),
            )
        )
        curr_mods = list((await session.execute(mod_q)).scalars().all())
        curr_mod_map = {mod.name: mod for mod in curr_mods}
        target_mod_names = {mod.name for mod in blueprint.modules}

        for mod_row in curr_mods:
            if mod_row.name not in target_mod_names:
                await session.delete(mod_row)
        await session.flush()

        created_mod_map: dict[str, uuid.UUID] = {}
        for m_name, curr_mod in curr_mod_map.items():
            if m_name in target_mod_names:
                created_mod_map[m_name] = curr_mod.id

        for bp_mod in blueprint.modules:
            if bp_mod.name not in curr_mod_map:
                mod_key = f"{blueprint.identifier.lower()}-{bp_mod.name.lower().replace(' ', '-')}"[
                    :200
                ]
                mod_id = (
                    await session.execute(
                        text(
                            "SELECT register_object("
                            "  CAST('module' AS object_kind), :ws, :proj, :key, :name, :creator"
                            ")"
                        ),
                        {
                            "ws": caller.workspace_id,
                            "proj": project_id,
                            "key": mod_key,
                            "name": bp_mod.name,
                            "creator": caller.principal_id,
                        },
                    )
                ).scalar_one()

                new_mod = Module(
                    id=mod_id,
                    workspace_id=caller.workspace_id,
                    project_id=project_id,
                    name=bp_mod.name,
                )
                session.add(new_mod)
                created_mod_map[bp_mod.name] = mod_id
        await session.flush()

        # Handle default modules
        await session.execute(
            delete(ProjectModuleDefault).where(ProjectModuleDefault.project_id == project_id)
        )
        for def_name in blueprint.default_modules:
            if def_name in created_mod_map:
                session.add(
                    ProjectModuleDefault(
                        project_id=project_id,
                        module_id=created_mod_map[def_name],
                        workspace_id=caller.workspace_id,
                    )
                )
        await session.flush()

        # Record activity
        await record_activity(
            session,
            workspace_id=caller.workspace_id,
            object_id=project_id,
            actor_principal_id=caller.principal_id,
            event_type=ActivityEventType.PROJECT_BLUEPRINT_APPLIED,
            payload={
                "identifier": blueprint.identifier,
                "plan_sha256": plan_sha256,
            },
        )

    return {
        "status": "applied",
        "project": blueprint.identifier,
        "plan_sha256": plan_sha256,
        "changes": changes,
    }


async def get_blueprint(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
) -> ProjectBlueprint:
    """Read the current project configuration and return as a ProjectBlueprint."""
    project = await get_project_or_404(session, caller, project_ref)
    await require_capability(session, caller, project.id, Capability.VIEW)

    # 1. States
    states_q = (
        select(WorkflowState)
        .where(WorkflowState.project_id == project.id)
        .order_by(WorkflowState.sort_order, WorkflowState.name)
    )
    states = list((await session.execute(states_q)).scalars().all())
    blueprint_states: list[BlueprintState] = []
    wip_limits: dict[str, dict[str, int]] = {}

    for s in states:
        blueprint_states.append(
            BlueprintState(
                name=s.name,
                group=s.state_group,  # type: ignore[arg-type]
                color=s.color_hex,
                sort_order=s.sort_order,
                is_default=s.is_default,
                wip_soft_limit=s.wip_soft_limit,
                wip_hard_limit=s.wip_hard_limit,
            )
        )
        if s.wip_soft_limit is not None or s.wip_hard_limit is not None:
            wip_limits[s.name] = {}
            if s.wip_soft_limit is not None:
                wip_limits[s.name]["soft"] = s.wip_soft_limit
            if s.wip_hard_limit is not None:
                wip_limits[s.name]["hard"] = s.wip_hard_limit

    # 2. Priorities
    pri_q = (
        select(ProjectPriority)
        .where(ProjectPriority.project_id == project.id)
        .order_by(ProjectPriority.sort_order)
    )
    priorities = list((await session.execute(pri_q)).scalars().all())
    blueprint_priorities = [
        BlueprintPriority(
            name=p.label,
            emoji=p.emoji or "",
            color=p.color_hex,
            sort_order=p.sort_order,
            is_default=p.is_default,
        )
        for p in priorities
    ]

    # 3. Labels
    lbl_q = (
        select(ProjectLabel)
        .where(ProjectLabel.project_id == project.id)
        .order_by(ProjectLabel.name)
    )
    labels = list((await session.execute(lbl_q)).scalars().all())
    blueprint_labels = [
        BlueprintLabel(
            name=lbl.name,
            exclusive_group=lbl.exclusive_group,
            color=lbl.color_hex,
        )
        for lbl in labels
    ]

    # 4. Modules
    mod_q = (
        select(Module)
        .join(ObjectRecord, ObjectRecord.id == Module.id)
        .where(
            Module.project_id == project.id,
            ObjectRecord.deleted_at.is_(None),
        )
        .order_by(Module.name)
    )
    modules = list((await session.execute(mod_q)).scalars().all())
    blueprint_modules = [BlueprintModule(name=m.name) for m in modules]

    # 5. Default modules
    def_mod_q = (
        select(Module.name)
        .join(ProjectModuleDefault, ProjectModuleDefault.module_id == Module.id)
        .where(ProjectModuleDefault.project_id == project.id)
        .order_by(Module.name)
    )
    default_modules = list((await session.execute(def_mod_q)).scalars().all())

    return ProjectBlueprint(
        identifier=project.identifier,
        name=project.name,
        description_markdown=project.description_markdown,
        states=blueprint_states,
        state_migrations={},
        priorities=blueprint_priorities,
        labels=blueprint_labels,
        modules_enabled=project.modules_enabled,
        modules=blueprint_modules,
        default_modules=default_modules,
        auto_archive_days=project.auto_archive_days,
        wip_limits=wip_limits,
    )
