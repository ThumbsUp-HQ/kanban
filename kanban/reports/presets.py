# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Built-in Jinja2 report templates and parameters schemas (KAN-317)."""

from __future__ import annotations

from typing import Any, Final

BUILTIN_REPORT_PRESETS: Final[list[dict[str, Any]]] = [
    {
        "slug": "security-assessment-report",
        "name": "Security Assessment Report",
        "description": (
            "Comprehensive security audit report with mission scope, boilerplate terms, "
            "table of contents, executive summary, issue summary table, details per finding, "
            "and appendix."
        ),
        "is_builtin": True,
        "template_markdown": """{{ mission }}
{{ boilerplate }}
{{ toc }}

# Executive Summary
{{ executive_summary }}

{{ issues_table }}

# Details
{% for issue in issues %}
## {{ issue.created_date }} - {{ issue.summary }} [{{ issue.priority | upper }}]
**Key:** {{ issue.key }} | **State:** {{ issue.state }}
**Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endfor %}

# Appendix
{{ appendix }}""",
        "parameters_schema_json": [
            {
                "name": "mission",
                "label": "Assessment Mission & Scope",
                "type": "textarea",
                "default": (
                    "Target Environment Security Assessment and Penetration Testing Review."
                ),
                "required": True,
            },
            {
                "name": "boilerplate",
                "label": "Boilerplate & Legal Notice",
                "type": "textarea",
                "default": (
                    "Confidential Security Audit Document. "
                    "Unauthorized reproduction or dissemination is strictly prohibited."
                ),
                "required": True,
            },
            {
                "name": "executive_summary",
                "label": "Executive Summary",
                "type": "textarea",
                "default": (
                    "This assessment report provides an audit of discovered issues "
                    "and security posture across the target scope."
                ),
                "required": True,
            },
            {
                "name": "appendix",
                "label": "Appendix & Methodology",
                "type": "textarea",
                "default": (
                    "All findings were assessed in accordance with OWASP Top 10 and CWE guidelines."
                ),
                "required": False,
            },
        ],
        "csv_columns_json": [
            {"header": "Key", "expr": "issue.key"},
            {"header": "Summary", "expr": "issue.summary"},
            {"header": "State", "expr": "issue.state"},
            {"header": "Priority", "expr": "issue.priority"},
            {"header": "Assignees", "expr": 'issue.assignees | join(", ")'},
            {"header": "Created Date", "expr": "issue.created_date"},
        ],
        "allowed_formats": ["pdf", "xlsx", "csv", "docx", "odt", "html", "md"],
    },
    {
        "slug": "sprint-release-notes",
        "name": "Sprint & Release Notes Report",
        "description": (
            "Sprint and release summary grouping completed features, fixes, "
            "and active work with contributor metrics."
        ),
        "is_builtin": True,
        "template_markdown": """# {{ release_title | default("Sprint & Release Notes") }}
{{ release_notes_summary }}

{{ toc }}

{{ issues_table }}

# Features & Fixes by State
{% for issue in issues %}
### [{{ issue.state }}] {{ issue.key }}: {{ issue.summary }}
**Priority:** {{ issue.priority }} | **Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endfor %}""",
        "parameters_schema_json": [
            {
                "name": "release_title",
                "label": "Release Title",
                "type": "text",
                "default": "Sprint & Release Notes",
                "required": True,
            },
            {
                "name": "release_notes_summary",
                "label": "Release Summary",
                "type": "textarea",
                "default": (
                    "Summary of delivered features, fixes, and improvements in this release cycle."
                ),
                "required": True,
            },
        ],
        "csv_columns_json": [
            {"header": "Key", "expr": "issue.key"},
            {"header": "Summary", "expr": "issue.summary"},
            {"header": "State", "expr": "issue.state"},
            {"header": "Priority", "expr": "issue.priority"},
            {"header": "Assignees", "expr": 'issue.assignees | join(", ")'},
        ],
        "allowed_formats": ["pdf", "xlsx", "csv", "docx", "odt", "html", "md"],
    },
    {
        "slug": "executive-status-risk",
        "name": "Executive Status & Risk Report",
        "description": (
            "High-level executive briefing with priority distribution, "
            "blockers, timeline risk analysis, and appendix."
        ),
        "is_builtin": True,
        "template_markdown": """# {{ executive_title | default("Executive Status & Risk Report") }}

# Executive Briefing
{{ briefing }}

{{ toc }}

# Priority & Risk Breakdown
Total tracked issues: {{ stats.total_issues }} (Urgent: {{ stats.urgent_count }}, """
        """High: {{ stats.high_count }}, Medium: {{ stats.medium_count }}, """
        """Low: {{ stats.low_count }})

{{ issues_table }}

# Critical & High Attention Items
{% for issue in issues %}
{% if issue.priority in ["urgent", "high"] %}
### ⚠️ {{ issue.key }} - {{ issue.summary }} [{{ issue.priority | upper }}]
**State:** {{ issue.state }} | **Assignees:** {{ issue.assignees | join(", ") }}

{{ issue.description_markdown }}
{% endif %}
{% endfor %}

# Risk Mitigation Strategy
{{ mitigation_notes }}""",
        "parameters_schema_json": [
            {
                "name": "executive_title",
                "label": "Report Title",
                "type": "text",
                "default": "Executive Status & Risk Report",
                "required": True,
            },
            {
                "name": "briefing",
                "label": "Executive Briefing",
                "type": "textarea",
                "default": (
                    "Executive briefing on system operational health and project trajectory."
                ),
                "required": True,
            },
            {
                "name": "mitigation_notes",
                "label": "Risk Mitigation Strategy",
                "type": "textarea",
                "default": (
                    "Continuous monitoring and triage of critical blockers "
                    "to ensure project delivery."
                ),
                "required": False,
            },
        ],
        "csv_columns_json": [
            {"header": "Key", "expr": "issue.key"},
            {"header": "Summary", "expr": "issue.summary"},
            {"header": "Priority", "expr": "issue.priority"},
            {"header": "State", "expr": "issue.state"},
        ],
        "allowed_formats": ["pdf", "xlsx", "csv", "docx", "odt", "html", "md"],
    },
]
