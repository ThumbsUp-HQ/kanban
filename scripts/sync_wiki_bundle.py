"""Synchronize and bundle wiki chapters and configuration references into offline manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

DEFAULT_WIKI_DIR = "/home/adamoutler/kanban/thumbs-up-kanban.wiki"
DEFAULT_OUT_FILE = "kanban/web/src/features/docs-center/wikiManifest.ts"


def slugify(text: str) -> str:
    """Generate a clean URL-safe anchor slug from heading text."""
    clean = re.sub(r"\[.*?\]\(.*?\)", "", text)  # remove links
    clean = re.sub(r"`.*?`", "", clean)  # remove inline code
    clean = re.sub(r"^[0-9]+\.\s*", "", clean.strip())  # remove leading numbers
    clean = clean.lower().strip()
    clean = re.sub(r"[^a-z0-9\s_-]", "", clean)
    clean = re.sub(r"[\s_]+", "-", clean)
    return clean.strip("-") or "section"


def sanitize_dashes(text: str) -> str:
    """Ensure zero em-dash or en-dash characters exist in output."""
    return text.replace("\u2014", "-").replace("\u2013", "-")


def parse_sidebar(sidebar_content: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Parse _Sidebar.md to extract category hierarchies and chapter titles."""
    categories: list[dict[str, Any]] = []
    current_category: dict[str, Any] | None = None
    file_to_category: dict[str, str] = {}

    for line in sidebar_content.splitlines():
        cat_match = re.match(r"^-\s+\*\*(.*?)\*\*", line)
        if cat_match:
            cat_name = cat_match.group(1).strip()
            current_category = {"name": cat_name, "chapters": []}
            categories.append(current_category)
            continue

        item_match = re.match(r"^\s+-\s+\[(.*?)\]\((.*?)\)", line)
        if item_match and current_category:
            title = item_match.group(1).strip()
            target = item_match.group(2).strip()
            target_slug = target.replace(".md", "")
            current_category["chapters"].append({"title": title, "file": target_slug})
            file_to_category[target_slug.lower()] = current_category["name"]

    return categories, file_to_category


def extract_sections_and_summary(content: str) -> tuple[list[dict[str, Any]], str, str]:
    """Extract sections, anchor ids, main title, and excerpt summary from markdown."""
    lines = content.splitlines()
    sections: list[dict[str, Any]] = []
    title = ""
    summary = ""
    paragraph_lines: list[str] = []
    excluded_prefixes = ("#", "-", "*", "|", ">", "```", "---")

    for line in lines:
        h1_match = re.match(r"^#\s+(.+)$", line)
        if h1_match and not title:
            raw_title = h1_match.group(1).strip()
            raw_title = re.sub(r"^\[.*?\]\s*", "", raw_title)  # strip [Guide] prefix
            title = sanitize_dashes(raw_title)
            continue

        h_match = re.match(r"^(#{2,3})\s+(.+)$", line)
        if h_match:
            level = len(h_match.group(1))
            sec_title = sanitize_dashes(h_match.group(2).strip())
            sec_id = slugify(sec_title)
            sections.append({"id": sec_id, "title": sec_title, "level": level})
            continue

        if not summary and line.strip() and not line.startswith(excluded_prefixes):
            paragraph_lines.append(line.strip())
        elif paragraph_lines and not summary:
            summary = sanitize_dashes(" ".join(paragraph_lines))

    if not summary and paragraph_lines:
        summary = sanitize_dashes(" ".join(paragraph_lines))

    return sections, title, summary


def build_configuration_reference() -> dict[str, list[dict[str, str]]]:
    """Build structured configuration value reference tables."""
    return {
        "environment_variables": [
            {
                "key": "DATABASE_URL",
                "type": "string (URL)",
                "default": "postgresql://kanban:kanban@localhost:5432/kanban",
                "description": "PostgreSQL connection string with UTF-8 and RLS support.",
            },
            {
                "key": "KANBAN_STANDALONE_MODE",
                "type": "boolean",
                "default": "false",
                "description": "Single-container standalone flag. Gates nsjail sandboxes.",
            },
            {
                "key": "KANBAN_SECRET_KEY",
                "type": "string (min 32 chars)",
                "default": "(required)",
                "description": "Cryptographic key for signing session cookies and tokens.",
            },
            {
                "key": "AI_PROVIDER",
                "type": "enum (openai, gemini, ollama, custom)",
                "default": "gemini",
                "description": "Default active AI engine provider for sparkle completions.",
            },
            {
                "key": "RUNNER_MTLS_CERT_PATH",
                "type": "string (filesystem path)",
                "default": "/etc/kanban/certs/client.crt",
                "description": "Client cert for outbound mTLS remote repository runners.",
            },
        ],
        "custom_field_tiers": [
            {
                "tier": "scalar",
                "latency_budget": "<1ms",
                "standalone": "Supported",
                "compose": "Supported",
                "description": "Static metadata, manual attributes, default strings.",
            },
            {
                "tier": "formula",
                "latency_budget": "<5ms",
                "standalone": "Supported",
                "compose": "Supported",
                "description": "In-process Python AST math, date arithmetic, conditionals.",
            },
            {
                "tier": "wasm",
                "latency_budget": "<25ms",
                "standalone": "Supported",
                "compose": "Supported",
                "description": "Compiled C, Rust, or AssemblyScript wasmtime runtime.",
            },
            {
                "tier": "nsjail",
                "latency_budget": "<250ms",
                "standalone": "Gated (Fail-closed)",
                "compose": "Supported",
                "description": "Isolated Linux namespace sandbox container.",
            },
        ],
        "system_roles_and_capabilities": [
            {
                "role": "SERVER_ADMIN",
                "scope": "Server",
                "description": "Full administrative authority over authentication and runners.",
            },
            {
                "role": "WORKSPACE_ADMIN",
                "scope": "Workspace",
                "description": "Workspace policy, user provisioning, and group management.",
            },
            {
                "role": "PROJECT_ADMIN",
                "scope": "Project",
                "description": "Project workflows, transition interceptors, and custom fields.",
            },
            {
                "role": "MEMBER",
                "scope": "Project/Workspace",
                "description": "Create, edit, transition, and comment on work items and docs.",
            },
            {
                "role": "VIEWER",
                "scope": "Project/Workspace",
                "description": "Read-only access to work items, boards, and docs.",
            },
        ],
    }


def build_config_chapter(order_idx: int) -> dict[str, Any]:
    """Generate the synthetic Configuration Value Reference chapter."""
    config_refs = build_configuration_reference()
    config_sections = [
        {"id": "environment-variables", "title": "Environment Variables", "level": 2},
        {"id": "custom-field-tiers", "title": "Custom Field Execution Tiers", "level": 2},
        {"id": "system-roles", "title": "System Roles and Capabilities", "level": 2},
    ]

    lines = [
        "# Configuration Value Reference",
        "",
        "Authoritative reference guide for system environment variables and execution tiers.",
        "",
        "## Environment Variables",
        "",
        "| Key | Type | Default | Description |",
        "| :--- | :--- | :--- | :--- |",
    ]
    lines.extend(
        f"| `{item['key']}` | {item['type']} | `{item['default']}` | {item['description']} |"
        for item in config_refs["environment_variables"]
    )
    lines.extend(
        [
            "",
            "## Custom Field Execution Tiers",
            "",
            "| Tier | Latency Budget | Standalone Mode | Multi-Container Compose | Best Used For |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    lines.extend(
        f"| **{t['tier']}** | {t['latency_budget']} | {t['standalone']} | "
        f"{t['compose']} | {t['description']} |"
        for t in config_refs["custom_field_tiers"]
    )
    lines.extend(
        [
            "",
            "## System Roles and Capabilities",
            "",
            "| Role | Scope | Description |",
            "| :--- | :--- | :--- |",
        ]
    )
    lines.extend(
        f"| **{r['role']}** | {r['scope']} | {r['description']} |"
        for r in config_refs["system_roles_and_capabilities"]
    )

    content = sanitize_dashes("\n".join(lines))
    return {
        "slug": "configuration-value-reference",
        "title": "Configuration Value Reference",
        "category": "Reference Guides",
        "order": order_idx,
        "summary": "Reference guide for system environment variables and execution tiers.",
        "sections": config_sections,
        "content": content,
    }


def load_chapters_from_wiki(wiki_path: Path, file_to_cat: dict[str, str]) -> list[dict[str, Any]]:
    """Scan and parse markdown files from the wiki directory."""
    chapters: list[dict[str, Any]] = []
    md_files = sorted(wiki_path.glob("*.md"))
    order_idx = 1

    for md_file in md_files:
        name = md_file.stem
        if name.startswith("_"):
            continue

        raw_content = md_file.read_text(encoding="utf-8")
        clean_content = sanitize_dashes(raw_content)

        slug = name.lower()
        sections, extracted_title, summary = extract_sections_and_summary(clean_content)
        title = extracted_title or name.replace("-", " ")
        category = file_to_cat.get(slug, "Reference Guides")

        chapters.append(
            {
                "slug": slug,
                "title": title,
                "category": category,
                "order": order_idx,
                "summary": summary or f"Documentation guide for {title}.",
                "sections": sections,
                "content": clean_content,
            }
        )
        order_idx += 1

    chapters.append(build_config_chapter(order_idx))
    return chapters


def generate_manifest_ts(chapters: list[dict[str, Any]], slug_aliases: dict[str, str]) -> str:
    """Format and generate the TypeScript bundle string."""
    categories_dict: dict[str, list[dict[str, str]]] = {}
    for ch in chapters:
        cat_name = ch["category"]
        if cat_name not in categories_dict:
            categories_dict[cat_name] = []
        categories_dict[cat_name].append({"slug": ch["slug"], "title": ch["title"]})

    categories_list = [
        {"name": cat_name, "chapters": chapter_list}
        for cat_name, chapter_list in categories_dict.items()
    ]

    config_refs = build_configuration_reference()
    dumped_chapters = json.dumps(chapters, indent=2)
    dumped_categories = json.dumps(categories_list, indent=2)
    dumped_config = json.dumps(config_refs, indent=2)
    dumped_aliases = json.dumps(slug_aliases, indent=2)

    ts_code = f"""// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
// Generated automatically by scripts/sync_wiki_bundle.py. Do not edit manually.

export interface WikiSection {{
  id: string;
  title: string;
  level: number;
}}

export interface WikiChapter {{
  slug: string;
  title: string;
  category: string;
  order: number;
  summary: string;
  sections: WikiSection[];
  content: string;
}}

export interface WikiCategory {{
  name: string;
  chapters: {{ slug: string; title: string }}[];
}}

export type ConfigReferenceItem = Record<string, string>;

export const WIKI_CHAPTERS: WikiChapter[] = {dumped_chapters};

export const WIKI_CATEGORIES: WikiCategory[] = {dumped_categories};

export const CONFIG_REFERENCES: Record<string, ConfigReferenceItem[]> = {dumped_config};

export const SLUG_ALIASES: Record<string, string> = {dumped_aliases};

export const CHAPTER_BY_SLUG: Record<string, WikiChapter> = Object.fromEntries(
  WIKI_CHAPTERS.map((ch) => [ch.slug, ch]),
);

export function resolveChapterSlug(slugOrAlias: string): string {{
  const normalized = slugOrAlias.toLowerCase().trim().replace(/^#+/, '');
  if (CHAPTER_BY_SLUG[normalized]) {{
    return normalized;
  }}
  if (SLUG_ALIASES[normalized]) {{
    return SLUG_ALIASES[normalized];
  }}
  return normalized;
}}

export function getChapter(slugOrAlias: string): WikiChapter | undefined {{
  const resolved = resolveChapterSlug(slugOrAlias);
  return CHAPTER_BY_SLUG[resolved];
}}
"""
    return sanitize_dashes(ts_code)


def sync_wiki(wiki_dir_str: str, out_file_str: str) -> None:
    """Read wiki files, bundle into manifest, and write TypeScript module."""
    wiki_path = Path(wiki_dir_str)
    out_path = Path(out_file_str)

    if not wiki_path.exists() or not wiki_path.is_dir():
        sys.stderr.write(f"Error: wiki directory {wiki_dir_str} does not exist.\n")
        sys.exit(1)

    sidebar_file = wiki_path / "_Sidebar.md"
    sidebar_content = ""
    if sidebar_file.exists():
        sidebar_content = sidebar_file.read_text(encoding="utf-8")

    _categories_spec, file_to_cat = parse_sidebar(sidebar_content)

    slug_aliases = {
        "custom-fields": "guide-custom-fields",
        "roles": "role-and-permission-matrix",
        "permissions": "role-and-permission-matrix",
        "auth": "multi-card-authentication-studio",
        "mcp": "mcp-tools-reference",
        "mcp-server": "three-surface-mcp-server-architecture",
        "api": "rest-api-architecture-and-openapi-guide",
        "workflows": "scriptrunner-workflows-and-transition-interceptors",
        "ai": "multi-provider-ai-engine-and-runners",
        "standalone": "production-promotion-and-backup-runbook",
        "links": "universal-object-graph-and-link-auditor",
        "config": "configuration-value-reference",
        "configuration": "configuration-value-reference",
    }

    chapters = load_chapters_from_wiki(wiki_path, file_to_cat)
    ts_code = generate_manifest_ts(chapters, slug_aliases)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ts_code, encoding="utf-8")
    count = len(chapters)
    size = len(ts_code)
    sys.stdout.write(
        f"Successfully synchronized {count} wiki chapters into {out_file_str} ({size} bytes).\n"
    )


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Synchronize wiki bundle into offline TypeScript manifest."
    )
    parser.add_argument(
        "--wiki-dir",
        default=DEFAULT_WIKI_DIR,
        help="Path to wiki repository directory containing .md chapters.",
    )
    parser.add_argument(
        "--out-file",
        default=DEFAULT_OUT_FILE,
        help="Target TypeScript file to generate.",
    )
    args = parser.parse_args()
    sync_wiki(args.wiki_dir, args.out_file)


if __name__ == "__main__":
    main()
