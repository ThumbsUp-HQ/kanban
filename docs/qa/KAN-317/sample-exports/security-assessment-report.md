Annual Red Team & Threat Surface Audit 2026
CONFIDENTIAL // PROPRIETARY - ACME CYBERSECURITY INC.
## Table of Contents

- [Executive Summary](#executive-summary)
- [Details](#details)
  - [{{ issue.created_date }} - {{ issue.summary }} [{{ issue.priority | upper }}]](#issuecreated_date-----issuesummary---issuepriority--upper)
- [Appendix](#appendix)

# Executive Summary
This security assessment identified 3 critical vulnerabilities across core platform components.

| Key | Summary | State | Priority | Assignees | Created Date |
| :--- | :--- | :--- | :--- | :--- | :--- |
| SEC-101 | Remote Code Execution via SSTI in Custom Field Template | In Progress | Urgent | sec-lead, app-sec | 2026-11-20 |
| SEC-102 | CWE-1236 Formula Injection in CSV Export | Resolved | High | backend-eng | 2026-11-21 |
| SEC-103 | Missing Strict Content-Security-Policy on Report Preview | Open | Medium | frontend-eng | 2026-11-22 |

# Details
## 2026-11-20 - Remote Code Execution via SSTI in Custom Field Template [URGENT]
**Key:** SEC-101 | **State:** In Progress
**Assignees:** sec-lead, app-sec

Template parser evaluated unsafe Jinja2 expressions allowing sandbox escape.
## 2026-11-21 - CWE-1236 Formula Injection in CSV Export [HIGH]
**Key:** SEC-102 | **State:** Resolved
**Assignees:** backend-eng

Spreadsheet formula characters (=, +, -, @) unescaped in export table cells.
## 2026-11-22 - Missing Strict Content-Security-Policy on Report Preview [MEDIUM]
**Key:** SEC-103 | **State:** Open
**Assignees:** frontend-eng

Inline script evaluation permitted on unauthenticated preview iframe.

# Appendix
Methodology follows OWASP ASVS 4.0.3 and NIST SP 800-115 standards.