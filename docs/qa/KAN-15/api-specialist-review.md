# API Specialist Review: KAN-15 (KB-P3-AUDIT-09)

- Ticket: KAN-15
- Title: [KB-P3-AUDIT-09] Add (?) FieldHelpHint Popovers, 4-Flavor Decision Matrix, and 6-Preset Starter Gallery (CVSS, Total Project Issues, SLA) to Custom Fields Studio (3 Problems)
- Reviewer: api-spec-2 (Clean-Room Backend / API / Security Specialist)
- Date: 2026-11-20
- Worktree: `/home/adamoutler/.gemini/antigravity-cli/worktrees/cec3609e-f993-4e05-b8c5-be0070e6116c/swarm-b-kan15-836f797e`
- Branch: `feat/KAN-15`
- Commit: `d83febf96adc1d5659bf0b901f0f5cab56bf022a`
- Status: STATUS: APPROVED

---

## 1. Executive Summary

This clean-room API, Security, and Architecture audit inspects ticket KAN-15 on branch `feat/KAN-15` (commit `d83febf`). The ticket implements accessible FieldHelpHint contextual popovers with strict timing and keyboard dismissal, integration across CustomFieldDefinitionEditor, EscalationApprovalPanel, and CustomFieldsRailSection, a 4-flavor interactive decision matrix, and a 6-preset starter gallery (CVSS 3.1/4.0, Total Project Issues, Days Until Due / SLA, Blocker Count, Sub-Issue Completion %, and Git PR Link Badge) with non-destructive dirty-state confirmation and one-click undo.

All API contracts, security invariants, CSP requirements, and test coverage gates are verified and approved:
1. Exact data model parity between the preset templates (`presets.ts`) and the backend `CustomFieldDefinition` entity contracts (`api.ts`).
2. Robust privilege-boundary documentation embedded directly into Target Scope and Credential Mode fields, preventing accidental or unauthorized privilege escalation.
3. Strict Content Security Policy (CSP) compliance: zero inline `style={...}` JSX attributes, using `style.setProperty` for portal layout and 100% canonical CSS design tokens.
4. Zero new external dependencies introduced.
5. High automated test coverage: 180 Vitest unit tests passing across 10 suites with 99.81% statement coverage and 96.01% branch coverage across all touched source files.

---

## 2. API Contract, Schema & Security Verification

### 2.1 Backend Data Model & Preset Schema Parity
- Backend Source: `kanban/custom_fields/` and `kanban/web/src/features/custom-fields/api.ts`
- Frontend Source: `kanban/web/src/features/custom-fields/presets.ts`
- Audited Presets:
  - `cvss-score`: Valid `wasm` tier, `severity_pill` output format, matching compiled WebAssembly scoring expectations.
  - `total-project-issues`: Valid `nsjail` tier, `number` output format with JSON format metadata (`maximum_fraction_digits: 0`, `unit_suffix: " issues"`), bounded egress to `127.0.0.1`.
  - `days-until-due-sla`: Valid `formula` flavor, `wasm` tier, `severity_pill` format using single-issue AST logic.
  - `blocker-count`: Valid `formula` flavor, `wasm` tier, `badge` format with tokenized color metadata.
  - `sub-issue-completion`: Valid `formula` flavor, `wasm` tier, `number` format with percentage formatting.
  - `git-pr-link`: Valid `nsjail` tier, `url` format with strict `allowed_schemes: ["https"]` metadata and allowlisted egress (`github.com`, `api.github.com`).
- Verification: Every starter preset payload validates strictly against backend `CustomFieldCreateRequest` and `CustomFieldUpdateRequest` schemas.

### 2.2 Privilege Escalation Boundaries & Security Invariants
- Custom field definitions can specify token scope (`PROJECT`, `WORKSPACE`, `SERVER`) and credential execution mode (`INVOKING_USER`, `PROJECT_ADMIN_SP`, `SERVER_ADMIN_SP`).
- Attached `<FieldHelpHint />` components explicitly communicate the security boundary:
  - Clarifies that elevating token scope beyond `PROJECT` requires formal administrative dual-control approval.
  - Warns that Service Principal execution grants elevated privileges across all viewers.
  - EscalationApprovalPanel hints provide clear guidance on business justification and mandatory AAL2 step-up verification.

### 2.3 CSP & Layering Architecture
- Zero inline React styles: All positioning math for the floating portal applies offsets via element CSS variables (`style.setProperty('--hint-x', ...)`).
- Import layering: Strict unidirectional boundaries maintained within frontend modules; no forbidden cyclical or cross-module leaks.
- Zero new runtime or development dependencies added to `package.json` or `pyproject.toml`.

---

## 3. Test Coverage & Quality Gates

- Vitest Suite:
  - 10 test files, 180 tests executed, 180 passed (100% pass rate).
  - Coverage Breakdown:
    * `components/help/FieldHelpHint.tsx`: 100.00% Stmts / 95.45% Branch
    * `features/custom-fields/CustomFieldDefinitionEditor.tsx`: 100.00% Stmts / 95.31% Branch
    * `features/custom-fields/CustomFieldsRailSection.tsx`: 100.00% Stmts / 98.30% Branch
    * `features/custom-fields/EscalationApprovalPanel.tsx`: 98.79% Stmts / 95.55% Branch
    * `features/custom-fields/FlavorDecisionMatrix.tsx`: 100.00% Stmts / 100.00% Branch
    * `features/custom-fields/PresetGallery.tsx`: 100.00% Stmts / 95.23% Branch
    * `features/custom-fields/presets.ts`: 100.00% Stmts / 100.00% Branch
    * Overall touched code: 99.81% Statements, 96.01% Branches, 100% Functions, 100% Lines.
  - All files strictly satisfy the `>=95%` unit test coverage requirement.
- Static Analysis:
  - `tsc -b --noEmit`: 0 errors.
  - `eslint . --max-warnings 0`: 0 warnings, 0 errors.
  - `cssTokensAudit.test.ts`: 4 passed (100% canonical design tokens).
  - `check_no_dashes`: Clean, 0 em-dashes and 0 en-dashes across all code, tests, and documentation.

---

## 4. Verification Verdict

The implementation adheres to all API schemas, security constraints, CSP standards, and test coverage requirements.

STATUS: APPROVED
Reviewed by: api-spec-2
