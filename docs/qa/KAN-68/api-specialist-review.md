# API and Security Specialist Review: KAN-68

- **Ticket:** KAN-68 ([KB-SEC-CODEX-06]) - Expose capability_mask & allowed_cidrs in MCP Access Studio, Align Runner Enrollment/Rotation UX, & Sync Security Wiki
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-68-mcp-runner-studio-ux`
- **Commit Under Audit:** `5e988f25` (`feat(mcp): expose capability_mask & allowed_cidrs, align runner ux, and sync wiki (KAN-68)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan68-1d9a754f`
- **Status:** APPROVED

---

## 1. Executive API & Security Architecture Evaluation

Ticket KAN-68 exposes and operationalizes the platform credential boundary, capability mask, and CIDR security controls in the user interfaces and documentation center.

Key security and API contract items audited:
1. **MCP Access Studio & Capability Scopes (`kanban/web/src/features/settings/`):**
   - Read-only keys (`capability_mask === 1` / `VIEW` only) now correctly generate configuration snippets with read-only scopes `scopes: ['${surface}:read']` rather than unconditionally emitting write scopes.
   - Introduced `Capability Ceiling` selector with preset configurations:
     - `View Only (1)`
     - `View + Comment (3)`
     - `Standard Member (31)`
     - `Full / Admin (255)`
     - `Custom` (with interactive bit toggles grid for bits 1, 2, 4, 8, 16, 32, 64, 128).
   - Enforces client-side IPv4 (`0.0.0.0/0` - `255.255.255.255/32`) and IPv6 (`::/0` - `ffff:.../128`) CIDR validation on the `Allowed CIDRs` field. Malformed CIDRs immediately disable the submission button and display an inline validation alert, preventing bad API requests.
   - Clarifies `CredentialBoundary` constraints with user-facing warnings confirming that minted tokens can never exceed caller permissions or bypass network CIDR restrictions.
2. **Runner Studio Enrollment & Zero-Trust Architecture (`kanban/web/src/features/admin-runners/`):**
   - Mint Enrollment Token modal generates the exact `kanban-agent-runner enroll` command with `--url <origin>`, `--token-stdin`, and `--pool <slug>`.
   - Explicitly displays the dedicated port `:8444` mTLS notification, directing external agent runners to the verified mutual TLS edge.
   - Adds certificate rotation guidance detailing zero-downtime runner migration (mint token -> enroll new runner -> verify heartbeat -> revoke old certificate).
   - Handles `AAL2_REQUIRED` and `AAL2_STALE` step-up authentication via inline `SecondFactorStep` modals.
3. **Documentation Center & Wiki Synchronization:**
   - Synchronized four core wiki chapters (`Zero-Trust-Security-and-Access-Visibility.md`, `Multi-Provider-AI-Engine-and-Runners.md`, `Studio-Configuration-Reference.md`, `System-Topology-and-Multi-Container-Architecture.md`) with accurate capability mask, CIDR, and runner mTLS descriptions.
   - Regenerated offline bundle `kanban/web/src/features/docs-center/wikiManifest.ts`.

---

## 2. Wire Contracts & Security Invariants

### A. API Request & Response Contracts
- `POST /api/v1/auth/mcp/tokens` payload accurately passes `capability_mask: number` and optional `allowed_cidrs: string[]`.
- Generated MCP client configuration JSON accurately maps surfaces (`agent`, `docs`, `admin`) to host URL and bearer token with surface-appropriate read or write scopes.

### B. Tenancy & Anti-Enumeration
- Tokens minted via MCP Studio inherit caller scoping constraints.
- Runner administration endpoints remain strictly protected by AAL2 administration dependencies (`require_admin_aal2`).

---

## 3. Unit Test Coverage & Verification Metrics

- **Frontend Vitest Results:** 81 tests passing (0 failures).
- **Branch Coverage on Touched Frontend Files:**
  - `settingsApi.ts`: 96.29% branch coverage (100% statements).
  - `McpConfigSnippetModal.tsx`: 98.03% branch coverage (100% statements).
  - `McpAccessStudio.tsx`: 96.00% branch coverage (99.51% statements).
  - `MintEnrollmentTokenModal.tsx`: 100% branch coverage (100% statements).
  - `RunnerStudioPage.tsx`: 98.11% branch coverage (100% statements).
  - All touched source files exceed the strict >=95% branch coverage standard.
- **Backend Wiki Tests:** 13 passed in `kanban/tests/docs/test_wiki_media_audit.py`.
- **Static Quality Checks:**
  - `eslint`: 0 errors, 0 warnings.
  - `tsc -b --noEmit`: 0 errors.
  - `vite build`: Clean production build in 1.34s.
  - `check_no_dashes`: Clean across repository (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
