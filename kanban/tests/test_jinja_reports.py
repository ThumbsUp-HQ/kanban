# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Comprehensive unit and integration tests for Jinja2 Report Templates.

Export Engine and 3-Tier Governance (KB-JINJA-REPORTS).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from defusedxml import ElementTree
from jinja2.exceptions import SecurityError
from sqlalchemy import text

from kanban.attachments.pdf import sanitize_and_validate_pdf
from kanban.reports.presets import BUILTIN_REPORT_PRESETS
from kanban.reports.renderers import (
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
    build_report_stats,
    generate_issues_table,
    generate_markdown_toc,
    render_sandboxed_template,
)
from kanban.reports.zip_packaging import create_aes256_zip, read_aes256_zip
from kanban.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import httpx

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


def _sample_issues() -> list[ReportIssueRow]:
    """Create sample ReportIssueRow instances."""
    return [
        ReportIssueRow(
            id=str(uuid.uuid4()),
            key="SEC-101",
            sequence_number=101,
            summary="Critical SQL Injection in Legacy Filter",
            description_markdown=(
                "Unsanitized raw SQL in filter predicate parser allows remote execution."
            ),
            state="In Progress",
            priority="Urgent",
            assignees=("Alice Architect",),
            created_date="2026-11-20 10:00 UTC",
            due_date="2026-11-25",
            labels=("security", "vulnerability"),
            cycle="Sprint 1",
            modules=("Security",),
        ),
        ReportIssueRow(
            id=str(uuid.uuid4()),
            key="SEC-102",
            sequence_number=102,
            summary="Formula Injection via Export Summary Field",
            description_markdown=(
                "Cell starting with =cmd|'/C calc'!A0 must be neutralized with apostrophe."
            ),
            state="Completed",
            priority="High",
            assignees=("Bob Builder",),
            created_date="2026-11-21 11:00 UTC",
            due_date="2026-11-28",
            labels=("security", "cwe-1236"),
            cycle="Sprint 1",
            modules=("Export",),
        ),
        ReportIssueRow(
            id=str(uuid.uuid4()),
            key="SEC-103",
            sequence_number=103,
            summary="Reflected XSS in Attachment File Name",
            description_markdown="Special characters in attachment filenames need sanitization.",
            state="Backlog",
            priority="Medium",
            assignees=("Carol Coder",),
            created_date="2026-11-22 08:00 UTC",
            due_date="2026-12-01",
            labels=("security",),
            cycle=None,
            modules=(),
        ),
    ]


# ==============================================================================
# 1. SSTI Sandbox Security Tests
# ==============================================================================


def test_ssti_sandbox_blocks_forbidden_attributes() -> None:
    """Verify SSTI sandbox strictly rejects introspection and code execution attributes."""
    context = ReportContext(issues=_sample_issues())

    attack_payloads = [
        "{{ [].__class__ }}",
        "{{ [].__class__.__mro__ }}",
        "{{ [].__class__.__subclasses__() }}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ [].__class__.__base__.__subclasses__() }}",
        "{{ context.__globals__ }}",
        "{{ ''.format }}",
        "{{ ''.format_map }}",
        "{{ issues[0]._secret }}",
        "{{ issues[0].__dict__ }}",
    ]

    for payload in attack_payloads:
        with pytest.raises((SecurityError, Exception)):
            render_sandboxed_template(payload, context)


def test_ssti_sandbox_template_size_limit() -> None:
    """Verify template exceeding 128 KiB is rejected immediately."""
    large_template = "# Huge\n" + ("A" * 140_000)
    context = ReportContext(issues=_sample_issues())
    with pytest.raises(ValueError, match="exceeds maximum allowed cap of 131072 bytes"):
        render_sandboxed_template(large_template, context)


def test_ssti_sandbox_output_size_limit() -> None:
    """Verify rendering output exceeding 10 MiB is blocked."""
    context = ReportContext(issues=_sample_issues())
    template = "{% for i in range(100) %}" + ("X" * 120_000) + "{% endfor %}"
    with pytest.raises(ValueError, match="exceeds maximum allowed cap of 10485760 bytes"):
        render_sandboxed_template(template, context)


def test_ssti_sandbox_timeout_limit() -> None:
    """Verify execution exceeding timeout budget raises TimeoutError."""
    context = ReportContext(issues=_sample_issues())
    slow_template = (
        "{% for i in range(1000) %}{% for j in range(1000) %}{{ i }}{{ j }}{% endfor %}{% endfor %}"
    )
    with pytest.raises(TimeoutError, match="Report rendering exceeded timeout"):
        render_sandboxed_template(slow_template, context, timeout_seconds=0.01)


def test_toc_and_issues_table_generation() -> None:
    """Verify markdown table of contents and issues table generators produce valid markdown."""
    sample_doc = "# Title\n\n## Section 1\n\n### Sub 1.1\n\n## Section 2"
    toc = generate_markdown_toc(sample_doc)
    assert "## Table of Contents" in toc
    assert "- [Title](#title)" in toc
    assert "  - [Section 1](#section-1)" in toc
    assert "    - [Sub 1.1](#sub-11)" in toc

    issues = _sample_issues()
    table = generate_issues_table(issues)
    assert "| Key | Summary | State | Priority | Assignees | Created Date |" in table
    assert "| SEC-101 | Critical SQL Injection in Legacy Filter |" in table
    assert "| SEC-102 | Formula Injection via Export Summary Field |" in table


def test_build_report_stats() -> None:
    """Verify build_report_stats correctly categorizes priorities."""
    issues = _sample_issues()
    stats = build_report_stats(issues)
    assert stats.total_issues == 3
    assert stats.urgent_count == 1
    assert stats.high_count == 1
    assert stats.medium_count == 1
    assert stats.low_count == 0


# ==============================================================================
# 2. WinZip AE-2 AES-256 ZIP Packaging Tests
# ==============================================================================


def test_winzip_ae2_aes256_roundtrip() -> None:
    """Verify AES-256 password-protected ZIP packaging creates valid AE-2 archive."""
    files = [
        ("report.md", b"# Secret Report\nConfidential findings."),
        ("data.csv", b"Key,Title\nSEC-1,SQLi\nSEC-2,XSS\n"),
    ]
    password = "SuperSecretPassword123!"

    zip_bytes = create_aes256_zip(files, password)
    assert len(zip_bytes) > 0
    assert zip_bytes[:4] == b"PK\x03\x04"

    unpacked = read_aes256_zip(zip_bytes, password)
    assert unpacked["report.md"] == b"# Secret Report\nConfidential findings."
    assert unpacked["data.csv"] == b"Key,Title\nSEC-1,SQLi\nSEC-2,XSS\n"


def test_winzip_ae2_aes256_wrong_password() -> None:
    """Verify incorrect password raises ValueError during archive decryption."""
    files = [("test.txt", b"Secret data")]
    zip_bytes = create_aes256_zip(files, "correct_password")

    with pytest.raises(ValueError, match="Incorrect password"):
        read_aes256_zip(zip_bytes, "wrong_password")


# ==============================================================================
# 3. Multi-Format Renderers & Security Invariants
# ==============================================================================


def test_formula_injection_neutralization() -> None:
    """Verify CWE-1236 dangerous leading characters are neutralized with apostrophe."""
    assert neutralize_formula("=cmd|'/C calc'!A0") == "'=cmd|'/C calc'!A0"
    assert neutralize_formula("+123456789") == "'+123456789"
    assert neutralize_formula("-5+5") == "'-5+5"
    assert neutralize_formula("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert neutralize_formula("\tTabbedText") == "'\tTabbedText"
    assert neutralize_formula("\rCarriageReturn") == "'\rCarriageReturn"
    assert neutralize_formula("Normal Text") == "Normal Text"
    assert neutralize_formula(123) == "123"
    assert neutralize_formula(None) == ""


def test_render_markdown_and_html_sanitization() -> None:
    """Verify markdown output and HTML output with strict nh3 sanitization."""
    context = ReportContext(
        workspace_name="Acme Corp",
        mission="Security Assessment",
        issues=_sample_issues(),
    )
    raw_md = (
        "# Security Assessment\n\n"
        "<script>alert('xss')</script>\n"
        '<a href="javascript:evil()">click</a>\n'
        "**Bold finding**"
    )

    rendered_md = render_markdown(raw_md, context)
    assert "# Security Assessment" in rendered_md.decode("utf-8")

    html = render_html(raw_md, context).decode("utf-8")
    assert "<script>" not in html
    assert "javascript:" not in html
    assert "<strong>Bold finding</strong>" in html
    assert "Acme Corp" in html


def test_render_csv_and_xlsx() -> None:
    """Verify CSV and XLSX builders neutralize formulas and generate valid OOXML."""
    issues = _sample_issues()
    context = ReportContext(issues=issues)

    # CSV
    csv_bytes = render_csv(
        context,
        [
            {"header": "Key", "expr": "issue.key"},
            {"header": "Title", "expr": "issue.summary"},
        ],
    )
    csv_str = csv_bytes.decode("utf-8")
    assert "Key,Title" in csv_str
    assert "SEC-101" in csv_str

    # XLSX
    xlsx_bytes = render_xlsx("# Issues\n", context)
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        assert "[Content_Types].xml" in zf.namelist()
        assert "xl/workbook.xml" in zf.namelist()
        assert "xl/worksheets/sheet1.xml" in zf.namelist()

        # Verify XML parses safely with defusedxml
        sheet_xml = zf.read("xl/worksheets/sheet1.xml")
        root = ElementTree.fromstring(sheet_xml)
        assert root is not None


def test_render_docx_and_odt() -> None:
    """Verify DOCX and ODT pure Python builders produce valid defusedxml-parseable documents."""
    context = ReportContext(
        workspace_name="Acme Corp",
        issues=_sample_issues(),
    )
    raw_md = "# Title\n## Subtitle\nParagraph 1.\n- Item 1\n- Item 2"

    # DOCX
    docx_bytes = render_docx(raw_md, context)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        assert "[Content_Types].xml" in zf.namelist()
        assert "word/document.xml" in zf.namelist()
        doc_xml = zf.read("word/document.xml")
        root = ElementTree.fromstring(doc_xml)
        assert root is not None

    # ODT
    odt_bytes = render_odt(raw_md, context)
    with zipfile.ZipFile(io.BytesIO(odt_bytes)) as zf:
        assert "mimetype" in zf.namelist()
        assert "content.xml" in zf.namelist()
        content_xml = zf.read("content.xml")
        root = ElementTree.fromstring(content_xml)
        assert root is not None


async def test_render_pdf_passes_sanitizer() -> None:
    """Verify generated PDF passes sanitize_and_validate_pdf validation without errors."""
    context = ReportContext(
        workspace_name="Acme Corp",
        project_name="Security Testing",
        issues=_sample_issues(),
    )
    raw_md = (
        "# Security Assessment Report\n\n"
        "## Executive Summary\n"
        "This is an executive summary of critical vulnerabilities.\n\n"
        "## Details\n"
        "Finding SEC-101: SQL Injection vulnerability in search filter.\n"
    )

    pdf_bytes = render_pdf(raw_md, context)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert pdf_bytes.rstrip().endswith(b"%%EOF")

    # Strict KAN-81 validator integration
    sanitized = await sanitize_and_validate_pdf(pdf_bytes)
    assert sanitized is not None
    assert len(sanitized.clean_bytes) > 0


def test_render_report_bundle_all_formats() -> None:
    """Verify render_report_bundle supports all 7 formats."""
    issues = _sample_issues()
    context = ReportContext(workspace_name="Test Workspace", issues=issues)
    formats = ["md", "html", "csv", "xlsx", "docx", "odt", "pdf"]
    for fmt in formats:
        content, _mime_type, ext = render_report_bundle(
            format_type=fmt,  # type: ignore[arg-type]
            rendered_markdown="# Report\n{{ issues_table }}",
            context=context,
        )
        assert ext.lower() == fmt
        assert len(content) > 0


# ==============================================================================
# 4. Built-in Report Presets Tests
# ==============================================================================


def test_builtin_presets_syntax_and_rendering() -> None:
    """Verify all built-in report presets parse and render with mock issues."""
    issues = _sample_issues()
    context = ReportContext(workspace_name="Test Workspace", issues=issues)
    assert len(BUILTIN_REPORT_PRESETS) == 3

    for preset in BUILTIN_REPORT_PRESETS:
        template_md = preset["template_markdown"]
        allowed = preset["allowed_formats"]
        assert len(allowed) == 7

        rendered_md = render_sandboxed_template(template_md, context)
        content, _mime_type, _ext = render_report_bundle(
            format_type="md",
            rendered_markdown=rendered_md,
            context=context,
        )
        assert len(content) > 0


# ==============================================================================
# 5. REST API Integration Tests
# ==============================================================================


async def test_report_templates_crud_api(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify report templates CRUD API endpoints."""
    admin = await make_user("report_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("report_member", workspace_role="WORKSPACE_MEMBER")

    # 1. List templates as admin: should see built-in templates seeded for workspace
    client_admin = as_principal(admin)
    res = await client_admin.get(f"/api/v1/workspaces/{api_env.workspace_id}/report-templates")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 3
    slugs = [t["slug"] for t in data["items"]]
    assert "security-assessment-report" in slugs

    # 2. Member cannot create custom template (403)
    create_payload = {
        "slug": "custom-qa-template",
        "name": "Custom QA Template",
        "template_markdown": "# QA Report\n{{ issues_table }}",
    }
    client_member = as_principal(member)
    res_member = await client_member.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates",
        json=create_payload,
    )
    assert res_member.status_code == 403

    # 3. Admin creates custom template (201)
    client_admin = as_principal(admin)
    res_admin = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates",
        json=create_payload,
    )
    assert res_admin.status_code == 201
    created_tpl = res_admin.json()
    assert created_tpl["slug"] == "custom-qa-template"
    assert created_tpl["is_builtin"] is False

    # 4. Built-in template cannot be modified or deleted (403 BUILTIN_IMMUTABLE)
    res_patch_builtin = await client_admin.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates/security-assessment-report",
        json={"name": "Hacked Builtin"},
    )
    assert res_patch_builtin.status_code == 403

    res_del_builtin = await client_admin.delete(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates/security-assessment-report",
    )
    assert res_del_builtin.status_code == 403

    # 5. Admin updates custom template (200)
    res_update = await client_admin.patch(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates/custom-qa-template",
        json={"name": "Updated QA Template"},
    )
    assert res_update.status_code == 200
    assert res_update.json()["name"] == "Updated QA Template"

    # 6. Admin deletes custom template (204)
    res_del = await client_admin.delete(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates/custom-qa-template",
    )
    assert res_del.status_code == 204


async def test_preview_report_api(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify POST /api/v1/workspaces/{workspace_ref}/reports/preview renders preview."""
    admin = await make_user("preview_admin", workspace_role="WORKSPACE_ADMIN")
    client_admin = as_principal(admin)

    preview_payload = {
        "template_ref": "security-assessment-report",
        "format": "HTML",
        "parameters": {"mission": "Live Preview Penetration Test"},
    }

    res = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/preview",
        json=preview_payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert "rendered_content" in data
    assert data["format"] == "HTML"


async def test_generate_report_workspace_and_project_api(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify POST reports/generate exports document with headers and optional ZIP encryption."""
    admin = await make_user("gen_admin", workspace_role="WORKSPACE_ADMIN")
    client_admin = as_principal(admin)

    proj_id = await make_project("SEC", created_by=admin)

    # 1. Generate Workspace PDF Report
    gen_payload = {
        "template_ref": "security-assessment-report",
        "format": "PDF",
    }
    res_pdf = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/generate",
        json=gen_payload,
    )
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert "attachment; filename=" in res_pdf.headers["content-disposition"]
    assert res_pdf.content.startswith(b"%PDF-1.4")

    # 2. Generate Project Report with WinZip AE-2 AES-256 ZIP encryption
    zip_payload = {
        "template_ref": "security-assessment-report",
        "format": "XLSX",
        "zip_password": "ArchivePassword123!",
    }
    res_zip = await client_admin.post(
        f"/api/v1/projects/{proj_id}/reports/generate",
        json=zip_payload,
    )
    assert res_zip.status_code == 200
    assert res_zip.headers["content-type"] == "application/zip"
    assert res_zip.content.startswith(b"PK\x03\x04")

    # Decrypt and verify XLSX inside zip
    unpacked = read_aes256_zip(res_zip.content, "ArchivePassword123!")
    xlsx_filename = next(name for name in unpacked if name.endswith(".xlsx"))
    xlsx_bytes = unpacked[xlsx_filename]
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as zf:
        assert "[Content_Types].xml" in zf.namelist()


async def test_3_tier_governance_enforcement(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify 3-tier governance: System setting -> Workspace setting -> Role permission."""
    admin = await make_user("gov_admin", workspace_role="WORKSPACE_ADMIN")
    member = await make_user("gov_member", workspace_role="WORKSPACE_MEMBER")

    client_admin = as_principal(admin)
    client_member = as_principal(member)

    # Tier 1: System setting disabled
    with patch("kanban.api.v1.reports.get_settings") as mock_settings:
        mock_settings.return_value = Settings(enable_report_templates=False)
        res_sys = await client_admin.post(
            f"/api/v1/workspaces/{api_env.workspace_id}/reports/preview",
            json={"template_ref": "security-assessment-report"},
        )
        assert res_sys.status_code == 403
        assert res_sys.json()["code"] == "REPORT_EXPORT_DISABLED"

    # Tier 2: Workspace setting disabled
    await api_env.seed.execute(
        text(
            "UPDATE workspace_settings SET report_export_enabled = false WHERE workspace_id = :ws"
        ),
        {"ws": api_env.workspace_id},
    )
    await api_env.seed.commit()

    res_ws = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/preview",
        json={"template_ref": "security-assessment-report"},
    )
    assert res_ws.status_code == 403
    assert res_ws.json()["code"] == "REPORT_EXPORT_DISABLED"

    # Reset workspace setting to enabled, but restrict roles to ADMIN only
    await api_env.seed.execute(
        text(
            "UPDATE workspace_settings SET report_export_enabled = true, "
            "report_export_allowed_roles = '[\"ADMIN\"]'::jsonb WHERE workspace_id = :ws"
        ),
        {"ws": api_env.workspace_id},
    )
    await api_env.seed.commit()

    # Tier 3: Member caller not permitted (only ADMIN allowed)
    res_role = await client_member.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/preview",
        json={"template_ref": "security-assessment-report"},
    )
    assert res_role.status_code == 403
    assert res_role.json()["code"] == "INSUFFICIENT_CAPABILITY"


# ==============================================================================
# 6. Comprehensive Coverage Booster Tests
# ==============================================================================


def test_docx_and_odt_comprehensive_formatting() -> None:
    """Verify DOCX and ODT document builders format complex markdown structures."""
    context = ReportContext(
        workspace_name="Acme Corp",
        mission="Security Assessment",
        issues=_sample_issues(),
    )
    complex_md = (
        "# Main Heading\n\n"
        "## Sub Heading\n\n"
        "### Section 3\n\n"
        "> Callout quote line 1\n"
        "> Callout quote line 2\n\n"
        "Paragraph with **bold text**, *italic text*, and `inline_code()`.\n\n"
        "```python\n"
        "def audit_pass():\n"
        "    return True\n"
        "```\n\n"
        "- Bullet point 1\n"
        "- Bullet point 2\n\n"
        "| Col A | Col B |\n"
        "| :--- | :--- |\n"
        "| Val 1 | Val 2 |\n\n"
        "---\n\n"
        "Trailing conclusion."
    )

    # DOCX formatting test
    docx_bytes = render_docx(complex_md, context)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "Main Heading" in doc_xml
        assert "audit_pass" in doc_xml

    # ODT formatting test
    odt_bytes = render_odt(complex_md, context)
    with zipfile.ZipFile(io.BytesIO(odt_bytes)) as zf:
        content_xml = zf.read("content.xml").decode("utf-8")
        assert "Main Heading" in content_xml
        assert "audit_pass" in content_xml


def test_render_csv_custom_columns() -> None:
    """Verify CSV rendering with custom column expressions and fallback defaults."""
    context = ReportContext(issues=_sample_issues())
    custom_cols = [
        {"header": "Key", "expr": "issue.key"},
        {"header": "Seq", "expr": "issue.sequence_number"},
        {"header": "StaticCol", "default": "FixedValue"},
        {"header": "State", "expr": "issue.state"},
    ]
    csv_bytes = render_csv(context, custom_cols)
    csv_str = csv_bytes.decode("utf-8")
    assert "Key,Seq,StaticCol,State" in csv_str
    assert "SEC-101,101,FixedValue,In Progress" in csv_str


def test_winzip_ae2_single_file_and_error_branches() -> None:
    """Verify single-file string input, empty password, and corruption branches in AE-2."""
    # 1. Single file string input
    zip_bytes = create_aes256_zip("test.txt", b"Single file content", "pass123")
    unpacked = read_aes256_zip(zip_bytes, "pass123")
    assert unpacked["test.txt"] == b"Single file content"

    # 2. String data input
    zip_bytes_str = create_aes256_zip("notes.md", "# Notes", "pass123")
    unpacked_str = read_aes256_zip(zip_bytes_str, "pass123")
    assert unpacked_str["notes.md"] == b"# Notes"

    # 3. Empty password raises ValueError
    with pytest.raises(ValueError, match="Password cannot be empty"):
        create_aes256_zip("test.txt", b"content", "")

    # 4. Short zip header raises ValueError
    with pytest.raises(ValueError, match="header too short"):
        read_aes256_zip(b"short", "pass123")

    # 5. Missing EOCD signature raises ValueError
    with pytest.raises(ValueError, match="missing end of central directory signature"):
        read_aes256_zip(b"\x00" * 40, "pass123")


def test_sandbox_and_stats_edge_cases() -> None:
    """Verify sandbox helper methods and stats priority coverage."""
    # 1. Empty markdown TOC returns empty string
    empty_toc = generate_markdown_toc("Plain text with no headers.")
    assert empty_toc == ""

    # 2. Sandbox safe attribute and callable checks
    env = HardenedSandboxedEnvironment()
    assert not env.is_safe_attribute(object(), "_private", None)
    assert not env.is_safe_attribute(object(), "mro", None)
    assert not env.is_safe_attribute(object(), "format", None)
    assert not env.is_safe_callable(dict)
    assert not env.is_safe_callable(object)

    with pytest.raises(SecurityError):
        env.getitem({}, "_forbidden")

    # 3. Stats priority buckets (low, none)
    low_issue = ReportIssueRow(
        id="low-1",
        key="LOW-1",
        sequence_number=1,
        summary="Minor typo",
        description_markdown="",
        state="Done",
        priority="low",
        assignees=(),
        created_date="2026-11-22",
    )
    none_issue = ReportIssueRow(
        id="none-1",
        key="NONE-1",
        sequence_number=2,
        summary="Unprioritized item",
        description_markdown="",
        state="Backlog",
        priority="",
        assignees=(),
        created_date="2026-11-22",
    )
    stats = build_report_stats([low_issue, none_issue])
    assert stats.low_count == 1
    assert stats.none_count == 1
    assert stats.total_issues == 2


async def test_reports_api_syntax_and_not_found_branches(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    as_principal: Callable[..., httpx.AsyncClient],
) -> None:
    """Verify API error handling for invalid template syntax and non-existent references."""
    admin = await make_user("syntax_admin", workspace_role="WORKSPACE_ADMIN")
    client_admin = as_principal(admin)

    # 1. Reject invalid Jinja2 template syntax on creation (422)
    bad_payload = {
        "slug": "bad-syntax-tpl",
        "name": "Bad Syntax Template",
        "template_markdown": "{% for issue in issues %}{{ unclosed_tag",
    }
    res_bad = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates",
        json=bad_payload,
    )
    assert res_bad.status_code == 422
    assert res_bad.json()["code"] == "INVALID_TEMPLATE_SYNTAX"

    # 2. Non-existent template lookup returns 404
    res_404 = await client_admin.get(
        f"/api/v1/workspaces/{api_env.workspace_id}/report-templates/does-not-exist",
    )
    assert res_404.status_code == 404

    # 3. Preview with raw template_markdown directly (200)
    res_preview = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/preview",
        json={
            "template_markdown": "# Live Preview {{ workspace_name }}\n{{ issues_table }}",
            "format": "HTML",
        },
    )
    assert res_preview.status_code == 200
    assert "Live Preview" in res_preview.json()["rendered_content"]

    # 4. Generate with non-existent template returns 404
    res_gen_404 = await client_admin.post(
        f"/api/v1/workspaces/{api_env.workspace_id}/reports/generate",
        json={"template_ref": "non-existent-template", "format": "MD"},
    )
    assert res_gen_404.status_code == 404


def test_renderers_deep_coverage() -> None:
    """Verify all column resolution expressions, docx tables, pdf pagination, and error branches."""
    # 1. Column resolution expressions
    iss1 = ReportIssueRow(
        id=str(uuid.uuid4()),
        key="ISS-1",
        sequence_number=1,
        summary="Issue One",
        description_markdown="Desc",
        state="Open",
        priority="Urgent",
        created_date="2026-11-20",
        due_date="2026-12-01",
        assignees=("alice", "bob"),
        labels=("security", "backend"),
        cycle="Cycle 12",
        modules=("Auth", "Core"),
    )
    iss2 = ReportIssueRow(
        id=str(uuid.uuid4()),
        key="ISS-2",
        sequence_number=2,
        summary="Issue Two",
        description_markdown="Desc",
        state="Done",
        priority="Low",
        created_date="2026-11-21",
        due_date=None,
        assignees=(),
        labels=(),
        cycle=None,
        modules=(),
    )
    ctx = ReportContext(issues=[iss1, iss2])
    cols = [
        {"header": "Prio", "expr": "issue.priority"},
        {"header": "Created", "expr": "issue.created_date"},
        {"header": "Due", "expr": "issue.due_date"},
        {"header": "Assignees", "expr": "issue.assignees"},
        {"header": "Labels", "expr": "issue.labels"},
        {"header": "Cycle", "expr": "issue.cycle"},
        {"header": "Modules", "expr": "issue.modules"},
        {"header": "Unknown", "expr": "issue.unknown_field"},
    ]
    csv_bytes = render_csv(ctx, cols)
    csv_str = csv_bytes.decode("utf-8")
    expected_row = (
        'Urgent,2026-11-20,2026-12-01,"alice, bob","security, backend",Cycle 12,"Auth, Core",'
    )
    assert expected_row in csv_str
    assert "Low,2026-11-21,,,,," in csv_str

    # 2. DOCX markdown table followed by non-table lines
    docx_table_md = (
        "# Report Title\n\n"
        "| Header 1 | Header 2 |\n"
        "| --- | --- |\n"
        "| Val 1 | Val 2 |\n\n"
        "Paragraph after table.\n"
    )
    docx_bytes = render_docx(docx_table_md, ctx)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        doc_xml = zf.read("word/document.xml").decode("utf-8")
        assert "<w:tbl>" in doc_xml
        assert "Val 1" in doc_xml

    # 3. PDF multi-page pagination and H3 subheadings
    para = "Paragraph line demonstrating report text wrapping and multi-page pagination.\n\n"
    long_pdf_md = "# Multi-Page Document\n\n## Section Heading\n\n### Subsection Heading 1\n\n" + (
        para * 120
    )
    pdf_bytes = render_pdf(long_pdf_md, ctx)
    assert len(pdf_bytes) > 0
    assert b"/Type /Page" in pdf_bytes

    # 4. PDF empty report fallback
    empty_pdf = render_pdf("", ctx)
    assert len(empty_pdf) > 0

    # 5. Unsupported export format in render_report_bundle raises ValueError
    with pytest.raises(ValueError, match="Unsupported report export format"):
        render_report_bundle("invalid_format", "# Title", ctx)  # type: ignore[arg-type]

    # 6. PDF subprocess error branch raises ValueError
    mock_err = {"status": "error", "detail": "Simulated PDF failure"}
    with (
        patch("kanban.reports.renderers._execute_subprocess", return_value=mock_err),
        pytest.raises(ValueError, match="Generated PDF failed security validation"),
    ):
        render_pdf("# Title", ctx)


def test_zip_packaging_tampering_and_corrupt_headers() -> None:
    """Verify HMAC failure, local header corruptions, and invalid encryption methods."""
    pw = "ZipTestPassword123"
    valid_zip = create_aes256_zip("secret.txt", b"Sensitive data payload", pw)

    # 1. Flip byte in HMAC auth code (last 10 bytes before Central Directory)
    # Tamper the zip by replacing a byte in the payload auth code
    # We find the central directory offset from the EOCD record
    eocd_idx = valid_zip.rfind(b"PK\x05\x06")
    assert eocd_idx != -1
    cd_offset = int.from_bytes(valid_zip[eocd_idx + 16 : eocd_idx + 20], "little")
    # The 10 bytes right before cd_offset are the HMAC auth code of the file
    tampered_bytes = bytearray(valid_zip)
    tampered_bytes[cd_offset - 5] ^= 0xFF
    with pytest.raises(ValueError, match="Authentication code verification failed"):
        read_aes256_zip(bytes(tampered_bytes), pw)

    # 2. Corrupt local header signature (first 4 bytes PK\x03\x04)
    corrupt_loc = bytearray(valid_zip)
    corrupt_loc[0] = 0x00
    with pytest.raises(ValueError, match="invalid local header signature"):
        read_aes256_zip(bytes(corrupt_loc), pw)

    # 3. Non-AES method (method != 99 in central directory)
    non_aes = bytearray(valid_zip)
    # in central directory, method is at cd_offset + 10 (2 bytes)
    non_aes[cd_offset + 10] = 0x00
    non_aes[cd_offset + 11] = 0x00
    with pytest.raises(ValueError, match="not encrypted with WinZip AES"):
        read_aes256_zip(bytes(non_aes), pw)


def test_sandbox_custom_parameters_and_toc_skip() -> None:
    """Verify custom parameters injection, TOC heading skip, and type inspection checks."""
    # 1. Custom parameters injection
    ctx = ReportContext(
        issues=[],
        parameters={"custom_metric": "99.9%", "audit_lead": "SecLead"},
    )
    rendered = render_sandboxed_template("Score: {{ custom_metric }} Lead: {{ audit_lead }}", ctx)
    assert rendered == "Score: 99.9% Lead: SecLead"

    # 2. TOC skips "Table of Contents" or "TOC" headings
    toc_doc = "# Table of Contents\n# Section A\n## TOC\n## Section B"
    toc = generate_markdown_toc(toc_doc)
    assert "Section A" in toc
    assert "Section B" in toc
    assert "[Table of Contents]" not in toc
    assert "[TOC]" not in toc
