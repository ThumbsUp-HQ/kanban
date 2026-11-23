# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Sandboxed Jinja2 report templates and multi-format export engine (KAN-317)."""

from __future__ import annotations

from kanban.reports.presets import BUILTIN_REPORT_PRESETS
from kanban.reports.renderers import (
    ReportFormat,
    neutralize_formula,
    render_csv,
    render_docx,
    render_html,
    render_markdown,
    render_odt,
    render_pdf,
    render_report_bundle,
    render_xlsx,
)
from kanban.reports.sandbox import (
    HardenedSandboxedEnvironment,
    ReportContext,
    ReportIssueRow,
    ReportStats,
    build_report_stats,
    create_sandboxed_environment,
    generate_issues_table,
    generate_markdown_toc,
    render_sandboxed_template,
)
from kanban.reports.zip_packaging import create_aes256_zip, read_aes256_zip

__all__ = [
    "BUILTIN_REPORT_PRESETS",
    "HardenedSandboxedEnvironment",
    "ReportContext",
    "ReportFormat",
    "ReportIssueRow",
    "ReportStats",
    "build_report_stats",
    "create_aes256_zip",
    "create_sandboxed_environment",
    "generate_issues_table",
    "generate_markdown_toc",
    "neutralize_formula",
    "read_aes256_zip",
    "render_csv",
    "render_docx",
    "render_html",
    "render_markdown",
    "render_odt",
    "render_pdf",
    "render_report_bundle",
    "render_sandboxed_template",
    "render_xlsx",
]
