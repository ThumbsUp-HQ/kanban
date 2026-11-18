# UI Specialist Review: KANBA-225

STATUS: APPROVED

Auditor: ui-spec (UI Designer / UX Architect / Accessibility Specialist)
Target Ticket: KANBA-225 (Harden Forwarded IP Rate Limiting, Free-Text Secret Scrubbing, Referer CSRF, and 428 Delete Preview Hint)
Branch: main (integrated from feat/w1-sec commit 6ccf0429)

## 1. Scope and Surface Audited

1. API and Frontend State / Error Alignment:
   - Actionable 428 Precondition Required Hint (`kanban/api/v1/issue_delete.py`, `kanban/services/issue_delete.py`):
     - When `DELETE /api/v1/issues/{id}` is called without the `Kb-Blast-Hash` header, the endpoint returns HTTP 428 `BLAST_HASH_REQUIRED` enriched with RFC 7807 problem details: `preview_url` (`/api/v1/issues/{issue_ref}/delete-preview`), `hint`, and `confirm_blast_hash: "Kb-Blast-Hash"`.
     - Frontend actions API (`kanban/web/src/features/drawer-actions/actionsApi.ts`) already implements the two-stage deletion pattern (`fetchDeletePreview` then `deleteIssue` with `Kb-Blast-Hash`). The enriched backend error message and metadata provide clear actionable guidance for direct API and MCP consumers without breaking frontend contracts.

2. Browser Referer CSRF Defense (`kanban/auth/sessions/csrf.py`):
   - Validates `Referer` origin when `Origin` header is absent on state-changing requests, matching against allowed origins derived from host and `KB_PUBLIC_ORIGIN`.
   - Protects standalone web clients and prevents cross-origin state tampering while permitting legitimate same-origin navigation and SPA AJAX requests.

3. Free-Text Secret Scrubber on REST Outputs:
   - Scrubbing high-entropy secret patterns (`sk-*`, `ghp_*`, `AKIA*`, PEM keys) across issue descriptions and comments preserves user-entered Markdown structure while preventing credential leakage on rendered issue surfaces and peek drawers.

4. Forwarded IP Rate Limiting (`kanban/security/client_ip.py`):
   - Safely binds `auth_login_ip` 429 rate limiting to connecting peer IP unless behind explicitly trusted proxy CIDRs. Prevents client-side spoofing while maintaining standard login flow UX.

5. Visual and DOM Impact:
   - Zero changes to frontend CSS, layout components, or DOM templates.
   - All frontend vitest suites and typechecks remain passing.

## 2. Verification and Quality Checks

- Dash Hygiene: Plain ASCII hyphens only; 0 em-dashes or en-dashes.
- OpenAPI Parity: Operation responses include 428 schema documentation.
- All web checks passed cleanly.

## 3. Verdict

The security controls, Referer CSRF validation, free-text scrubbing, and enriched 428 delete hint align with frontend consumption patterns and user experience standards.

STATUS: APPROVED
