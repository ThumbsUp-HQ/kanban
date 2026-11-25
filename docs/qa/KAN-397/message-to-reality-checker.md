# Message to Reality-Checker (KAN-397)

## Forensic Handover Packet: KAN-397

- **Ticket**: `KAN-397` (`[KB-MIGRATION-STUDIO-RENAME] Rename "Plane Migration Import Studio" and "Plane Migration" to "Migration Import Studio" and "Migration"`)
- **Author Agent**: Builder `b-kan397`
- **Target Auditor**: Clean-Room `reality-checker` (`rc-kan397`)
- **Review Mode**: Passive Forensic Verification Mode (Zero shared implementation assumptions)

---

## 1. Summary of Changes

This ticket updates user-facing navigation copy and headings from "Plane Migration Import Studio" and "Plane Migration" to "Migration Import Studio" and "Migration" to accurately reflect multi-source migration capabilities (Plane, Jira, GitHub Issues, Linear):

1. **Title Generalization across all Sources (`PlaneImportStudio.tsx`)**:
   - `kanban/web/src/features/admin-imports/PlaneImportStudio.tsx`:
   - Updated `<h1 className="kb-plane-import-title" data-testid="studio-title">` to render the exact literal string `Migration Import Studio` across all 4 import sources (`plane`, `jira`, `github`, `linear`).
   - Individual source selector buttons retain their dedicated source labels: `Plane`, `Jira`, `GitHub Issues`, and `Linear`.

2. **Unified Admin Hub Subnav Label (`AdminStudioSubnav.tsx`)**:
   - `kanban/web/src/features/admin/AdminStudioSubnav.tsx`:
   - Updated the navigation item for `tab-admin-imports` from `label: 'Plane Migration'` to the exact literal `label: 'Migration'`.

3. **Topbar Avatar Menu Link Text (`Topbar.tsx`)**:
   - `kanban/web/src/app/Topbar.tsx`:
   - Changed the menu item link text for `topbar-admin-imports-link` from `Plane Migration Studio` to the exact literal `Migration Import Studio`.

4. **AppShell Route-to-Section Mapping (`AppShell.tsx`)**:
   - `kanban/web/src/app/AppShell.tsx`:
   - Updated `computeCurrentSection(pathname)` to map:
     - `/admin/imports` -> `'Migration Import Studio'`
     - `/admin/auth` -> `'Auth Cards'`
     - `/admin/oauth` -> `'OAuth Clients'`
     - `/admin/agent-runners` -> `'Agent Runners'`
     - `/admin/ai` -> `'AI Providers'`
     - `/admin/agents` -> `'Autonomous Agents'`

5. **Authoritative Wiki Documentation Updates & Sync**:
   - Updated `thumbs-up-kanban.wiki/Home.md`, `thumbs-up-kanban.wiki/Migration-and-Cutover-Runbook.md`, and `thumbs-up-kanban.wiki/Multi-Source-Migration-and-Key-Alias-Redirects.md` to reference `Migration Import Studio` and `Migration`.
   - Re-synchronized the wiki bundle via `uv run python -m scripts.sync_wiki_bundle`, generating an updated offline `kanban/web/src/features/docs-center/wikiManifest.ts`.

---

## 2. Automated Test Verification and Coverage

- **Target Vitest Suite**:
  - `src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx` (12 tests)
  - `src/app/__tests__/MenuConsolidation_KAN362.test.tsx` (25 tests)
- **Results**: 37 passed tests, 0 failed.
- **Coverage**:
  - Statements: 100%
  - Branches: 95.56%
  - Functions: 100%
  - Lines: 100%
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

Zero-mock Playwright screenshots captured at multiple viewports and themes in `docs/qa/KAN-397/screenshots/`:
- `01-desktop-1440x900-light.png` / `1440x900-desktop-light.png`
- `01-desktop-1440x900-light-menu-open.png`
- `02-desktop-1440x900-dark.png` / `1440x900-desktop-dark.png`
- `02-desktop-1440x900-dark-menu-open.png`
- `03-tablet-portrait-768x1024.png` / `768x1024-tablet-portrait.png`
- `04-mobile-390x844.png` / `390x844-mobile-portrait.png`

All screenshots verify:
- Literal `Migration Import Studio` in the studio title heading
- Literal `Migration` active tab in AdminStudioSubnav
- Literal `Migration Import Studio` in Topbar avatar navigation menu
- Zero visual clipping across all desktop, tablet, and mobile viewports

---

## 5. Forensic Verification Command Reference

```bash
# Verify unit tests and >=95% coverage
COVERAGE_INCLUDE="src/features/admin-imports/PlaneImportStudio.tsx,src/features/admin/AdminStudioSubnav.tsx" \
pnpm --dir kanban/web exec vitest run --coverage \
src/features/admin-imports/__tests__/PlaneImportStudio.test.tsx \
src/app/__tests__/MenuConsolidation_KAN362.test.tsx

# Verify static analysis and build
python3 scripts/check_no_dashes.py --all
pnpm --dir kanban/web typecheck
pnpm --dir kanban/web lint
pnpm --dir kanban/web build

# Verify changed files checksums
cd docs/qa/KAN-397 && sha256sum -c changed-files-manifest.txt
```
