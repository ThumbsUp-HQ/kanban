# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Multi-Source Migration and Key Alias Redirects Guide (KAN-352)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.sync_wiki_bundle import CHAPTER_TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
WIKI_DIR = Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
CHAPTER_SLUG = "multi-source-migration-and-key-alias-redirects"
MARKDOWN_FILENAME = "Multi-Source-Migration-and-Key-Alias-Redirects.md"


def load_chapter() -> tuple[str, dict]:
    """Load chapter content and manifest metadata, falling back to wikiManifest.ts in CI."""
    wiki_file = WIKI_DIR / MARKDOWN_FILENAME
    content = ""
    if wiki_file.is_file():
        content = wiki_file.read_text(encoding="utf-8")

    assert MANIFEST_PATH.is_file(), f"Missing manifest at {MANIFEST_PATH}"
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    m = re.search(r"export const WIKI_CHAPTERS: WikiChapter\[\] = (\[.*?\]);", manifest_text, re.DOTALL)
    assert m, "Failed to find WIKI_CHAPTERS in wikiManifest.ts"
    chapters = json.loads(m.group(1))
    meta = next((c for c in chapters if c["slug"] == CHAPTER_SLUG), None)
    assert meta, f"Chapter '{CHAPTER_SLUG}' not found in wikiManifest.ts"

    if not content:
        content = meta["content"]
    return content, meta


def test_migration_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "guide"
    assert tax["track"] == "Step-by-Step Guides"
    assert tax["subtrack"] == "Data Migration"
    assert tax["audience"] == "Enterprise Administrators & DevOps Engineers"


def test_migration_guide_markdown_content() -> None:
    """Verify chapter title, importer capabilities, alias routing, and CSV governance."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith("# [Guide] End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide")
    assert meta["title"] == "[Guide] End-to-End Multi-Source Migration, Key Alias Redirects, and Cross-Project Merge Guide"
    assert meta["category"] == "guide"

    # Multi-source importers
    assert "Jira" in content
    assert "GitHub" in content
    assert "Linear" in content
    assert "Plane-DB" in content
    assert "export_plane_db.py" in content
    assert "Atlassian Document Format" in content or "ADF" in content

    # Key alias redirects
    assert "IssueKeyAlias" in content
    assert "issue_key_aliases" in content
    assert "p6_03_multi_source_imports_and_aliases" in content
    assert "HTTP 308 Permanent Redirect" in content or "308" in content

    # Cross-project merge
    assert "Cross-Project Merge Mode" in content
    assert "KANBA -> KAN" in content or "KANBA" in content

    # CSV governance & WinZip AE-2
    assert "16 Canonical CSV Columns" in content
    assert "CWE-1236" in content
    assert "WinZip AE-2" in content or "AES-256" in content
    assert "zeroize" in content

    # CLI commands
    assert "kanban-ctl import plane-bundle" in content


def test_migration_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in migration guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_migration_guide_sections_and_anchors() -> None:
    """Verify table of contents sections and anchor slugs."""
    _, meta = load_chapter()
    section_ids = [s["id"] for s in meta["sections"]]
    assert "multi-source-importer-architecture" in section_ids
    assert "legacy-key-alias-routing-and-permalinks" in section_ids
    assert "canonical-csv-import-export-and-winzip-aes-256-packaging" in section_ids
