# Evidence Packet & Verification Hand-off: KAN-370

- **Ticket ID:** KAN-370
- **Title:** [KB-ADVANCED-DISCLOSURE-04] Workspace Settings, Personal Settings Security Details, and Flow Analytics Tunables Progressive Disclosure
- **Author / Implementer:** `b-kan370`
- **Branch:** `feat/KAN-370`
- **Audit Target:** `reality-checker` (Forensic QA Gate)
- **Target Verification Level:** Grade-A READY Certification

---

## 1. Executive Summary

Ticket KAN-370 implements progressive disclosure across three key surfaces:
1. **Workspace Settings (`WorkspaceSettingsPage.tsx`):** Workspace Name, Slug, Display Name, Default Project Visibility, and high-level Role Matrix remain primary and visible by default. Granular field-level override rules, session idle/absolute TTL overrides, trash retention days, MCP key max TTL, air-gap mode, agent-safe numbering, issue export/import toggles, export roles, and webhook egress restrictions are cleanly collapsed inside `<AdvancedSection title="Advanced Security & Governance" testId="workspace-advanced-security-section" defaultOpen={false}>`.
2. **Personal Settings (`PersonalSettingsPage.tsx`):** Passkey nicknames, registration date, last used date, and primary actions (Test Key, Rename, Remove) remain visible by default. Raw cryptographic details (AAGUID, Credential ID, Sign Count, Transport Flags, and Session Metadata) are collapsed inside `<AdvancedSection title="Advanced Security Details" testId="passkey-advanced-{pk.id}" defaultOpen={false}>` with dedicated responsive styles in `PersonalSettingsPage.css`.
3. **Flow Analytics Telemetry Studio (`FlowAnalyticsPage.tsx`):** Added a top-level 3-card headline KPI bar (`flow-headline-kpis`) presenting Throughput, Cycle Time (P50/P85), and Active WIP Count alongside the primary Cumulative Flow Diagram (CFD). 10,000-trial Monte Carlo forecast parameters, percentile band tunables, aging WIP thresholds, and raw tabular data matrices are collapsed inside `<AdvancedSection title="Advanced Statistical Parameters & Simulation" testId="flow-advanced-stats-section" defaultOpen={false}>`.

All 118 unit tests across `WorkspaceSettingsPage.test.tsx`, `PersonalSettingsPage.test.tsx`, and `FlowAnalyticsPage.test.tsx` pass cleanly with 99.11% statement, 95.25% branch, 98.08% function, and 99.88% line coverage. Zero inline styles, zero linter warnings, zero TypeScript errors, and zero em-dashes/en-dashes.

---

## 2. Deliverables & Artifact Index

1. **Source Code Modifications:**
   - `kanban/web/src/features/settings/WorkspaceSettingsPage.tsx`
   - `kanban/web/src/features/settings/PersonalSettingsPage.tsx`
   - `kanban/web/src/features/settings/PersonalSettingsPage.css`
   - `kanban/web/src/features/analytics/FlowAnalyticsPage.tsx`
   - `kanban/web/src/features/analytics/FlowAnalyticsPage.css`

2. **Feature Unit Tests:**
   - `kanban/web/src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx` (Test: `collapses TTL overrides and field-level override rules under AdvancedSection (KAN-370)`)
   - `kanban/web/src/features/settings/__tests__/PersonalSettingsPage.test.tsx` (Test: `renders Passkey label with raw AAGUID and transport flags collapsed in AdvancedSection (KAN-370)`)
   - `kanban/web/src/features/analytics/__tests__/FlowAnalyticsPage.test.tsx` (Test: `renders headline KPIs with Monte Carlo trial count collapsed in AdvancedSection (KAN-370)`)

3. **Forensic Evidence Artifacts:**
   - UI Specialist Review: `docs/qa/KAN-370/ui-specialist-review.md` (APPROVED)
   - API Specialist Review: `docs/qa/KAN-370/api-specialist-review.md` (APPROVED)
   - Vitest Unit Test Log: `docs/qa/KAN-370/unit-test-results.txt` (118 passed)
   - Build Verification Log: `docs/qa/KAN-370/build-check.txt` (TypeScript, ESLint, Vite build)
   - Git Diff Patch: `docs/qa/KAN-370/git-diff.patch`
   - Changed Files Manifest: `docs/qa/KAN-370/changed-files-manifest.txt`

4. **Responsive Visual Screenshots (`docs/qa/KAN-370/screenshots/`):**
   - `1440x900-desktop-light-collapsed.png` (Desktop 1440x900 Light collapsed default)
   - `1440x900-desktop-dark-expanded.png` (Desktop 1440x900 Dark expanded with overrides)
   - `768x1024-tablet-collapsed.png` (Tablet portrait 768x1024 collapsed)
   - `390x844-mobile-portrait-expanded.png` (Mobile portrait 390x844 expanded)
   - `844x390-mobile-landscape-collapsed.png` (Mobile landscape 844x390 collapsed)

---

## 3. Verification Instructions for Reality Checker

1. Confirm git diff: `git diff origin/main --stat`
2. Run unit tests: `pnpm --dir kanban/web exec vitest run src/features/settings/__tests__/WorkspaceSettingsPage.test.tsx src/features/settings/__tests__/PersonalSettingsPage.test.tsx src/features/analytics/__tests__/FlowAnalyticsPage.test.tsx`
3. Run typography/dashes check: `uv run python -m scripts.check_no_dashes --all`
4. Verify checksum manifest: `sha256sum -c docs/qa/KAN-370/changed-files-manifest.txt`
5. Inspect screenshots in `docs/qa/KAN-370/screenshots/`
