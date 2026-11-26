"""Unit tests for scripts/sync_wiki_bundle.py offline documentation bundler."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from scripts import sync_wiki_bundle

if TYPE_CHECKING:
    from pathlib import Path


def test_slugify_and_sanitize_dashes() -> None:
    """Verify anchor slug generation and Unicode dash sanitization."""
    assert sync_wiki_bundle.slugify("1. Hello [World](https://example.com) `code`!") == "hello"
    assert sync_wiki_bundle.slugify("Role & Permission_Matrix") == "role-permission-matrix"
    assert sync_wiki_bundle.slugify("!!!") == "section"
    assert sync_wiki_bundle.sanitize_dashes("a\u2014b\u2013c") == "a-b-c"


def test_parse_sidebar_hierarchy_and_orphans() -> None:
    """Verify _Sidebar.md category and chapter link extraction."""
    sidebar = (
        "  - [Orphan Before Category](Orphan.md)\n"
        "- **Track 1: Step-by-Step Guides**\n"
        "  - [Custom Fields](Guide-Custom-Fields.md)\n"
        "  - [Auth Studio](Multi-Card-Authentication-Studio)\n"
        "- **Empty Category**\n"
        "Plain text line ignored\n"
    )
    categories, file_to_cat = sync_wiki_bundle.parse_sidebar(sidebar)
    assert len(categories) == 2
    assert categories[0]["name"] == "Track 1: Step-by-Step Guides"
    assert len(categories[0]["chapters"]) == 2
    assert categories[0]["chapters"][0] == {
        "title": "Custom Fields",
        "file": "Guide-Custom-Fields",
    }
    assert file_to_cat["guide-custom-fields"] == "Track 1: Step-by-Step Guides"
    assert file_to_cat["multi-card-authentication-studio"] == "Track 1: Step-by-Step Guides"
    assert categories[1] == {"name": "Empty Category", "chapters": []}


def test_extract_sections_and_summary_branches() -> None:
    """Verify H1/H2/H3 extraction and multi-line or EOF summary handling."""
    md_with_trailing_block = (
        "# [Guide] First Title\n\n"
        "First sentence of summary\n"
        "second line of summary.\n\n"
        "# Ignored Duplicate H1\n"
        "## 1. Setup `Step`\n"
        "### Deep Detail\n"
        "Later paragraph ignored for summary.\n"
    )
    sections, title, summary = sync_wiki_bundle.extract_sections_and_summary(md_with_trailing_block)
    assert title == "[Guide] First Title"
    assert summary == "First sentence of summary second line of summary."
    assert sections == [
        {"id": "setup-step", "title": "1. Setup Step", "level": 2},
        {"id": "deep-detail", "title": "Deep Detail", "level": 3},
    ]

    md_eof_paragraph = "# Simple Title\nSummary right at EOF without blank line."
    sections_eof, title_eof, summary_eof = sync_wiki_bundle.extract_sections_and_summary(
        md_eof_paragraph
    )
    assert sections_eof == []
    assert title_eof == "Simple Title"
    assert summary_eof == "Summary right at EOF without blank line."


def test_build_config_chapter_structure() -> None:
    """Verify synthetic Configuration Value Reference chapter generation."""
    refs = sync_wiki_bundle.build_configuration_reference()
    assert "environment_variables" in refs
    assert "custom_field_tiers" in refs
    assert "system_roles_and_capabilities" in refs

    chapter = sync_wiki_bundle.build_config_chapter(35)
    assert chapter["slug"] == "configuration-value-reference"
    assert chapter["order"] == 35
    assert "DATABASE_URL" in chapter["content"]
    assert "nsjail" in chapter["content"]
    assert "SERVER_ADMIN" in chapter["content"]


def test_sync_wiki_images_and_load_chapters(tmp_path: Path) -> None:
    """Verify image copying, fallback taxonomy inference, and Home ordering."""
    wiki_dir = tmp_path / "wiki"
    images_dir = wiki_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "shot.png").write_bytes(b"png")
    (images_dir / "diagram.svg").write_text("<svg/>", encoding="utf-8")
    (images_dir / "notes.txt").write_text("skip", encoding="utf-8")
    (images_dir / "nested").mkdir()

    public_dir = tmp_path / "public"
    copied = sync_wiki_bundle.sync_wiki_images(wiki_dir, public_dir)
    assert copied == 2
    assert (public_dir / "docs-images" / "shot.png").is_file()
    assert (public_dir / "docs-images" / "diagram.svg").is_file()
    assert not (public_dir / "docs-images" / "notes.txt").exists()

    (wiki_dir / "_Sidebar.md").write_text("- **Custom Track**\n", encoding="utf-8")
    (wiki_dir / "Home.md").write_text("# Home\n\nWelcome home.\n", encoding="utf-8")
    (wiki_dir / "Alpha-Guide.md").write_text("# [Guide] Alpha\n\nGuide body.\n", encoding="utf-8")
    (wiki_dir / "Beta-Arch.md").write_text("# [Architectural] Beta\n", encoding="utf-8")
    (wiki_dir / "Gamma-Info.md").write_text("No H1 heading here.\n", encoding="utf-8")

    chapters = sync_wiki_bundle.load_chapters_from_wiki(wiki_dir, {"alpha-guide": "Custom Track"})
    assert chapters[0]["slug"] == "home"
    slug_map = {c["slug"]: c for c in chapters}
    assert slug_map["alpha-guide"]["category"] == "guide"
    assert slug_map["alpha-guide"]["track"] == "Custom Track"
    assert slug_map["beta-arch"]["category"] == "architectural"
    assert slug_map["beta-arch"]["summary"].startswith("Documentation guide for")
    assert slug_map["gamma-info"]["category"] == "informational"
    assert slug_map["gamma-info"]["title"] == "Gamma Info"
    assert slug_map["configuration-value-reference"]["order"] == len(chapters)


def test_generate_manifest_ts_category_merging() -> None:
    """Verify generate_manifest_ts handles both Track 2 append and new track creation."""
    chapters = [
        {
            "slug": "home",
            "title": "Home",
            "category": "informational",
            "track": "Overview",
            "subtrack": "Overview",
            "audience": "All",
            "order": 1,
            "summary": "Home summary",
            "sections": [],
            "content": "# Home",
        },
        {
            "slug": "extra-ref",
            "title": "Extra Ref",
            "category": "informational",
            "track": "Feature & Field Reference",
            "subtrack": "General",
            "audience": "Devs",
            "order": 2,
            "summary": "Extra summary",
            "sections": [],
            "content": "# Extra Ref",
        },
    ]
    sidebar_with_track2 = [
        {
            "name": "Track 2: Feature & Field Reference",
            "chapters": [
                {"title": "Home", "file": "Home"},
                {"title": "Missing", "file": "Does-Not-Exist"},
            ],
        },
        {"name": "Empty Cat", "chapters": [{"title": "Ghost", "file": "Ghost"}]},
    ]
    ts_track2 = sync_wiki_bundle.generate_manifest_ts(
        chapters, {"docs-home": "home"}, sidebar_with_track2
    )
    assert "export const WIKI_CHAPTERS: WikiChapter[]" in ts_track2
    assert '"extra-ref"' in ts_track2
    assert '"docs-home": "home"' in ts_track2

    ts_no_sidebar = sync_wiki_bundle.generate_manifest_ts(chapters, {}, None)
    assert '"Overview"' in ts_no_sidebar


def test_sync_wiki_end_to_end_and_cli_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify sync_wiki error exit on missing dir and full CLI execution via main()."""
    with pytest.raises(SystemExit) as exc_info:
        sync_wiki_bundle.sync_wiki(
            str(tmp_path / "missing_wiki"),
            str(tmp_path / "out.ts"),
            str(tmp_path / "pub"),
        )
    assert exc_info.value.code == 1

    wiki_dir = tmp_path / "valid_wiki"
    (wiki_dir / "images").mkdir(parents=True)
    (wiki_dir / "images" / "test.webp").write_bytes(b"webp")
    (wiki_dir / "_Sidebar.md").write_text("- **Overview**\n  - [Home](Home.md)\n", encoding="utf-8")
    (wiki_dir / "Home.md").write_text("# Home\n\nOverview text.\n", encoding="utf-8")

    out_ts = tmp_path / "generated" / "wikiManifest.ts"
    pub_dir = tmp_path / "public"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_wiki_bundle.py",
            "--wiki-dir",
            str(wiki_dir),
            "--out-file",
            str(out_ts),
            "--public-dir",
            str(pub_dir),
        ],
    )
    sync_wiki_bundle.main()
    captured = capsys.readouterr()
    assert "Successfully synchronized" in captured.out
    assert out_ts.is_file()
    assert (pub_dir / "docs-images" / "test.webp").is_file()
