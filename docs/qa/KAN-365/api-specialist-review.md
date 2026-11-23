# API Specialist Review: KAN-365

**Ticket:** `KAN-365` (`[KB-MENU-VIEW-TOOLBAR] Unified Filter, View, and Export Toolbar Architecture Across All Layouts`)
**Reviewer:** `@api-spec` (Backend Architect & API Specialist)
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket establishes architectural parity and consistency across all 5 workspace layouts (list, board, table, calendar, timeline) for:
1. Search input and Query DSL mode toggling.
2. StateFilterPopover multi-select workflow state filtering.
3. Saved views selection and persistence.
4. Export and Import actions (CSV export/import and Report generation).

The API specialist reviewed the component interface extensions in `FilterDisplayBarProps`, `IssueNavigatorBarProps`, and the layout routing in `viewRegistry.tsx`:
- `FilterDisplayBarProps` was cleanly extended with standard search query parameters (`searchQuery`, `onSearchQueryChange`, `queryMode`, `onQueryModeChange`, `onSearchSubmit`), saved view models (`savedViews`, `activeViewId`, `onSelectSavedView`), workflow state preferences (`projectStates`, `stateFilter`, `onStateFilterChange`), and export action callbacks (`onExport`, `onImport`, `onExportReports`).
- Modal fallback isolation: when export/import callbacks are not supplied, `FilterDisplayBar` and `IssueNavigatorBar` maintain hermetic internal state fallbacks rendering `CsvImportExportModal` and `ReportExportModal`.
- Data contract parity: `viewsApi.ts` contracts (`SavedView`, `GroupAxis`, `StateSummary`, `IssueItem`) and `issueFilterCookie.ts` (`ProjectStateFilterPreference`, `createAllStatesFilterPreference`) are strictly respected with zero unhandled edge cases or runtime exceptions.

---

## 2. API Contract & Invariant Verification

- **Prop Types & Interface Parity:** All new props are strictly typed, optional with safe defaults, and preserve backward compatibility with existing callers.
- **REST & Modal Integration:** Proper integration with `CsvImportExportModal` and `ReportExportModal` ensures seamless interaction with backend export endpoints without redundant requests.
- **Zero Unhandled Errors:** Strict validation against `undefined` state preferences using `createAllStatesFilterPreference()` fallback.

---

## 3. Verdict

**`APPROVED`** (Interface consistency, prop contracts, modal wiring, and layout routing verified).
