# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for Zero-Trust Service Auth and Workload OIDC Guide (KAN-353)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from scripts.sync_wiki_bundle import CHAPTER_TAXONOMY

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
WIKI_DIR = Path(os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki"))
CHAPTER_SLUG = "zero-trust-service-auth-and-workload-oidc"
MARKDOWN_FILENAME = "Zero-Trust-Service-Auth-and-Workload-OIDC.md"


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


def test_service_auth_guide_taxonomy() -> None:
    """Assert chapter is correctly registered in taxonomy."""
    assert CHAPTER_SLUG in CHAPTER_TAXONOMY
    tax = CHAPTER_TAXONOMY[CHAPTER_SLUG]
    assert tax["category"] == "architectural"
    assert tax["track"] == "Engineering & Security Architecture"
    assert tax["subtrack"] == "Security Architecture"
    assert tax["audience"] == "Security Architects & Application Engineers"


def test_service_auth_guide_markdown_content() -> None:
    """Verify chapter title, HKDF service authentication, workload OIDC, and CredentialBoundary."""
    content, meta = load_chapter()

    # Title verification
    assert content.startswith("# [Architectural] Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide")
    assert meta["title"] == "[Architectural] Zero-Trust Service Auth, Headless Workload OIDC, and CredentialBoundary Enforcement Guide"
    assert meta["category"] == "architectural"

    # HKDF-HMAC service authentication
    assert "HKDF-SHA256" in content or "HKDF" in content
    assert "master_kek" in content
    assert "canonical request envelope" in content.lower() or "canonical request" in content.lower()
    assert "300" in content  # clock drift
    assert "hmac.compare_digest" in content
    assert "client_cert" in content

    # Headless Workload OIDC (RFC 8693)
    assert "RFC 8693" in content
    assert "workload_identity_policies" in content
    assert "workload_jti_replays" in content
    assert "RS256" in content
    assert "POST /oauth/token" in content
    assert "grant_type=urn:ietf:params:oauth:grant-type:token-exchange" in content

    # CredentialBoundary & RLS
    assert "CredentialBoundary" in content
    assert "app.credential_boundary" in content
    assert "FORCE ROW LEVEL SECURITY" in content or "FORCE RLS" in content


def test_service_auth_guide_no_forbidden_dashes() -> None:
    """Assert zero Unicode em-dashes or en-dashes exist in service auth guide."""
    content, meta = load_chapter()
    assert "\u2014" not in content, "Forbidden em-dash found in content"
    assert "\u2013" not in content, "Forbidden en-dash found in content"
    assert "\u2014" not in meta["summary"], "Forbidden em-dash found in summary"
    assert "\u2013" not in meta["summary"], "Forbidden en-dash found in summary"


def test_service_auth_guide_sections_and_anchors() -> None:
    """Verify table of contents sections and anchor slugs."""
    _, meta = load_chapter()
    section_ids = [s["id"] for s in meta["sections"]]
    assert "zero-trust-security-philosophy-the-hostile-wire" in section_ids
    assert "role-bound-hkdf-hmac-internal-service-authentication" in section_ids
    assert "headless-workload-identity-federation-rfc-8693" in section_ids
