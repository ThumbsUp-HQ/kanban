# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Admin Diagnostics and Link Inspector Studio Guide (KAN-351)."""

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
WIKI_DIR = Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
CHAPTER_SLUG = "admin-diagnostics-and-link-inspector-studio"
MARKDOWN_FILENAME = "Admin-Diagnostics-and-Link-Inspector-Studio.md"


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


def test_diagnostics_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "guide"
    assert tax["track"] == "Step-by-Step Guides"
    assert tax["subtrack"] == "Diagnostics & Maintenance"
    assert tax["audience"] == "System Administrators & Core Maintainers"


def test_diagnostics_guide_markdown_content() -> None:
    """Verify chapter title, core architecture, and operational procedures."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith(
        "# [Guide] Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough"
    )
    assert (
        meta["title"]
        == "[Guide] Admin Diagnostics and Link Inspector Studio Guide and Architecture Walkthrough"
    )
    assert meta["category"] == "guide"

    # Core architecture concepts
    assert "/admin/diagnostics" in content
    assert "/admin/link-auditor" in content
    assert "require_admin_aal2" in content
    assert "assert_admin_routes_protected" in content

    # 6 Defect Classes
    defect_classes = [
        "ORPHAN_SOURCE",
        "ORPHAN_TARGET",
        "CROSS_WORKSPACE",
        "INVALID_KIND",
        "INVERTED_DEPENDENCY",
        "DANGLING_PARENT",
    ]
    for defect in defect_classes:
        assert defect in content, f"Missing defect class {defect} in diagnostics guide"

    # Remediation & Blast-Radius
    assert "PURGE INVALID LINKS" in content
    assert "POST /api/v1/admin/link-auditor/purge" in content
    assert "audit_events" in content

    # Subsystem Probes
    assert "PostgreSQL" in content
    assert "76" in content  # 76 single-head migrations
    assert "FORCE ROW LEVEL SECURITY" in content or "FORCE RLS" in content
    assert "database/outbox/relay.py" in content
    assert "Wasmtime" in content
    assert "nsjail" in content

    # CLI diagnostics
    assert "kanban-ctl db check-migrations" in content
    assert "kanban-ctl db audit-links" in content


def test_diagnostics_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in diagnostics guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_diagnostics_guide_sections_and_anchors() -> None:
    """Verify table of contents sections and anchor slugs."""
    _, meta = load_chapter()
    section_ids = [s["id"] for s in meta["sections"]]
    assert "executive-summary-and-architecture-overview" in section_ids
    assert "universal-object-graph-link-auditor-and-inspector-studio" in section_ids
    assert "operational-runbook-inspections-and-disaster-recovery" in section_ids
