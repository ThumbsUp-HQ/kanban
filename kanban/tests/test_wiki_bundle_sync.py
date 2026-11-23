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
