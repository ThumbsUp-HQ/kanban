"""Synchronize and bundle wiki chapters and configuration references into offline manifest."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

DEFAULT_WIKI_DIR = (
    "thumbs-up-kanban.wiki"
    if Path("thumbs-up-kanban.wiki").is_dir()
    else "/home/adamoutler/kanban/thumbs-up-kanban.wiki"
)
DEFAULT_OUT_FILE = "kanban/web/src/features/docs-center/wikiManifest.ts"
DEFAULT_PUBLIC_DIR = "kanban/web/public"

CHAPTER_TAXONOMY: dict[str, dict[str, str]] = {
    "home": {
        "category": "informational",
        "track": "Overview",
        "subtrack": "Overview",
        "audience": "All Roles & Stakeholders",
    },
    # Track 1: Step-by-Step Guides
    "production-promotion-and-backup-runbook": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Deployment & Backups",
        "audience": "DevOps & Platform Operators",
    },
    "migration-and-cutover-runbook": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Data Migration",
        "audience": "Enterprise Administrators",
    },
    "guide-custom-fields": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Custom Fields",
        "audience": "Project & Workspace Admins",
    },
    "scripted-workflows-and-transition-helpers": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Workflow Automation",
        "audience": "Engineers & Workflow Designers",
    },
    "multi-card-authentication-studio": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Authentication & Identity",
        "audience": "Security & Identity Administrators",
    },
    "multi-provider-ai-engine-and-runners": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "AI & Distributed Runners",
        "audience": "DevOps & Platform Architects",
    },
    "three-surface-mcp-server-architecture": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "MCP & OAuth Clients",
        "audience": "Autonomous Agent Developers",
    },
    "admin-diagnostics-and-link-inspector-studio": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Diagnostics & Maintenance",
        "audience": "System Administrators & Core Maintainers",
    },
    "multi-source-migration-and-key-alias-redirects": {
        "category": "guide",
        "track": "Step-by-Step Guides",
        "subtrack": "Data Migration",
        "audience": "Enterprise Administrators & DevOps Engineers",
    },
    # Track 2: Feature & Field Reference
    "studio-configuration-reference": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Studio Configuration",
        "audience": "Workspace & Project Administrators",
    },
    "enterprise-whitespace-and-kanban-board": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Board & Visual Design",
        "audience": "End Users & Product Leads",
    },
    "ticket-screen-and-work-item-features": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Issue Studio & Peek Drawer",
        "audience": "Software Engineers & Contributors",
    },
    "hierarchical-docs-and-stickies-with-smart-promotion": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Knowledge Management",
        "audience": "Technical Writers & Product Managers",
    },
    "blinking-cursor-sparkle-completion-engine": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Inline AI Completion",
        "audience": "Authors & Engineers",
    },
    "mcp-tools-reference": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Protocol Reference",
        "audience": "AI Integrators & Developers",
    },
    "rest-api-architecture-and-openapi-guide": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "API & SDK Reference",
        "audience": "Frontend & Backend Developers",
    },
    "statistical-flow-telemetry-and-lean-analytics": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Flow Telemetry & Analytics",
        "audience": "Engineering Leads, Product Managers & Scrum Masters",
    },
    # Track 3: Security & Adoption Overview
    "role-and-permission-matrix": {
        "category": "informational",
        "track": "Security & Adoption Overview",
        "subtrack": "Access Control & Governance",
        "audience": "Security Officers & Compliance Auditors",
    },
    "zero-trust-security-and-access-visibility": {
        "category": "informational",
        "track": "Security & Adoption Overview",
        "subtrack": "Zero-Trust Architecture",
        "audience": "Security Architects & Hardening Engineers",
    },
    "security-and-stride-threat-matrix": {
        "category": "informational",
        "track": "Security & Adoption Overview",
        "subtrack": "Zero-Trust Architecture",
        "audience": "Security Officers & Compliance Auditors",
    },
    "feature-comparison": {
        "category": "informational",
        "track": "Security & Adoption Overview",
        "subtrack": "Market & Capability Analysis",
        "audience": "Technology Evaluators & Leadership",
    },
    # Track 4: Engineering & Security Architecture
    "system-topology-and-multi-container-architecture": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Functional Architecture",
        "audience": "Infrastructure & Systems Architects",
    },
    "universal-object-graph-and-link-auditor": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Functional Architecture",
        "audience": "Database Engineers & Core Architects",
    },
    "real-time-web-and-websocket-architecture": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Functional Architecture",
        "audience": "Realtime Systems & Network Engineers",
    },
    "canonical-markdown-and-safe-media-pipeline": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Functional Architecture",
        "audience": "Security Engineers & Content Architects",
    },
    "clean-db-testing-and-governance-gates": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Functional Architecture",
        "audience": "QA Engineers & Test Automation Leads",
    },
    "admin-custom-scripted-fields-and-sandbox": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Security Architecture",
        "audience": "Security Architects & Sandbox Engineers",
    },
    "custom-scripts-and-json-security-architecture": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Security Architecture",
        "audience": "Application Security Engineers",
    },
    "zero-trust-service-auth-and-workload-oidc": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Security Architecture",
        "audience": "Security Architects & Application Engineers",
    },
    "agent-lease-fencing-workpads-and-push-protection": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Agent Systems Architecture",
        "audience": "AI Platform Architects & Autonomous Agent Developers",
    },
    "architecture-delta-and-missing-features": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Engineering Appendix",
        "audience": "Core Contributors & Maintainers",
    },
    "user-tasks-and-qa-matrix": {
        "category": "architectural",
        "track": "Engineering & Security Architecture",
        "subtrack": "Engineering Appendix",
        "audience": "Forensic QA & Certification Auditors",
    },
    "configuration-value-reference": {
        "category": "informational",
        "track": "Feature & Field Reference",
        "subtrack": "Studio Configuration",
        "audience": "System Administrators",
    },
}


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

        item_match = re.match(r"^\s*-\s+\[(.+)\]\(([^)]+)\)", line)
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
    excluded_prefixes = ("#", "-", "*", "|", ">", "```", "---", "<")

    for line in lines:
        h1_match = re.match(r"^#\s+(.+)$", line)
        if h1_match and not title:
            raw_title = h1_match.group(1).strip()
            title = sanitize_dashes(raw_title)
            continue

        h_match = re.match(r"^(#{2,3})\s+(.+)$", line)
        if h_match:
            level = len(h_match.group(1))
            sec_title = sanitize_dashes(h_match.group(2).strip().replace("`", ""))
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
                "description": "Project workflows, transition helpers, and custom fields.",
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
        "# [Informational] Configuration Value Reference",
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
    meta = CHAPTER_TAXONOMY["configuration-value-reference"]
    return {
        "slug": "configuration-value-reference",
        "title": "[Informational] Configuration Value Reference",
        "category": meta["category"],
        "track": meta["track"],
        "subtrack": meta["subtrack"],
        "audience": meta["audience"],
        "order": order_idx,
        "summary": "Reference guide for system environment variables and execution tiers.",
        "sections": config_sections,
        "content": content,
    }


def sync_wiki_images(wiki_path: Path, public_dir: Path) -> int:
    """Copy wiki image assets into public/docs-images directory."""
    images_src = wiki_path / "images"
    if not images_src.exists() or not images_src.is_dir():
        fallback = Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki/images")
        if fallback.exists() and fallback.is_dir():
            images_src = fallback
        else:
            return 0

    docs_images_dir = public_dir / "docs-images"
    docs_images_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    for img in sorted(images_src.iterdir()):
        if img.is_file() and img.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg", ".webp"}:
            shutil.copy2(img, docs_images_dir / img.name)
            copied += 1
    return copied


def load_chapters_from_wiki(wiki_path: Path, file_to_cat: dict[str, str]) -> list[dict[str, Any]]:
    """Scan and parse markdown files from the wiki directory."""
    chapters: list[dict[str, Any]] = []
    all_files = [f for f in sorted(wiki_path.glob("*.md")) if not f.stem.startswith("_")]
    home_files = [f for f in all_files if f.stem.lower() == "home"]
    other_files = [f for f in all_files if f.stem.lower() != "home"]
    md_files = home_files + other_files
    order_idx = 1

    for md_file in md_files:
        name = md_file.stem
        raw_content = md_file.read_text(encoding="utf-8")
        clean_content = sanitize_dashes(raw_content)

        slug = name.lower()
        sections, extracted_title, summary = extract_sections_and_summary(clean_content)
        title = extracted_title or name.replace("-", " ")

        taxonomy = CHAPTER_TAXONOMY.get(
            slug,
            {
                "category": (
                    "guide"
                    if title.startswith("[Guide]")
                    else (
                        "architectural" if title.startswith("[Architectural]") else "informational"
                    )
                ),
                "track": file_to_cat.get(slug, "Feature & Field Reference"),
                "subtrack": "General",
                "audience": "Developers & Operators",
            },
        )

        chapters.append(
            {
                "slug": slug,
                "title": title,
                "category": taxonomy["category"],
                "track": taxonomy["track"],
                "subtrack": taxonomy["subtrack"],
                "audience": taxonomy["audience"],
                "order": order_idx,
                "summary": summary or f"Documentation guide for {title}.",
                "sections": sections,
                "content": clean_content,
            }
        )
        order_idx += 1

    chapters.append(build_config_chapter(order_idx))
    return chapters


def generate_manifest_ts(
    chapters: list[dict[str, Any]],
    slug_aliases: dict[str, str],
    sidebar_categories: list[dict[str, Any]] | None = None,
) -> str:
    """Format and generate the TypeScript bundle string."""
    slug_to_chapter = {ch["slug"]: ch for ch in chapters}
    categories_list: list[dict[str, Any]] = []

    if sidebar_categories:
        for cat in sidebar_categories:
            cat_chapters = []
            for ch in cat["chapters"]:
                target_slug = ch["file"].lower()
                ch_obj = slug_to_chapter.get(target_slug)
                if ch_obj:
                    cat_chapters.append(
                        {
                            "slug": target_slug,
                            "title": ch_obj["title"],
                            "category": ch_obj["category"],
                        }
                    )
            if cat_chapters:
                categories_list.append({"name": cat["name"], "chapters": cat_chapters})

    included_slugs = {item["slug"] for cat in categories_list for item in cat["chapters"]}
    for ch in chapters:
        if ch["slug"] not in included_slugs:
            target_cat_name = "Track 2: Feature & Field Reference"
            target_cat = next((c for c in categories_list if c["name"] == target_cat_name), None)
            if target_cat:
                target_cat["chapters"].append(
                    {
                        "slug": ch["slug"],
                        "title": ch["title"],
                        "category": ch["category"],
                    }
                )
            else:
                categories_list.append(
                    {
                        "name": ch["track"],
                        "chapters": [
                            {
                                "slug": ch["slug"],
                                "title": ch["title"],
                                "category": ch["category"],
                            }
                        ],
                    }
                )

    config_refs = build_configuration_reference()
    dumped_chapters = json.dumps(chapters, indent=2)
    dumped_categories = json.dumps(categories_list, indent=2)
    dumped_config = json.dumps(config_refs, indent=2)
    dumped_aliases = json.dumps(slug_aliases, indent=2)

    ts_code = f"""// Copyright 2026 Kanban Platform Contributors
// Apache-2.0 License. See LICENSE for details.
// Generated automatically by scripts/sync_wiki_bundle.py. Do not edit manually.

export type WikiChapterCategory = 'guide' | 'informational' | 'architectural';

export interface WikiSection {{
  id: string;
  title: string;
  level: number;
}}

export interface WikiChapter {{
  slug: string;
  title: string;
  category: WikiChapterCategory;
  track: string;
  subtrack: string;
  audience: string;
  order: number;
  summary: string;
  sections: WikiSection[];
  content: string;
}}

export interface WikiCategory {{
  name: string;
  chapters: {{ slug: string; title: string; category?: WikiChapterCategory }}[];
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


def sync_wiki(
    wiki_dir_str: str,
    out_file_str: str,
    public_dir_str: str = DEFAULT_PUBLIC_DIR,
) -> None:
    """Read wiki files, bundle into manifest, copy images, and write TypeScript module."""
    wiki_path = Path(wiki_dir_str)
    out_path = Path(out_file_str)
    public_path = Path(public_dir_str)

    if not wiki_path.exists() or not wiki_path.is_dir():
        sys.stderr.write(f"Error: wiki directory {wiki_dir_str} does not exist.\n")
        sys.exit(1)

    sidebar_file = wiki_path / "_Sidebar.md"
    sidebar_content = ""
    if sidebar_file.exists():
        sidebar_content = sidebar_file.read_text(encoding="utf-8")

    categories_spec, file_to_cat = parse_sidebar(sidebar_content)

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
        "workspace-settings": "studio-configuration-reference",
        "project-settings": "studio-configuration-reference",
        "personal-settings": "studio-configuration-reference",
        "user-profile-and-personal-settings": "studio-configuration-reference",
        "diagnostics": "admin-diagnostics-and-link-inspector-studio",
        "link-inspector": "admin-diagnostics-and-link-inspector-studio",
        "migration": "multi-source-migration-and-key-alias-redirects",
        "migrations": "multi-source-migration-and-key-alias-redirects",
        "importers": "multi-source-migration-and-key-alias-redirects",
        "service-auth": "zero-trust-service-auth-and-workload-oidc",
        "workload-oidc": "zero-trust-service-auth-and-workload-oidc",
        "flow": "statistical-flow-telemetry-and-lean-analytics",
        "flow-telemetry": "statistical-flow-telemetry-and-lean-analytics",
        "analytics": "statistical-flow-telemetry-and-lean-analytics",
        "lease": "agent-lease-fencing-workpads-and-push-protection",
        "leases": "agent-lease-fencing-workpads-and-push-protection",
        "workpad": "agent-lease-fencing-workpads-and-push-protection",
        "push-protection": "agent-lease-fencing-workpads-and-push-protection",
        "rbac": "role-and-permission-matrix",
        "auth-studio": "multi-card-authentication-studio",
        "user-profile-and-personal-settings": "studio-configuration-reference",
    }

    copied_images = sync_wiki_images(wiki_path, public_path)

    chapters = load_chapters_from_wiki(wiki_path, file_to_cat)
    ts_code = generate_manifest_ts(chapters, slug_aliases, categories_spec)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ts_code, encoding="utf-8")
    count = len(chapters)
    size = len(ts_code)
    sys.stdout.write(
        f"Successfully synchronized {count} wiki chapters into {out_file_str} ({size} bytes, "
        f"{copied_images} images copied to {public_dir_str}/docs-images).\n"
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
    parser.add_argument(
        "--public-dir",
        default=DEFAULT_PUBLIC_DIR,
        help="Target public web directory for static documentation assets.",
    )
    args = parser.parse_args()
    sync_wiki(args.wiki_dir, args.out_file, args.public_dir)


if __name__ == "__main__":
    main()
