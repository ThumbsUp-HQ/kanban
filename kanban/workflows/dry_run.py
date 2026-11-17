# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: C901, PLR0912, PLR0915, S101, TRY301, TRY003, TRY004, EM101, BLE001, E501
"""Synchronous dry-run transition pipeline simulator (KB-P5-17b, S14.4)."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text

from database.models.agent_definition import AgentDefinition
from database.models.issues import Issue
from database.models.projects import ProjectPriority
from database.models.wasm_module import ApprovedWasmModule
from database.models.workflow import WorkflowTransitionHook
from kanban.api.problems import ProblemException
from kanban.content import normalize_plain_text
from kanban.sandbox.wasm_runner import TierAWasmRunner, WasmRunLimits
from kanban.services.board_rank import allocate_initial_board_rank
from kanban.services.issue_keys import resolve_issue_ref
from kanban.services.projects import get_project_or_404
from kanban.workflows.hooks_service import WorkflowHookService
from kanban.workflows.manifest import compute_hook_manifest_sha256
from kanban.workflows.mutations import validate_field_updates

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

MAX_DESCRIPTION_BYTES: Final[int] = 1048576  # 1 MiB boundary
SYNC_HOOK_BUDGET_US: Final[int] = 25000  # 25ms monotonic budget

HookKind = Literal["sync_validator", "sync_mutator", "agent_interceptor"]
StepResultKind = Literal["allowed", "mutated", "rejected", "error", "skipped_async"]


class DryRunSampleTicket(BaseModel):
    """Sample ticket payload for dry-run simulation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(min_length=1, max_length=500, description="Ticket summary")
    description_markdown: str = Field(description="Markdown ticket description")
    priority: str = Field(default="medium", description="Priority slug or name")
    labels: list[str] = Field(default_factory=list, description="List of label names")


class DryRunPayload(BaseModel):
    """Request payload for dry-running workflow hooks against a ticket."""

    model_config = ConfigDict(extra="forbid", strict=True)

    from_state: str | None = Field(default=None, description="Source state name, UUID, or null/'*'")
    to_state: str = Field(min_length=1, description="Target state name or UUID")
    issue_key: str | None = Field(default=None, description="Existing issue key or UUID")
    sample_ticket: DryRunSampleTicket | None = Field(
        default=None, description="Synthetic ticket for dry-run"
    )


class DryRunStepResult(BaseModel):
    """Result of a single hook execution in the dry-run pipeline."""

    model_config = ConfigDict(extra="allow")

    order: int
    name: str
    hook_kind: str
    result: StepResultKind
    reason: str | None = None
    field_updates: dict[str, Any] | None = None
    duration_us: int = 0
    cli_command: str | None = None


class DryRunResponse(BaseModel):
    """Aggregated dry-run response."""

    model_config = ConfigDict(extra="allow")

    steps: list[DryRunStepResult]
    would_commit: bool


async def run_dry_run(
    session: AsyncSession,
    caller: PrincipalContext,
    project_ref: str,
    payload: DryRunPayload,
) -> DryRunResponse:
    """Execute the synchronous workflow hook pipeline inside a strictly non-committing SAVEPOINT."""
    # 1. Access control: PROJECT_ADMIN required (S3.4: 404 for non-admins)
    project = await get_project_or_404(session, caller, project_ref)
    await WorkflowHookService.require_admin(session, caller, project.id)

    # 2. Input validation: Exactly one of issue_key or sample_ticket
    has_key = payload.issue_key is not None and bool(payload.issue_key.strip())
    has_sample = payload.sample_ticket is not None
    if has_key == has_sample:
        raise ProblemException(
            code="INVALID_DRY_RUN_INPUT",
            status=422,
            title="Invalid Dry-Run Input",
            detail="Exactly one of issue_key or sample_ticket must be provided",
        )

    # 3. Resolve states
    from_id, from_name = await WorkflowHookService.resolve_state(
        session, project.id, payload.from_state, allow_wildcard=True
    )
    to_id, to_name = await WorkflowHookService.resolve_state(
        session, project.id, payload.to_state, allow_wildcard=False
    )
    assert to_id is not None
    assert to_name is not None

    # Validate description length on sample ticket
    norm_description = ""
    if has_sample and payload.sample_ticket is not None:
        raw_desc = payload.sample_ticket.description_markdown
        desc_bytes = raw_desc.encode("utf-8")
        if len(desc_bytes) > MAX_DESCRIPTION_BYTES:
            raise ProblemException(
                code="DESCRIPTION_TOO_LARGE",
                status=422,
                title="Description Too Large",
                detail=f"description_markdown exceeds {MAX_DESCRIPTION_BYTES} bytes limit",
            )
        norm_description = normalize_plain_text(raw_desc)

    steps: list[DryRunStepResult] = []
    would_commit = True
    cumulative_us = 0

    # 4. Strict non-persistence isolation via SAVEPOINT
    # We open a nested transaction that is ALWAYS rolled back
    try:
        async with session.begin_nested():
            issue_id: uuid.UUID
            issue_summary: str
            issue_desc: str
            issue_desc_sha: bytes
            issue_priority_str: str
            issue_labels: list[str]
            issue_key_str: str

            if has_sample and payload.sample_ticket is not None:
                # Find priority for project
                prio_stmt = select(ProjectPriority.id, ProjectPriority.slug).where(
                    ProjectPriority.project_id == project.id,
                    ProjectPriority.slug == payload.sample_ticket.priority.strip().lower(),
                )
                prio_row = (await session.execute(prio_stmt)).first()
                if prio_row is None:
                    prio_stmt_def = (
                        select(ProjectPriority.id, ProjectPriority.slug)
                        .where(ProjectPriority.project_id == project.id)
                        .limit(1)
                    )
                    prio_row = (await session.execute(prio_stmt_def)).first()
                assert prio_row is not None
                prio_id, prio_slug = prio_row[0], prio_row[1]

                seq_val = await session.scalar(
                    text("SELECT allocate_issue_sequence(:proj)"),
                    {"proj": project.id},
                )
                sample_ckey = f"{project.identifier}-{seq_val}"

                issue_summary = payload.sample_ticket.summary.strip()
                issue_desc = norm_description
                issue_desc_sha = hashlib.sha256(issue_desc.encode("utf-8")).digest()
                issue_priority_str = prio_slug
                issue_labels = list(payload.sample_ticket.labels)
                issue_key_str = sample_ckey

                reg_row = await session.execute(
                    text(
                        "SELECT register_object("
                        "  CAST('issue' AS object_kind), :ws, :proj, :key, :title, :creator"
                        ")"
                    ),
                    {
                        "ws": caller.workspace_id,
                        "proj": project.id,
                        "key": sample_ckey,
                        "title": issue_summary,
                        "creator": caller.principal_id,
                    },
                )
                issue_id = reg_row.scalar_one()

                # Ephemeral issue row inside savepoint
                synth_issue = Issue(
                    id=issue_id,
                    workspace_id=caller.workspace_id,
                    project_id=project.id,
                    sequence_id=seq_val,
                    summary=issue_summary,
                    description_markdown=issue_desc,
                    state_id=from_id or to_id,
                    priority_id=prio_id,
                    created_by_id=caller.principal_id,
                    board_rank=allocate_initial_board_rank(seq_val),
                )
                session.add(synth_issue)
                await session.flush()

            else:
                assert payload.issue_key is not None
                issue_row = await resolve_issue_ref(session, caller, payload.issue_key)
                issue_id = issue_row.id
                issue_summary = issue_row.summary
                issue_desc = issue_row.description_markdown or ""
                issue_desc_sha = issue_row.description_sha256 or b"\x00" * 32
                issue_priority_str = str(issue_row.priority_id)
                issue_labels = []
                issue_key_str = payload.issue_key.strip()

            # Query enabled hooks for this transition in sort_rank order
            hook_stmt = select(WorkflowTransitionHook).where(
                WorkflowTransitionHook.project_id == project.id,
                WorkflowTransitionHook.workspace_id == caller.workspace_id,
                WorkflowTransitionHook.to_state_id == to_id,
                WorkflowTransitionHook.is_enabled == True,  # noqa: E712
            )
            if from_id is None:
                hook_stmt = hook_stmt.where(WorkflowTransitionHook.from_state_id.is_(None))
            else:
                hook_stmt = hook_stmt.where(
                    (WorkflowTransitionHook.from_state_id == from_id)
                    | (WorkflowTransitionHook.from_state_id.is_(None))
                )
            hook_stmt = hook_stmt.order_by(WorkflowTransitionHook.sort_rank)

            hooks = list((await session.execute(hook_stmt)).scalars().all())

            # Pre-load agents
            agent_ids = [h.agent_definition_id for h in hooks if h.agent_definition_id]
            agents_map: dict[uuid.UUID, AgentDefinition] = {}
            if agent_ids:
                ag_stmt = select(AgentDefinition).where(AgentDefinition.id.in_(agent_ids))
                for ag in (await session.execute(ag_stmt)).scalars().all():
                    agents_map[ag.id] = ag

            # Execute pipeline
            for idx, hook in enumerate(hooks):
                order_num = idx + 1

                # 1. Agent interceptor -> skipped_async
                if hook.hook_kind == "agent_interceptor":
                    agent_def = (
                        agents_map.get(hook.agent_definition_id)
                        if hook.agent_definition_id
                        else None
                    )
                    agent_slug = agent_def.slug if agent_def else "agent"
                    harness = agent_def.harness_kind if agent_def else "cli_pipe"
                    cli_cmd = (
                        f"uv run kanban-agent validate-transition --harness {harness} "
                        f"--agent {agent_slug} --project {project.identifier} --issue {issue_key_str} "
                        f'--to-state "{to_name}"'
                    )
                    steps.append(
                        DryRunStepResult(
                            order=order_num,
                            name=hook.name,
                            hook_kind="agent_interceptor",
                            result="skipped_async",
                            duration_us=0,
                            cli_command=cli_cmd,
                        )
                    )
                    continue

                # 2. Sync hook manifest check
                calc_manifest = compute_hook_manifest_sha256(
                    from_state_id=hook.from_state_id,
                    to_state_id=hook.to_state_id,
                    hook_kind=hook.hook_kind,
                    wasm_module_sha256=hook.wasm_module_sha256,
                    agent_definition_id=hook.agent_definition_id,
                    allowed_mutable_fields=hook.allowed_mutable_fields,
                    failure_policy=hook.failure_policy,
                )
                if calc_manifest != hook.manifest_sha256:
                    steps.append(
                        DryRunStepResult(
                            order=order_num,
                            name=hook.name,
                            hook_kind=hook.hook_kind,
                            result="error",
                            reason="HOOK_MANIFEST_MISMATCH",
                            duration_us=0,
                        )
                    )
                    would_commit = False
                    if hook.failure_policy == "fail_closed":
                        break
                    continue

                # 3. Check cumulative latency budget
                if cumulative_us >= SYNC_HOOK_BUDGET_US:
                    if hook.failure_policy == "fail_closed":
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="error",
                                reason="SYNC_HOOK_BUDGET_EXCEEDED",
                                duration_us=0,
                            )
                        )
                        would_commit = False
                        break
                    steps.append(
                        DryRunStepResult(
                            order=order_num,
                            name=hook.name,
                            hook_kind=hook.hook_kind,
                            result="allowed",
                            reason="fail_open_warn: SYNC_HOOK_BUDGET_EXCEEDED",
                            duration_us=0,
                        )
                    )
                    continue

                # 4. Execute WASM module
                assert hook.wasm_module_sha256 is not None
                mod_stmt = select(ApprovedWasmModule.wasm_bytes).where(
                    ApprovedWasmModule.workspace_id == hook.workspace_id,
                    ApprovedWasmModule.sha256 == hook.wasm_module_sha256,
                )
                wasm_bytes = (await session.execute(mod_stmt)).scalar_one_or_none()
                if wasm_bytes is None:
                    steps.append(
                        DryRunStepResult(
                            order=order_num,
                            name=hook.name,
                            hook_kind=hook.hook_kind,
                            result="error",
                            reason="WASM module binary not found",
                            duration_us=0,
                        )
                    )
                    would_commit = False
                    if hook.failure_policy == "fail_closed":
                        break
                    continue

                runner = TierAWasmRunner.get_instance()
                hook_input = {
                    "issue": {
                        "id": str(issue_id),
                        "key": issue_key_str,
                        "summary": issue_summary,
                        "description_markdown": issue_desc,
                        "description_sha256": issue_desc_sha.hex(),
                        "priority": issue_priority_str,
                        "labels": issue_labels,
                    },
                    "transition": {
                        "from_state": from_name,
                        "to_state": to_name,
                    },
                    "actor": {
                        "id": str(caller.principal_id),
                        "display_name": getattr(caller, "display_name", str(caller.principal_id)),
                        "role": "PROJECT_ADMIN",
                    },
                }

                input_json_bytes = json.dumps(hook_input, separators=(",", ":")).encode("utf-8")
                t0 = time.perf_counter()
                try:
                    remaining_ms = max(1.0, (SYNC_HOOK_BUDGET_US - cumulative_us) / 1000.0)
                    timeout_int = max(1, int(remaining_ms))
                    limits = WasmRunLimits(timeout_ms=min(500, timeout_int))
                    res = runner.run_sync(wasm_bytes, input_json_bytes, limits=limits)
                    raw_dur_ms = getattr(res, "duration_ms", None)
                    hook_ms = (
                        float(raw_dur_ms)
                        if isinstance(raw_dur_ms, (int, float))
                        else (time.perf_counter() - t0) * 1000.0
                    )
                    dur_us = max(1, int(hook_ms * 1000.0))
                    cumulative_us += dur_us

                    output_raw = res.output_bytes if hasattr(res, "output_bytes") else res
                    raw_out = json.loads(
                        output_raw.decode("utf-8")
                        if isinstance(output_raw, (bytes, bytearray))
                        else str(output_raw)
                    )
                    if not isinstance(raw_out, dict):
                        raise ValueError("WASM output must be JSON object")

                    is_allow = (
                        raw_out.get("verdict") == "allow"
                        or raw_out.get("decision") == "allow"
                        or raw_out.get("allowed") is True
                        or raw_out.get("allow") is True
                    )
                    is_reject = (
                        raw_out.get("verdict") == "reject"
                        or raw_out.get("decision") == "reject"
                        or raw_out.get("allowed") is False
                        or raw_out.get("allow") is False
                    )
                    f_updates = raw_out.get("field_updates") or raw_out.get("mutations")

                    if (
                        hook.hook_kind == "sync_mutator"
                        and isinstance(f_updates, dict)
                        and f_updates
                    ):
                        try:
                            validate_field_updates(hook.allowed_mutable_fields, f_updates)
                            steps.append(
                                DryRunStepResult(
                                    order=order_num,
                                    name=hook.name,
                                    hook_kind=hook.hook_kind,
                                    result="mutated",
                                    field_updates=f_updates,
                                    duration_us=dur_us,
                                )
                            )
                        except ProblemException as mut_exc:
                            if hook.failure_policy == "fail_open_warn":
                                steps.append(
                                    DryRunStepResult(
                                        order=order_num,
                                        name=hook.name,
                                        hook_kind=hook.hook_kind,
                                        result="allowed",
                                        reason=f"fail_open_warn: {mut_exc.detail}",
                                        duration_us=dur_us,
                                    )
                                )
                            else:
                                steps.append(
                                    DryRunStepResult(
                                        order=order_num,
                                        name=hook.name,
                                        hook_kind=hook.hook_kind,
                                        result="error",
                                        reason=mut_exc.detail,
                                        duration_us=dur_us,
                                    )
                                )
                                would_commit = False
                                break
                    elif is_allow:
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="allowed",
                                duration_us=dur_us,
                            )
                        )
                    elif is_reject:
                        rej_reason = str(raw_out.get("reason") or "Rejected by hook")
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="rejected",
                                reason=rej_reason,
                                duration_us=dur_us,
                            )
                        )
                        would_commit = False
                        if hook.failure_policy == "fail_closed":
                            break
                    else:
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="allowed",
                                duration_us=dur_us,
                            )
                        )

                except Exception as exc:
                    dur_us = max(1, int((time.perf_counter() - t0) * 1_000_000))
                    cumulative_us += dur_us
                    if hook.failure_policy == "fail_open_warn":
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="allowed",
                                reason=f"fail_open_warn: {exc}",
                                duration_us=dur_us,
                            )
                        )
                    else:
                        steps.append(
                            DryRunStepResult(
                                order=order_num,
                                name=hook.name,
                                hook_kind=hook.hook_kind,
                                result="error",
                                reason=str(exc),
                                duration_us=dur_us,
                            )
                        )
                        would_commit = False
                        break

            # Force rollback of the savepoint
            await session.rollback()

    except Exception:
        await session.rollback()
        raise

    return DryRunResponse(steps=steps, would_commit=would_commit)
