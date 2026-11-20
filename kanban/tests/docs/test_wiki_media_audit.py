"""Wiki media, link resolution, and document structure audit tests (KAN-56)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast

import pytest

DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WIKI_DIR = Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki")
WIKI_MANIFEST_PATH = (
    DEFAULT_REPO_ROOT / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
)
PUBLIC_DOCS_IMAGES = DEFAULT_REPO_ROOT / "kanban" / "web" / "public" / "docs-images"


def get_wiki_dir(
    repo_root: Path = DEFAULT_REPO_ROOT,
    default_wiki: Path | None = DEFAULT_WIKI_DIR,
) -> Path | None:
    """Resolve the authoritative wiki directory path if available."""
    env_path = os.environ.get("KANBAN_WIKI_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
        return None
    candidates = [
        repo_root / "thumbs-up-kanban.wiki",
        repo_root.parent / "thumbs-up-kanban.wiki",
    ]
    if default_wiki is not None:
        candidates.append(default_wiki)
    for c in candidates:
        if c.exists():
            return c
    return None


def load_bundled_chapters(manifest_path: Path = WIKI_MANIFEST_PATH) -> list[dict[str, Any]]:
    """Parse and return bundled WIKI_CHAPTERS from wikiManifest.ts."""
    content = manifest_path.read_text(encoding="utf-8")
    match = re.search(
        r"export const WIKI_CHAPTERS: WikiChapter\[\] = (\[.*?\]);\n\nexport const WIKI_CATEGORIES",
        content,
        re.DOTALL,
    )
    assert match is not None, f"Could not find WIKI_CHAPTERS in {manifest_path}"
    return cast("list[dict[str, Any]]", json.loads(match.group(1)))


def github_heading_slug(text: str) -> str:
    """Generate a clean GitHub-compatible anchor slug from a markdown heading."""
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    clean = re.sub(r"`([^`]+)`", r"\1", clean)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = clean.lower().strip()
    clean = re.sub(r"[^\w\s-]", "", clean)
    clean = re.sub(r"[\s_]+", "-", clean)
    return clean.strip("-")


def extract_heading_slugs(content: str) -> set[str]:
    """Extract all valid heading anchor slugs for a markdown page."""
    slugs: set[str] = set()
    counts: dict[str, int] = {}
    for line in content.splitlines():
        match = re.match(r"^#{1,6}\s+(.+)$", line)
        if match:
            heading = match.group(1).strip()
            base = github_heading_slug(heading)
            if not base:
                continue
            if base in counts:
                counts[base] += 1
                slugs.add(f"{base}-{counts[base]}")
            else:
                counts[base] = 0
                slugs.add(base)
            slugs.add(base)
            no_num = re.sub(r"^[0-9]+-", "", base)
            if no_num:
                slugs.add(no_num)
    return slugs


def validate_markdown_links(
    pages_or_chapters: list[tuple[str, str]],
    headings_map: dict[str, set[str]],
    *,
    is_manifest: bool = False,
) -> list[tuple[str, str, str]]:
    """Validate that internal markdown links and anchor fragments point to valid targets."""
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    broken_links: list[tuple[str, str, str]] = []
    slug_to_canonical = {k.lower(): k for k in headings_map}

    for current_id, content in pages_or_chapters:
        for text, link in link_pattern.findall(content):
            link_clean = link.strip()
            if link_clean.startswith(("http://", "https://", "images/", "mailto:")):
                continue

            target_raw = link_clean
            if is_manifest:
                target_raw = target_raw.removeprefix("/docs/").removeprefix("./")

            if "#" in target_raw:
                target_part, anchor_part = target_raw.split("#", 1)
                target_slug = target_part.removesuffix(".md").strip()
                anchor_slug = anchor_part.split("?")[0].strip()
            else:
                target_slug = target_raw.split("?")[0].removesuffix(".md").strip()
                anchor_slug = ""

            if is_manifest:
                target_key = target_slug.lower().replace("_", "-")
                target_page = slug_to_canonical.get(target_key) if target_slug else current_id
            else:
                target_page = target_slug or current_id

            if not target_page or target_page not in headings_map:
                broken_links.append((current_id, text, link_clean))
                continue

            if anchor_slug:
                valid_anchors = headings_map.get(target_page, set())
                if anchor_slug.lower() not in valid_anchors and anchor_slug not in valid_anchors:
                    broken_links.append((current_id, text, link_clean))

    return broken_links


def check_image_references(
    pages_or_chapters: list[tuple[str, str]],
    wiki_dir: Path | None = None,
    public_dir: Path = PUBLIC_DOCS_IMAGES,
) -> list[tuple[str, str, str]]:
    """Validate that local media references point to existing image assets."""
    img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    broken_images: list[tuple[str, str, str]] = []

    for page_id, content in pages_or_chapters:
        for alt, src in img_pattern.findall(content):
            src_clean = src.strip()
            if src_clean.startswith(("http://", "https://")):
                continue

            clean_src = src_clean.split("#")[0].split("?")[0]
            if wiki_dir is not None:
                resolved = (wiki_dir / clean_src).resolve()
                if resolved.is_file() or (public_dir / Path(clean_src).name).is_file():
                    continue
            elif (public_dir / Path(clean_src).name).is_file():
                continue

            broken_images.append((page_id, alt, src_clean))

    return broken_images


class TestWikiMediaAndLinkAudit:
    """Validates wiki document renames, media assets, and link integrity."""

    @pytest.fixture(autouse=True)
    def setup_wiki(self) -> None:
        """Fixture configuring authoritative wiki path for assertions."""
        self.wiki_dir = get_wiki_dir()

    def test_renamed_scripted_workflows_doc_exists_and_old_is_purged(self) -> None:
        """Assert Scripted-Workflows-and-Transition-Helpers exists and old doc is purged."""
        if self.wiki_dir is not None:
            canonical_file = self.wiki_dir / "Scripted-Workflows-and-Transition-Helpers.md"
            obsolete_file = self.wiki_dir / "ScriptRunner-Workflows-and-Transition-Interceptors.md"

            assert canonical_file.is_file(), (
                f"Expected canonical wiki doc to exist: {canonical_file}"
            )
            assert not obsolete_file.exists(), (
                f"Obsolete wiki doc must not exist after rename: {obsolete_file}"
            )
        else:
            chapters = load_bundled_chapters()
            slugs = {ch["slug"] for ch in chapters}
            assert "scripted-workflows-and-transition-helpers" in slugs, (
                "Expected bundled chapter 'scripted-workflows-and-transition-helpers' "
                "in wikiManifest.ts"
            )
            for slug in slugs:
                assert "scriptrunner" not in slug.lower(), f"Obsolete slug found: {slug}"
                assert "transition-interceptor" not in slug.lower(), f"Obsolete slug found: {slug}"

    def test_all_internal_wiki_links_resolve_cleanly(self) -> None:
        """Assert all internal markdown links and anchor fragments resolve cleanly."""
        if self.wiki_dir is not None:
            all_md_files = sorted(self.wiki_dir.glob("*.md"))
            assert len(all_md_files) > 0, "No markdown files found in wiki directory"

            headings_map: dict[str, set[str]] = {}
            pages: list[tuple[str, str]] = []
            for md_file in all_md_files:
                doc_name = md_file.name[:-3]
                doc_text = md_file.read_text(encoding="utf-8")
                headings_map[doc_name] = extract_heading_slugs(doc_text)
                pages.append((doc_name, doc_text))

            broken_links = validate_markdown_links(pages, headings_map, is_manifest=False)
        else:
            chapters = load_bundled_chapters()
            assert len(chapters) > 0, "No chapters found in wikiManifest.ts"

            headings_map = {}
            pages = []
            for ch in chapters:
                slug = ch["slug"]
                content = ch.get("content", "")
                anchors = extract_heading_slugs(content)
                for sec in ch.get("sections", []):
                    if "id" in sec:
                        anchors.add(sec["id"].lower())
                headings_map[slug] = {a.lower() for a in anchors}
                pages.append((slug, content))

            broken_links = validate_markdown_links(pages, headings_map, is_manifest=True)

        assert not broken_links, (
            f"Found {len(broken_links)} broken internal wiki link(s): {broken_links}"
        )

    def test_all_wiki_image_references_exist_on_disk(self) -> None:
        """Assert all local media and image references point to valid files."""
        if self.wiki_dir is not None:
            pages = [
                (f.name, f.read_text(encoding="utf-8")) for f in sorted(self.wiki_dir.glob("*.md"))
            ]
            broken_images = check_image_references(pages, wiki_dir=self.wiki_dir)
        else:
            chapters = load_bundled_chapters()
            pages = [(ch["slug"], ch.get("content", "")) for ch in chapters]
            broken_images = check_image_references(pages, wiki_dir=None)

        assert not broken_images, (
            f"Found {len(broken_images)} broken image link(s): {broken_images}"
        )

    def test_wiki_mermaid_and_headings_use_canonical_branding(self) -> None:
        """Assert canonical file contains HelperEngine and no old interceptor headings."""
        if self.wiki_dir is not None:
            canonical_file = self.wiki_dir / "Scripted-Workflows-and-Transition-Helpers.md"
            content = canonical_file.read_text(encoding="utf-8")
        else:
            chapters = load_bundled_chapters()
            target_ch = next(
                (
                    ch
                    for ch in chapters
                    if ch["slug"] == "scripted-workflows-and-transition-helpers"
                ),
                None,
            )
            assert target_ch is not None, "Scripted workflows chapter missing from wikiManifest.ts"
            content = target_ch.get("content", "")

        assert re.search(
            r"^#\s+(?:\[(?:Guide|Informational|Architectural)\]\s+)?Scripted Workflows",
            content,
            re.MULTILINE,
        ), "Title check failed"
        assert 'HelperEngine["Transition Helper Engine"]' in content
        assert "## Helper Architecture" in content
        assert re.search(r"^### Failure Policies$", content, re.MULTILINE), (
            "Expected exact h3 heading '### Failure Policies'"
        )
        assert "ScriptRunner" not in content
        assert "Transition Interceptor Engine" not in content

    def test_bundled_manifest_fallback_all_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Assert all 4 audit gates pass against wikiManifest.ts when wiki repo is absent."""
        monkeypatch.setenv("KANBAN_WIKI_PATH", "/nonexistent")
        self.wiki_dir = None
        self.test_renamed_scripted_workflows_doc_exists_and_old_is_purged()
        self.test_all_internal_wiki_links_resolve_cleanly()
        self.test_all_wiki_image_references_exist_on_disk()
        self.test_wiki_mermaid_and_headings_use_canonical_branding()

    def test_github_heading_slug_and_extract_slugs_unit(self) -> None:
        """Unit test confirming heading slug extraction and deduplication logic."""
        sample_md = (
            "# Main Title\n"
            "## 1. First [Section](http://example.com)\n"
            "### Duplicate Heading\n"
            "### Duplicate Heading\n"
            "#### `code_snippet` in heading\n"
            "##### <span class='tag'>HTML Tag</span>\n"
        )
        slugs = extract_heading_slugs(sample_md)
        assert "main-title" in slugs
        assert "1-first-section" in slugs or "first-section" in slugs
        assert "duplicate-heading" in slugs
        assert "duplicate-heading-1" in slugs
        assert "code_snippet-in-heading" in slugs or "code-snippet-in-heading" in slugs

        assert github_heading_slug("   ") == ""
        assert github_heading_slug("Simple Heading") == "simple-heading"

    def test_wiki_dir_resolution_and_fallbacks(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Verify get_wiki_dir supports KANBAN_WIKI_PATH, repo sibling, and None fallback."""
        fake_wiki = tmp_path / "fake.wiki"
        fake_wiki.mkdir()

        monkeypatch.setenv("KANBAN_WIKI_PATH", str(fake_wiki))
        assert get_wiki_dir() == fake_wiki

        monkeypatch.setenv("KANBAN_WIKI_PATH", str(tmp_path / "nonexistent"))
        assert get_wiki_dir() is None

        monkeypatch.delenv("KANBAN_WIKI_PATH", raising=False)
        empty_root = tmp_path / "empty_repo"
        empty_root.mkdir()
        assert get_wiki_dir(empty_root, default_wiki=None) is None

        sibling_wiki = tmp_path / "thumbs-up-kanban.wiki"
        sibling_wiki.mkdir()
        repo_sub = tmp_path / "nested_repo"
        repo_sub.mkdir()
        assert get_wiki_dir(repo_sub, default_wiki=None) == sibling_wiki

    def test_internal_link_and_anchor_validation_unit(self) -> None:
        """Unit test confirming broken internal link and anchor detection."""
        headings = {
            "page-a": {"section-one", "section-two"},
            "page-b": {"overview"},
        }
        pages_wiki = [
            (
                "page-a",
                (
                    "[Good link](page-b#overview)\n"
                    "[Good in-page](#section-one)\n"
                    "[Broken link](nonexistent-page)\n"
                    "[Broken anchor](page-b#nonexistent)\n"
                    "[Broken in-page](#missing-section)\n"
                ),
            )
        ]
        broken_wiki = validate_markdown_links(pages_wiki, headings, is_manifest=False)
        assert len(broken_wiki) == 3
        assert ("page-a", "Broken link", "nonexistent-page") in broken_wiki
        assert ("page-a", "Broken anchor", "page-b#nonexistent") in broken_wiki
        assert ("page-a", "Broken in-page", "#missing-section") in broken_wiki

        pages_manifest = [
            (
                "page-a",
                (
                    "[Good manifest](/docs/page-b#overview)\n"
                    "[Broken manifest page](/docs/missing-doc)\n"
                    "[Broken manifest anchor](/docs/page-b#bad-anchor)\n"
                ),
            )
        ]
        broken_manifest = validate_markdown_links(pages_manifest, headings, is_manifest=True)
        assert len(broken_manifest) == 2
        assert ("page-a", "Broken manifest page", "/docs/missing-doc") in broken_manifest
        assert ("page-a", "Broken manifest anchor", "/docs/page-b#bad-anchor") in broken_manifest

    def test_image_reference_validation_unit(self, tmp_path: Path) -> None:
        """Unit test confirming broken image reference detection."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        public_dir = tmp_path / "public"
        public_dir.mkdir()

        (public_dir / "valid.png").write_text("png", encoding="utf-8")
        pages = [
            (
                "page-1",
                (
                    "![alt](images/valid.png)\n"
                    "![broken](images/missing.png)\n"
                    "![ext](https://example.com/pic.png)\n"
                ),
            )
        ]
        broken = check_image_references(pages, wiki_dir=wiki_dir, public_dir=public_dir)
        assert len(broken) == 1
        assert broken[0] == ("page-1", "broken", "images/missing.png")
