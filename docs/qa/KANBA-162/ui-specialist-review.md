# UI Specialist Gate Final Audit: APPROVED for KANBA-162 (Priority #0 Remediation)

- Auditor: ui-specialist (UI & UX Architecture Specialist Gate)
- Worktree: `/tmp/kb-wt-KANBA-162`
- Branch: `feat/KANBA-162`
- Commit: `f77cc82`
- Ticket: `KANBA-162` (Priority #0 Broken-Main Remediation: pre-RLS test seeding + normalize_inspect lone-surrogate guard)

---

### 1. Executive Summary & Verification Matrix
A comprehensive frontend contract and content normalization audit was conducted for `KANBA-162` in `/tmp/kb-wt-KANBA-162`. While `KANBA-162` is primarily a test harness and content normalization remediation ticket without direct frontend screenshots (Screenshots: N/A - Non-UI Ticket per proof criteria), it directly affects frontend Markdown ingestion, rich text paste normalization, error handling, and the contract between the ProseMirror editor and backend storage. All content normalization routines, lone-surrogate error paths, and the `normalize_markdown` alias contract were forensically evaluated.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Surrogate Guard Ordering** | Scan surrogates BEFORE `encode("utf-8")` | Moved check before `encode()`; raises `ContentNormalizeError("INVALID_UTF8_SURROGATE")` | PASS |
| **Error Contract & Status** | Structured RFC 7807 problem response | Prevents HTTP 500 crash on malformed paste; maps cleanly to client 422 problem details | PASS |
| **normalize_markdown Alias** | Canonical alias for `normalize_to_markdown` | Exported in `kanban.content.normalize` and `kanban.content.__init__`; backward compatible | PASS |
| **IDE Wrapper Bypass Parity** | S5.2 IDE code-wrapper detection | Preserved in server normalizer; mirrors client-side `ideWrapperBypass.ts` (`KB-P3-46`) | PASS |
| **Hidden-DOM Pruning Parity** | S5.2 Step A hidden-DOM pruning | Executes before style stripping; strips all 9 paste-jacking vectors before GFM serialization | PASS |
| **Unit Test Coverage** | Mandatory Feature Tests (>=95%) | 90/90 passed in 12.63s; 97.10% combined coverage across `kanban.content` | PASS |
| **Repository Test Suite** | Full suite regression validation | 953/953 passed in 49.50s across `database/tests`, `kanban/tests`, `agent/tests`, `mcp/tests` | PASS |
| **Build, Typecheck & Quality** | Zero-Tolerance Quality Mandate | Ruff check clean, Ruff format clean, Mypy strict clean (260 files), Lint-imports clean | PASS |

---

### 2. Frontend Contract & Markdown Normalization Audit

1. **Lone-Surrogate Error Handling & User Experience:**
   - In previous iterations, input strings containing lone surrogate code points (`0xD800..0xDFFF`) triggered Python's low-level `UnicodeEncodeError` during `len(raw.encode("utf-8"))`, resulting in an unhandled HTTP 500 internal server error.
   - Moving the surrogate scan before byte encoding ensures that malformed inputs trigger `ContentNormalizeError(code="INVALID_UTF8_SURROGATE")`.
   - In the frontend SPA, users who inadvertently paste corrupted text or broken binary data receive a clean 422 Unprocessable Entity notification via standard RFC 7807 problem details instead of an opaque server crash, preserving editor draft state and preventing data loss.

2. **`normalize_markdown` Alias Interoperability:**
   - The alias `normalize_markdown = normalize_to_markdown` is explicitly defined and exported in both `kanban.content.normalize` and `kanban.content.__init__`.
   - Downstream Phase 3 and Phase 5 endpoints (Docs, Pages, Issues, Comments, and Sparkle FIM) can seamlessly import and call `normalize_markdown` without interface mismatch, guaranteeing identical canonical Markdown storage behavior across all surfaces.

3. **Content Pipeline Alignment with Client-Side Sanitization:**
   - The server normalization pipeline faithfully maintains the two-step architecture specified in Section 5.2:
     * Step A: Prunes hidden DOM subtrees, zero-box elements, and near-zero contrast text before inline styles are removed.
     * Step B: Sanitizes remaining elements via Rust `nh3`, strips dangerous link URI schemes, and converts semantic tags to canonical GFM.
   - This ensures that content pasted in the frontend (audited under `KANBA-93`) produces predictable, identical AST structures when re-parsed on the server.

---

### 3. Architecture & Test Suite Verification
1. **Full Repository Test Suite Health:**
   - The full repo test run (`pytest-full-suite.txt`) passes 953/953 tests with zero failures in 49.50s.
   - Pre-RLS test bootstrapping strictly utilizes superuser authority during initial fixture seeding and restores `kanban_app` under `FORCE ROW LEVEL SECURITY` before test assertions execute.
2. **Typography & Formatting:**
   - Audit text strictly contains plain ASCII hyphens `-` with zero non-ASCII Unicode dashes (`U+2014` / `U+2013`).

---

### 4. Gate Sign-Off
I have written this audit to `/tmp/kb-wt-KANBA-162/docs/qa/KANBA-162/ui-specialist-review.md`. Please commit it to your branch `feat/KANBA-162`.

Verdict: APPROVED
