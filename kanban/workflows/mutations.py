# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Allowed mutable field universe and field update application for workflow hooks.

KB-P5-17a, S14.1, S14.2.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import delete, select

from database.models.custom_field import CustomFieldDefinition, CustomFieldValue
from database.models.issues import Issue, IssueAssignee, IssueLabel
from database.models.principals import Principal, User
from database.models.projects import Cycle, ProjectLabel, ProjectPriority
from kanban.api.problems import ProblemException

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

_CUSTOM_FIELD_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")

MUTABLE_BASE_FIELDS: Final[frozenset[str]] = frozenset(
    {"labels", "priority", "assignees", "start_date", "due_date", "cycle"}
)

IMMUTABLE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "state",
        "state_id",
        "summary",
        "description_markdown",
        "created_by",
        "created_by_id",
        "original_created_by_id",
        "parent",
        "parent_issue_id",
        "id",
        "workspace_id",
        "project_id",
        "sequence_id",
    }
)

# Canonical set definition per spec
MUTABLE_FIELD_UNIVERSE: Final[frozenset[str]] = MUTABLE_BASE_FIELDS


def is_in_mutable_universe(field_name: str) -> bool:
    """Return True if field_name belongs to MUTABLE_FIELD_UNIVERSE or valid custom_fields.<slug>."""
    if field_name in MUTABLE_BASE_FIELDS:
        return True
    if field_name.startswith("custom_fields."):
        slug = field_name[len("custom_fields.") :]
        return bool(_CUSTOM_FIELD_SLUG_PATTERN.match(slug))
    return False


def validate_field_updates(
    allowed_mutable_fields: Collection[str],
    field_updates: Mapping[str, Any] | None,
) -> None:
    """Validate that every key in field_updates is permitted, in universe, and non-immutable."""
    if not field_updates:
        return

    allowed_set = set(allowed_mutable_fields)
    for key in field_updates:
        if key in IMMUTABLE_FIELDS:
            raise ProblemException(
                code="HOOK_MUTATION_NOT_ALLOWED",
                status=422,
                title="Hook Mutation Not Allowed",
                detail=f"Field '{key}' is immutable (TOCTOU security invariant)",
                field=key,
            )
        if not is_in_mutable_universe(key):
            raise ProblemException(
                code="HOOK_MUTATION_NOT_ALLOWED",
                status=422,
                title="Hook Mutation Not Allowed",
                detail=f"Field '{key}' is not in MUTABLE_FIELD_UNIVERSE",
                field=key,
            )
        if key not in allowed_set:
            raise ProblemException(
                code="HOOK_MUTATION_NOT_ALLOWED",
                status=422,
                title="Hook Mutation Not Allowed",
                detail=f"Field '{key}' is not in hook's allowed_mutable_fields",
                field=key,
            )


async def apply_field_updates(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    issue: Issue,
    field_updates: Mapping[str, Any] | None,
    _caller: PrincipalContext,
) -> dict[str, tuple[Any, Any]]:
    """Apply validated field_updates to issue within session, returning changes dict."""
    if not field_updates:
        return {}

    changes: dict[str, tuple[Any, Any]] = {}

    for key, val in field_updates.items():
        if key == "labels":
            # val can be list of label names or UUIDs
            raw_labels: list[Any] = list(val) if isinstance(val, (list, tuple)) else [val]
            label_ids: list[uuid.UUID] = []
            for item in raw_labels:
                if isinstance(item, uuid.UUID):
                    label_ids.append(item)
                else:
                    item_str = str(item).strip()
                    try:
                        parsed_u = uuid.UUID(item_str)
                        label_ids.append(parsed_u)
                    except ValueError:
                        # Find or create project label by name
                        pl_stmt = select(ProjectLabel.id).where(
                            ProjectLabel.project_id == issue.project_id,
                            ProjectLabel.name == item_str,
                        )
                        found_id = (await session.execute(pl_stmt)).scalar_one_or_none()
                        if found_id is not None:
                            label_ids.append(found_id)
                        else:
                            new_pl_id = uuid.uuid4()
                            session.add(
                                ProjectLabel(
                                    id=new_pl_id,
                                    workspace_id=issue.workspace_id,
                                    project_id=issue.project_id,
                                    name=item_str,
                                    color_hex="#0284c7",
                                )
                            )
                            await session.flush()
                            label_ids.append(new_pl_id)

            unique_label_ids = list(dict.fromkeys(label_ids))
            await session.execute(delete(IssueLabel).where(IssueLabel.issue_id == issue.id))
            for lid in unique_label_ids:
                session.add(
                    IssueLabel(
                        issue_id=issue.id,
                        label_id=lid,
                        workspace_id=issue.workspace_id,
                    )
                )
            changes["labels"] = (None, [str(x) for x in unique_label_ids])

        elif key == "priority":
            prio_obj_id: uuid.UUID | None = None
            if isinstance(val, uuid.UUID):
                prio_obj_id = val
            elif val is not None:
                val_str = str(val).strip()
                try:
                    prio_obj_id = uuid.UUID(val_str)
                except ValueError:
                    p_stmt = select(ProjectPriority.id).where(
                        ProjectPriority.project_id == issue.project_id,
                        (ProjectPriority.slug == val_str.lower())
                        | (ProjectPriority.label.ilike(val_str)),
                    )
                    prio_obj_id = (await session.execute(p_stmt)).scalar_one_or_none()

            if prio_obj_id is not None and prio_obj_id != issue.priority_id:
                old_prio = issue.priority_id
                issue.priority_id = prio_obj_id
                changes["priority"] = (str(old_prio), str(prio_obj_id))

        elif key == "assignees":
            raw_assignees: list[Any] = list(val) if isinstance(val, (list, tuple)) else [val]
            await session.execute(delete(IssueAssignee).where(IssueAssignee.issue_id == issue.id))
            for a_item in raw_assignees:
                a_str = str(a_item).strip()
                target_p_id: uuid.UUID | None = None
                try:
                    target_p_id = uuid.UUID(a_str)
                except ValueError:
                    # Look up user by email or username
                    u_stmt = select(User.id).where(
                        User.workspace_id == issue.workspace_id,
                        User.email == a_str,
                    )
                    target_p_id = (await session.execute(u_stmt)).scalar_one_or_none()
                    if target_p_id is None:
                        # Check display_name in principals
                        pr_stmt = select(Principal.id).where(
                            Principal.workspace_id == issue.workspace_id,
                            Principal.display_name == a_str,
                        )
                        target_p_id = (await session.execute(pr_stmt)).scalar_one_or_none()

                session.add(
                    IssueAssignee(
                        workspace_id=issue.workspace_id,
                        issue_id=issue.id,
                        principal_id=target_p_id,
                        free_text_assignee=a_str if target_p_id is None else None,
                    )
                )
            changes["assignees"] = (None, raw_assignees)

        elif key == "start_date":
            old_sd = issue.start_date
            new_sd: dt.date | None = None
            if isinstance(val, dt.date):
                new_sd = val
            elif isinstance(val, str) and val.strip():
                new_sd = dt.date.fromisoformat(val.strip())
            issue.start_date = new_sd
            changes["start_date"] = (
                old_sd.isoformat() if old_sd else None,
                new_sd.isoformat() if new_sd else None,
            )

        elif key == "due_date":
            old_dd = issue.due_date
            new_dd: dt.date | None = None
            if isinstance(val, dt.date):
                new_dd = val
            elif isinstance(val, str) and val.strip():
                new_dd = dt.date.fromisoformat(val.strip())
            issue.due_date = new_dd
            changes["due_date"] = (
                old_dd.isoformat() if old_dd else None,
                new_dd.isoformat() if new_dd else None,
            )

        elif key == "cycle":
            old_cy = issue.cycle_id
            new_cy_id: uuid.UUID | None = None
            if isinstance(val, uuid.UUID):
                new_cy_id = val
            elif val is not None:
                val_str = str(val).strip()
                try:
                    new_cy_id = uuid.UUID(val_str)
                except ValueError:
                    cy_stmt = select(Cycle.id).where(
                        Cycle.project_id == issue.project_id,
                        Cycle.name.ilike(val_str),
                    )
                    new_cy_id = (await session.execute(cy_stmt)).scalar_one_or_none()

            issue.cycle_id = new_cy_id
            changes["cycle"] = (
                str(old_cy) if old_cy else None,
                str(new_cy_id) if new_cy_id else None,
            )

        elif key.startswith("custom_fields."):
            slug = key[len("custom_fields.") :]
            cf_stmt = select(CustomFieldDefinition).where(
                CustomFieldDefinition.project_id == issue.project_id,
                CustomFieldDefinition.slug == slug,
            )
            cf_def = (await session.execute(cf_stmt)).scalar_one_or_none()
            if cf_def is not None:
                cfv_stmt = select(CustomFieldValue).where(
                    CustomFieldValue.issue_id == issue.id,
                    CustomFieldValue.field_id == cf_def.id,
                )
                cfv = (await session.execute(cfv_stmt)).scalar_one_or_none()
                if cfv is None:
                    now = dt.datetime.now(dt.UTC)
                    cfv = CustomFieldValue(
                        workspace_id=issue.workspace_id,
                        project_id=issue.project_id,
                        field_id=cf_def.id,
                        issue_id=issue.id,
                        script_version=cf_def.script_version,
                        user_access_hash=b"",
                        value_json=val,
                        last_latency_ms=0,
                        expires_at=now + dt.timedelta(days=1),
                    )
                    session.add(cfv)
                else:
                    cfv.value_json = val
                changes[key] = (None, val)

    await session.flush()
    return changes
