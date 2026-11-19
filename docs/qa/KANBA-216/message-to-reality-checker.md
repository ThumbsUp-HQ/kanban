# Forensic QA Packet for KANBA-216: Reality-Checker Verification

## 1. Ticket Overview
- **Ticket ID**: KANBA-216
- **Title**: [KB-AUDIT-10] Fix Custom Scripted Fields Studio Wasm/Scalar Templates, Pattern Regex, Test-Execute, Dual-Control Approval UX, and Ticket Rail Rendering
- **Branch**: `feat/w6-cf`
- **Owner**: `w6-cf` (Wave 6 Builder)

---

## 2. Completed Scope & Requirements Verification

### A. Identifier Slug Regex Syntax Fix
- **Issue**: Modern browsers parsing `pattern` with UnicodeSets `/v` flag raised `Pattern attribute syntax error: Invalid character in character class` on unescaped hyphens `[a-z0-9-]`.
- **Resolution**: Escaped hyphen to `^[a-z0-9][a-z0-9\-]{1,62}$` in `CustomFieldDefinitionEditor.tsx`.
- **Proof**: 0 console errors during studio mount and submission; unit test assertions in `CustomFieldDefinitionEditor.test.tsx` verify legal slugs pass and illegal slugs reject.

### B. Starter Templates & Field Flavors Alignment
- **Issue**: Defaulting `script_source` to `return "Hello";` failed backend Wasm bytecode validation with `422 WASM_BINARY_INVALID`.
- **Resolution**:
  - Implemented 4 distinct field flavors: `scalar`, `formula`, `wasm`, `nsjail`.
  - Created tailored `STARTER_TEMPLATES[flavor][format]` for all 7 formats (text, number, badge, markdown_snippet, url, json_table, severity_pill).
  - Built AST-based safe formula evaluator (`_eval_safe_formula`) in Python backend supporting safe literals, math/comparison operators, JS ternary conversion, and `issue.*` attribute context while blocking dunder attributes and dangerous AST nodes.
- **Proof**: 6 unit tests passing in `kanban/tests/custom_fields/test_safe_formula_unit.py`; 31 unit tests in `CustomFieldDefinitionEditor.test.tsx`.

### C. Test Execute Button, Textarea Enlargement, Query Cache & Dual-Control UX
- **Interactive Evaluation**: Added `Test Execute` section with issue key input, `Test Execute` action button, latency pill (`[data-testid="test-latency"]`), live rendered output pill (`[data-testid="test-output-pill"]`), and monospace truncated logs viewer (`[data-testid="test-logs"]`).
- **Enlarged Textarea**: Set `rows={8}` on `[data-testid="format-metadata-textarea"]` ensuring closing braces and nested metadata JSON are visible without inner scroll clipping.
- **Immediate Query Cache Refresh**: Updated TanStack Query cache directly in mutation `onSuccess` handlers (`queryClient.setQueryData(qk.customFields.project(...), ...)`), eliminating the F5 refresh race condition.
- **Dual-Control Explanation Banner**: Added literal banner (`[data-testid="dual-control-explanation-banner"]`) explaining that escalating to WORKSPACE or SERVER scope requires another distinct administrator with fresh AAL2, self-approval is blocked (403), and source edits reset approvals.

### D. Computed Field Rendering in Drawer & Fullscreen Issue Views
- **Resolution**:
  - `CustomFieldsRailSection.tsx` resolves `projectKey` from `issueKey` (e.g. `KANBA-1` -> `KANBA`) when route props lack explicit key.
  - Active definitions render with live values without showing `Unavailable`.
  - True sandbox errors (`SANDBOX_UNAVAILABLE_IN_STANDALONE`) render an informative indicator with `<EmojiHint>` tooltip (`custom-field-sandbox-hint-${slug}`).
  - Consistent layout and state rendering across both `?peek=` Drawer and Fullscreen Issue View.

---

## 3. Strict Quality & Gate Evidence

### Automated Unit Test Branch Coverage (Threshold >= 95.0%)
- `kanban/web/src/features/custom-fields/CustomFieldDefinitionEditor.tsx`: **97.80%** Branch, **100%** Lines
- `kanban/web/src/features/custom-fields/CustomFieldValue.tsx`: **98.16%** Branch, **100%** Lines
- `kanban/web/src/features/custom-fields/CustomFieldsRailSection.tsx`: **98.11%** Branch, **100%** Lines
- `kanban/web/src/features/custom-fields/CustomFieldsStudio.tsx`: **100%** Branch, **100%** Lines
- `kanban/web/src/features/custom-fields/EscalationApprovalPanel.tsx`: **95.45%** Branch, **100%** Lines
- `kanban/web/src/features/custom-fields/api.ts`: **97.91%** Branch, **100%** Lines
- `kanban/web/src/features/drawer/IssueSurface.tsx`: **95.13%** Branch, **99.18%** Lines

### Static Analysis & Type Checking
- TypeScript: `tsc --noEmit` exited `0` (0 errors).
- ESLint: `eslint` exited `0` (0 errors, 0 warnings).
- Ruff: `ruff check` exited `0` (0 errors).
- Python Tests: `pytest` exited `0` (6 passed).

### Specialist Audits & Approvals
- API Specialist Review: `docs/qa/KANBA-216/api-specialist-review.md` (Approved, Grade A)
- UI Specialist Review: `docs/qa/KANBA-216/ui-specialist-review.md` (Approved, Grade A)

### Visual Regression & Proof Screenshots
Playwright automated screenshots captured across Light/Dark x Desktop/Tablet/Mobile:
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-light-desktop.png`
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-dark-desktop.png`
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-light-tablet.png`
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-dark-tablet.png`
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-light-mobile.png`
- `docs/qa/KANBA-216/screenshots/01-studio-test-execute-dark-mobile.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-light-desktop.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-dark-desktop.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-light-tablet.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-dark-tablet.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-light-mobile.png`
- `docs/qa/KANBA-216/screenshots/02-studio-dual-control-dark-mobile.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-light-desktop.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-dark-desktop.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-light-tablet.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-dark-tablet.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-light-mobile.png`
- `docs/qa/KANBA-216/screenshots/03-drawer-custom-fields-dark-mobile.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-light-desktop.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-dark-desktop.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-light-tablet.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-dark-tablet.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-light-mobile.png`
- `docs/qa/KANBA-216/screenshots/04-fullscreen-custom-fields-dark-mobile.png`

### Character Set Invariant
- Verified with `python3 -m scripts.check_no_dashes --all`: strictly plain ASCII hyphens (`-`) only; zero Unicode em or en dashes.
