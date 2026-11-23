# API Specialist Review: KAN-374

**Ticket:** `KAN-374` (`[KB-SEARCH-SINGLE-EXPORT-MENU] Consolidate Duplicate Search Bar Export Buttons into Single Export Button with 3 Options (CSV, Password-Protected ZIP, Report Template)`)
**Reviewer:** `@api-spec` (Backend Architect & API Specialist)
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket refines the issue export API surface across search and view toolbars:
1. Extended `CsvImportExportModalProps` with optional `initialExportFormat?: 'csv' | 'zip_csv'`, establishing pre-selection of export formats when launching the modal.
2. Extended `IssueNavigatorBarProps` and `FilterDisplayBarProps` with `onExport?: (format?: 'csv' | 'zip_csv') => void`, permitting consumers to receive the chosen export format directly from toolbar menu actions.
3. Updated layout routing in `viewRegistry.tsx` to maintain stateful tracking of `csvExportFormat` (`'csv' | 'zip_csv'`) and pass `initialExportFormat` directly to `CsvImportExportModal`.
4. Ensured backward compatibility: when `onExport` or `onExportReports` callbacks are omitted, `IssueNavigatorBar` and `FilterDisplayBar` fall back gracefully to internal modal state handlers without unhandled exceptions or broken workflows.

---

## 2. API Contract & Invariant Verification

- **Prop Types & Interface Parity:** All modified interfaces (`CsvImportExportModalProps`, `IssueNavigatorBarProps`, `FilterDisplayBarProps`) use strictly typed optional parameters (`format?: 'csv' | 'zip_csv'`) with safe default fallbacks.
- **REST & Modal Integration:** Modal continues to dispatch payload `{ format: exportFormat, zip_password: ... }` to `POST /api/v1/projects/{project_ref}/issues/export` or workspace fallback without breaking change.
- **Lint & Type Safety:** Verified with `tsc -b --noEmit` (0 errors) and `eslint . --max-warnings 0` (0 warnings).

---

## 3. Verdict

**`APPROVED`** (API prop contracts, modal format dispatch, backward compatibility, and layout routing verified).
