# UI & UX Specialist Review: KANBA-184

**Auditor:** UI Specialist (`ux-architect` / ArchitectUX)  
**Date:** 2026-11-17  
**STATUS: APPROVED**  
**Target Ticket:** `KANBA-184` (`[KB-OAUTH-01] End-to-End MCP OAuth 2.1 Discovery, RFC 7591 Registration, Scoped /w/ & /p/ Routing, Login Redirect, and RLS Workspace Slug Resolution`)

---

## 1. Executive Summary & UX Mission

In Model Context Protocol (MCP) workflows with clients such as Claude Desktop, Cursor, ChatGPT, and Antigravity, the browser-based authorization step is the primary human-facing touchpoint. Prior to `KANBA-184`, this experience suffered from critical failures:
1. Unauthenticated users were met with an abrupt `401 Authentication Required` JSON error in their browser with no path to log in.
2. Even after initial redirect handling, absolute redirect targets broke `resolveSafeNext()`, falling back to `/`.
3. Valid OAuth query strings containing colons (like `scope=agent:read+agent:write` or loopback redirect URIs) were rejected by overly restrictive sanitizers.
4. Server-rendered consent screen styles and form actions were stripped or blocked by global CSP headers.

As the project UI Specialist and UX Architect, I reviewed the user flow, server-rendered layouts, interaction states, accessibility, and visual presentation introduced in `kanban/api/v1/oauth.py`, `kanban/oauth/server.py`, and `kanban/web/src/features/auth/authApi.ts`.

The changes in `KANBA-184` successfully resolve all of these friction points, providing a smooth login-and-return handshake, robust CSP protection with unblocked styles/callbacks, and an informative, accessible consent screen.

---

## 2. Forensic UX & Ergonomics Audit

### 2.1 Relative Browser Login Redirection (`kanban/api/v1/oauth.py`)
- **Relative Path Encoding:**
  - In `oauth_authorize` (lines 537-542), when `caller is None`, the endpoint constructs a relative `next_target`:
    ```python
    next_target = f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path
    login_url = f"/login?next={urllib.parse.quote(next_target, safe='')}"
    return RedirectResponse(login_url, status_code=302)
    ```
  - Previously, encoding the full absolute URL (`https://...`) caused `resolveSafeNext()` in `LoginPage.tsx` to reject the target as an external URI and fall back to `/`, stranding the user on the home screen after login.
  - With relative path encoding, `searchParams.get('next')` safely retrieves `/oauth/authorize?response_type=code&...`.
  - All login flows (`LocalAdmin`, `LDAP`, and `OIDC`/`OAuth2` cards via `/api/v1/auth/cards/{slug}/start?next=...`) preserve `next`, seamlessly resuming the authorization flow immediately upon authentication.
- **Machine Client Discrimination:**
  - Callers requesting `Accept: application/json` without `text/html` continue to receive clean `401 ProblemException` JSON payloads, preserving headless API semantics.

### 2.2 Query String Permissiveness with Strict Path Isolation (`authApi.ts`)
- **Query Parameter Ergonomics:**
  - In `kanban/web/src/features/auth/authApi.ts`, `resolveSafeNext()` was refined:
    ```ts
    const SAFE_NEXT_REGEX = /^\/(?!\/)[A-Za-z0-9/_\-?=&.%:+~]*$/;
    const [pathPart = ''] = next.split('?');
    if (!SAFE_NEXT_REGEX.test(next) || next.includes('\\') || pathPart.includes(':')) {
      return '/';
    }
    return next;
    ```
  - This allows characters required by OAuth 2.1 query parameters (colons in scopes like `scope=agent:read+agent:write`, plus signs for space delimiters, tildes, and URL-encoded loopback redirect URIs like `redirect_uri=http%3A%2F%2F127.0.0.1%3A54321%2Fcallback`).
  - Simultaneously, it strictly rejects any colon in `pathPart` (the portion before `?`), blocking protocol/scheme injection attacks such as `/javascript:...` or `/https:...`. Protocol-relative `//` and backslashes `\` remain strictly forbidden.

### 2.3 Route-Specific Content Security Policy (`kanban/oauth/server.py`)
- **Visual Integrity & Style Preservation:**
  - In `render_consent_screen`, a route-specific `Content-Security-Policy` header is applied:
    ```
    default-src 'none'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self' http://127.0.0.1:* http://localhost:* http://[::1]:* https:; frame-ancestors 'none'; base-uri 'none';
    ```
  - Global application CSP specifies `style-src 'self'`, which would otherwise strip the inline `<style>` block and render an unstyled, broken consent card. `style-src 'self' 'unsafe-inline'` on this isolated endpoint ensures the styled card renders consistently.
- **Unblocked Loopback and HTTPS Form Actions:**
  - MCP clients use loopback callback ports (e.g. `http://127.0.0.1:54321/callback`) or HTTPS endpoints. A generic `form-action 'self'` header blocks the browser from submitting the consent form to these external destinations.
  - Explicitly permitting `http://127.0.0.1:*`, `http://localhost:*`, `http://[::1]:*`, and `https:` in `form-action` ensures seamless callback completion across Claude Desktop, Cursor, Antigravity, and remote agents.

### 2.4 Active Identity Attribution (`user-badge`)
- **Visual Presentation:**
  - The endpoint binds the caller RLS session and queries `principals.display_name` (falling back to UUID).
  - The consent screen renders:
    ```html
    <div class="user-badge">Signed in as <strong>{safe_principal}</strong></div>
    ```
  - Styled with `.user-badge` (`font-size: 0.8125rem`, `color: var(--text-muted)`, `margin-top: 0.5rem`) and high-contrast bold typography for the principal name.
  - Eliminates ambiguity in multi-account setups by showing exactly which account is granting authorization.

### 2.5 Human-Readable Scope Cards & Interaction Ergonomics
- **Intuitive Descriptions (`SCOPE_DESCRIPTIONS`):**
  - Replaced raw technical strings with structured two-tier items:
    - `agent:read`: Bold identifier + *"Read-only access to boards, tickets, stickies, and issues"*
    - `agent:write`: Bold identifier + *"Read and write access to tickets, comments, stickies, and workflows"*
    - `docs:read`: Bold identifier + *"Read-only access to documents and knowledge spaces"*
    - `docs:write`: Bold identifier + *"Read and write access to documents, stickies, and knowledge bases"*
    - `admin:read`: Bold identifier + *"Read-only access to system users, audit logs, and settings"*
    - `admin:write`: Bold identifier + *"Administrative write access to policies and configurations"*
    - `admin:destructive`: Bold identifier + *"Full destructive administrative control (purge and hard delete)"*
- **Layout & Visual Hierarchy:**
  - Flexible rows with top-aligned checkboxes (`.scope-item`).
  - Verified host redirect badge (`.host-badge`) for destination transparency.
  - Surface banner (`AGENT`, `DOCS`, `ADMIN`) prevents cross-surface confusion.
  - Project scope dropdown (`All Accessible Projects` vs specific project) gives operators clear least-privilege control.
  - High-contrast, accessible action buttons: `.btn-approve` (`#3b82f6`) and `.btn-deny` (`#334155`).

---

## 3. Verification & Compliance Evidence

- **Frontend Auth Unit Tests (`LoginPage.test.tsx`):**
  - 24 tests passed covering open redirect security, query parameter permissiveness (`:`, `+`, `~`), and relative target preservation.
- **Backend OAuth Tests (`test_oauth_flow.py`, `test_oauth_unit.py`):**
  - Verified relative `/login?next=%2Foauth%2Fauthorize%3F...` redirect.
  - Verified default resource fallback to `/mcp/agent` when omitted.
  - Verified consent CSP headers (`style-src 'self' 'unsafe-inline'`, loopback `form-action`).
- **Static Analysis & Typecheck:**
  - `tsc -b --noEmit` and `eslint . --max-warnings 0` passed with zero errors or warnings.
  - `ruff check` passed with zero errors.

---

## 4. Final Verdict

The relative login redirect, query string sanitization, route-specific CSP, and human-readable consent screen deliver an attack-resistant, frictionless, and polished experience for AI agent authorization.

**STATUS: APPROVED**  
**Role:** UI Specialist (`ux-architect` / ArchitectUX)  
**Verification Packet:** `docs/qa/KANBA-184/`
