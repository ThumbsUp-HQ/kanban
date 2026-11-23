# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Automated consistency and parity tests for Feature Comparison and Core Docs (KAN-322)."""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Final

from database.models.base import Base
from kanban.app import create_app

ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[2]
DOCS_FC_PATH: Final[Path] = ROOT_DIR / "docs" / "FEATURE_COMPARISON.md"
WIKI_FC_PATH: Final[Path] = Path(
    "/home/adamoutler/kanban/thumbs-up-kanban.wiki/Feature-Comparison.md"
)
README_PATH: Final[Path] = ROOT_DIR / "README.md"
DOCS_DELTA_PATH: Final[Path] = ROOT_DIR / "docs" / "ARCHITECTURE_DELTA.md"
WIKI_DELTA_PATH: Final[Path] = Path(
    "/home/adamoutler/kanban/thumbs-up-kanban.wiki/Architecture-Delta-and-Missing-Features.md"
)
WIKI_HOME_PATH: Final[Path] = Path("/home/adamoutler/kanban/thumbs-up-kanban.wiki/Home.md")
WIKI_MANIFEST_PATH: Final[Path] = (
    ROOT_DIR / "kanban" / "web" / "src" / "features" / "docs-center" / "wikiManifest.ts"
)

SHIPPED_TICKETS: Final[list[str]] = [
    "KAN-48",
    "KAN-52",
    "KAN-63",
    "KAN-66",
    "KAN-67",
    "KAN-68",
    "KAN-69",
    "KAN-70",
    "KAN-71",
    "KAN-72",
    "KAN-73",
    "KAN-74",
    "KAN-75",
    "KAN-76",
    "KAN-77",
    "KAN-78",
    "KAN-79",
    "KAN-80",
    "KAN-81",
    "KAN-82",
    "KAN-83",
    "KAN-307",
    "KAN-308",
    "KAN-309",
    "KAN-310",
    "KAN-312",
    "KAN-313",
    "KAN-316",
    "KAN-317",
]


def test_feature_comparison_markdown_parity() -> None:
    """Verify 1:1 parity between docs/FEATURE_COMPARISON.md and wiki Feature-Comparison.md."""
    assert DOCS_FC_PATH.exists(), f"Missing {DOCS_FC_PATH}"
    docs_lines = DOCS_FC_PATH.read_text(encoding="utf-8").splitlines()
    assert docs_lines[0] == "# Feature Comparison"

    if WIKI_FC_PATH.exists():
        wiki_lines = WIKI_FC_PATH.read_text(encoding="utf-8").splitlines()
        assert wiki_lines[0] == "# [Informational] Feature Comparison Matrix (46 Features)"
        # All lines from line 2 onwards must match with 100% identical content
        assert docs_lines[1:] == wiki_lines[1:], (
            "Parity mismatch between docs and wiki Feature-Comparison"
        )
    else:
        manifest_text = WIKI_MANIFEST_PATH.read_text(encoding="utf-8")
        assert "# [Informational] Feature Comparison Matrix (46 Features)" in manifest_text


def test_feature_comparison_tables_and_shipped_status() -> None:
    """Assert all 46 comparison rows in Sections 1-5 have checkmark for thumbs-up-kanban."""
    content = DOCS_FC_PATH.read_text(encoding="utf-8")

    # Extract all rows from comparison tables in Sections 1 through 5
    # Feature tables have header: | Feature | 👍kanban | Jira | ...
    table_row_re = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|.*\|$")

    section_feature_rows: list[tuple[str, str]] = []
    in_section = False

    for line in content.splitlines():
        if line.startswith(("## 1. ", "## 2. ", "## 3. ", "## 4. ", "## 5. ")):
            in_section = True
            continue
        if line.startswith("## 6. "):
            in_section = False
            break
        if in_section and line.startswith("|") and not line.startswith(("| Feature", "| ---")):
            m = table_row_re.match(line)
            if m:
                feat_name = m.group(1).strip()
                status = m.group(2).strip()
                section_feature_rows.append((feat_name, status))

    assert len(section_feature_rows) == 46, (
        f"Expected 46 feature rows, got {len(section_feature_rows)}"
    )

    for feat_name, status in section_feature_rows:
        assert status == "✅", f"Feature '{feat_name}' has status '{status}', expected '✅'"


def test_shipped_tickets_documented() -> None:
    """Assert all shipped wave 1-6 tickets are documented across FEATURE_COMPARISON and README."""
    fc_text = DOCS_FC_PATH.read_text(encoding="utf-8")
    readme_text = README_PATH.read_text(encoding="utf-8")
    combined = fc_text + "\n" + readme_text

    for ticket in SHIPPED_TICKETS:
        assert ticket in combined, (
            f"Ticket {ticket} is not documented in FEATURE_COMPARISON or README"
        )


def test_mcp_tool_counts_and_architecture_delta_parity() -> None:
    """Assert exact MCP tool counts and verify ARCHITECTURE_DELTA reports live metrics."""
    agent_mod = importlib.import_module("mcp.surfaces.agent")
    docs_mod = importlib.import_module("mcp.surfaces.docs")
    admin_mod = importlib.import_module("mcp.surfaces.admin")

    agent_reg = agent_mod.create_agent_registry()
    docs_reg = docs_mod.build_docs_registry()
    admin_reg = admin_mod.build_admin_registry()

    agent_count = len(agent_reg.list_specs())
    docs_count = len(docs_reg.list_specs())
    admin_count = len(admin_reg.list_specs())
    total_tools = agent_count + docs_count + admin_count

    assert agent_count == 10  # 9 core + update_workpad (KAN-71)
    assert docs_count == 3  # search, create, update
    assert admin_count == 12  # 12 admin governance tools
    assert total_tools == 25  # 24 standard + 1 workpad

    for delta_path in [p for p in (DOCS_DELTA_PATH, WIKI_DELTA_PATH) if p.exists()]:
        text = delta_path.read_text(encoding="utf-8")
        # Ensure delta docs do not claim hybrid search is unexecuted or locked to lexical
        assert 'locking executed_mode="lexical"' not in text
        assert "24-25" in text or "24" in text


def test_codebase_metrics_parity() -> None:
    """Assert ORM model, migration, and OpenAPI counts in README match live codebase."""
    # Live ORM models
    orm_count = len(Base.metadata.tables)
    assert orm_count == 92, f"Expected 92 Base.metadata.tables, got {orm_count}"

    # Live migrations
    sql_up_files = list((ROOT_DIR / "database" / "migrations" / "sql").glob("*.up.sql"))
    versions_dir = ROOT_DIR / "database" / "migrations" / "versions"
    alembic_files = [f for f in versions_dir.glob("*.py") if not f.name.endswith("__init__.py")]
    assert len(sql_up_files) == 76, f"Expected 76 SQL up files, got {len(sql_up_files)}"
    assert len(alembic_files) == 76, f"Expected 76 Alembic versions, got {len(alembic_files)}"

    # Live OpenAPI schema
    app = create_app()
    openapi = app.openapi()
    paths_count = len(openapi.get("paths", {}))
    http_verbs = {"get", "post", "put", "delete", "patch", "options", "head"}
    ops_count = sum(
        len([m for m in methods if m.lower() in http_verbs])
        for methods in openapi.get("paths", {}).values()
    )
    schemas_count = len(openapi.get("components", {}).get("schemas", {}))

    assert paths_count == 275
    assert ops_count == 366
    assert schemas_count == 384

    readme_text = README_PATH.read_text(encoding="utf-8")
    assert "92 SQLAlchemy 2.0 models" in readme_text
    assert "76 Alembic single-head migrations" in readme_text
    assert "275" in readme_text
    assert "366" in readme_text
    assert "384" in readme_text


def test_wiki_manifest_synchronization() -> None:
    """Assert wikiManifest.ts contains synchronized feature comparison content."""
    assert WIKI_MANIFEST_PATH.exists()
    manifest_text = WIKI_MANIFEST_PATH.read_text(encoding="utf-8")
    assert "Feature Comparison Matrix" in manifest_text
    assert "Atomic Agent Lease & Fencing" in manifest_text


def test_no_unicode_dashes() -> None:
    """Assert zero Unicode em-dashes (U+2014) or en-dashes (U+2013) across audited files."""
    files_to_check = [
        DOCS_FC_PATH,
        WIKI_FC_PATH,
        README_PATH,
        DOCS_DELTA_PATH,
        WIKI_DELTA_PATH,
        WIKI_HOME_PATH,
    ]
    for path in files_to_check:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            assert "\u2014" not in text, f"Em-dash found in {path}"
            assert "\u2013" not in text, f"En-dash found in {path}"
