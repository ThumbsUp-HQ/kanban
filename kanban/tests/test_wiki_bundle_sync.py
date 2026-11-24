# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for offline wiki bundle synchronization and image parity (KAN-323 / KAN-311)."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import pytest

from scripts import sync_wiki_bundle


def get_wiki_and_public_paths() -> tuple[Path, Path, Path]:
    """Resolve wiki dir, web public images dir, and README path."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    wiki_dir = Path(
        os.environ.get("KANBAN_WIKI_PATH", "/home/adamoutler/kanban/thumbs-up-kanban.wiki")
    )
    public_images_dir = repo_root / "kanban" / "web" / "public" / "docs-images"
    readme_path = repo_root / "README.md"
    return wiki_dir, public_images_dir, readme_path


def compute_sha256(file_path: Path) -> str:
    """Compute hex-encoded SHA-256 digest of a file."""
    h = hashlib.sha256()
    h.update(file_path.read_bytes())
    return h.hexdigest()


def test_wiki_and_public_images_sha256_parity() -> None:
    """Assert all images in wiki/images match web/public/docs-images with identical SHA-256."""
    wiki_dir, public_images_dir, _ = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    wiki_images_dir = wiki_dir / "images"
    assert wiki_images_dir.is_dir(), f"Missing wiki images dir: {wiki_images_dir}"
    assert public_images_dir.is_dir(), f"Missing public docs-images dir: {public_images_dir}"

    wiki_files = sorted(wiki_images_dir.glob("*.png"))
    public_files = sorted(public_images_dir.glob("*.png"))

    assert len(wiki_files) >= 70, f"Expected at least 70 wiki images, found {len(wiki_files)}"
    assert len(public_files) == len(wiki_files), (
        f"File count mismatch: {len(public_files)} public vs {len(wiki_files)} wiki images"
    )

    wiki_names = {p.name for p in wiki_files}
    public_names = {p.name for p in public_files}
    assert wiki_names == public_names, f"Name mismatch: {wiki_names ^ public_names}"

    mismatched: list[str] = []
    for f in wiki_files:
        pub = public_images_dir / f.name
        assert pub.exists(), f"Missing public copy for {f.name}"
        wiki_hash = compute_sha256(f)
        pub_hash = compute_sha256(pub)
        if wiki_hash != pub_hash:
            mismatched.append(f"{f.name}: wiki={wiki_hash} vs pub={pub_hash}")

    assert not mismatched, f"SHA-256 mismatch detected: {mismatched}"


def test_zero_duplicate_numeric_prefix_collisions() -> None:
    """Assert zero duplicate numeric prefix collisions exist in wiki/images/."""
    wiki_dir, public_images_dir, _ = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    for target_dir in [wiki_dir / "images", public_images_dir]:
        seen_prefixes: dict[str, str] = {}
        duplicates: list[str] = []
        for img in sorted(target_dir.glob("*.png")):
            m = re.match(r"^(\d{2})-", img.name)
            if not m:
                continue
            prefix = m.group(1)
            if prefix in seen_prefixes:
                duplicates.append(
                    f"Prefix '{prefix}' duplicated by {seen_prefixes[prefix]} and {img.name}"
                )
            else:
                seen_prefixes[prefix] = img.name

        assert not duplicates, f"Found duplicate prefix collisions in {target_dir}: {duplicates}"


def test_every_markdown_image_reference_resolves() -> None:
    """Assert every images/*.png reference across wiki and README.md resolves to a valid file."""
    wiki_dir, public_images_dir, readme_path = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    wiki_images_dir = wiki_dir / "images"
    md_files = list(wiki_dir.glob("*.md"))
    if readme_path.is_file():
        md_files.append(readme_path)

    image_ref_pattern = re.compile(r"(?:images/|docs-images/)([0-9a-zA-Z_-]+\.png)")
    broken_refs: list[str] = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        for match in image_ref_pattern.finditer(content):
            img_name = match.group(1)
            wiki_target = wiki_images_dir / img_name
            public_target = public_images_dir / img_name
            if not wiki_target.is_file():
                broken_refs.append(f"{md_file.name}: wiki missing {img_name}")
            if not public_target.is_file():
                broken_refs.append(f"{md_file.name}: public missing {img_name}")

    assert not broken_refs, f"Broken image references found: {broken_refs}"


def test_reject_external_image_links_in_wiki() -> None:
    """Reject any external http:// or https:// image link inside wiki markdown (offline-first)."""
    wiki_dir, _, _ = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    external_img_pattern = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)")
    violations: list[str] = []

    for md_file in sorted(wiki_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        violations.extend(
            f"{md_file.name}: external image URL '{m.group(1)}'"
            for m in external_img_pattern.finditer(content)
        )

    assert not violations, f"External image links violate offline-first policy: {violations}"


def test_reject_unreferenced_orphan_images() -> None:
    """Reject any unreferenced orphan image file in wiki/images/."""
    wiki_dir, _, readme_path = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    wiki_images_dir = wiki_dir / "images"
    all_images = {p.name for p in wiki_images_dir.glob("*.png")}

    referenced: set[str] = set()
    md_files = list(wiki_dir.glob("*.md"))
    if readme_path.is_file():
        md_files.append(readme_path)

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:images/|docs-images/)([0-9a-zA-Z_-]+\.png)", content):
            referenced.add(m.group(1))

    orphans = all_images - referenced
    assert not orphans, f"Found unreferenced orphan images in {wiki_images_dir}: {sorted(orphans)}"


def test_sync_wiki_bundle_execution(tmp_path: Path) -> None:
    """Verify sync_wiki_bundle module functions execute cleanly and generate valid manifest."""
    wiki_dir, _, _ = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    temp_out_manifest = tmp_path / "wikiManifest.ts"
    temp_public_dir = tmp_path / "public"
    temp_public_dir.mkdir(parents=True)

    sync_wiki_bundle.sync_wiki(
        wiki_dir_str=str(wiki_dir),
        out_file_str=str(temp_out_manifest),
        public_dir_str=str(temp_public_dir),
    )

    assert temp_out_manifest.is_file()
    assert (temp_public_dir / "docs-images").is_dir()
    manifest_content = temp_out_manifest.read_text(encoding="utf-8")
    assert "export const WIKI_CHAPTERS: WikiChapter[] =" in manifest_content


def test_feature_comparison_day2_clean_and_synced() -> None:
    """Assert Feature-Comparison is clean, day-2 ops are complete, and docs/wiki sync (KAN-388)."""
    wiki_dir, _, _ = get_wiki_and_public_paths()
    if not wiki_dir.is_dir():
        pytest.skip(f"Wiki directory not found at {wiki_dir}")

    repo_root = Path(__file__).resolve().parent.parent.parent
    docs_fc = repo_root / "docs" / "FEATURE_COMPARISON.md"
    wiki_fc = wiki_dir / "Feature-Comparison.md"

    assert docs_fc.is_file(), f"Missing docs comparison: {docs_fc}"
    assert wiki_fc.is_file(), f"Missing wiki comparison: {wiki_fc}"

    docs_text = docs_fc.read_text(encoding="utf-8")
    wiki_text = wiki_fc.read_text(encoding="utf-8")

    # Assert identical body content after line 1
    docs_lines = docs_text.splitlines()
    wiki_lines = wiki_text.splitlines()
    assert len(docs_lines) > 1
    assert len(wiki_lines) > 1
    assert docs_lines[1:] == wiki_lines[1:], (
        "Body content mismatch between docs and wiki Feature Comparison"
    )

    # Neither file contains obsolete roadmap symbols or planned legend bullet
    for label, content in [("docs", docs_text), ("wiki", wiki_text)]:
        assert "🎯✅" not in content, f"{label} still contains obsolete 🎯✅ symbol"
        assert "Planned in Core" not in content, f"{label} still contains 'Planned in Core' legend"

    # Neither file contains internal ticket citations (KAN-\d+) or raw migration paths (.up.sql)
    for label, content in [("docs", docs_text), ("wiki", wiki_text)]:
        kan_matches = re.findall(r"\bKAN-\d+\b", content)
        assert not kan_matches, f"{label} contains internal ticket citations: {kan_matches}"
        assert ".up.sql" not in content, f"{label} contains raw migration file paths (.up.sql)"

    # All 10 rows under Section 5 have ✅ in the 👍kanban column
    sec5_pattern = (
        r"## 5\. Orchestration, Provenance & Day-2 Operations\s*\n"
        r"\s*\|([^\n]+)\|\s*\n\s*\|([^\n]+)\|\s*\n((?:\|[^\n]+\|\s*\n)+)"
    )
    sec5_match = re.search(sec5_pattern, docs_text)
    assert sec5_match is not None, "Failed to locate Section 5 table in docs/FEATURE_COMPARISON.md"
    table_rows = [r.strip() for r in sec5_match.group(3).strip().splitlines() if r.strip()]
    assert len(table_rows) == 10, f"Expected 10 rows in Section 5 table, found {len(table_rows)}"

    for row in table_rows:
        cols = [c.strip() for c in row.split("|")[1:-1]]
        feature_name = cols[0]
        kanban_status = cols[1]
        assert kanban_status == "✅", (
            f"Feature '{feature_name}' does not have ✅ in 👍kanban column: {kanban_status}"
        )

    # Assert all 50 comparison rows across Sections 1-5 have 9 columns
    sec_headers = [
        "1. Security, Identity, Audit & Deployment",
        "2. Agentic Tasks, MCP, AI & Workflow Gates",
        "3. Issue Tracker & Kanban Board",
        "4. Docs, Stickies, Markdown & Object Graph",
        "5. Orchestration, Provenance & Day-2 Operations",
    ]
    all_feature_rows: list[str] = []
    for header in sec_headers:
        pattern = (
            rf"## {re.escape(header)}\s*\n\s*\|([^\n]+)\|\s*\n"
            r"\s*\|([^\n]+)\|\s*\n((?:\|[^\n]+\|\s*\n)+)"
        )
        match = re.search(pattern, docs_text)
        assert match is not None, f"Failed to locate section {header}"
        rows = [r.strip() for r in match.group(3).strip().splitlines() if r.strip()]
        for r in rows:
            cols = [c.strip() for c in r.strip("|").split("|")]
            assert len(cols) == 9, f"Expected 9 GFM columns in row: {r}"
            all_feature_rows.append(cols[0])

    assert len(all_feature_rows) == 50, (
        f"Expected 50 capability rows, found {len(all_feature_rows)}"
    )
    assert "Active Directory / LDAP" in all_feature_rows
    assert "OIDC" in all_feature_rows
    assert "/llms.txt & Skills Discovery" in all_feature_rows
    assert "Issue Tracker" in all_feature_rows
    assert "Kanban Board" in all_feature_rows
    assert "Synaptic Hybrid Vector Search" in all_feature_rows
    assert "Multi-Card OIDC & LDAPS" not in all_feature_rows
    assert "Core Kanban & Issues" not in all_feature_rows
