"""Unit tests for documentation taxonomy and link integrity audit script (KAN-33)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_docs_taxonomy import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_WEB_SRC_DIR,
    DEFAULT_WIKI_DIR,
    build_wiki_chapter_anchors_map,
    check_internal_wiki_links,
    check_manifest_taxonomy,
    check_no_em_en_dashes,
    check_web_src_doc_links,
    check_wiki_chapters_taxonomy,
    extract_wiki_anchors,
    main,
    run_taxonomy_audit,
    slugify_anchor,
    slugify_gfm_anchor,
)


class TestSlugifyAnchor:
    """Tests for anchor slug generation."""

    def test_slugify_clean_text(self) -> None:
        """Assert clean ASCII slug generation from headings."""
        assert slugify_anchor("Introduction to WebAuthn") == "introduction-to-webauthn"
        assert slugify_anchor("1. Section Heading") == "section-heading"
        assert slugify_anchor("Code `sample` with [Link](url)") == "code-with"
        assert slugify_anchor("Special !@#$ Characters") == "special-characters"
        assert slugify_anchor("") == "section"
        assert slugify_anchor("   ") == "section"

    def test_slugify_gfm_anchor(self) -> None:
        """Assert GitHub Flavored Markdown github-slugger anchor compatibility."""
        assert (
            slugify_gfm_anchor("1. Security, Identity, Audit & Deployment")
            == "1-security-identity-audit--deployment"
        )
        assert (
            slugify_gfm_anchor("5. Orchestration, Provenance & Day-2 Operations")
            == "5-orchestration-provenance--day-2-operations"
        )
        assert slugify_gfm_anchor("") == "section"


class TestExtractWikiAnchors:
    """Tests for anchor extraction from markdown content."""

    def test_extract_headings_and_anchor_tags(self) -> None:
        """Assert extraction of headings and explicit anchor tags."""
        content = """# Main Heading
## Second Level Heading
### Third Level Heading
<a id="custom-anchor-1"></a>
<a name="custom-anchor-2"></a>
Some paragraph content.
"""
        anchors = extract_wiki_anchors(content)
        assert "main-heading" in anchors
        assert "second-level-heading" in anchors
        assert "third-level-heading" in anchors
        assert "custom-anchor-1" in anchors
        assert "custom-anchor-2" in anchors


class TestCheckWikiChaptersTaxonomy:
    """Tests for chapter title taxonomy enforcement."""

    def test_valid_wiki_directory(self, tmp_path: Path) -> None:
        """Assert clean validation of properly classified chapter titles."""
        (tmp_path / "Guide-Test.md").write_text("# [Guide] Test Guide\nContent", encoding="utf-8")
        (tmp_path / "Info-Test.md").write_text(
            "# [Informational] Test Info\nContent", encoding="utf-8"
        )
        (tmp_path / "Arch-Test.md").write_text(
            "# [Architectural] Test Arch\nContent", encoding="utf-8"
        )
        (tmp_path / "Home.md").write_text("# Home Overview\nContent", encoding="utf-8")
        (tmp_path / "_Sidebar.md").write_text("- Sidebar", encoding="utf-8")

        violations = check_wiki_chapters_taxonomy(tmp_path)
        assert not violations

    def test_empty_directory_reports_violation(self, tmp_path: Path) -> None:
        """Assert empty wiki directory is flagged as a violation."""
        violations = check_wiki_chapters_taxonomy(tmp_path)
        assert len(violations) == 1
        assert "No markdown files found" in violations[0]

    def test_missing_h1_reports_violation(self, tmp_path: Path) -> None:
        """Assert file without an H1 heading is flagged."""
        (tmp_path / "Missing-H1.md").write_text(
            "Just some text without an H1 heading.", encoding="utf-8"
        )
        violations = check_wiki_chapters_taxonomy(tmp_path)
        assert len(violations) == 1
        assert "Missing H1 title heading" in violations[0]

    def test_invalid_h1_prefix_reports_violation(self, tmp_path: Path) -> None:
        """Assert unclassified H1 heading is flagged."""
        (tmp_path / "Unprefixed.md").write_text("# Unprefixed Heading\nContent", encoding="utf-8")
        violations = check_wiki_chapters_taxonomy(tmp_path)
        assert len(violations) == 1
        assert "H1 title must start with" in violations[0]


class TestCheckManifestTaxonomy:
    """Tests for wikiManifest.ts taxonomy metadata checks."""

    def test_missing_manifest_file(self, tmp_path: Path) -> None:
        """Assert missing manifest file is reported as a violation."""
        violations = check_manifest_taxonomy(tmp_path / "nonexistent.ts")
        assert len(violations) == 1
        assert "Manifest file not found" in violations[0]

    def test_manifest_missing_array_pattern(self, tmp_path: Path) -> None:
        """Assert manifest without WIKI_CHAPTERS array is reported."""
        manifest = tmp_path / "manifest.ts"
        manifest.write_text("export const SOMETHING_ELSE = 123;", encoding="utf-8")
        violations = check_manifest_taxonomy(manifest)
        assert len(violations) == 1
        assert "Failed to locate WIKI_CHAPTERS" in violations[0]

    def test_manifest_invalid_json(self, tmp_path: Path) -> None:
        """Assert malformed JSON in WIKI_CHAPTERS is reported."""
        manifest = tmp_path / "manifest.ts"
        manifest.write_text(
            "export const WIKI_CHAPTERS: WikiChapter[] = [ { invalid json } ];", encoding="utf-8"
        )
        violations = check_manifest_taxonomy(manifest)
        assert len(violations) == 1
        assert "Failed to parse WIKI_CHAPTERS JSON" in violations[0]

    def test_manifest_valid_and_invalid_entries(self, tmp_path: Path) -> None:
        """Assert validation of valid and invalid manifest entries."""
        valid_json = """[
  {
    "slug": "home",
    "title": "Home Title",
    "category": "informational",
    "track": "Overview",
    "subtrack": "Overview",
    "audience": "All Users"
  },
  {
    "slug": "good-guide",
    "title": "[Guide] Proper Title",
    "category": "guide",
    "track": "Track 1",
    "subtrack": "Subtrack 1",
    "audience": "Developers"
  },
  {
    "slug": "bad-title",
    "title": "No Prefix Title",
    "category": "invalid-cat",
    "track": "",
    "subtrack": "",
    "audience": ""
  }
]"""
        manifest = tmp_path / "manifest.ts"
        manifest.write_text(
            f"export const WIKI_CHAPTERS: WikiChapter[] = {valid_json};", encoding="utf-8"
        )
        violations = check_manifest_taxonomy(manifest)
        assert any("Title must start with" in v for v in violations)
        assert any("Invalid category" in v for v in violations)
        assert any("Missing required 'track'" in v for v in violations)
        assert any("Missing required 'subtrack'" in v for v in violations)
        assert any("Missing required 'audience'" in v for v in violations)

    def test_manifest_invalid_home_metadata(self, tmp_path: Path) -> None:
        """Assert invalid Home chapter metadata is reported."""
        invalid_home = """[
  {
    "slug": "home",
    "title": "Home Title",
    "category": "bad_cat",
    "track": "",
    "subtrack": "",
    "audience": ""
  }
]"""
        manifest = tmp_path / "manifest.ts"
        manifest.write_text(
            f"export const WIKI_CHAPTERS: WikiChapter[] = {invalid_home};", encoding="utf-8"
        )
        violations = check_manifest_taxonomy(manifest)
        assert any("category must be one of" in v for v in violations)
        assert any("Missing required 'track'" in v for v in violations)
        assert any("Missing required 'audience'" in v for v in violations)


class TestInternalAndCodeLinks:
    """Tests for link and anchor resolution across wiki files and web/src."""

    def test_internal_wiki_links(self, tmp_path: Path) -> None:
        """Assert detection of broken internal wiki links and anchors."""
        doc_a_content = (
            "# [Guide] Doc A\n"
            "## Section One\n"
            "[Link to B](doc-b#section-b)\n"
            "[Broken Link](doc-nonexistent)\n"
            "[Broken Anchor](doc-b#missing-anchor)\n"
            "[Local Anchor](#section-one)\n"
            "[Broken Local](#missing-local)"
        )
        (tmp_path / "doc-a.md").write_text(doc_a_content, encoding="utf-8")
        (tmp_path / "doc-b.md").write_text(
            "# [Informational] Doc B\n## Section B\nContent B", encoding="utf-8"
        )

        anchors_map = build_wiki_chapter_anchors_map(tmp_path)
        violations = check_internal_wiki_links(tmp_path, anchors_map)
        assert any("Broken internal link target" in v for v in violations)
        assert any("Broken anchor '#missing-anchor'" in v for v in violations)
        assert any("Broken local anchor '#missing-local'" in v for v in violations)

    def test_web_src_doc_links(self, tmp_path: Path) -> None:
        """Assert detection of broken /docs links in web source files."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "Component.tsx").write_text(
            """
        <FieldHelpHint docHref="/docs/valid-doc#valid-sec" />
        <FieldHelpHint docHref="/docs/valid-doc#broken-sec" />
        <StudioDocLink href="/docs/unknown-doc" />
        <StudioDocLink href="/other-route/not-docs" />
        """,
            encoding="utf-8",
        )

        anchors_map = {
            "valid-doc": {"valid-sec"},
        }
        violations = check_web_src_doc_links(src_dir, anchors_map)
        assert any("Unknown anchor '#broken-sec'" in v for v in violations)
        assert any("Unknown documentation chapter 'unknown-doc'" in v for v in violations)

    def test_web_src_nonexistent_directory(self, tmp_path: Path) -> None:
        """Assert nonexistent web source directory yields zero violations."""
        violations = check_web_src_doc_links(tmp_path / "nonexistent", {})
        assert not violations


class TestCheckNoEmEnDashes:
    """Tests for em/en-dash detection in documentation."""

    def test_clean_files_pass(self, tmp_path: Path) -> None:
        """Assert clean markdown and manifest files pass without dash violations."""
        clean_file = tmp_path / "clean.md"
        clean_file.write_text("# Clean Title - Subtitle\nPlain ASCII hyphens.", encoding="utf-8")
        manifest = tmp_path / "manifest.ts"
        manifest.write_text("// Clean manifest\nexport const x = 1;", encoding="utf-8")

        violations = check_no_em_en_dashes(tmp_path, manifest)
        assert not violations

    def test_forbidden_dashes_detected(self, tmp_path: Path) -> None:
        """Assert em-dashes and en-dashes are detected and reported."""
        em_file = tmp_path / "em.md"
        em_file.write_text("Contains em\u2014dash and en\u2013dash.", encoding="utf-8")
        violations = check_no_em_en_dashes(tmp_path, tmp_path / "nonexistent.ts")
        assert len(violations) == 2
        assert "U+2014 (em-dash)" in violations[0]
        assert "U+2013 (en-dash)" in violations[1]

    def test_invalid_utf8_file(self, tmp_path: Path) -> None:
        """Assert non-UTF-8 files are reported as encoding errors."""
        bad_file = tmp_path / "bad.md"
        bad_file.write_bytes(b"\xff\xfe\x00\x00\x80\x81")
        violations = check_no_em_en_dashes(tmp_path, tmp_path / "nonexistent.ts")
        assert len(violations) == 1
        assert "Invalid UTF-8 encoding" in violations[0]


class TestAuditIntegrationAndCLI:
    """Integration and CLI tests."""

    def test_live_repository_taxonomy_passes_cleanly(self) -> None:
        """Assert live repository wiki and manifest pass the complete taxonomy audit."""
        wiki_dir = Path(DEFAULT_WIKI_DIR)
        if not wiki_dir.is_dir():
            pytest.skip("Wiki directory not available on this machine")

        repo_root = Path(__file__).resolve().parents[3]
        manifest_path = repo_root / DEFAULT_MANIFEST_PATH
        web_src = repo_root / DEFAULT_WEB_SRC_DIR

        count, violations = run_taxonomy_audit(wiki_dir, manifest_path, web_src)
        assert count == 0, f"Expected 0 violations, found {count}: {violations}"

    def test_main_cli_success(self) -> None:
        """Assert CLI main returns exit code 0 when auditing live repository docs."""
        wiki_dir = Path(DEFAULT_WIKI_DIR)
        if not wiki_dir.is_dir():
            pytest.skip("Wiki directory not available on this machine")

        repo_root = Path(__file__).resolve().parents[3]
        manifest_path = repo_root / DEFAULT_MANIFEST_PATH
        web_src = repo_root / DEFAULT_WEB_SRC_DIR

        code = main(
            [
                "--wiki-dir",
                str(wiki_dir),
                "--manifest-file",
                str(manifest_path),
                "--web-src",
                str(web_src),
            ]
        )
        assert code == 0

    def test_main_cli_missing_wiki_dir(self, tmp_path: Path) -> None:
        """Assert CLI main returns exit code 1 when wiki directory does not exist."""
        code = main(["--wiki-dir", str(tmp_path / "nonexistent")])
        assert code == 1

    def test_main_cli_failure_reports_nonzero(self, tmp_path: Path) -> None:
        """Assert CLI main returns exit code 1 when violations are found."""
        (tmp_path / "Invalid.md").write_text(
            "# Invalid Title Without Label\nContent", encoding="utf-8"
        )
        manifest = tmp_path / "manifest.ts"
        manifest.write_text("export const WIKI_CHAPTERS: WikiChapter[] = [];", encoding="utf-8")

        code = main(
            [
                "--wiki-dir",
                str(tmp_path),
                "--manifest-file",
                str(manifest),
                "--web-src",
                str(tmp_path),
            ]
        )
        assert code == 1

    def test_feature_comparison_matrix_sync_and_gfm_columns(self) -> None:
        """Assert Feature Comparison has 9 columns (with OpenAI Symphony) and stays in sync."""
        repo_root = Path(__file__).resolve().parents[3]
        spec_file = repo_root / "docs" / "FEATURE_COMPARISON.md"
        assert spec_file.is_file()
        spec_lines = spec_file.read_text(encoding="utf-8").splitlines()

        expected_header = (
            "| Feature | 👍kanban | Jira | Plane | GitHub | "
            "Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |"
        )
        expected_separator = "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"

        sec6_idx = next(
            i
            for i, line in enumerate(spec_lines)
            if line.startswith("## 6. When 👍kanban Is Not the Right Fit")
        )
        cap_table_lines = [line for line in spec_lines[:sec6_idx] if line.startswith("|")]
        header_lines = [line for line in cap_table_lines if line.startswith("| Feature |")]
        separator_lines = [line for line in cap_table_lines if line.startswith("| --- |")]
        data_lines = [
            line
            for line in cap_table_lines
            if line not in header_lines and line not in separator_lines
        ]

        assert header_lines == [expected_header] * 5
        assert separator_lines == [expected_separator] * 5
        assert len(data_lines) == 46
        planned_core_rows = [row for row in data_lines if "| 🎯✅ |" in row]
        assert len(planned_core_rows) == 0
        for row in cap_table_lines:
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            assert len(cells) == 9, f"Expected 9 GFM columns, got {len(cells)} in row: {row}"

        sec6_table_lines = [line for line in spec_lines[sec6_idx:] if line.startswith("|")]
        sec6_9col = sec6_table_lines[:8]
        sec6_4col = sec6_table_lines[8:]
        assert sec6_9col[0].startswith("| Non-Goal Use Case | 👍kanban |")
        assert sec6_9col[1] == expected_separator
        for row in sec6_9col:
            assert len(row.strip("|").split("|")) == 9
        assert sec6_4col[0] == (
            "| Use Case | 👍kanban Fit | Recommended Tools (FOSS & Commercial) | "
            "How to Pair Alongside 👍kanban (or When to Replace) |"
        )
        assert sec6_4col[1] == "| --- | --- | --- | --- |"
        assert len(sec6_4col) == 8
        for row in sec6_4col:
            assert len(row.strip("|").split("|")) == 4

        wiki_dir = Path(DEFAULT_WIKI_DIR)
        if wiki_dir.is_dir():
            wiki_file = wiki_dir / "Feature-Comparison.md"
            wiki_lines = wiki_file.read_text(encoding="utf-8").splitlines()
            assert wiki_lines[0] == "# [Informational] Feature Comparison Matrix (46 Features)"
            assert wiki_lines[1:] == spec_lines[1:]
