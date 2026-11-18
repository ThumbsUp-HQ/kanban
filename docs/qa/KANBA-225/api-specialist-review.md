# API Specialist Forensic QA Review: KANBA-225

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KANBA-225 (Harden Forwarded IP Rate Limiting, Secret Scrubbing, Referer CSRF, and 428 Delete Hint)
Branch: feat/w1-sec (integrated into main at commit 82c2f1a)
Review Date: 2026-11-18

## 1. Architectural & Engineering Assessment

### 1.1 Trusted Proxy Rate Limiting (kanban/security/client_ip.py, deploy/standalone/entrypoint.py)
- Enforces strict parsing of trusted proxy networks (`KB_TRUSTED_PROXIES` / `KANBAN_TRUSTED_PROXIES`).
- Evaluates `X-Forwarded-For` ONLY when the immediate connecting peer IP belongs to an explicitly configured trusted proxy CIDR.
- Untrusted direct peer connections ignore spoofed `X-Forwarded-For` headers, binding IP-based rate limiting (`auth_login_ip` 429) directly to the peer IP.
- Standalone Uvicorn invocation avoids wildcard `--forwarded-allow-ips=*` defaults, passing configured trusted proxy CIDRs safely.
- Coverage: `kanban/security/client_ip.py` achieves 97% branch and statement coverage.

### 1.2 Free-Text Secret Scrubber on REST & MCP Outputs (kanban/security/scrubber.py, mcp/yaml_out.py)
- Extends recursive dictionary secret masking in `mcp/yaml_out.py` to scrub free-text strings via `scrub_text()`.
- Redacts high-entropy API keys (OpenAI `sk-*`, GitHub `ghp_*`, AWS `AKIA*`, internal agent tokens `kb_agt_*`, and PEM private keys) in issue descriptions, comments, and MCP `read_ticket` YAML/JSON output.
- Employs fast substring heuristics prior to regex execution, preserving <= 1.0ms performance budget while maintaining Markdown formatting.

### 1.3 Standalone Cross-Origin Referer CSRF Check (kanban/auth/sessions/csrf.py)
- When state-changing HTTP requests omit the `Origin` header (common with browser navigation or fallback flows), `CsrfMiddleware` parses and validates the `Referer` header against allowed origins (`Host` and `KB_PUBLIC_ORIGIN`).
- Cross-origin Referers are rejected with HTTP 403 `CSRF_REJECTED`, blocking cross-origin form submissions and attacks without breaking legitimate same-origin requests.

### 1.4 Actionable 428 Precondition Required Hint (kanban/api/v1/issue_delete.py, kanban/services/issue_delete.py)
- Soft-deleting an issue via `DELETE /api/v1/issues/{id}` without the `Kb-Blast-Hash` header triggers HTTP 428 `BLAST_HASH_REQUIRED`.
- Enriches the response payload with `preview_url` (`/api/v1/issues/{id}/delete-preview`), `confirm_blast_hash: "Kb-Blast-Hash"`, and actionable guidance for human and agent clients.
- Conforms to OpenAPI 3.1 specification update declaring the 428 response schema.

## 2. Test Verification & Code Quality

- `kanban/tests/security/test_client_ip.py`: 10/10 passed (97% coverage).
- `kanban/tests/auth/test_csrf.py`: 9/9 passed (96% coverage).
- `kanban/tests/api/test_issue_delete.py` & `kanban/services/issue_delete.py`: 100% and 95% coverage.
- `mcp/tests/test_yaml_out.py` & `mcp/tests/agent/test_read_ticket.py`: 20/20 passed (98% coverage).
- Static Analysis: `ruff check` (0 errors), `mypy` (0 errors), `scripts.check_no_dashes --all` passed.

## 3. Specialist Verdict

The security controls, rate limiting, secret scrubbing, CSRF defenses, and 428 preview hints satisfy all Security Priority #0 and API contract invariants.
`STATUS: APPROVED`
