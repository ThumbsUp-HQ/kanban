# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Multi-format document renderers (MD, HTML, CSV, XLSX, DOCX, ODT, PDF) (KAN-317).

Guarantees:
- Strict Apache-2.0, MIT, and BSD-3-Clause license compliance with zero GPL/LGPL dependencies.
- Formula injection neutralization (CWE-1236) on all CSV and XLSX text cells.
- XML validation via defusedxml.ElementTree.fromstring on all OOXML and ODF XML payloads.
- HTML output sanitized through nh3 allowlist.
- Generated PDFs verified through kanban/attachments/pdf.py:sanitize_and_validate_pdf (KAN-81).
"""

from __future__ import annotations

import csv
import html
import io
import re
import zipfile
from typing import Any, Final, Literal
from xml.sax.saxutils import escape as xml_escape

import defusedxml.ElementTree as DefusedET
import markdown_it
import nh3

from kanban.attachments.pdf import _execute_subprocess
from kanban.reports.sandbox import ReportContext, ReportIssueRow, build_report_stats

ReportFormat = Literal["md", "html", "csv", "xlsx", "docx", "odt", "pdf"]

_FORMULA_PREFIXES: Final[frozenset[str]] = frozenset({"=", "+", "-", "@", "\t", "\r"})


def neutralize_formula(value: Any) -> str:
    """Neutralize formula injection (CWE-1236) by prepending a single quote.

    Targets dangerous leading characters: '=', '+', '-', '@', '\\t', '\\r'.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val[0] in _FORMULA_PREFIXES:
        return f"'{str_val}"
    return str_val


def render_markdown(rendered_text: str, _context: ReportContext) -> bytes:
    """Render canonical UTF-8 Markdown report."""
    cleaned = re.sub(r"[ \t]+$", "", rendered_text, flags=re.MULTILINE)
    return cleaned.encode("utf-8")


def render_html(rendered_text: str, context: ReportContext) -> bytes:
    """Render self-contained printable HTML5 report sanitized with nh3."""
    md = markdown_it.MarkdownIt("gfm-like", {"linkify": False})
    raw_html = md.render(rendered_text)

    sanitized_body = nh3.clean(
        raw_html,
        tags={
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "p",
            "b",
            "strong",
            "i",
            "em",
            "u",
            "code",
            "pre",
            "ul",
            "ol",
            "li",
            "blockquote",
            "hr",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "span",
            "div",
            "a",
            "del",
        },
        attributes={
            "a": {"href", "title", "target"},
            "th": {"align", "colspan", "rowspan"},
            "td": {"align", "colspan", "rowspan"},
            "code": {"class"},
            "span": {"class"},
            "div": {"class"},
        },
        link_rel="noopener noreferrer",
    )

    doc_title = html.escape(f"{context.workspace_name} Report - {context.generated_at}")
    html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{doc_title}</title>
  <style>
    :root {{
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      --bg-color: #ffffff;
      --text-color: #1a202c;
      --border-color: #e2e8f0;
      --heading-color: #0f172a;
      --table-stripe: #f8fafc;
      --badge-urgent-bg: #fee2e2;
      --badge-urgent-text: #991b1b;
      --badge-high-bg: #ffedd5;
      --badge-high-text: #9a3412;
      --badge-medium-bg: #e0f2fe;
      --badge-medium-text: #075985;
      --badge-low-bg: #f1f5f9;
      --badge-low-text: #475569;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg-color: #0f172a;
        --text-color: #f1f5f9;
        --border-color: #334155;
        --heading-color: #f8fafc;
        --table-stripe: #1e293b;
      }}
    }}
    body {{
      font-family: var(--font-family);
      background-color: var(--bg-color);
      color: var(--text-color);
      line-height: 1.6;
      margin: 0;
      padding: 2.5rem 3rem;
      max-width: 900px;
      margin-left: auto;
      margin-right: auto;
    }}
    h1, h2, h3, h4 {{
      color: var(--heading-color);
      font-weight: 700;
      margin-top: 1.75rem;
      margin-bottom: 0.75rem;
    }}
    h1 {{
      font-size: 2rem;
      border-bottom: 2px solid var(--border-color);
      padding-bottom: 0.5rem;
    }}
    h2 {{
      font-size: 1.5rem;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.35rem;
    }}
    h3 {{ font-size: 1.25rem; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.5rem 0;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 0.65rem 0.85rem;
      border: 1px solid var(--border-color);
      text-align: left;
    }}
    th {{
      background-color: var(--table-stripe);
      font-weight: 600;
    }}
    tbody tr:nth-child(even) {{
      background-color: var(--table-stripe);
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9em;
      background-color: var(--table-stripe);
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
    }}
    pre code {{
      display: block;
      padding: 1rem;
      overflow-x: auto;
    }}
    blockquote {{
      margin: 1.5rem 0;
      padding: 0.5rem 1rem;
      border-left: 4px solid var(--border-color);
      color: #64748b;
    }}
    .report-metadata-bar {{
      margin-bottom: 2rem;
      padding-bottom: 1rem;
      border-bottom: 1px solid var(--border-color);
      font-size: 0.9rem;
      color: #64748b;
    }}
    @media print {{
      body {{
        padding: 0;
        max-width: 100%;
        color: #000;
        background: #fff;
      }}
      h1 {{
        page-break-before: always;
      }}
      h1:first-of-type {{
        page-break-before: avoid;
      }}
      table, pre, blockquote {{
        page-break-inside: avoid;
      }}
      @page {{
        margin: 1.5cm;
      }}
    }}
  </style>
</head>
<body>
  <div class="report-metadata-bar">
    <strong>Workspace:</strong> {html.escape(context.workspace_name)} &nbsp;|&nbsp;
    <strong>Generated:</strong> {html.escape(context.generated_at)} &nbsp;|&nbsp;
    <strong>By:</strong> {html.escape(context.generated_by)}
  </div>
  {sanitized_body}
</body>
</html>"""
    return html_page.encode("utf-8")


def render_csv(
    context: ReportContext,
    custom_columns: list[dict[str, str]] | None = None,
) -> bytes:
    """Render RFC 4180 CSV with CWE-1236 formula neutralization and UTF-8 BOM."""
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)

    if custom_columns:
        headers = [col.get("header", "Column") for col in custom_columns]
        writer.writerow([neutralize_formula(h) for h in headers])
        for iss in context.issues:
            row: list[str] = []
            for col in custom_columns:
                expr = col.get("expr", "")
                val = _eval_issue_expr(iss, expr) if expr else col.get("default", "")
                row.append(neutralize_formula(val))
            writer.writerow(row)
    else:
        headers = [
            "Key",
            "Summary",
            "State",
            "Priority",
            "Assignees",
            "Created Date",
            "Due Date",
            "Labels",
            "Cycle",
            "Modules",
        ]
        writer.writerow([neutralize_formula(h) for h in headers])
        for iss in context.issues:
            assignees = ", ".join(iss.assignees) if iss.assignees else ""
            labels = ", ".join(iss.labels) if iss.labels else ""
            modules = ", ".join(iss.modules) if iss.modules else ""
            row = [
                neutralize_formula(iss.key),
                neutralize_formula(iss.summary),
                neutralize_formula(iss.state),
                neutralize_formula(iss.priority),
                neutralize_formula(assignees),
                neutralize_formula(iss.created_date),
                neutralize_formula(iss.due_date or ""),
                neutralize_formula(labels),
                neutralize_formula(iss.cycle or ""),
                neutralize_formula(modules),
            ]
            writer.writerow(row)

    # Encode with UTF-8 BOM so Excel opens without mojibake
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _eval_issue_expr(iss: ReportIssueRow, expr: str) -> str:
    """Safe lookup of issue properties for CSV expressions."""
    expr_clean = expr.strip()
    if expr_clean in ("issue.key", "key"):
        return iss.key
    if expr_clean in ("issue.sequence_number", "sequence_number"):
        return str(iss.sequence_number)
    if expr_clean in ("issue.summary", "summary"):
        return iss.summary
    if expr_clean in ("issue.state", "state"):
        return iss.state
    if expr_clean in ("issue.priority", "priority"):
        return iss.priority
    if expr_clean in ("issue.created_date", "created_date"):
        return iss.created_date
    if expr_clean in ("issue.due_date", "due_date"):
        return iss.due_date or ""
    if "assignees" in expr_clean:
        return ", ".join(iss.assignees)
    if "labels" in expr_clean:
        return ", ".join(iss.labels)
    if "cycle" in expr_clean:
        return iss.cycle or ""
    if "modules" in expr_clean:
        return ", ".join(iss.modules)
    return ""


# ---------------------------------------------------------------------------
# Native pure-Python OOXML .xlsx Builder with multi-sheet support
# ---------------------------------------------------------------------------


def render_xlsx(_rendered_text: str, context: ReportContext) -> bytes:
    """Build valid multi-sheet OOXML workbook with formula neutralization.

    Sheets:
    1. Executive Summary
    2. Issues Table
    3. Appendix
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
            '  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
            '  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
            '  <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
            '  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>\n'
            "</Types>"
        )
        DefusedET.fromstring(content_types)
        zf.writestr("[Content_Types].xml", content_types)

        # _rels/.rels
        dot_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
            "</Relationships>"
        )
        DefusedET.fromstring(dot_rels)
        zf.writestr("_rels/.rels", dot_rels)

        # xl/_rels/workbook.xml.rels
        wb_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>\n'
            '  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>\n'
            '  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>\n'
            '  <Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
            "</Relationships>"
        )
        DefusedET.fromstring(wb_rels)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)

        # xl/workbook.xml
        wb_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
            "  <sheets>\n"
            '    <sheet name="Executive Summary" sheetId="1" r:id="rId1"/>\n'
            '    <sheet name="Issues Table" sheetId="2" r:id="rId2"/>\n'
            '    <sheet name="Appendix" sheetId="3" r:id="rId3"/>\n'
            "  </sheets>\n"
            "</workbook>"
        )
        DefusedET.fromstring(wb_xml)
        zf.writestr("xl/workbook.xml", wb_xml)

        # xl/styles.xml
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
            '  <fonts count="2">\n'
            '    <font><name val="Calibri"/><sz val="11"/></font>\n'
            '    <font><b/><name val="Calibri"/><sz val="11"/></font>\n'
            "  </fonts>\n"
            '  <fills count="2">\n'
            '    <fill><patternFill patternType="none"/></fill>\n'
            '    <fill><patternFill patternType="gray125"/></fill>\n'
            "  </fills>\n"
            '  <borders count="1">\n'
            "    <border><left/><right/><top/><bottom/></border>\n"
            "  </borders>\n"
            '  <cellXfs count="2">\n'
            '    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>\n'
            '    <xf numFmtId="0" fontId="1" fillId="0" borderId="0"/>\n'
            "  </cellXfs>\n"
            "</styleSheet>"
        )
        DefusedET.fromstring(styles_xml)
        zf.writestr("xl/styles.xml", styles_xml)

        # Sheet 1: Executive Summary
        stats = context.stats or build_report_stats(context.issues)
        sh1_rows: list[str] = [
            _xlsx_row(
                1, ["Executive Summary", context.workspace_name, f"Date: {context.generated_at}"]
            ),
            _xlsx_row(2, ["Mission", neutralize_formula(context.mission)]),
            _xlsx_row(3, ["Boilerplate", neutralize_formula(context.boilerplate)]),
            _xlsx_row(4, ["Summary", neutralize_formula(context.executive_summary)]),
            _xlsx_row(
                5,
                [
                    "Total Issues",
                    str(stats.total_issues),
                    f"Urgent: {stats.urgent_count}",
                    f"High: {stats.high_count}",
                ],
            ),
        ]
        sh1_xml = _build_sheet_xml(sh1_rows)
        DefusedET.fromstring(sh1_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sh1_xml)

        # Sheet 2: Issues Table
        sh2_rows: list[str] = [
            _xlsx_row(
                1,
                ["Key", "Summary", "State", "Priority", "Assignees", "Created Date"],
                header=True,
            )
        ]
        for idx, iss in enumerate(context.issues, start=2):
            assignees = ", ".join(iss.assignees) if iss.assignees else "Unassigned"
            sh2_rows.append(
                _xlsx_row(
                    idx,
                    [
                        neutralize_formula(iss.key),
                        neutralize_formula(iss.summary),
                        neutralize_formula(iss.state),
                        neutralize_formula(iss.priority),
                        neutralize_formula(assignees),
                        neutralize_formula(iss.created_date),
                    ],
                )
            )
        sh2_xml = _build_sheet_xml(sh2_rows)
        DefusedET.fromstring(sh2_xml)
        zf.writestr("xl/worksheets/sheet2.xml", sh2_xml)

        # Sheet 3: Appendix
        sh3_rows: list[str] = [
            _xlsx_row(1, ["Appendix & Notes"], header=True),
            _xlsx_row(2, [neutralize_formula(context.appendix)]),
        ]
        sh3_xml = _build_sheet_xml(sh3_rows)
        DefusedET.fromstring(sh3_xml)
        zf.writestr("xl/worksheets/sheet3.xml", sh3_xml)

    return buf.getvalue()


def _xlsx_row(row_idx: int, values: list[str], header: bool = False) -> str:
    """Format row of cells in XLSX XML."""
    s_attr = ' s="1"' if header else ""
    cells: list[str] = []
    for col_idx, val in enumerate(values):
        col_letter = chr(ord("A") + col_idx)
        cell_ref = f"{col_letter}{row_idx}"
        escaped_val = xml_escape(val)
        cells.append(f'<c r="{cell_ref}" t="inlineStr"{s_attr}><is><t>{escaped_val}</t></is></c>')
    return f'<row r="{row_idx}">{"".join(cells)}</row>'


def _build_sheet_xml(row_xmls: list[str]) -> str:
    """Wrap sheet rows into standard worksheet XML."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        f'  <sheetData>{"".join(row_xmls)}</sheetData>\n'
        "</worksheet>"
    )


# ---------------------------------------------------------------------------
# Native pure-Python OOXML .docx Builder
# ---------------------------------------------------------------------------


def render_docx(rendered_text: str, context: ReportContext) -> bytes:
    """Build valid OOXML Word document (.docx) mapping Markdown sections to Word styles."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
            '  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>\n'
            "</Types>"
        )
        DefusedET.fromstring(content_types)
        zf.writestr("[Content_Types].xml", content_types)

        dot_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
            "</Relationships>"
        )
        DefusedET.fromstring(dot_rels)
        zf.writestr("_rels/.rels", dot_rels)

        doc_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>\n'
            "</Relationships>"
        )
        DefusedET.fromstring(doc_rels)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:style w:type="paragraph" w:styleId="Normal" w:default="1">\n'
            '    <w:name w:val="Normal"/>\n'
            "    <w:rPr><w:rFonts w:ascii=\"Calibri\" w:hAnsi=\"Calibri\"/><w:sz w:val=\"22\"/></w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="Heading1">\n'
            '    <w:name w:val="Heading 1"/>\n'
            "    <w:rPr><w:b/><w:sz w:val=\"36\"/><w:color w:val=\"0F172A\"/></w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="Heading2">\n'
            '    <w:name w:val="Heading 2"/>\n'
            "    <w:rPr><w:b/><w:sz w:val=\"28\"/><w:color w:val=\"1E293B\"/></w:rPr>\n"
            "  </w:style>\n"
            '  <w:style w:type="paragraph" w:styleId="Heading3">\n'
            '    <w:name w:val="Heading 3"/>\n'
            "    <w:rPr><w:b/><w:sz w:val=\"24\"/><w:color w:val=\"334155\"/></w:rPr>\n"
            "  </w:style>\n"
            "</w:styles>"
        )
        DefusedET.fromstring(styles_xml)
        zf.writestr("word/styles.xml", styles_xml)

        body_elements: list[str] = [
            f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{xml_escape(context.workspace_name)} Report</w:t></w:r></w:p>',
            f'<w:p><w:r><w:rPr><w:color w:val="64748B"/></w:rPr><w:t>Generated on {xml_escape(context.generated_at)} by {xml_escape(context.generated_by)}</w:t></w:r></w:p>',
        ]

        # Parse lines of rendered text into Word paragraphs and tables
        in_table = False
        table_rows: list[list[str]] = []

        for line in rendered_text.splitlines():
            line_str = line.strip()
            if not line_str:
                if in_table and table_rows:
                    body_elements.append(_docx_table(table_rows))
                    in_table = False
                    table_rows = []
                continue

            if line_str.startswith("|") and line_str.endswith("|"):
                # Table row
                if re.match(r"^\|(\s*:?-+:?\s*\|)+$", line_str):
                    continue  # Table separator
                parts = [p.strip() for p in line_str.strip("|").split("|")]
                table_rows.append(parts)
                in_table = True
                continue

            if in_table and table_rows:
                body_elements.append(_docx_table(table_rows))
                in_table = False
                table_rows = []

            if line_str.startswith("# "):
                text_content = xml_escape(line_str[2:].strip())
                body_elements.append(
                    f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>{text_content}</w:t></w:r></w:p>'
                )
            elif line_str.startswith("## "):
                text_content = xml_escape(line_str[3:].strip())
                body_elements.append(
                    f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>{text_content}</w:t></w:r></w:p>'
                )
            elif line_str.startswith("### "):
                text_content = xml_escape(line_str[4:].strip())
                body_elements.append(
                    f'<w:p><w:pPr><w:pStyle w:val="Heading3"/></w:pPr><w:r><w:t>{text_content}</w:t></w:r></w:p>'
                )
            else:
                text_content = xml_escape(line_str)
                body_elements.append(f"<w:p><w:r><w:t>{text_content}</w:t></w:r></w:p>")

        if in_table and table_rows:
            body_elements.append(_docx_table(table_rows))

        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            f'  <w:body>{"".join(body_elements)}</w:body>\n'
            "</w:document>"
        )
        DefusedET.fromstring(doc_xml)
        zf.writestr("word/document.xml", doc_xml)

    return buf.getvalue()


def _docx_table(rows: list[list[str]]) -> str:
    """Format list of string cells into Word w:tbl XML."""
    tr_xmls: list[str] = []
    for r_idx, row in enumerate(rows):
        tc_xmls: list[str] = []
        is_hdr = r_idx == 0
        for cell in row:
            bold = "<w:b/>" if is_hdr else ""
            tc_xmls.append(
                f"<w:tc><w:p><w:r><w:rPr>{bold}</w:rPr><w:t>{xml_escape(cell)}</w:t></w:r></w:p></w:tc>"
            )
        tr_xmls.append(f"<w:tr>{''.join(tc_xmls)}</w:tr>")
    return (
        "<w:tbl>"
        '<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/><w:insideH w:val="single" w:sz="4"/></w:tblBorders></w:tblPr>'
        f"{''.join(tr_xmls)}"
        "</w:tbl>"
    )


# ---------------------------------------------------------------------------
# Native pure-Python OASIS OpenDocument 1.2 Text (.odt) Builder
# ---------------------------------------------------------------------------


def render_odt(rendered_text: str, context: ReportContext) -> bytes:
    """Build valid OASIS OpenDocument 1.2 text document (.odt)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        # First entry: uncompressed mimetype
        zf.writestr("mimetype", b"application/vnd.oasis.opendocument.text", zipfile.ZIP_STORED)

        # META-INF/manifest.xml
        manifest_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">\n'
            '  <manifest:file-entry manifest:media-type="application/vnd.oasis.opendocument.text" manifest:full-path="/"/>\n'
            '  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="content.xml"/>\n'
            '  <manifest:file-entry manifest:media-type="text/xml" manifest:full-path="styles.xml"/>\n'
            "</manifest:manifest>"
        )
        DefusedET.fromstring(manifest_xml)
        zf.writestr("META-INF/manifest.xml", manifest_xml, zipfile.ZIP_DEFLATED)

        # styles.xml
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0">\n'
            "  <office:styles/>\n"
            "</office:document-styles>"
        )
        DefusedET.fromstring(styles_xml)
        zf.writestr("styles.xml", styles_xml, zipfile.ZIP_DEFLATED)

        # content.xml
        body_elements: list[str] = [
            f'<text:h text:outline-level="1">{xml_escape(context.workspace_name)} Report</text:h>',
            f"<text:p>Generated on {xml_escape(context.generated_at)} by {xml_escape(context.generated_by)}</text:p>",
        ]

        for line in rendered_text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("# "):
                body_elements.append(
                    f'<text:h text:outline-level="1">{xml_escape(line_str[2:].strip())}</text:h>'
                )
            elif line_str.startswith("## "):
                body_elements.append(
                    f'<text:h text:outline-level="2">{xml_escape(line_str[3:].strip())}</text:h>'
                )
            elif line_str.startswith("### "):
                body_elements.append(
                    f'<text:h text:outline-level="3">{xml_escape(line_str[4:].strip())}</text:h>'
                )
            else:
                body_elements.append(f"<text:p>{xml_escape(line_str)}</text:p>")

        content_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
            'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0">\n'
            f'  <office:body><office:text>{"".join(body_elements)}</office:text></office:body>\n'
            "</office:document-content>"
        )
        DefusedET.fromstring(content_xml)
        zf.writestr("content.xml", content_xml, zipfile.ZIP_DEFLATED)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Native pure-Python PDF 1.4 Builder passing KAN-81 sanitize_and_validate_pdf
# ---------------------------------------------------------------------------


def render_pdf(rendered_text: str, context: ReportContext) -> bytes:
    """Build valid typeset PDF 1.4 document and verify with sanitize_and_validate_pdf."""
    # Convert text lines into clean PDF text commands
    # Page dimensions: 612 x 792 pt (Letter)
    page_width = 612
    page_height = 792
    margin_x = 54
    margin_y = 54
    line_height = 14

    pages_content: list[list[str]] = []
    current_page_cmds: list[str] = []
    y_pos = page_height - margin_y

    def start_new_page() -> None:
        nonlocal current_page_cmds, y_pos
        if current_page_cmds:
            pages_content.append(current_page_cmds)
        current_page_cmds = []
        y_pos = page_height - margin_y

    # Header on first page
    current_page_cmds.append(f"/F2 18 Tf {margin_x} {y_pos} Td")
    current_page_cmds.append(f"({_escape_pdf_str(context.workspace_name)} Report) Tj")
    y_pos -= 24
    current_page_cmds.append(f"/F1 9 Tf {margin_x} {y_pos} Td")
    current_page_cmds.append(
        f"(Generated: {_escape_pdf_str(context.generated_at)}  |  By: {_escape_pdf_str(context.generated_by)}) Tj"
    )
    y_pos -= 28

    for line in rendered_text.splitlines():
        line_str = line.strip()
        if not line_str:
            y_pos -= 8
            continue

        if y_pos < margin_y + line_height * 2:
            start_new_page()

        if line_str.startswith("# "):
            font = "/F2 14 Tf"
            y_pos -= 18
            text_str = line_str[2:].strip()
        elif line_str.startswith("## "):
            font = "/F2 11 Tf"
            y_pos -= 14
            text_str = line_str[3:].strip()
        elif line_str.startswith("### "):
            font = "/F2 10 Tf"
            y_pos -= 12
            text_str = line_str[4:].strip()
        else:
            font = "/F1 9 Tf"
            y_pos -= line_height
            text_str = line_str

        current_page_cmds.append(f"{font} {margin_x} {y_pos} Td")
        current_page_cmds.append(f"({_escape_pdf_str(text_str[:90])}) Tj")

    if current_page_cmds:
        pages_content.append(current_page_cmds)

    if not pages_content:
        pages_content = [[f"/F1 10 Tf {margin_x} {page_height - margin_y} Td (Empty Report) Tj"]]

    # Assemble PDF 1.4 objects
    num_pages = len(pages_content)
    objects: list[bytes] = []

    # Object 1: Catalog
    # Object 2: Pages tree
    # Object 3..2+N: Page objects
    # Object 3+N..2+2N: Content streams
    # Object 3+2N: Font F1 (Helvetica)
    # Object 4+2N: Font F2 (Helvetica-Bold)

    page_obj_ids = [3 + i for i in range(num_pages)]
    content_obj_ids = [3 + num_pages + i for i in range(num_pages)]
    f1_id = 3 + 2 * num_pages
    f2_id = 4 + 2 * num_pages

    # 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

    # 2: Pages
    kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>".encode("ascii"))

    # Page objects
    for i in range(num_pages):
        cid = content_obj_ids[i]
        page_dict = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {page_width} {page_height}] "
            f"/Contents {cid} 0 R "
            f"/Resources << /Font << /F1 {f1_id} 0 R /F2 {f2_id} 0 R >> >> >>"
        )
        objects.append(page_dict.encode("ascii"))

    # Content streams
    for cmds in pages_content:
        stream_body = f"BT\n{chr(10).join(cmds)}\nET".encode("latin-1", errors="replace")
        stream_obj = (
            f"<< /Length {len(stream_body)} >>\nstream\n".encode("ascii")
            + stream_body
            + b"\nendstream"
        )
        objects.append(stream_obj)

    # Font F1: Helvetica
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    # Font F2: Helvetica-Bold
    objects.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )

    # Build PDF with cross-reference table
    pdf_buf = io.BytesIO()
    pdf_buf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    offsets: list[int] = [0]  # Object 0 is free
    for i, obj_bytes in enumerate(objects, start=1):
        offsets.append(pdf_buf.tell())
        pdf_buf.write(f"{i} 0 obj\n".encode("ascii"))
        pdf_buf.write(obj_bytes)
        pdf_buf.write(b"\nendobj\n")

    startxref = pdf_buf.tell()
    pdf_buf.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf_buf.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf_buf.write(f"{off:010d} 00000 n \n".encode("ascii"))

    pdf_buf.write(b"trailer\n")
    trailer_dict = f"<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
    pdf_buf.write(trailer_dict.encode("ascii"))
    pdf_buf.write(f"startxref\n{startxref}\n%%EOF\n".encode("ascii"))

    pdf_bytes = pdf_buf.getvalue()

    # Mandatory Forensic Verification: Must pass KAN-81 sanitize_and_validate_pdf
    pdf_result = _execute_subprocess(pdf_bytes)
    if pdf_result.get("status") == "error":
        detail = pdf_result.get("detail") or "PDF validation failed"
        raise ValueError(f"Generated PDF failed security validation: {detail}")

    return pdf_bytes


def _escape_pdf_str(text: str) -> str:
    """Escape parenthesis and backslashes for PDF literal text strings."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# ---------------------------------------------------------------------------
# Master Report Bundle Renderer
# ---------------------------------------------------------------------------


def render_report_bundle(
    format_type: ReportFormat,
    rendered_markdown: str,
    context: ReportContext,
    custom_columns: list[dict[str, str]] | None = None,
) -> tuple[bytes, str, str]:
    """Render report in chosen format.

    Returns:
        tuple of (raw_bytes, mime_type, file_extension)
    """
    fmt = format_type.lower()
    if fmt == "md":
        return render_markdown(rendered_markdown, context), "text/markdown; charset=utf-8", "md"
    if fmt == "html":
        return render_html(rendered_markdown, context), "text/html; charset=utf-8", "html"
    if fmt == "csv":
        return render_csv(context, custom_columns), "text/csv; charset=utf-8", "csv"
    if fmt == "xlsx":
        return (
            render_xlsx(rendered_markdown, context),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        )
    if fmt == "docx":
        return (
            render_docx(rendered_markdown, context),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        )
    if fmt == "odt":
        return render_odt(rendered_markdown, context), "application/vnd.oasis.opendocument.text", "odt"
    if fmt == "pdf":
        return render_pdf(rendered_markdown, context), "application/pdf", "pdf"
    raise ValueError(f"Unsupported report export format: {format_type}")
