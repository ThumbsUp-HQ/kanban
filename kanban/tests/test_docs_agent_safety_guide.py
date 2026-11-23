# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Push Protection (KAN-355)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.sync_wiki_bundle import CHAPTER_TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
WIKI_DIR = Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
CHAPTER_SLUG = "agent-lease-fencing-workpads-and-push-protection"
MARKDOWN_FILENAME = "Agent-Lease-Fencing-Workpads-and-Push-Protection.md"


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


def test_agent_safety_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "architectural"
    assert tax["track"] == "Engineering & Security Architecture"
    assert tax["subtrack"] == "Agent Systems Architecture"
    assert tax["audience"] == "AI Platform Architects & Autonomous Agent Developers"


def test_agent_safety_guide_markdown_content() -> None:
    """Verify chapter title, issue leases, monotonic fencing, workpads, rework breaker, and push protection."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith("# [Architectural] Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide")
    assert meta["title"] == "[Architectural] Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide"
    assert meta["category"] == "architectural"

    # Multi-agent coordination challenges
    assert "Split-Brain" in content
    assert "Zombie" in content
    assert "Comment" in content
    assert "Rework" in content

    # Issue leases & monotonic fencing
    assert "fencing_token" in content
    assert "lease_expires_at" in content
    assert "Compare-And-Swap" in content or "CAS" in content
    assert "409 LEASE_CONFLICT" in content or "LEASE_CONFLICT" in content

    # Workpads & Rework Circuit Breaker
    assert "issue_workpads" in content
    assert "update_workpad" in content
    assert "65,536" in content or "65536" in content
    assert "max_rework_attempts" in content
    assert "rework_rejection_streak" in content
    assert "409 REWORK_LOOP_LIMIT_EXCEEDED" in content
    assert "POST /api/v1/issues/{key}/reset-rework-breaker" in content

    # Secret Push-Protection
    assert "Shannon" in content
    assert "4.5" in content  # entropy threshold
    assert "Exemptions" in content
    assert "UUID" in content
    assert "AWS" in content
    assert "GitHub" in content


def test_agent_safety_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in agent safety guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_agent_safety_guide_sections_and_anchors() -> None:
    """Verify table of contents sections and anchor slugs."""
    _, meta = load_chapter()
    section_ids = [s["id"] for s in meta["sections"]]
    assert "the-autonomous-multi-agent-coordination-challenge" in section_ids
    assert "postgresql-issue-leases-and-monotonic-fencing-tokens" in section_ids
    assert "dedicated-issue-workpads-and-rework-circuit-breakers" in section_ids
    assert "synchronous-pre-persistence-secret-push-protection" in section_ids
