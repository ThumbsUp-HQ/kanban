# Message to Reality-Checker (KAN-397)

## Forensic Handover Packet: KAN-397 (Round-1 Remediation)

- **Ticket**: `KAN-397` (`[KB-MIGRATION-STUDIO-RENAME] Rename "Plane Migration Import Studio" and "Plane Migration" to "Migration Import Studio" and "Migration"`)
- **Author Agent**: Builder `b-kan397-rc1`
- **Target Auditor**: Clean-Room `reality-checker` (`rc-kan397`)
- **Branch**: `fix/KAN-397-rc1`
- **Review Mode**: Passive Forensic Verification Mode (Zero shared implementation assumptions)

---

## 1. Summary of Changes and Round-1 Reality-Checker Remediation

This ticket updates user-facing navigation copy and headings from "Plane Migration Import Studio" and "Plane Migration" to "Migration Import Studio" and "Migration" to accurately reflect multi-source migration capabilities (Plane, Jira, GitHub Issues, Linear).

### Reality-Checker Remediation Address Matrix:
1. **Negative Assertions and Coverage in Unit Tests**:
   - Added explicit negative assertions in `kanban/web/src/app/__tests__/MenuConsolidation_KAN362.test.tsx` verifying that `tab-admin-imports` and `topbar-admin-imports-link` do NOT contain `'Plane Migration'` or `'Plane Migration Import Studio'`, paired with exact literal string checks (`📥Migration` and `📥Migration Import Studio`).
   - Covered full suite without hiding `Topbar.tsx` or `AppShell.tsx`: all 4 target files (`PlaneImportStudio.tsx`, `AdminStudioSubnav.tsx`, `Topbar.tsx`, `AppShell.tsx`) are exercised across 86 passing tests achieving 99.31% statements, 95.30% branch, 99.01% functions, and 99.76% lines. Persisted raw in `docs/qa/KAN-397/unit-test-results.txt`.
2. **Clean Scoped `docs/qa/KAN-397/git-diff.patch` and Manifest**:
   - Generated scoped diff containing only KAN-397 modifications (f9aff391 source commit + fix/KAN-397-rc1 test additions + wiki repo commit 3b2b696) with zero unrelated KAN-399/KAN-400 reversions.
   - Included all 3 updated wiki files (`thumbs-up-kanban.wiki/Home.md`, `thumbs-up-kanban.wiki/Migration-and-Cutover-Runbook.md`, `thumbs-up-kanban.wiki/Multi-Source-Migration-and-Key-Alias-Redirects.md`) in `changed-files-manifest.txt`.
3. **Tablet/Mobile Centering, Multi-Source Proof and Honest Review**:
   - Centered active `'Migration'` tab in `AdminStudioSubnav` on tablet (768x1024) and mobile (390x844) viewports via `scrollIntoView({ inline: 'center', block: 'nearest' })`.
   - Prevented WebSocket reconnect toast overlap on dropzone by applying `display: none` styling.
   - Captured multi-source screenshots (`05-source-jira.png`, `06-source-github.png`, `07-source-linear.png`) demonstrating the title remains `Migration Import Studio` across all sources.
   - Rewrote `docs/qa/KAN-397/ui-specialist-review.md` honestly documenting the horizontal scroll centering behavior.
4. **Explicit Build Check Command Headers and Exit Code**:
   - Recorded commands with explicit command headers, positional dash checks, and exit code 0 in `docs/qa/KAN-397/build-check.txt`.

---

## 2. Automated Test Verification and Coverage

- **Target Vitest Suite**:
  - `src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx`
  - `src/app/__tests__/MenuConsolidation_KAN362.test.tsx`
  - `src/app/Topbar.test.tsx`
  - `src/app/AppShell.test.tsx`
- **Results**: 86 passed tests, 0 failed.
- **Coverage**:
  - Statements: 99.31% (>=95% required)
  - Branches: 95.30% (>=95% required)
  - Functions: 99.01% (>=95% required)
  - Lines: 99.76% (>=95% required)
- Raw test logs persisted in `docs/qa/KAN-397/unit-test-results.txt`.

---

## 3. Static Analysis and Quality Gates

- `python3 scripts/check_no_dashes.py --all`: 0 violations
- `pnpm --dir kanban/web typecheck`: 0 TypeScript compiler errors
- `pnpm --dir kanban/web lint`: 0 ESLint warnings
- `pnpm --dir kanban/web build`: Clean production build
- Raw build and static analysis outputs persisted in `docs/qa/KAN-397/build-check.txt`.

---

## 4. Visual Proof Packet

Zero-mock Playwright screenshots captured at multiple viewports, themes, and sources in `docs/qa/KAN-397/screenshots/`:
- `01-desktop-1440x900-light.png` / `1440x900-desktop-light.png`
- `01-desktop-1440x900-light-menu-open.png`
- `02-desktop-1440x900-dark.png` / `1440x900-desktop-dark.png`
- `02-desktop-1440x900-dark-menu-open.png`
- `03-tablet-portrait-768x1024.png` / `768x1024-tablet-portrait.png`
- `04-mobile-390x844.png` / `390x844-mobile-portrait.png`
- `05-source-jira.png`
- `06-source-github.png`
- `07-source-linear.png`

All screenshots visually inspected:
- Literal `Migration Import Studio` in the studio title heading across all 4 sources
- Literal `Migration` active tab in AdminStudioSubnav, centered in scrollable subnav on tablet and mobile
- Literal `Migration Import Studio` in Topbar avatar navigation menu
- Zero WebSocket toast overlap on dropzone
- Zero visual clipping across all desktop, tablet, and mobile viewports

---

## 5. Forensic Verification Command Reference

```bash
# Verify unit tests and >=95% coverage across all 4 files
COVERAGE_INCLUDE="src/features/admin-imports/PlaneImportStudio.tsx,src/features/admin/AdminStudioSubnav.tsx,src/app/Topbar.tsx,src/app/AppShell.tsx" \
pnpm --dir kanban/web test:coverage \
src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx \
src/app/__tests__/MenuConsolidation_KAN362.test.tsx \
src/app/Topbar.test.tsx \
src/app/AppShell.test.tsx

# Verify static analysis and build
python3 scripts/check_no_dashes.py --all
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build

# Verify changed files checksums
sha256sum -c docs/qa/KAN-397/changed-files-manifest.txt
```
