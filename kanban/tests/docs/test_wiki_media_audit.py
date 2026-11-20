"""Wiki media, link resolution, and document structure audit tests (KAN-56)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

DEFAULT_WIKI_DIR = Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki")


def get_wiki_dir() -> Path:
    """Resolve the authoritative wiki directory path."""
    env_path = os.environ.get("KANBAN_WIKI_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p
    return DEFAULT_WIKI_DIR


class TestWikiMediaAndLinkAudit:
    """Validates wiki document renames, media assets, and link integrity."""

    @pytest.fixture(autouse=True)
    def setup_wiki(self) -> None:
        """Fixture configuring authoritative wiki path for assertions."""
        self.wiki_dir = get_wiki_dir()
        if not self.wiki_dir.exists():
            pytest.skip(f"Wiki directory not found at {self.wiki_dir}")

    def test_renamed_scripted_workflows_doc_exists_and_old_is_purged(self) -> None:
        """Assert Scripted-Workflows-and-Transition-Helpers.md exists and old file is gone."""
        canonical_file = self.wiki_dir / "Scripted-Workflows-and-Transition-Helpers.md"
        obsolete_file = self.wiki_dir / "ScriptRunner-Workflows-and-Transition-Interceptors.md"

        assert canonical_file.is_file(), f"Expected canonical wiki doc to exist: {canonical_file}"
        assert not obsolete_file.exists(), (
            f"Obsolete wiki doc must not exist after rename: {obsolete_file}"
        )

    def test_all_internal_wiki_links_resolve_cleanly(self) -> None:
        """Assert all internal markdown links across all wiki pages resolve cleanly."""
        all_md_files = {
            f.name[:-3] for f in self.wiki_dir.iterdir() if f.is_file() and f.name.endswith(".md")
        }
        assert len(all_md_files) > 0, "No markdown files found in wiki directory"

        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        broken_links: list[tuple[str, str, str]] = []

        for md_file in sorted(self.wiki_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            for text, link in link_pattern.findall(content):
                link_clean = link.strip()
                # Skip external links, pure anchors, and media paths
                if link_clean.startswith(("http://", "https://", "#", "images/", "mailto:")):
                    continue

                # Strip anchor fragment
                target = link_clean.split("#")[0].split("?")[0]
                if not target:
                    continue

                # Strip .md extension if present
                target_slug = target.removesuffix(".md")
                if target_slug not in all_md_files:
                    broken_links.append((md_file.name, text, link_clean))

        assert not broken_links, (
            f"Found {len(broken_links)} broken internal wiki link(s): {broken_links}"
        )

    def test_all_wiki_image_references_exist_on_disk(self) -> None:
        """Assert all local media and image references point to valid files."""
        img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
        broken_images: list[tuple[str, str, str]] = []

        for md_file in sorted(self.wiki_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            for alt, src in img_pattern.findall(content):
                src_clean = src.strip()
                if src_clean.startswith(("http://", "https://")):
                    continue

                clean_src = src_clean.split("#")[0].split("?")[0]
                resolved_path = (self.wiki_dir / clean_src).resolve()
                if not resolved_path.is_file():
                    broken_images.append((md_file.name, alt, src_clean))

        assert not broken_images, (
            f"Found {len(broken_images)} broken image link(s): {broken_images}"
        )

    def test_wiki_mermaid_and_headings_use_canonical_branding(self) -> None:
        """Assert canonical file contains HelperEngine and no old interceptor headings."""
        canonical_file = self.wiki_dir / "Scripted-Workflows-and-Transition-Helpers.md"
        content = canonical_file.read_text(encoding="utf-8")

        assert 'HelperEngine["Transition Helper Engine"]' in content
        assert "## Helper Architecture" in content
        assert "## Failure Policies" in content
        assert "ScriptRunner" not in content
        assert "Transition Interceptor Engine" not in content
