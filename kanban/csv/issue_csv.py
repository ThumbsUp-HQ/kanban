# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Canonical RFC 4180 CSV schema, CWE-1236 defense, and template generator for issues (KAN-316)."""

from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from database.models import (
    Cycle,
    Issue,
    Module,
    Project,
    ProjectLabel,
    ProjectPriority,
    WorkflowState,
)
from kanban.api.v1.schemas.issues import IssueCreate, IssuePatch
from kanban.content.normalize import ContentNormalizeError, normalize_to_markdown
from kanban.content.unicode_guard import SURROGATE_MAX, SURROGATE_MIN
from kanban.security.push_protection import (
    PushProtectionMode,
    enforce_secret_push_protection,
)
from kanban.services import issues as issue_svc

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.api.deps import PrincipalContext

logger = logging.getLogger(__name__)

CSV_COLUMNS: Final[list[str]] = [
    "key",
    "project_key",
    "summary",
    "description_markdown",
    "state",
    "priority",
    "assignees",
    "labels",
    "cycle",
    "modules",
    "parent_key",
    "start_date",
    "due_date",
    "created_at",
    "updated_at",
    "custom_fields_json",
]

FORMULA_TRIGGERS: Final[tuple[str, ...]] = ("=", "+", "-", "@", "\t", "\r")


class ImportRowError(BaseModel):
    """Validation or integrity error encountered during CSV issue import."""

    model_config = ConfigDict(extra="ignore")

    row: int = 0
    row_number: int = 0
    column: str | None = None
    message: str = ""


class CsvImportDiffReport(BaseModel):
    """Forensic diff and validation report for issue CSV import preview or execution."""

    model_config = ConfigDict(extra="ignore")

    dry_run: bool = True
    total_rows: int = 0
    to_create: int = 0
    to_update: int = 0
    creates_count: int = 0
    updates_count: int = 0
    error_count: int = 0
    unchanged: int = 0
    created_keys: list[str] = Field(default_factory=list)
    updated_keys: list[str] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[ImportRowError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_no_surrogates(text_val: str) -> None:
    """Reject hostile Unicode UTF-16 lone surrogates (0xD800..0xDFFF)."""
    for char in text_val:
        cp = ord(char)
        if SURROGATE_MIN <= cp <= SURROGATE_MAX:
            msg = "INVALID_UTF8_SURROGATE"
            raise ContentNormalizeError(msg)


def sanitize_cell_for_export(val: object) -> str:
    """Neutralize CWE-1236 formula injection when writing cells to CSV."""
    if val is None:
        return ""
    text_val = "; ".join(str(x) for x in val) if isinstance(val, (list, tuple, set)) else str(val)
    if text_val and text_val[0] in FORMULA_TRIGGERS:
        return f"'{text_val}"
    return text_val


def desanitize_cell_from_import(val: str) -> str:
    """Strip leading formula defense quote when reading imported CSV cells."""
    if val.startswith("'") and len(val) > 1 and val[1] in FORMULA_TRIGGERS:
        return val[1:]
    return val


def generate_issue_import_template(
    project_key: str,
    state_names: list[str] | None = None,
    priority_names: list[str] | None = None,
) -> str:
    """Generate a canonical RFC 4180 CSV import template pre-populated with project metadata."""
    effective_states = state_names or ["Backlog", "Todo", "In Progress", "Done"]
    effective_priorities = priority_names or ["medium", "high", "urgent", "low"]

    state_example_1 = effective_states[0]
    state_example_2 = effective_states[1] if len(effective_states) > 1 else effective_states[0]

    prio_example_1 = effective_priorities[0]
    prio_example_2 = (
        effective_priorities[1] if len(effective_priorities) > 1 else effective_priorities[0]
    )

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    today_str = datetime.now(UTC).date().isoformat()

    # Sample Row 1 (new issue creation example)
    writer.writerow(
        [
            "",  # key empty for new issue
            project_key,
            sanitize_cell_for_export("Integrate single sign-on authentication card"),
            sanitize_cell_for_export(
                "## Objective\nConfigure corporate OIDC provider with PKCE and AAL2 step-up."
            ),
            state_example_1,
            prio_example_1,
            "@alice, @bob",
            "security, backend",
            "Sprint 1",
            "Authentication",
            "",  # parent_key
            today_str,
            today_str,
            "",  # created_at
            "",  # updated_at
            "{}",
        ]
    )

    # Sample Row 2 (feature with parent and due date)
    writer.writerow(
        [
            "",  # key empty
            project_key,
            sanitize_cell_for_export("Add biometric WebAuthn security keys support"),
            sanitize_cell_for_export(
                "Implement passkey registration and verification according to FIDO2 guidelines."
            ),
            state_example_2,
            prio_example_2,
            "@charlie",
            "auth, passkey",
            "Sprint 1",
            "Authentication",
            f"{project_key}-1",  # parent_key example
            today_str,
            today_str,
            "",
            "",
            '{"compliance": "SOC2"}',
        ]
    )

    return output.getvalue()


def export_issues_to_csv(issues_rows: list[dict[str, Any]]) -> str:
    """Serialize list of issue row dictionaries to canonical UTF-8 RFC 4180 CSV."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)

    for item in issues_rows:
        row = [
            sanitize_cell_for_export(item.get("key", "")),
            sanitize_cell_for_export(item.get("project_key", "")),
            sanitize_cell_for_export(item.get("summary", "")),
            sanitize_cell_for_export(item.get("description_markdown", "")),
            sanitize_cell_for_export(item.get("state", "")),
            sanitize_cell_for_export(item.get("priority", "")),
            sanitize_cell_for_export(item.get("assignees", "")),
            sanitize_cell_for_export(item.get("labels", "")),
            sanitize_cell_for_export(item.get("cycle", "")),
            sanitize_cell_for_export(item.get("modules", "")),
            sanitize_cell_for_export(item.get("parent_key", "")),
            sanitize_cell_for_export(item.get("start_date", "")),
            sanitize_cell_for_export(item.get("due_date", "")),
            sanitize_cell_for_export(item.get("created_at", "")),
            sanitize_cell_for_export(item.get("updated_at", "")),
            sanitize_cell_for_export(item.get("custom_fields_json", "{}")),
        ]
        writer.writerow(row)

    return output.getvalue()


def parse_issues_from_csv(raw_csv: str | bytes) -> list[dict[str, str]]:
    """Parse raw CSV input into list of column-mapped dictionaries with surrogate validation."""
    text_content = raw_csv.decode("utf-8") if isinstance(raw_csv, bytes) else raw_csv

    validate_no_surrogates(text_content)

    reader = csv.reader(io.StringIO(text_content))
    header: list[str] | None = None
    rows: list[dict[str, str]] = []

    for _row_idx, row in enumerate(reader, start=1):
        if not row or all(not cell.strip() for cell in row):
            continue
        if header is None:
            header = [col.strip().lower() for col in row]
            continue

        row_dict: dict[str, str] = {}
        for col_name, cell_val in zip(header, row, strict=False):
            row_dict[col_name] = desanitize_cell_from_import(cell_val.strip())
        rows.append(row_dict)

    return rows


async def process_issue_import(  # noqa: C901, PLR0912, PLR0915
    session: AsyncSession,
    caller: PrincipalContext,
    project: Project,
    rows: list[dict[str, str]],
    *,
    dry_run: bool = True,
) -> CsvImportDiffReport:
    """Process parsed CSV rows into created or updated issues under savepoint rollback or commit."""
    report = CsvImportDiffReport(dry_run=dry_run, total_rows=len(rows))

    # Pre-fetch project workflows, priorities, cycles, modules, labels for resolution
    state_res = await session.execute(
        select(WorkflowState).where(WorkflowState.project_id == project.id)
    )
    states = list(state_res.scalars().all())
    state_by_name = {s.name.lower(): s for s in states}
    default_state = next((s for s in states if s.is_default), states[0] if states else None)

    prio_res = await session.execute(
        select(ProjectPriority).where(ProjectPriority.project_id == project.id)
    )
    priorities = list(prio_res.scalars().all())
    prio_by_name = {p.slug.lower(): p for p in priorities}
    prio_by_label = {p.label.lower(): p for p in priorities}
    default_prio = next(
        (p for p in priorities if p.is_default), priorities[0] if priorities else None
    )

    label_res = await session.execute(
        select(ProjectLabel).where(ProjectLabel.project_id == project.id)
    )
    labels_by_name = {lbl.name.lower(): lbl for lbl in label_res.scalars().all()}

    cycle_res = await session.execute(select(Cycle).where(Cycle.project_id == project.id))
    cycles_by_name = {c.name.lower(): c for c in cycle_res.scalars().all()}

    mod_res = await session.execute(select(Module).where(Module.project_id == project.id))
    modules_by_name = {m.name.lower(): m for m in mod_res.scalars().all()}

    savepoint = await session.begin_nested()

    for idx, row in enumerate(rows, start=2):  # row 1 is header
        summary_raw = row.get("summary", "").strip()
        if not summary_raw:
            report.errors.append(
                ImportRowError(row=idx, column="summary", message="Summary is required")
            )
            continue

        try:
            validate_no_surrogates(summary_raw)
            enforce_secret_push_protection(
                summary_raw, field="summary", mode=PushProtectionMode.BLOCK
            )
        except Exception as exc:  # noqa: BLE001
            report.errors.append(ImportRowError(row=idx, column="summary", message=str(exc)))
            continue

        desc_raw = row.get("description_markdown", "")
        try:
            validate_no_surrogates(desc_raw)
            enforce_secret_push_protection(
                desc_raw, field="description_markdown", mode=PushProtectionMode.BLOCK
            )
            norm_desc = normalize_to_markdown(desc_raw) if desc_raw else ""
        except Exception as exc:  # noqa: BLE001
            report.errors.append(
                ImportRowError(row=idx, column="description_markdown", message=str(exc))
            )
            continue

        # Resolve State
        state_str = row.get("state", "").strip().lower()
        if state_str:
            matched_state = state_by_name.get(state_str)
            if matched_state is None:
                report.errors.append(
                    ImportRowError(
                        row=idx,
                        column="state",
                        message=f"Workflow state '{row.get('state')}' not found",
                    )
                )
                continue
        else:
            matched_state = default_state

        # Resolve Priority
        prio_str = row.get("priority", "").strip().lower()
        if prio_str:
            matched_prio = prio_by_name.get(prio_str) or prio_by_label.get(prio_str)
            if matched_prio is None:
                report.errors.append(
                    ImportRowError(
                        row=idx,
                        column="priority",
                        message=f"Priority '{row.get('priority')}' not found",
                    )
                )
                continue
        else:
            matched_prio = default_prio

        # Dates
        start_d: date | None = None
        due_d: date | None = None
        if row.get("start_date", "").strip():
            try:
                start_d = date.fromisoformat(row["start_date"].strip())
            except ValueError:
                report.errors.append(
                    ImportRowError(
                        row=idx, column="start_date", message="Invalid start_date format"
                    )
                )
                continue
        if row.get("due_date", "").strip():
            try:
                due_d = date.fromisoformat(row["due_date"].strip())
            except ValueError:
                report.errors.append(
                    ImportRowError(row=idx, column="due_date", message="Invalid due_date format")
                )
                continue
        if start_d and due_d and due_d < start_d:
            report.errors.append(
                ImportRowError(
                    row=idx, column="due_date", message="due_date cannot be earlier than start_date"
                )
            )
            continue

        # Cycle
        cycle_str = row.get("cycle", "").strip().lower()
        matched_cycle = cycles_by_name.get(cycle_str) if cycle_str else None

        # Labels
        target_label_ids: list[uuid.UUID] = []
        raw_labels = [lbl.strip() for lbl in row.get("labels", "").split(",") if lbl.strip()]
        for lbl_name in raw_labels:
            existing_lbl = labels_by_name.get(lbl_name.lower())
            if existing_lbl:
                target_label_ids.append(existing_lbl.id)

        # Modules
        target_mod_ids: list[uuid.UUID] = []
        raw_modules = [m.strip() for m in row.get("modules", "").split(",") if m.strip()]
        for mod_name in raw_modules:
            existing_mod = modules_by_name.get(mod_name.lower())
            if existing_mod:
                target_mod_ids.append(existing_mod.id)

        # Parent Key
        parent_key = row.get("parent_key", "").strip()

        issue_key = row.get("key", "").strip()

        # Check if existing issue by key
        existing_issue: Issue | None = None
        if issue_key:
            seq_val = (
                int(issue_key.split("-")[-1])
                if "-" in issue_key and issue_key.split("-")[-1].isdigit()
                else -1
            )
            res = await session.execute(
                select(Issue).where(
                    Issue.project_id == project.id,
                    Issue.sequence_id == seq_val,
                )
            )
            existing_issue = res.scalar_one_or_none()

        if existing_issue:
            # Update path
            if not dry_run:
                patch_payload = IssuePatch(
                    summary=summary_raw,
                    description_markdown=norm_desc,
                    state_id=matched_state.id if matched_state else None,
                    priority=matched_prio.id if matched_prio else None,
                    start_date=start_d,
                    due_date=due_d,
                    cycle_id=matched_cycle.id if matched_cycle else None,
                    label_ids=target_label_ids or None,
                    module_ids=target_mod_ids or None,
                )
                if_match = (
                    existing_issue.description_sha256.hex()
                    if existing_issue.description_sha256
                    else str(existing_issue.row_version)
                )
                await issue_svc.update_issue(
                    session, caller, issue_key, patch_payload, if_match=if_match
                )
            report.to_update += 1
            report.updated_keys.append(issue_key)
            report.items.append(
                {
                    "row_number": idx,
                    "action": "update",
                    "key": issue_key,
                    "summary": summary_raw,
                    "state": matched_state.name if matched_state else "",
                    "priority": matched_prio.slug if matched_prio else "",
                }
            )
        else:
            # Create path
            if not dry_run:
                create_payload = IssueCreate(
                    summary=summary_raw,
                    description_markdown=norm_desc,
                    state_id=matched_state.id if matched_state else None,
                    priority=matched_prio.id if matched_prio else None,
                    start_date=start_d,
                    due_date=due_d,
                    cycle_id=matched_cycle.id if matched_cycle else None,
                    parent=parent_key or None,
                    label_ids=target_label_ids or None,
                    module_ids=target_mod_ids or None,
                )
                created, _ = await issue_svc.create_issue(
                    session, caller, project.identifier, create_payload
                )
                report.created_keys.append(created.key)
                report.items.append(
                    {
                        "row_number": idx,
                        "action": "create",
                        "key": created.key,
                        "summary": summary_raw,
                        "state": matched_state.name if matched_state else "",
                        "priority": matched_prio.slug if matched_prio else "",
                    }
                )
            else:
                sim_key = f"{project.identifier}-{project.issue_seq_counter + report.to_create + 1}"
                report.created_keys.append(sim_key)
                report.items.append(
                    {
                        "row_number": idx,
                        "action": "create",
                        "key": sim_key,
                        "summary": summary_raw,
                        "state": matched_state.name if matched_state else "",
                        "priority": matched_prio.slug if matched_prio else "",
                    }
                )
            report.to_create += 1

    report.creates_count = report.to_create
    report.updates_count = report.to_update
    report.error_count = len(report.errors)

    if dry_run or report.errors:
        await savepoint.rollback()
    else:
        await savepoint.commit()

    return report
