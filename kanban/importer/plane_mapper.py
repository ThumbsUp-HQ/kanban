# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Lossless Plane mapper and entity transformation engine (KB-P6-01, S1.3, S5.2)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from database.models import LinkKind
from kanban.content.normalize import normalize_to_markdown

if TYPE_CHECKING:
    import uuid

    from kanban.importer.plane_client import PlaneBundle, PlaneIssue

logger = logging.getLogger(__name__)

MAX_TREE_DEPTH: int = 6


class ImportDiffReport(BaseModel):
    """Forensic diff and impact report produced by Plane import dry-run or execution."""

    to_create: int = 0
    to_update: int = 0
    unchanged: int = 0
    sequence_high_water_mark: int = 0
    unmapped_members: list[str] = Field(default_factory=list)
    rewritten_attachments: int = 0
    invalid_link_count: int = 0
    warnings: list[str] = Field(default_factory=list)


STATE_GROUP_MAP: dict[str, str] = {
    "backlog": "backlog",
    "unstarted": "unstarted",
    "started": "started",
    "completed": "completed",
    "cancelled": "cancelled",
}

PRIORITY_MAP: dict[str, str] = {
    "urgent": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "none",
}

RELATION_KIND_MAP: dict[str, LinkKind] = {
    "blocking": LinkKind.BLOCKS,
    "blocked_by": LinkKind.BLOCKED_BY,
    "relates_to": LinkKind.RELATES_TO,
    "duplicate": LinkKind.DUPLICATES,
}


def compute_source_sha256(data: BaseModel | dict[str, Any]) -> bytes:
    """Compute deterministic SHA-256 digest of entity data for idempotency checking."""
    raw_dict = data.model_dump() if isinstance(data, BaseModel) else data
    serialized = json.dumps(raw_dict, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).digest()


class _DagState:
    def __init__(self, children_map: dict[str | None, list[PlaneIssue]]) -> None:
        self.children_map = children_map
        self.visited: set[str] = set()
        self.active_branch: list[str] = []
        self.sorted_issues: list[PlaneIssue] = []

    def traverse(self, parent_key: str | None, current_depth: int) -> None:
        if current_depth > MAX_TREE_DEPTH:
            msg = (
                f"Parent hierarchy depth {current_depth} exceeds maximum allowable "
                f"depth of {MAX_TREE_DEPTH}"
            )
            raise ValueError(msg)

        for child in self.children_map.get(parent_key, []):
            if child.id in self.active_branch:
                msg = f"Parent-child cycle detected involving issue {child.id}"
                raise ValueError(msg)
            if child.id not in self.visited:
                self.visited.add(child.id)
                self.active_branch.append(child.id)
                self.sorted_issues.append(child)
                self.traverse(child.id, current_depth + 1)
                self.active_branch.pop()


class PlaneMapper:
    """Engine mapping Plane snapshot structures into Kanban universal object graph schemas."""

    def __init__(
        self,
        *,
        user_map: dict[str, str] | None = None,
        unmapped_assignees_as_free_text: bool = True,
    ) -> None:
        """Initialize PlaneMapper with mapping dictionaries and configuration flags."""
        self.user_map = user_map or {}
        self.unmapped_assignees_as_free_text = unmapped_assignees_as_free_text

    def sort_issues_topologically(
        self, issues: list[PlaneIssue]
    ) -> tuple[list[PlaneIssue], list[str]]:
        """Sort issues root-first to construct valid DAG, detecting cycles and depth > 6."""
        warnings: list[str] = []
        issue_by_id = {issue.id: issue for issue in issues}
        children_map: dict[str | None, list[PlaneIssue]] = {}

        for issue in issues:
            parent_id = issue.parent or issue.parent_id
            if parent_id and parent_id not in issue_by_id:
                warnings.append(
                    f"Issue {issue.sequence_id} references missing parent {parent_id}; "
                    "treating as root."
                )
                parent_id = None
            children_map.setdefault(parent_id, []).append(issue)

        dag = _DagState(children_map)
        dag.traverse(None, 0)

        # Check unvisited issues for cycles and append remaining
        for issue in issues:
            if issue.id not in dag.visited:
                dag.traverse(issue.id, 0)
                if issue.id not in dag.visited:
                    dag.visited.add(issue.id)
                    dag.sorted_issues.append(issue)

        return dag.sorted_issues, warnings

    def normalize_content_and_rewrite_attachments(
        self,
        raw_html_or_md: str | None,
        attachment_url_map: dict[str, uuid.UUID],
        md_attachments: dict[str, str] | None = None,
    ) -> tuple[str, int]:
        """Convert Plane HTML to canonical Markdown and rewrite inline asset links.

        Rewrites Plane/MinIO inline asset URLs before nh3 strips http:// URLs,
        and appends any associated .md attachments as collapsible blocks.
        """
        if not raw_html_or_md:
            return "", 0

        rewritten_count = 0
        preprocessed = raw_html_or_md

        # 1. Pre-rewrite Plane/MinIO inline asset URLs BEFORE nh3 sanitization
        # to ensure relative /api/v1/attachments/ endpoints are preserved
        for original_ref, att_id in attachment_url_map.items():
            canonical_path = f"/api/v1/attachments/{att_id}"
            pattern = re.compile(re.escape(original_ref))
            if pattern.search(preprocessed):
                preprocessed, count = pattern.subn(canonical_path, preprocessed)
                rewritten_count += count

        # 2. Normalize to markdown stripping hostile HTML
        markdown = normalize_to_markdown(preprocessed, mode="auto")

        # 3. Post-normalization pass for any markdown references that were not caught
        for original_ref, att_id in attachment_url_map.items():
            canonical_path = f"/api/v1/attachments/{att_id}"
            pattern = re.compile(re.escape(original_ref))
            if pattern.search(markdown):
                markdown, count = pattern.subn(canonical_path, markdown)
                rewritten_count += count

        # 4. Ingest .md attachments as collapsible Markdown blocks
        if md_attachments:
            for md_fn, md_content in md_attachments.items():
                if md_fn in raw_html_or_md or md_fn in markdown:
                    collapsible_block = (
                        f"\n\n<details>\n<summary>Attachment: {md_fn}</summary>\n\n"
                        f"{md_content}\n\n</details>"
                    )
                    if collapsible_block not in markdown:
                        markdown += collapsible_block

        return markdown, rewritten_count

    def rewrite_issue_references(
        self,
        markdown: str,
        key_remap_manifest: dict[str, str],
    ) -> str:
        """Context-aware rewrite of issue key references.

        Skips fenced code blocks (``` or ~~~), inline code spans (`...`),
        and docs/qa/ paths (e.g. docs/qa/KANBA-12/).
        """
        if not markdown or not key_remap_manifest:
            return markdown

        lines = markdown.splitlines(keepends=True)
        out_lines: list[str] = []
        in_code_fence = False

        pattern = re.compile(
            r"(docs/qa/[A-Z][A-Z0-9]{1,9}-\d+)|"
            r"(`+[^`\n]+`+)|"
            r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b"
        )

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("```", "~~~")):
                in_code_fence = not in_code_fence
                out_lines.append(line)
                continue

            if in_code_fence:
                out_lines.append(line)
                continue

            def _sub(match: re.Match[str]) -> str:
                if match.group(1):
                    # docs/qa/KEY path - preserve verbatim
                    return match.group(1)
                if match.group(2):
                    # inline code span - preserve verbatim
                    return match.group(2)
                key = match.group(3)
                return key_remap_manifest.get(key, key)

            out_lines.append(pattern.sub(_sub, line))

        return "".join(out_lines)

    def resolve_user_handle(
        self,
        plane_user_id: str | None,
        bundle: PlaneBundle,
    ) -> tuple[str, bool]:
        """Resolve Plane user to target workspace handle.

        Returns:
            Tuple of (handle, is_unmapped_placeholder).

        """
        if not plane_user_id:
            return "system", False

        if plane_user_id in self.user_map:
            target_handle = self.user_map[plane_user_id].lstrip("@")
            return target_handle, False

        # Check bundle members for email or name to form deterministic placeholder
        short_id = plane_user_id[:8]
        for m in bundle.members:
            if m.id == plane_user_id:
                if m.email:
                    prefix = m.email.split("@")[0].lower()
                    clean_prefix = re.sub(r"[^a-z0-9_-]", "-", prefix)
                    return f"plane-import-{clean_prefix[:16]}", True
                break

        return f"plane-import-{short_id}", True
