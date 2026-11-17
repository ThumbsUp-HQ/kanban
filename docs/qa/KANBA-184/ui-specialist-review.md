# UI & UX Specialist Review: KANBA-184

**Auditor:** UI Specialist (`ux-architect` / ArchitectUX)  
**Date:** 2026-11-16  
**STATUS: APPROVED**  
**Target Ticket:** `KANBA-184` (`[KB-OAUTH-01] End-to-End MCP OAuth 2.1 Discovery, RFC 7591 Registration, Scoped /w/ & /p/ Routing, Login Redirect, and RLS Workspace Slug Resolution`)

---

## 1. Executive Summary & UX Mission

In Model Context Protocol (MCP) workflows with clients such as Claude Desktop, Cursor, ChatGPT, and Antigravity, the browser-based authorization step is the primary human-facing touchpoint. Prior to `KANBA-184`, this experience suffered from a critical failure: unauthenticated users were met with an abrupt `401 Authentication Required` JSON error in their browser with no way to log in. Furthermore, the consent screen presented raw technical scope strings without contextual descriptions or logged-in identity attribution.

As the project UI Specialist and UX Architect, I reviewed the user flow, server-rendered layouts, interaction states, accessibility, and visual presentation introduced in `kanban/api/v1/oauth.py` and `kanban/oauth/server.py`.

The changes in `KANBA-184` successfully eliminate the unauthenticated dead-end, provide a smooth login-and-return handshake, and transform the consent screen into an informative, trustworthy, and accessible interface.

---

## 2. Forensic UX & Ergonomics Audit

### 2.1 Interactive Browser Login Redirection (`kanban/api/v1/oauth.py`)
- **Seamless 302 Redirection:**
  - In `oauth_authorize` (lines 526–541), the blocking `Depends(get_principal)` dependency was replaced with dynamic resolution via `resolver.resolve(request)`.
  - When `caller is None`, the endpoint inspects the `Accept` header. If the request is a standard browser navigation (not pure JSON), it returns:
    ```python
    login_url = f"/login?next={urllib.parse.quote(str(request.url), safe='')}"
    return RedirectResponse(login_url, status_code=302)
    ```
  - All PKCE parameters (`response_type=code`, `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method=S256`, `state`, `resource`, `scope`) are preserved in the `next` target query string.
  - This URL encoding is fully compliant with `resolveSafeNext()` in the frontend login page (`SAFE_NEXT_REGEX`), guaranteeing the user returns seamlessly to `/oauth/authorize` after authenticating via Passkey, Google, GitHub, or LDAP.
- **Machine Client Discrimination:**
  - Machine clients requesting `Accept: application/json` without `text/html` continue to receive clean `401 ProblemException` JSON payloads, maintaining API integrity for non-browser callers.

### 2.2 Active Identity Attribution (`user-badge`)
- **Visual Presentation:**
  - In `kanban/api/v1/oauth.py` (lines 559–562), the endpoint queries the `principals` table for the user's `display_name`, falling back to their UUID.
  - In `kanban/oauth/server.py`, the consent screen renders:
    ```html
    <div class="user-badge">Signed in as <strong>{safe_principal}</strong></div>
    ```
  - Styled with `.user-badge` (`font-size: 0.8125rem`, `color: var(--text-muted)`, `margin-top: 0.5rem`) and high-contrast bold text for the identity.
- **Operator Confidence:**
  - In multi-account and multi-tenant environments, this immediately resolves ambiguity by affirming exactly which user profile is granting permissions to the AI agent.

### 2.3 Human-Readable Permission Scope Cards (`SCOPE_DESCRIPTIONS`)
- **Elimination of Raw Scope Strings:**
  - In `kanban/oauth/server.py`, `SCOPE_DESCRIPTIONS` maps each technical scope to an intuitive plain-English description:
    - `agent:read`: *"Read-only access to boards, tickets, stickies, and issues"*
    - `agent:write`: *"Read and write access to tickets, comments, stickies, and workflows"*
    - `docs:read`: *"Read-only access to documents and knowledge spaces"*
    - `docs:write`: *"Read and write access to documents, stickies, and knowledge bases"*
    - `admin:read`: *"Read-only access to system users, audit logs, and settings"*
    - `admin:write`: *"Administrative write access to policies and configurations"*
    - `admin:destructive`: *"Full destructive administrative control (purge and hard delete)"*
- **Two-Tier Typography & Layout:**
  - Each item is structured as a flexible row with top alignment:
    ```html
    <label class="scope-item">
      <input type="checkbox" name="scopes" value="{safe_sc}" checked />
      <span class="scope-info">
        <span class="scope-name">{safe_sc}</span>
        <span class="scope-desc">{desc}</span>
      </span>
    </label>
    ```
  - `.scope-name` retains the monospace identifier (`font-weight: 600; color: #cbd5e1;`) for technical accuracy, while `.scope-desc` (`font-size: 0.75rem; color: var(--text-muted);`) clearly communicates the real-world impact of the grant.

### 2.4 Destination Verification & Trust Signifiers
- **Host Redirect Badge:**
  - Prominently displays `<span class="host-badge">Redirects to {host_display}</span>` directly under the application title.
  - For loopback connections (`127.0.0.1:port` used by Claude Desktop, Cursor, Antigravity), users can clearly verify that tokens return to their local machine.
- **Surface Banner:**
  - The high-visibility `.surface-banner` (`AGENT`, `DOCS`, `ADMIN`) prevents cross-surface confusion by highlighting the MCP context.
- **Project Boundary Selector:**
  - Accessible `<select name="allowed_project_id">` allows operators to confine the agent's token to a single target project or grant workspace-wide access (`All Accessible Projects`), adhering to the principle of least privilege.
- **Button Ergonomics:**
  - High-contrast, keyboard-focusable action buttons: `.btn-approve` (`background: var(--primary, #3b82f6)`) and `.btn-deny` (`background: #334155`).

---

## 3. Verification & Compliance Evidence

- **Transcript Validation (`docs/qa/KANBA-184/oauth-mcp-transcript.json`):**
  - Confirms the end-to-end handshake:
    1. `GET /.well-known/oauth-protected-resource` returns 200 with supported scopes.
    2. `POST /oauth/register` returns 201 with client credentials.
    3. `GET /oauth/authorize` returns 200 with `consent_rendered: true` and `signed_in_badge: true`.
- **Automated Test Results (`docs/qa/KANBA-184/unit-test-results.txt`):**
  - 174 test cases passed (0 failures) covering RFC 7591 dynamic registration, PKCE authorization code flow, and consent rendering.
- **Static Analysis & Linting (`docs/qa/KANBA-184/build-check.txt`):**
  - Python: `ruff check` passed with zero errors.
  - Web: `tsc -b --noEmit` and `eslint . --max-warnings 0` passed with zero errors or warnings.
  - Architecture: `lint-imports` verified all unidirectional module contracts.

---

## 4. Final Verdict

The interactive OAuth 2.1 login redirect and enhanced consent screen provide a polished, frictionless, and secure client experience for developers and end-users connecting AI agents to 👍kanban.

**STATUS: APPROVED**  
**Role:** UI Specialist (`ux-architect` / ArchitectUX)  
**Verification Packet:** `docs/qa/KANBA-184/`
