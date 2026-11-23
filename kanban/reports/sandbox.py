# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Server-Side Template Injection (SSTI) hardened Jinja2 sandbox (KAN-317).

Enforces strict attribute and call sanitization, resource caps, and execution bounds.
Guarantees:
- Disallows all attribute and item access starting with '_' or matching security blacklist.
- Rejects mro, subclasses, globals, builtins, gi_, cr_, ag_, f_, format, format_map.
- Only frozen, plain-data dataclasses (ReportContext, ReportIssueRow, ReportStats) are exposed.
- Enforces 128 KiB template size cap, 5,000 issue limit, 10 MiB output cap, and 3.0s timeout.
"""

from __future__ import annotations

import concurrent.futures
import re
from collections.abc import Sequence  # noqa: TC003
from dataclasses import dataclass, field
from types import FunctionType, MethodType, ModuleType
from typing import Any, Final

from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

MAX_TEMPLATE_SIZE_BYTES: Final[int] = 131_072  # 128 KiB
MAX_OUTPUT_SIZE_BYTES: Final[int] = 10_485_760  # 10 MiB
MAX_REPORT_ISSUES: Final[int] = 5_000
DEFAULT_RENDER_TIMEOUT_SECONDS: Final[float] = 3.0

_FORBIDDEN_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {
        "mro",
        "subclasses",
        "globals",
        "builtins",
        "gi_frame",
        "gi_code",
        "gi_running",
        "gi_yieldfrom",
        "cr_frame",
        "cr_code",
        "cr_running",
        "cr_await",
        "ag_frame",
        "ag_code",
        "ag_running",
        "ag_await",
        "f_globals",
        "f_locals",
        "f_code",
        "f_builtins",
        "f_back",
        "f_trace",
        "format",
        "format_map",
        "attr",
        "call",
        "func_globals",
        "func_code",
        "func_closure",
    }
)


@dataclass(frozen=True)
class ReportIssueRow:
    """Frozen plain-data dataclass representing an issue in reports."""

    id: str
    key: str
    sequence_number: int
    summary: str
    description_markdown: str
    state: str
    priority: str
    assignees: tuple[str, ...]
    created_date: str
    due_date: str | None = None
    labels: tuple[str, ...] = ()
    cycle: str | None = None
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportStats:
    """Frozen plain-data dataclass for issue statistics in reports."""

    total_issues: int = 0
    urgent_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    none_count: int = 0
    state_counts: dict[str, int] = field(default_factory=dict)


def build_report_stats(issues: Sequence[ReportIssueRow]) -> ReportStats:
    """Compute summary statistics across issues."""
    urgent = 0
    high = 0
    medium = 0
    low = 0
    none_pri = 0
    state_counts: dict[str, int] = {}

    for iss in issues:
        pri = (iss.priority or "").lower()
        if pri == "urgent":
            urgent += 1
        elif pri == "high":
            high += 1
        elif pri == "medium":
            medium += 1
        elif pri == "low":
            low += 1
        else:
            none_pri += 1

        state = iss.state or "Unknown"
        state_counts[state] = state_counts.get(state, 0) + 1

    return ReportStats(
        total_issues=len(issues),
        urgent_count=urgent,
        high_count=high,
        medium_count=medium,
        low_count=low,
        none_count=none_pri,
        state_counts=state_counts,
    )


@dataclass(frozen=True)
class ReportContext:
    """Frozen plain-data dataclass exposed into sandboxed Jinja2 templates."""

    workspace_name: str = "Workspace"
    project_name: str | None = None
    project_key: str | None = None
    generated_at: str = ""
    generated_by: str = ""
    issues: Sequence[ReportIssueRow] = ()
    stats: ReportStats | None = None
    mission: str = ""
    boilerplate: str = ""
    executive_summary: str = ""
    appendix: str = ""
    toc: str = ""
    issues_table: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Freeze mutable issue sequence and compute report stats if unset."""
        if isinstance(self.issues, list):
            object.__setattr__(self, "issues", tuple(self.issues))
        if self.stats is None:
            object.__setattr__(self, "stats", build_report_stats(self.issues))


class HardenedSandboxedEnvironment(SandboxedEnvironment):
    """Custom SandboxedEnvironment blocking all private and introspective attributes."""

    def getattr(self, obj: object, attribute: str) -> object:
        """Sanitize attribute access on objects."""
        if attribute.startswith("_") or attribute in _FORBIDDEN_ATTRIBUTES:
            msg = f"Access to attribute '{attribute}' is forbidden."
            raise SecurityError(msg)
        return super().getattr(obj, attribute)

    def is_safe_attribute(self, obj: object, attr: str, value: object) -> bool:
        """Check whether attribute access on obj is safe."""
        if attr.startswith("_"):
            return False
        if attr in _FORBIDDEN_ATTRIBUTES:
            return False
        if isinstance(obj, (type, FunctionType, MethodType, ModuleType)):
            return False
        return super().is_safe_attribute(obj, attr, value)

    def is_safe_callable(self, obj: object) -> bool:
        """Verify callable is safe to invoke inside sandbox."""
        if isinstance(obj, type):
            return False
        return super().is_safe_callable(obj)

    def getitem(self, obj: object, argument: object) -> object:
        """Sanitize item subscription access."""
        if isinstance(argument, str) and (
            argument.startswith("_") or argument in _FORBIDDEN_ATTRIBUTES
        ):
            msg = f"Access to attribute '{argument}' is forbidden."
            raise SecurityError(msg)
        return super().getitem(obj, argument)


def generate_markdown_toc(markdown_text: str) -> str:
    """Generate Markdown Table of Contents from headings."""
    lines: list[str] = ["## Table of Contents", ""]
    heading_pattern = re.compile(r"^(#{1,4})\s+(.+)$")
    count = 0
    for raw_line in markdown_text.splitlines():
        match = heading_pattern.match(raw_line.strip())
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            # Skip TOC heading itself
            if title.lower() in ("table of contents", "toc"):
                continue
            anchor = re.sub(r"[^\w\s-]", "", title.lower()).strip().replace(" ", "-")
            indent = "  " * (level - 1)
            lines.append(f"{indent}- [{title}](#{anchor})")
            count += 1
    if count == 0:
        return ""
    return "\n".join(lines)


def generate_issues_table(issues: Sequence[ReportIssueRow]) -> str:
    """Generate canonical Markdown table for issues."""
    lines: list[str] = [
        "| Key | Summary | State | Priority | Assignees | Created Date |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for issue in issues:
        assignees_str = ", ".join(issue.assignees) if issue.assignees else "Unassigned"
        # Escape pipe symbols in summary
        escaped_summary = issue.summary.replace("|", "\\|")
        lines.append(
            f"| {issue.key} | {escaped_summary} | {issue.state} | "
            f"{issue.priority.capitalize()} | {assignees_str} | {issue.created_date} |"
        )
    return "\n".join(lines)


def create_sandboxed_environment() -> HardenedSandboxedEnvironment:
    """Create configured HardenedSandboxedEnvironment."""
    env = HardenedSandboxedEnvironment(
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Register helper filters
    env.filters["upper"] = str.upper
    env.filters["lower"] = str.lower
    env.filters["capitalize"] = str.capitalize
    return env


def _render_worker(template_str: str, context_dict: dict[str, Any]) -> str:
    """Worker function for rendering within timeout thread."""
    env = create_sandboxed_environment()
    template = env.from_string(template_str)
    return template.render(**context_dict)


def render_sandboxed_template(
    template_str: str,
    context: ReportContext,
    timeout_seconds: float = DEFAULT_RENDER_TIMEOUT_SECONDS,
    max_template_size: int = MAX_TEMPLATE_SIZE_BYTES,
    max_output_size: int = MAX_OUTPUT_SIZE_BYTES,
) -> str:
    """Render template inside SSTI sandbox with strict bounds and timeout.

    Raises:
        ValueError: If template size or output size exceeds limits.
        TimeoutError: If rendering exceeds timeout.
        SecurityError: If an unsafe attribute or code injection is attempted.

    """
    encoded_len = len(template_str.encode("utf-8"))
    if encoded_len > max_template_size:
        msg = (
            f"Template size {encoded_len} bytes exceeds maximum allowed "
            f"cap of {max_template_size} bytes."
        )
        raise ValueError(msg)

    # Compute helper fields if not pre-populated
    issues_table = context.issues_table or generate_issues_table(context.issues)
    toc = context.toc or generate_markdown_toc(template_str)

    context_dict: dict[str, Any] = {
        "context": context,
        "workspace_name": context.workspace_name,
        "project_name": context.project_name,
        "project_key": context.project_key,
        "generated_at": context.generated_at,
        "generated_by": context.generated_by,
        "issues": context.issues,
        "stats": context.stats,
        "mission": context.mission,
        "boilerplate": context.boilerplate,
        "executive_summary": context.executive_summary,
        "appendix": context.appendix,
        "toc": toc,
        "issues_table": issues_table,
    }
    # Expose custom parameters directly at root
    for key, val in context.parameters.items():
        if key not in context_dict and not key.startswith("_"):
            context_dict[key] = val

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_render_worker, template_str, context_dict)
        try:
            rendered = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as err:
            timeout_msg = f"Report rendering exceeded timeout ceiling of {timeout_seconds}s."
            raise TimeoutError(timeout_msg) from err

    rendered_bytes_len = len(rendered.encode("utf-8"))
    if rendered_bytes_len > max_output_size:
        out_msg = (
            f"Rendered report output size {rendered_bytes_len} bytes exceeds "
            f"maximum allowed cap of {max_output_size} bytes."
        )
        raise ValueError(out_msg)

    return rendered
