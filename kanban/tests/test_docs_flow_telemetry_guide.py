# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Statistical Flow Telemetry and Lean Analytics Guide (KAN-354)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.sync_wiki_bundle import CHAPTER_TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
WIKI_DIR = Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
CHAPTER_SLUG = "statistical-flow-telemetry-and-lean-analytics"
MARKDOWN_FILENAME = "Statistical-Flow-Telemetry-and-Lean-Analytics.md"


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


def test_flow_telemetry_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "informational"
    assert tax["track"] == "Feature & Field Reference"
    assert tax["subtrack"] == "Flow Telemetry & Analytics"
    assert tax["audience"] == "Engineering Leads, Product Managers & Scrum Masters"


def test_flow_telemetry_guide_markdown_content() -> None:
    """Verify chapter title, Little's Law, CFD engine, percentiles, and Monte Carlo forecasting."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith("# [Informational] Statistical Flow Telemetry, Lead Time Percentiles, and Monte Carlo Forecasting Guide")
    assert meta["title"] == "[Informational] Statistical Flow Telemetry, Lead Time Percentiles, and Monte Carlo Forecasting Guide"
    assert meta["category"] == "informational"

    # Little's Law & Lean foundations
    assert "Little's Law" in content
    assert "WIP" in content
    assert "Throughput" in content
    assert "Lead Time" in content

    # CFD engine & state groups
    assert "Cumulative Flow Diagram" in content or "CFD" in content
    assert "activity_events" in content
    state_groups = ["backlog", "unstarted", "started", "completed", "cancelled"]
    for grp in state_groups:
        assert grp in content, f"Missing state group {grp} in flow telemetry guide"

    # Percentiles
    assert "p50" in content
    assert "p85" in content
    assert "p95" in content

    # Aging WIP
    assert "Aging WIP" in content

    # Monte Carlo simulation
    assert "Monte Carlo" in content
    assert "10,000" in content or "10000" in content
    assert "bootstrap resampling" in content.lower()

    # REST API
    assert "GET /api/v1/projects/{project_ref}/analytics/flow" in content


def test_flow_telemetry_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in flow telemetry guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_flow_telemetry_guide_sections_and_anchors() -> None:
    """Verify table of contents sections and anchor slugs."""
    _, meta = load_chapter()
    section_ids = [s["id"] for s in meta["sections"]]
    assert "lean-flow-principles-and-littles-law-foundation" in section_ids
    assert "cumulative-flow-diagram-cfd-engine" in section_ids
    assert "monte-carlo-probabilistic-delivery-forecasting" in section_ids
