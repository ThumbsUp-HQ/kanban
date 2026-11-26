# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Custom Fields Studio and Sandboxed Execution Guide (KAN-429)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from scripts.sync_wiki_bundle import CHAPTER_TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
)
WIKI_DIR = (
    Path("thumbs-up-kanban.wiki")
    if Path("thumbs-up-kanban.wiki").is_dir()
    else Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
)
CHAPTER_SLUG = "guide-custom-fields"
MARKDOWN_FILENAME = "Guide-Custom-Fields.md"


def load_chapter() -> tuple[str, dict[str, Any]]:
    """Load chapter content and manifest metadata, falling back to wikiManifest.ts in CI."""
    wiki_file = WIKI_DIR / MARKDOWN_FILENAME
    content = ""
    if wiki_file.is_file():
        content = wiki_file.read_text(encoding="utf-8")

    assert MANIFEST_PATH.is_file(), f"Missing manifest at {MANIFEST_PATH}"
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    m = re.search(
        r"export const WIKI_CHAPTERS: WikiChapter\[\] = (\[.*?\]);", manifest_text, re.DOTALL
    )
    assert m, "Failed to find WIKI_CHAPTERS in wikiManifest.ts"
    chapters = json.loads(m.group(1))
    meta = next((c for c in chapters if c["slug"] == CHAPTER_SLUG), None)
    assert meta, f"Chapter '{CHAPTER_SLUG}' not found in wikiManifest.ts"

    if not content:
        content = meta["content"]
    return content, meta


def test_custom_fields_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "guide"
    assert tax["track"] == "Step-by-Step Guides"
    assert tax["subtrack"] == "Custom Fields"
    assert tax["audience"] == "Project & Workspace Admins"


def test_custom_fields_guide_markdown_content() -> None:
    """Verify chapter title, execution tiers, output formats, and dual-control escalation."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith("# [Guide] How to Use Custom Fields")
    assert meta["title"] == "[Guide] How to Use Custom Fields"
    assert meta["category"] == "guide"

    # Core execution tiers
    assert "scalar" in content.lower()
    assert "formula" in content.lower()
    assert "wasm" in content.lower() or "wasmtime" in content.lower()
    assert "nsjail" in content.lower()

    # Standalone vs Multi-Container Compose gating
    assert "SANDBOX_UNAVAILABLE_IN_STANDALONE" in content
    assert (
        "Multi-Container Compose Required" in content
        or "multi-container compose" in content.lower()
    )

    # 7 Canonical Output Formats
    output_formats = [
        "text",
        "number",
        "badge",
        "severity_pill",
        "url",
        "markdown_snippet",
        "json_table",
    ]
    for fmt in output_formats:
        assert fmt in content, f"Missing output format {fmt} in custom fields guide"

    # Dual-Control & Scope Escalation
    assert "PROJECT" in content
    assert "WORKSPACE" in content
    assert "SERVER" in content
    assert "AAL2" in content
    assert "INVOKING_USER" in content
    assert "PROJECT_ADMIN_SP" in content
    assert "SERVER_ADMIN_SP" in content


def test_custom_fields_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in custom fields guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_custom_fields_guide_sections_and_anchors() -> None:
    """Verify field editor help anchors exist as real markdown heading slugs."""
    content, _ = load_chapter()
    required_anchors = [
        "display-name",
        "slug",
        "flavors",
        "output-formats",
        "format-metadata",
        "script-source",
        "sandbox-tier",
        "target-scope",
        "credential-mode",
        "egress-allowlist",
        "aal2-stepup",
        "approvals",
    ]
    raw_headings = re.findall(r"^#{2,4}\s+(.+)$", content, re.MULTILINE)
    heading_slugs: set[str] = set()
    for h in raw_headings:
        clean = re.sub(r"^[0-9]+\.\s*", "", h).strip().lower()
        clean = re.sub(r"[^a-z0-9\s_-]", "", clean)
        clean = re.sub(r"[\s_]+", "-", clean).strip("-")
        if clean:
            heading_slugs.add(clean)
    for anchor in required_anchors:
        assert anchor in heading_slugs, (
            f"Missing required heading slug '{anchor}' in custom fields guide."
        )
