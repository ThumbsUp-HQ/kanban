# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit tests for workflow hook mutable field updates (KB-P5-17a)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, text

from database.models.custom_field import CustomFieldDefinition, CustomFieldValue
from database.models.issues import Issue, IssueAssignee, IssueLabel
from database.models.projects import Cycle, ProjectLabel, ProjectPriority, WorkflowState
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.workflows.mutations import (
    apply_field_updates,
    is_in_mutable_universe,
    validate_field_updates,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def test_is_in_mutable_universe() -> None:
    """Test validation of base and custom field universe members."""
    for base in ("labels", "priority", "assignees", "start_date", "due_date", "cycle"):
        assert is_in_mutable_universe(base) is True

    assert is_in_mutable_universe("custom_fields.qa_status") is True
    assert is_in_mutable_universe("custom_fields.risk-level_1") is True
    assert is_in_mutable_universe("custom_fields.") is False
    assert is_in_mutable_universe("custom_fields.INVALID/CHARS") is False
    assert is_in_mutable_universe("state") is False
    assert is_in_mutable_universe("summary") is False
    assert is_in_mutable_universe("description_markdown") is False
    assert is_in_mutable_universe("unknown_field") is False


def test_validate_field_updates_validation() -> None:
    """Test validate_field_updates against immutable, unknown, and forbidden fields."""
    # None or empty is a no-op
    validate_field_updates([], None)
    validate_field_updates([], {})

    # Valid allowed fields
    validate_field_updates(["labels", "priority"], {"labels": ["foo"], "priority": "high"})

    # Immutable fields reject with HOOK_MUTATION_NOT_ALLOWED
    for imm in ("state", "state_id", "summary", "description_markdown", "created_by", "parent"):
        with pytest.raises(ProblemException) as exc_info:
            validate_field_updates([imm], {imm: "val"})
        assert exc_info.value.code == "HOOK_MUTATION_NOT_ALLOWED"
        assert exc_info.value.status == 422
        assert "immutable" in (exc_info.value.detail or "")

    # Unknown field outside universe
    with pytest.raises(ProblemException) as exc_info:
        validate_field_updates(["bogus"], {"bogus": "val"})
    assert exc_info.value.code == "HOOK_MUTATION_NOT_ALLOWED"
    assert "not in MUTABLE_FIELD_UNIVERSE" in (exc_info.value.detail or "")

    # Field in universe but not allowed by hook
    with pytest.raises(ProblemException) as exc_info:
        validate_field_updates(["labels"], {"priority": "urgent"})
    assert exc_info.value.code == "HOOK_MUTATION_NOT_ALLOWED"
    assert "not in hook's allowed_mutable_fields" in (exc_info.value.detail or "")


async def test_apply_field_updates_all_fields(  # noqa: PLR0915
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Test applying labels, priority, assignees, dates, cycle, and custom fields."""
    admin = await make_user("mut_admin", workspace_role="WORKSPACE_ADMIN")
    dev = await make_user("mut_dev", workspace_role="WORKSPACE_MEMBER")
    proj_id = await make_project(
        "MUT", created_by=admin, roles={admin: "PROJECT_ADMIN", dev: "MEMBER"}
    )

    actor = PrincipalContext(
        principal_id=admin.id,
        workspace_id=api_env.workspace_id,
        token_scopes=("session",),
    )

    # Empty updates return {}
    empty_changes = await apply_field_updates(api_env.seed, None, None, actor)  # type: ignore[arg-type]
    assert empty_changes == {}

    # Get seeded Project Priority
    prio_urgent = (
        await api_env.seed.execute(
            select(ProjectPriority).where(
                ProjectPriority.project_id == proj_id,
                ProjectPriority.slug == "urgent",
            )
        )
    ).scalar_one()
    prio_medium = (
        await api_env.seed.execute(
            select(ProjectPriority).where(
                ProjectPriority.project_id == proj_id,
                ProjectPriority.slug == "medium",
            )
        )
    ).scalar_one()
    prio_id = prio_urgent.id
    medium_id = prio_medium.id

    # Seed Project Cycle
    cy_id = uuid.uuid4()
    await api_env.seed.execute(
        text(
            "SELECT register_object("
            "'cycle'::object_kind, :ws, :proj, 'CY-1', 'Sprint 1', :uid, :id)"
        ),
        {"ws": api_env.workspace_id, "proj": proj_id, "uid": admin.id, "id": cy_id},
    )
    cy = Cycle(
        id=cy_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        name="Sprint 1",
    )
    api_env.seed.add(cy)

    # Seed Custom Field Definition
    cf_def_id = uuid.uuid4()
    cf_def = CustomFieldDefinition(
        id=cf_def_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        slug="qa-signoff",
        name="QA Signoff",
        tier="wasm",
        output_format="text",
        script_source="return 'ok';",
        manifest_sha256=b"\x00" * 32,
        created_by_id=admin.id,
    )
    api_env.seed.add(cf_def)

    # Seed an existing Project Label
    existing_pl_id = uuid.uuid4()
    existing_pl = ProjectLabel(
        id=existing_pl_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        name="backend",
        color_hex="#0284c7",
    )
    api_env.seed.add(existing_pl)
    await api_env.seed.commit()

    # Get default state for project
    default_state_id = (
        (
            await api_env.seed.execute(
                select(WorkflowState.id).where(WorkflowState.project_id == proj_id)
            )
        )
        .scalars()
        .first()
    )

    # Create issue
    issue_id = uuid.uuid4()
    seq_id = (
        await api_env.seed.execute(
            text("SELECT allocate_issue_sequence(:proj)"),
            {"proj": proj_id},
        )
    ).scalar_one()

    await api_env.seed.execute(
        text(
            "SELECT register_object("
            "'issue'::object_kind, :ws, :proj, 'MUT-1', 'Mut Issue', :uid, :id)"
        ),
        {"ws": api_env.workspace_id, "proj": proj_id, "uid": admin.id, "id": issue_id},
    )
    issue = Issue(
        id=issue_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        sequence_id=seq_id,
        summary="Mut Issue",
        state_id=default_state_id,
        priority_id=medium_id,
        board_rank="0|i00000:",
        created_by_id=admin.id,
    )
    api_env.seed.add(issue)
    await api_env.seed.commit()

    # 1. Apply labels: one existing UUID, one existing name, one new name
    new_label_name = "security-audit"
    updates: dict[str, object] = {
        "labels": [existing_pl_id, "backend", new_label_name],
        "priority": "Urgent",
        "assignees": [dev.id, "external@example.com"],
        "start_date": "2026-11-15",
        "due_date": dt.date(2026, 11, 20),
        "cycle": "Sprint 1",
        "custom_fields.qa-signoff": "Approved by SecTeam",
    }

    changes = await apply_field_updates(api_env.seed, issue, updates, actor)
    await api_env.seed.commit()

    assert "labels" in changes
    assert "priority" in changes
    assert changes["priority"] == (str(medium_id), str(prio_id))
    assert "assignees" in changes
    assert "start_date" in changes
    assert changes["start_date"] == (None, "2026-11-15")
    assert "due_date" in changes
    assert changes["due_date"] == (None, "2026-11-20")
    assert "cycle" in changes
    assert "custom_fields.qa-signoff" in changes

    # Verify Issue in DB
    await api_env.seed.rollback()
    reloaded = (await api_env.seed.execute(select(Issue).where(Issue.id == issue_id))).scalar_one()
    assert reloaded.priority_id == prio_id
    assert reloaded.start_date == dt.date(2026, 11, 15)
    assert reloaded.due_date == dt.date(2026, 11, 20)
    assert reloaded.cycle_id == cy_id

    # Verify labels in DB
    labels_in_db = (
        (await api_env.seed.execute(select(IssueLabel).where(IssueLabel.issue_id == issue_id)))
        .scalars()
        .all()
    )
    assert len(labels_in_db) == 2

    # Verify assignees in DB
    assignees_in_db = (
        (
            await api_env.seed.execute(
                select(IssueAssignee).where(IssueAssignee.issue_id == issue_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(assignees_in_db) == 2

    # Verify custom field value in DB
    cfv_in_db = (
        await api_env.seed.execute(
            select(CustomFieldValue).where(
                CustomFieldValue.issue_id == issue_id,
                CustomFieldValue.field_id == cf_def_id,
            )
        )
    ).scalar_one()
    assert cfv_in_db.value_json == "Approved by SecTeam"

    # 2. Update custom field value, cycle to None, priority to medium by UUID
    updates_2: dict[str, object] = {
        "labels": [str(existing_pl_id)],
        "priority": medium_id,
        "assignees": [admin.handle],
        "cycle": None,
        "start_date": None,
        "due_date": None,
        "custom_fields.qa-signoff": "Updated Signoff",
        "custom_fields.nonexistent-field": "ignored-value",
    }
    changes_2 = await apply_field_updates(api_env.seed, reloaded, updates_2, actor)
    await api_env.seed.commit()
    assert changes_2["custom_fields.qa-signoff"] == (None, "Updated Signoff")
    assert changes_2["priority"] == (str(prio_id), str(medium_id))
    assert changes_2["cycle"] == (str(cy_id), None)
    assert changes_2["start_date"] == ("2026-11-15", None)
    assert changes_2["due_date"] == ("2026-11-20", None)

    # 3. Test cycle with UUID, start_date with date, due_date with string
    updates_3: dict[str, object] = {
        "cycle": cy_id,
        "start_date": dt.date(2026, 12, 1),
        "due_date": "2026-12-15",
    }
    changes_3 = await apply_field_updates(api_env.seed, reloaded, updates_3, actor)
    await api_env.seed.commit()
    assert changes_3["cycle"] == (None, str(cy_id))
    assert changes_3["start_date"] == (None, "2026-12-01")
    assert changes_3["due_date"] == (None, "2026-12-15")
