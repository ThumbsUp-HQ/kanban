"""Brand terminology and hygiene audit tests (KAN-56).

Enforces zero occurrences of competitor self-descriptions, deprecated
ScriptRunner references, and legacy transition interceptor phrasing
across UI, CSS, Python, manifests, docs, and wiki surfaces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WIKI_ROOT = Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki")

BANNED_PATTERNS: dict[str, Pattern[str]] = {
    "scriptrunner": re.compile(r"\bscriptrunner\b", re.IGNORECASE),
    "transition_interceptor": re.compile(r"\btransition\s+interceptor(s)?\b", re.IGNORECASE),
    "plane_parity": re.compile(r"plane-parity", re.IGNORECASE),
    "plane_calm": re.compile(r"plane-calm", re.IGNORECASE),
    "plane_style": re.compile(r"plane-style", re.IGNORECASE),
    "jira_plane": re.compile(r"jira/plane", re.IGNORECASE),
    "jira_surpassing": re.compile(r"jira-surpassing", re.IGNORECASE),
}

# Explicitly allowed wire identifiers or constants preserved for backward compatibility
ALLOWED_WIRE_TOKENS: set[str] = {
    "agent_interceptor",
    "manage_workflow_interceptors",
    "workflow_interceptors",
    "create_manage_workflow_interceptors_tool",
}

DEFAULT_EXCLUDED_PATHS: set[str] = {
    "docs/FEATURE_COMPARISON.md",
    "docs/CUTOVER.md",
    ".backup_schedule.json",
    "kanban/web/src/features/docs-center/wikiManifest.ts",
    "kanban/web/src/features/docs-center/__tests__/DocsCenter.test.tsx",
}


@dataclass(frozen=True)
class BrandViolation:
    """Represents a detected forbidden brand terminology occurrence."""

    file_path: str
    line_number: int
    pattern_name: str
    matched_text: str


def is_path_excluded(rel_path: str) -> bool:
    """Check if a relative path is in the authorized exclusion list."""
    norm_path = rel_path.replace("\\", "/")
    if norm_path in DEFAULT_EXCLUDED_PATHS:
        return True
    if norm_path.startswith("docs/qa/"):
        return True
    if norm_path.startswith("docs/tickets/"):
        return True
    if norm_path.startswith("kanban/importer/plane_"):
        return True
    if norm_path.startswith("thumbs-up-kanban.wiki/"):
        return True
    return bool(norm_path.endswith(("test_brand_terminology_audit.py", "test_wiki_media_audit.py")))


def line_has_only_allowed_wire_tokens(line: str, pattern_name: str) -> bool:
    """Return True if the match in the line is solely an allowed wire token."""
    if pattern_name in ("scriptrunner", "transition_interceptor"):
        for token in ALLOWED_WIRE_TOKENS:
            if token in line:
                stripped = line
                for t in ALLOWED_WIRE_TOKENS:
                    stripped = stripped.replace(t, " ")
                if not BANNED_PATTERNS[pattern_name].search(stripped):
                    return True
    return False


def scan_file_for_violations(
    file_path: Path,
    rel_path: str,
    patterns: dict[str, Pattern[str]] | None = None,
) -> list[BrandViolation]:
    """Scan a single text file against banned brand patterns."""
    if patterns is None:
        patterns = BANNED_PATTERNS

    violations: list[BrandViolation] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return violations

    for lno, line in enumerate(content.splitlines(), start=1):
        for name, pattern in patterns.items():
            if pattern.search(line):
                if line_has_only_allowed_wire_tokens(line, name):
                    continue
                violations.append(
                    BrandViolation(
                        file_path=rel_path,
                        line_number=lno,
                        pattern_name=name,
                        matched_text=line.strip()[:140],
                    )
                )
    return violations


def collect_repo_files(repo_root: Path) -> Iterable[Path]:
    """Collect relevant source, manifest, and doc files from the repo."""
    target_exts = {".py", ".ts", ".tsx", ".css", ".md", ".toml", ".json"}
    ignore_dirs = {
        ".git",
        "node_modules",
        "backups",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "thumbs-up-kanban.wiki",
    }

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_dirs for part in path.parts):
            continue
        if path.suffix in target_exts:
            yield path


class TestBrandTerminologyAudit:
    """CI gate validating zero occurrences of banned brand strings."""

    def test_scanner_unit_detects_violations_and_respects_exclusions(self, tmp_path: Path) -> None:
        """Unit test confirming scanner catches violations and excludes permitted files."""
        dirty_file = tmp_path / "dirty.md"
        dirty_file.write_text("This has ScriptRunner workflows.\n", encoding="utf-8")

        clean_file = tmp_path / "clean.md"
        clean_file.write_text("This has Scripted Workflows and Helpers.\n", encoding="utf-8")

        wire_file = tmp_path / "wire.py"
        wire_file.write_text('hook_kind = "agent_interceptor"\n', encoding="utf-8")

        v_dirty = scan_file_for_violations(dirty_file, "dirty.md")
        assert len(v_dirty) == 1
        assert v_dirty[0].pattern_name == "scriptrunner"

        v_clean = scan_file_for_violations(clean_file, "clean.md")
        assert len(v_clean) == 0

        v_wire = scan_file_for_violations(wire_file, "wire.py")
        assert len(v_wire) == 0

        assert is_path_excluded("docs/FEATURE_COMPARISON.md") is True
        assert is_path_excluded("docs/qa/KAN-56/proof.txt") is True
        assert is_path_excluded("docs/tickets/KB-P3-34.md") is True
        assert is_path_excluded("kanban/importer/plane_client.py") is True
        assert is_path_excluded("kanban/tests/docs/test_wiki_media_audit.py") is True
        assert is_path_excluded("kanban/tests/platform/test_brand_terminology_audit.py") is True
        assert is_path_excluded("kanban/web/src/features/workflows/AttachHookDialog.tsx") is False

        # Verify missing file error handling branch
        missing_file = tmp_path / "non_existent.md"
        v_missing = scan_file_for_violations(missing_file, "non_existent.md")
        assert v_missing == []

        # Verify line_has_only_allowed_wire_tokens edge cases
        assert line_has_only_allowed_wire_tokens("normal clean text", "scriptrunner") is False
        assert (
            line_has_only_allowed_wire_tokens("agent_interceptor with ScriptRunner", "scriptrunner")
            is False
        )
        assert line_has_only_allowed_wire_tokens("plane-parity rule", "plane_parity") is False
        assert (
            line_has_only_allowed_wire_tokens('wire: "agent_interceptor"', "transition_interceptor")
            is True
        )

        # Exercise collect_repo_files over sample hierarchy
        sub_dir = tmp_path / "subdir"
        sub_dir.mkdir()
        ignore_dir = tmp_path / "node_modules"
        ignore_dir.mkdir()
        (sub_dir / "test.py").write_text("x = 1\n", encoding="utf-8")
        (sub_dir / "skip.txt").write_text("ignore\n", encoding="utf-8")
        (ignore_dir / "ignored.py").write_text("x = 2\n", encoding="utf-8")
        found = list(collect_repo_files(tmp_path))
        assert any(p.name == "test.py" for p in found)
        assert not any(p.name == "ignored.py" for p in found)
        assert not any(p.name == "skip.txt" for p in found)

    def test_main_repo_has_zero_brand_terminology_violations(self) -> None:
        """Assert zero banned phrases in UI, CSS, Python, manifests, and documentation."""
        repo_root = DEFAULT_REPO_ROOT
        all_violations: list[BrandViolation] = []

        for file_path in collect_repo_files(repo_root):
            rel_path = file_path.relative_to(repo_root).as_posix()
            if is_path_excluded(rel_path):
                continue
            violations = scan_file_for_violations(file_path, rel_path)
            all_violations.extend(violations)

        error_report = "\n".join(
            f"  {v.file_path}:{v.line_number} [{v.pattern_name}] {v.matched_text}"
            for v in all_violations
        )
        assert not all_violations, (
            f"Found {len(all_violations)} brand terminology violation(s) in main repository:\n"
            f"{error_report}"
        )

    def test_wiki_repo_has_zero_brand_terminology_violations(self) -> None:
        """Assert zero banned phrases in wiki documentation outside comparison tables."""
        wiki_root = DEFAULT_WIKI_ROOT
        if not wiki_root.exists():
            pytest.skip(f"Wiki directory not found at {wiki_root}")  # pragma: no cover

        all_violations: list[BrandViolation] = []
        for file_path in sorted(wiki_root.glob("*.md")):
            name_lower = file_path.name.lower()
            if "comparison" in name_lower or "cutover" in name_lower:
                continue

            rel_path = file_path.name
            violations = scan_file_for_violations(file_path, rel_path)
            all_violations.extend(violations)

        error_report = "\n".join(
            f"  {v.file_path}:{v.line_number} [{v.pattern_name}] {v.matched_text}"
            for v in all_violations
        )
        assert not all_violations, (
            f"Found {len(all_violations)} brand terminology violation(s) in wiki repository:\n"
            f"{error_report}"
        )
