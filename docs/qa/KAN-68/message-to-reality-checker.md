# Forensic QA Verification Packet: KAN-68

## Executive Summary
- Ticket: `KAN-68` ([KB-SEC-CODEX-06] Expose capability_mask & allowed_cidrs in MCP Access Studio, Align Runner Enrollment/Rotation UX, & Sync Security Wiki)
- Branch: `main` (merged from `feat/KAN-68-mcp-runner-studio-ux`)
- Merged Commit (`HEAD`): `86c2da2d6f4ff9558b6e3cbc84950c6fc09c0604` (`86c2da2d`)
- Pre-Ticket Base Commit (`main`): `22d88335b81e61216d97121145ee644ba8ea5641` (`22d88335`)
- Workspace: `/home/adamoutler/kanban`
- Status: READY FOR SPECIALIST AND REALITY-CHECKER AUDIT

All three core actions specified in ticket KAN-68 have been implemented, tested with >=95% branch coverage, validated with visual browser screenshots, and synced with the documentation wiki with zero em-dashes or en-dashes.

---

## 1. Action 1: MCP Access Studio Enhancements
### Files Modified
- `kanban/web/src/features/settings/McpAccessStudio.tsx`
- `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`
- `kanban/web/src/features/settings/settingsApi.ts`
- `kanban/web/src/features/settings/__tests__/McpAccessStudio.test.tsx`

### Implementation Details
1. **Read-Only Scopes Alignment:**
   - When minting or displaying client config snippets for read-only keys (`capability_mask === 1` / `VIEW` only), configuration snippets emit `scopes: ['${surface}:read']` instead of hardcoded `'${surface}:write'`.
2. **Capability Ceiling Selector & Preset Grid:**
   - Added `Capability Ceiling` selector with standard presets:
     - `View Only (1)`
     - `View + Comment (3)`
     - `Standard Member (31)`
     - `Full / Admin (255)`
     - `Custom`
   - Added interactive bit toggles grid (`data-testid="cap-bit-${String(bit)}"`) allowing granular toggling of bits 1, 2, 4, 8, 16, 32, 64, and 128.
3. **Allowed CIDRs Input & Client-Side Validation:**
   - Added `Allowed CIDRs (Optional)` text input (`data-testid="mint-allowed-cidrs-input"`).
   - Implemented strict client-side IPv4 (`0.0.0.0/0` to `255.255.255.255/32`) and IPv6 (`::/0` to `ffff:.../128`) CIDR validation.
   - Malformed inputs (e.g. `999.999.1.1/99` or non-CIDR strings) display an inline validation error banner (`data-testid="cidr-validation-error"`) and disable the Submit button (`data-testid="submit-mint-key-btn"`).
4. **Credential Boundary Notice & Row Badges:**
   - Added `data-testid="credential-boundary-note"` explaining that tokens cannot exceed the issuing user capabilities or bypass CIDR limits.
   - Rendered key rows display `data-testid="key-cap-mask-${k.id}"` and `data-testid="key-cidr-badge-${k.id}"` pills.

---

## 2. Action 2: Runner Studio Enrollment & Rotation UX
### Files Modified
- `kanban/web/src/features/admin-runners/MintEnrollmentTokenModal.tsx`
- `kanban/web/src/features/admin-runners/RunnerStudioPage.tsx`
- `kanban/web/src/features/admin-runners/__tests__/RunnerStudioPage.test.tsx`

### Implementation Details
1. **Runner Enrollment CLI Command:**
   - The mint enrollment token modal renders the exact copyable CLI command:
     `echo "<TOKEN>" | uv run kanban-agent-runner enroll --url <window.location.origin> --token-stdin --pool <POOL_SLUG>`
   - Displays dedicated notice (`data-testid="runner-mtls-notice"`) clarifying that remote workers establish mutual TLS with the server on dedicated port `:8444`.
2. **Certificate Rotation Guidance:**
   - Added persistent rotation lifecycle guidance card (`data-testid="runner-rotation-guidance"`) detailing zero-downtime certificate rotation (mint new enrollment token -> enroll new runner instance -> verify healthy heartbeat -> revoke stale certificate).
   - In the runner revocation confirmation modal, added explicit guidance note (`data-testid="revoke-rotation-note"`).
3. **Step-Up Authentication (AAL2) Handling:**
   - Integrated inline `SecondFactorStep` modal for step-up verification when runner administration actions return `AAL2_REQUIRED` or `AAL2_STALE`.

---

## 3. Action 3: Wiki Synchronization & Zero-Dash Compliance
### Files Modified
- `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Zero-Trust-Security-and-Access-Visibility.md`
- `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Multi-Provider-AI-Engine-and-Runners.md`
- `/home/adamoutler/kanban/thumbs-up-kanban.wiki/Studio-Configuration-Reference.md`
- `/home/adamoutler/kanban/thumbs-up-kanban.wiki/System-Topology-and-Multi-Container-Architecture.md`
- `kanban/web/src/features/docs-center/wikiManifest.ts`

### Implementation Details
1. **Documentation Updates:**
   - Synchronized all 4 chapters with accurate documentation for `capability_mask`, `allowed_cidrs`, mTLS port `:8444`, and runner enrollment CLI syntax.
   - Committed changes to wiki git repository.
   - Ran `python3 scripts/sync_wiki_bundle.py` to regenerate the offline bundle `wikiManifest.ts`.
2. **Strict Zero Em/En-Dash Policy:**
   - Verified with `uv run python -m scripts.check_no_dashes --all`: zero violations found across all source files, docs, and wiki chapters.

---

## 4. Test Coverage & Quality Gates

### Unit Test Coverage
All touched frontend source files exceed the strict >=95% branch coverage mandate:
- `kanban/web/src/features/settings/settingsApi.ts`:
  - Statements: 100% | Branches: 96.29% | Functions: 100% | Lines: 100%
- `kanban/web/src/features/settings/McpConfigSnippetModal.tsx`:
  - Statements: 100% | Branches: 98.03% | Functions: 100% | Lines: 100%
- `kanban/web/src/features/settings/McpAccessStudio.tsx`:
  - Statements: 99.51% | Branches: 96.00% | Functions: 100% | Lines: 100%
- `kanban/web/src/features/admin-runners/MintEnrollmentTokenModal.tsx`:
  - Statements: 100% | Branches: 100% | Functions: 100% | Lines: 100%
- `kanban/web/src/features/admin-runners/RunnerStudioPage.tsx`:
  - Statements: 100% | Branches: 98.11% | Functions: 100% | Lines: 100%

### Test Execution Summary
- Vitest suites: 81 tests passing (0 failures).
- Pytest wiki audit: 13 tests passing (`kanban/tests/docs/test_wiki_media_audit.py`).
- ESLint: 0 errors, 0 warnings (`pnpm --dir kanban/web lint`).
- TypeScript: 0 errors (`pnpm --dir kanban/web typecheck`).
- Web build: Completed in 1.34s with exit code 0 (`pnpm --dir kanban/web build`).

---

## 5. Visual Proof Screenshots
Ten annotated screenshots captured in `docs/qa/KAN-68/screenshots/`:
1. `01-mcp-studio-desktop-1440x900.png`: Desktop view of MCP Access Studio with Capability Ceiling and Allowed CIDRs badges.
2. `02-mcp-studio-tablet-768x1024.png`: Tablet viewport of MCP Access Studio.
3. `03-mcp-studio-mobile-390x844.png`: Mobile viewport of MCP Access Studio.
4. `04-mcp-mint-modal-desktop.png`: Mint Token Modal showing Capability Ceiling presets, bitmask toggles, and CIDR input.
5. `05-mcp-mint-modal-validation-error.png`: Mint Token Modal with inline CIDR validation error for invalid CIDR (`999.999.1.1/99`).
6. `06-runner-studio-desktop-1440x900.png`: Runner Studio page showing Certificate Rotation Guidance banner and active runners table.
7. `07-runner-studio-tablet-768x1024.png`: Tablet viewport of Runner Studio.
8. `08-runner-studio-mobile-390x844.png`: Mobile viewport of Runner Studio.
9. `09-runner-mint-modal-desktop.png`: Runner Mint Enrollment Token modal displaying `:8444` mTLS notice and copyable CLI command.
10. `10-docs-wiki-chapter-desktop.png`: In-app Docs Center displaying synchronized wiki chapter.

---

## 6. QA Artifacts Checklist
- `docs/qa/KAN-68/git-diff.patch`: Full unified patch of all modifications.
- `docs/qa/KAN-68/unit-test-results.txt`: Raw test execution output with branch coverage tables.
- `docs/qa/KAN-68/build-check.txt`: Clean lint, typecheck, and build logs.
- `docs/qa/KAN-68/changed-files-manifest.txt`: SHA256 checksum manifest of all touched and proof files.
- `docs/qa/KAN-68/message-to-reality-checker.md`: This comprehensive verification report.
