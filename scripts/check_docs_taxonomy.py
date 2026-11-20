"""Automated documentation taxonomy, title classification, and link audit gate (KAN-33)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_WIKI_DIR = "/home/adamoutler/kanban/thumbs-up-kanban.wiki"
DEFAULT_MANIFEST_PATH = "kanban/web/src/features/docs-center/wikiManifest.ts"
DEFAULT_WEB_SRC_DIR = "kanban/web/src"

FORBIDDEN_DASHES = {"\u2014": "U+2014 (em-dash)", "\u2013": "U+2013 (en-dash)"}
VALID_CATEGORIES = {"guide", "informational", "architectural"}
VALID_PREFIXES = ("# [Guide] ", "# [Informational] ", "# [Architectural] ")
VALID_TITLE_PREFIXES = ("[Guide] ", "[Informational] ", "[Architectural] ")
EXEMPT_WIKI_FILES = {"Home.md", "_Sidebar.md", "_Footer.md"}


def slugify_anchor(text: str) -> str:
    """Generate a clean URL-safe anchor slug from heading text."""
    clean = re.sub(r"\[.*?\]\(.*?\)", "", text)
    clean = re.sub(r"`.*?`", "", clean)
    clean = re.sub(r"^[0-9]+\.\s*", "", clean.strip())
    clean = clean.lower().strip()
    clean = re.sub(r"[^a-z0-9\s_-]", "", clean)
    clean = re.sub(r"[\s_]+", "-", clean)
    return clean.strip("-") or "section"


def extract_wiki_anchors(content: str) -> set[str]:
    """Extract all heading and anchor IDs from markdown content."""
    anchors: set[str] = set()
    for line in content.splitlines():
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            slug = slugify_anchor(heading_match.group(2))
            if slug:
                anchors.add(slug)
        for anchor_match in re.finditer(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', line):
            anchors.add(anchor_match.group(1).lower().strip("-"))
    return anchors


def check_wiki_chapters_taxonomy(wiki_dir: Path) -> list[str]:
    """Assert wiki chapter H1 starts with [Guide], [Informational], or [Architectural]."""
    violations: list[str] = []
    md_files = sorted(wiki_dir.glob("*.md"))
    if not md_files:
        violations.append(f"No markdown files found in wiki directory: {wiki_dir}")
        return violations

    for md_file in md_files:
        if md_file.name in EXEMPT_WIKI_FILES:
            continue

        content = md_file.read_text(encoding="utf-8")
        h1_line = ""
        for line in content.splitlines():
            if line.startswith("# "):
                h1_line = line.strip()
                break

        if not h1_line:
            violations.append(f"{md_file.name}: Missing H1 title heading (# ...)")
        elif not any(h1_line.startswith(prefix) for prefix in VALID_PREFIXES):
            violations.append(
                f"{md_file.name}: H1 title must start with '# [Guide] ', '# [Informational] ', "
                f"or '# [Architectural] '. Found: '{h1_line}'"
            )

    return violations


def _validate_manifest_chapter(ch: dict[str, Any]) -> list[str]:
    """Validate metadata fields and title classification for a single manifest chapter entry."""
    violations: list[str] = []
    slug = ch.get("slug", "")
    title = ch.get("title", "")
    category = ch.get("category", "")
    track = ch.get("track", "")
    subtrack = ch.get("subtrack", "")
    audience = ch.get("audience", "")

    if slug == "home":
        if not category or category not in VALID_CATEGORIES:
            violations.append(
                f"Chapter '{slug}': category must be one of {VALID_CATEGORIES}. Found: '{category}'"
            )
        if not track:
            violations.append(f"Chapter '{slug}': Missing required 'track' metadata")
        if not audience:
            violations.append(f"Chapter '{slug}': Missing required 'audience' metadata")
        return violations

    if not any(title.startswith(prefix) for prefix in VALID_TITLE_PREFIXES):
        violations.append(
            f"Chapter '{slug}': Title must start with '[Guide] ', '[Informational] ', "
            f"or '[Architectural] '. Found: '{title}'"
        )
    if category not in VALID_CATEGORIES:
        violations.append(
            f"Chapter '{slug}': Invalid category '{category}'. Must be one of {VALID_CATEGORIES}"
        )
    if not track:
        violations.append(f"Chapter '{slug}': Missing required 'track' metadata")
    if not subtrack:
        violations.append(f"Chapter '{slug}': Missing required 'subtrack' metadata")
    if not audience:
        violations.append(f"Chapter '{slug}': Missing required 'audience' metadata")
    return violations


def check_manifest_taxonomy(manifest_path: Path) -> list[str]:
    """Assert every WIKI_CHAPTERS entry has valid classification title and metadata fields."""
    violations: list[str] = []
    if not manifest_path.is_file():
        violations.append(f"Manifest file not found: {manifest_path}")
        return violations

    content = manifest_path.read_text(encoding="utf-8")
    chapters_match = re.search(
        r"export const WIKI_CHAPTERS: WikiChapter\[\] = (\[.*?\]);",
        content,
        re.DOTALL,
    )
    if not chapters_match:
        violations.append(f"{manifest_path.name}: Failed to locate WIKI_CHAPTERS array in manifest")
        return violations

    try:
        chapters = json.loads(chapters_match.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        violations.append(f"{manifest_path.name}: Failed to parse WIKI_CHAPTERS JSON: {exc}")
        return violations

    for ch in chapters:
        violations.extend(_validate_manifest_chapter(ch))

    return violations


def build_wiki_chapter_anchors_map(wiki_dir: Path) -> dict[str, set[str]]:
    """Build a map of lowercase chapter slug -> set of lowercase anchor IDs."""
    chapter_anchors: dict[str, set[str]] = {}
    for md_file in wiki_dir.glob("*.md"):
        slug = md_file.stem.lower()
        content = md_file.read_text(encoding="utf-8")
        chapter_anchors[slug] = extract_wiki_anchors(content)

    # Standard aliases from manifest
    slug_aliases = {
        "custom-fields": "guide-custom-fields",
        "roles": "role-and-permission-matrix",
        "permissions": "role-and-permission-matrix",
        "auth": "multi-card-authentication-studio",
        "mcp": "mcp-tools-reference",
        "mcp-server": "three-surface-mcp-server-architecture",
        "api": "rest-api-architecture-and-openapi-guide",
        "workflows": "scripted-workflows-and-transition-helpers",
        "ai": "multi-provider-ai-engine-and-runners",
        "standalone": "production-promotion-and-backup-runbook",
        "links": "universal-object-graph-and-link-auditor",
        "config": "configuration-value-reference",
        "configuration": "configuration-value-reference",
        "studio-config": "studio-configuration-reference",
        "studio-configuration": "studio-configuration-reference",
    }
    for alias, target in slug_aliases.items():
        if target in chapter_anchors and alias not in chapter_anchors:
            chapter_anchors[alias] = chapter_anchors[target]

    return chapter_anchors


def check_internal_wiki_links(wiki_dir: Path, chapter_anchors: dict[str, set[str]]) -> list[str]:
    """Verify all internal markdown links and #anchors in wiki files resolve cleanly."""
    violations: list[str] = []
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for md_file in sorted(wiki_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        current_slug = md_file.stem.lower()

        for text, raw_link in link_pattern.findall(content):
            clean_link = raw_link.strip()
            if clean_link.startswith(("http://", "https://", "mailto:", "images/")):
                continue

            if clean_link.startswith("#"):
                anchor = clean_link[1:].lower().strip("-")
                if anchor and anchor not in chapter_anchors.get(current_slug, set()):
                    violations.append(
                        f"{md_file.name}: Broken local anchor '{clean_link}' "
                        f"in link '[{text}]({clean_link})'"
                    )
                continue

            target_part = clean_link.split("?")[0]
            if "#" in target_part:
                target_file, anchor = target_part.split("#", 1)
            else:
                target_file = target_part
                anchor = None

            target_slug = target_file.removesuffix(".md").lower()
            if not target_slug:
                target_slug = current_slug

            if target_slug not in chapter_anchors:
                violations.append(
                    f"{md_file.name}: Broken internal link target '{clean_link}' "
                    f"in link '[{text}]({clean_link})'"
                )
            elif anchor and anchor.lower().strip("-") not in chapter_anchors[target_slug]:
                violations.append(
                    f"{md_file.name}: Broken anchor '#{anchor}' on target '{target_slug}' "
                    f"in link '[{text}]({clean_link})'"
                )

    return violations


def _extract_doc_links_from_code(content: str) -> set[str]:
    """Extract /docs links from TS/TSX source content."""
    extracted_links: set[str] = set()
    for m in re.finditer(r'(?:docHref|moreInfoHref)=["\'{]([^"\'}]+)["\'}]', content):
        extracted_links.add(m.group(1))
    for m in re.finditer(r'<StudioDocLink[^>]*href=["\'{]([^"\'}]+)["\'}]', content):
        extracted_links.add(m.group(1))
    for m in re.finditer(r'docSlug=["\'{]([^"\'}]+)["\'}]', content):
        extracted_links.add(f"/docs/{m.group(1)}")
    return {link for link in extracted_links if link.startswith("/docs")}


def _validate_single_code_doc_link(
    raw_link: str,
    file_path: Path,
    chapter_anchors: dict[str, set[str]],
) -> list[str]:
    """Validate a single /docs link extracted from TypeScript source code."""
    violations: list[str] = []
    clean_target = raw_link.replace("/docs/", "").replace("/docs", "")
    if "#" in clean_target:
        target_slug, anchor = clean_target.split("#", 1)
    else:
        target_slug = clean_target
        anchor = None

    target_slug = target_slug.lower().strip() or "home"
    if target_slug not in chapter_anchors:
        violations.append(
            f"{file_path}: Unknown documentation chapter '{target_slug}' in link '{raw_link}'"
        )
    elif anchor and anchor.lower().strip("-") not in chapter_anchors[target_slug]:
        violations.append(
            f"{file_path}: Unknown anchor '#{anchor}' in chapter '{target_slug}' "
            f"in link '{raw_link}'"
        )
    return violations


def check_web_src_doc_links(web_src_dir: Path, chapter_anchors: dict[str, set[str]]) -> list[str]:
    """Verify all doc links in web/src (docHref, moreInfoHref, docSlug, StudioDocLink) resolve."""
    violations: list[str] = []
    if not web_src_dir.is_dir():
        return violations

    for root, _, files in os.walk(web_src_dir):
        for file_name in files:
            if not file_name.endswith((".tsx", ".ts")):
                continue

            file_path = Path(root) / file_name
            content = file_path.read_text(encoding="utf-8")
            doc_links = _extract_doc_links_from_code(content)
            for raw_link in sorted(doc_links):
                violations.extend(
                    _validate_single_code_doc_link(raw_link, file_path, chapter_anchors)
                )

    return violations


def check_no_em_en_dashes(wiki_dir: Path, manifest_path: Path) -> list[str]:
    """Verify zero forbidden em/en-dashes exist across all wiki markdown files and the manifest."""
    violations: list[str] = []
    files_to_check: list[Path] = sorted(wiki_dir.glob("*.md"))
    if manifest_path.is_file():
        files_to_check.append(manifest_path)

    for path in files_to_check:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            violations.append(f"{path}: Invalid UTF-8 encoding")
            continue

        for line_idx, line in enumerate(content.splitlines(), start=1):
            for col_idx, char in enumerate(line, start=1):
                if char in FORBIDDEN_DASHES:
                    violations.append(
                        f"{path}:{line_idx}:{col_idx}: Forbidden dash {FORBIDDEN_DASHES[char]}"
                    )

    return violations


def run_taxonomy_audit(
    wiki_dir: Path,
    manifest_path: Path,
    web_src_dir: Path,
) -> tuple[int, list[str]]:
    """Run complete taxonomy, link resolution, and dash audit suite."""
    all_violations: list[str] = []

    # 1. Wiki chapter H1 taxonomy
    all_violations.extend(check_wiki_chapters_taxonomy(wiki_dir))

    # 2. Manifest taxonomy & metadata
    all_violations.extend(check_manifest_taxonomy(manifest_path))

    # 3. Anchor map & link checks
    chapter_anchors = build_wiki_chapter_anchors_map(wiki_dir)
    all_violations.extend(check_internal_wiki_links(wiki_dir, chapter_anchors))
    all_violations.extend(check_web_src_doc_links(web_src_dir, chapter_anchors))

    # 4. Forbidden dashes
    all_violations.extend(check_no_em_en_dashes(wiki_dir, manifest_path))

    return len(all_violations), all_violations


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for check_docs_taxonomy."""
    parser = argparse.ArgumentParser(
        description="Verify wiki & /docs information architecture, labels, and link integrity."
    )
    parser.add_argument(
        "--wiki-dir",
        default=os.environ.get("KANBAN_WIKI_PATH", DEFAULT_WIKI_DIR),
        help=f"Path to wiki markdown directory (default: {DEFAULT_WIKI_DIR})",
    )
    parser.add_argument(
        "--manifest-file",
        default=DEFAULT_MANIFEST_PATH,
        help=f"Path to wikiManifest.ts file (default: {DEFAULT_MANIFEST_PATH})",
    )
    parser.add_argument(
        "--web-src",
        default=DEFAULT_WEB_SRC_DIR,
        help=f"Path to web source directory (default: {DEFAULT_WEB_SRC_DIR})",
    )

    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    wiki_path = Path(args.wiki_dir).resolve()
    manifest_path = Path(args.manifest_file).resolve()
    web_src_path = Path(args.web_src).resolve()

    if not wiki_path.is_dir():
        sys.stderr.write(f"Error: Wiki directory does not exist: {wiki_path}\n")
        return 1

    sys.stdout.write(f"Auditing documentation taxonomy and link integrity in {wiki_path}...\n")
    count, violations = run_taxonomy_audit(wiki_path, manifest_path, web_src_path)

    if count == 0:
        sys.stdout.write(
            "OK: All documentation taxonomy, title labels, internal anchors, code links, "
            "and dashes verified successfully (0 violations).\n"
        )
        return 0

    sys.stderr.write(f"FAIL: Found {count} documentation taxonomy or link violation(s):\n")
    for v in violations:
        sys.stderr.write(f"  - {v}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
