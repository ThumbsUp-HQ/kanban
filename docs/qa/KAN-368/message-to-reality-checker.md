# Evidence Packet & Verification Hand-off: KAN-368

- **Ticket ID:** KAN-368
- **Title:** [KB-ADVANCED-DISCLOSURE-02] Issue Creation Modal, Detail Surface, Properties Rail, and Search DSL Progressive Disclosure
- **Author / Implementer:** `b-kan368`
- **Branch:** `feat/KAN-368`
- **Audit Target:** `reality-checker` (Forensic QA Gate)
- **Target Verification Level:** Grade-A READY Certification

---

## 1. Executive Summary

Ticket `KAN-368` implements clean, accessible progressive disclosure across `QuickCreateIssueModal.tsx` and `PropertiesRail.tsx` utilizing the shared `<AdvancedSection>` component (`kanban/web/src/ui/AdvancedSection.tsx`):
1. **QuickCreateIssueModal Progressive Disclosure:**
   - Primary visible fields: Summary (required), Description markdown, State, and Priority.
   - Secondary metadata collapsed into `<AdvancedSection>`: Module selector (when `modulesEnabled`), Due Date picker, and Parent Issue key.
   - Active overrides counter badge renders `N custom settings active` when secondary settings are populated.
   - Auto-expands on submit error (`hasErrors={true}`) or when opened with pre-filled default overrides (`defaultAdvancedOpen` or non-empty `defaultModuleIds`).
   - Value preservation across toggle states and submit payloads.
2. **PropertiesRail Progressive Disclosure:**
   - Core triage rows remain immediately accessible: State, Priority, Assignees, Dates, Cycle, Modules, Parent, and Labels.
   - Secondary audit provenance (`CreatedByRow`) and admin-defined custom fields (`CustomFieldsRailSection`) stowed under `<AdvancedSection title="Advanced Properties">`.
   - Computes active overrides across custom fields, provenance overrides, and linked development branches/PRs.
   - Backward-compatible DOM mounting ensures all existing drawer, rail, and booster tests pass without disruption.
3. **Responsive Visual Proofs:**
   - Automated Playwright suite executes against all 5 responsive viewports producing screenshot artifacts in `docs/qa/KAN-368/screenshots/`.
4. **Code Quality and Coverage:**
   - 39 feature unit tests in `QuickCreateIssueModal.test.tsx` and `PropertiesRail.test.tsx` passing with 0 failures.
   - Target files line coverage: 97.30% (threshold: >=95%).
   - Strict TypeScript (`tsc -b --noEmit`), ESLint (`--max-warnings 0`), Vite production build, and ASCII hyphens validator (`check_no_dashes`) all pass with 0 errors.

---

## 2. Forensic Verification Checklist

| Requirement | Status | Evidence Reference |
| :--- | :---: | :--- |
| **Primary Fields Visible by Default** | PASS | `QuickCreateIssueModal.tsx`: Summary, Description, State, Priority outside `<AdvancedSection>` |
| **Secondary Creation Metadata Stowed** | PASS | `<AdvancedSection>` encapsulates Module, Due Date, and Parent Issue |
| **Properties Rail Advanced Section** | PASS | `PropertiesRail.tsx`: `<AdvancedSection title="Advanced Properties">` stows `CreatedByRow` and custom fields |
| **Active Overrides Indicator** | PASS | Badge renders dynamic counter (`N custom settings active`) on both surfaces |
| **Error Auto-Expansion** | PASS | `hasErrors={Boolean(submitError)}` auto-expands section on validation failure |
| **Unit Test Coverage >= 95%** | PASS | `docs/qa/KAN-368/unit-test-results.txt` (97.30% lines, 39 tests pass) |
| **TypeScript Strict Compilation** | PASS | `docs/qa/KAN-368/build-check.txt` (`tsc -b --noEmit`: 0 errors) |
| **ESLint Zero Warnings** | PASS | `docs/qa/KAN-368/build-check.txt` (`eslint . --max-warnings 0`: 0 warnings) |
| **Vite Production Build** | PASS | `docs/qa/KAN-368/build-check.txt` (`vite build`: 0 errors) |
| **Plain ASCII Hyphens** | PASS | `docs/qa/KAN-368/build-check.txt` (`scripts.check_no_dashes`: 0 errors) |
| **UI Specialist Sign-off** | PASS | `docs/qa/KAN-368/ui-specialist-review.md` |
| **API Specialist Sign-off** | PASS | `docs/qa/KAN-368/api-specialist-review.md` |
| **Responsive Screenshots** | PASS | `docs/qa/KAN-368/screenshots/` (5 responsive viewports) |

---

## 3. Evidence Artifact Index

All required forensic proof artifacts are organized in `docs/qa/KAN-368/`:
- `docs/qa/KAN-368/git-diff.patch`: Unified diff of all modifications on `feat/KAN-368`.
- `docs/qa/KAN-368/unit-test-results.txt`: Vitest console run output and coverage report.
- `docs/qa/KAN-368/build-check.txt`: Console logs of typecheck, lint, build, and dash checks.
- `docs/qa/KAN-368/ui-specialist-review.md`: UI/UX Architect audit and sign-off.
- `docs/qa/KAN-368/api-specialist-review.md`: API/Security Specialist audit and sign-off.
- `docs/qa/KAN-368/screenshots/`:
  - `1440x900-desktop-light-collapsed.png`
  - `1440x900-desktop-dark-expanded.png`
  - `768x1024-tablet-collapsed.png`
  - `390x844-mobile-portrait-expanded.png`
  - `844x390-mobile-landscape-collapsed.png`
- `docs/qa/KAN-368/changed-files-manifest.txt`: Cryptographic SHA-256 manifest of touched and created files.
