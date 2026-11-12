# Verification Proof and Audit Manifest for Reality-Checker

**Ticket:** `KANBA-15` (`KB-P0-01`)
**Title:** `[Phase 0 / Repo] Monorepo uv workspace skeleton & module manifests`
**Author:** `builder-w00` (Wave W00 Implementation Author)
**Screenshots:** N/A - Non-UI Ticket (Headless repository infrastructure bootstrap)
**Encoding Mandate:** Plain ASCII hyphens (`-`) only; zero `U+2014` or `U+2013` dashes.

---

## 1. Important Context: Board Angle-Bracket Import Demangling

When Plane imported the original ticket markdown into its HTML issue description, angle brackets (`<...>`) were stripped by Plane's HTML sanitization pipeline (e.g. `>=3.12,<3.13` appeared truncated or stripped in the web UI, `<module>/GEMINI.md` lost its placeholder, etc.).
The authoritative, unmangled source specification for this ticket is located at:
`docs/tickets/KB-P0-01.md`

All implementation actions, configuration declarations, and test verifications were executed against `docs/tickets/KB-P0-01.md`.

---

## 2. Definition of Done Traceability Matrix

| Scoped DoD Requirement | Verifying Artifact | Line / Evidence Reference | Status |
| :--- | :--- | :--- | :--- |
| **File Existence & Implementation:** All Target Files exist; `<module>/AGENTS.md` are relative symlinks to `GEMINI.md`; root `pyproject.toml` contains `[tool.uv.workspace]` members `database`, `kanban`, `mcp`, `agent` and `layers` import-linter contract. | `docs/qa/KANBA-15/tree.txt`<br>`tests/test_workspace_layout.py` | `tree.txt`: lines 5, 15, 25, 35 (`AGENTS.md -> GEMINI.md`).<br>`pyproject.toml`: lines 12-25. | **PASS** |
| **Lockfile:** `uv lock --check` / `uv lock --locked` exits `0`; `uv.lock` is committed. | `docs/qa/KANBA-15/build-check.txt` | `build-check.txt`: lines 5-8 (`uv lock --locked` exited 0). Lines 10-18 document `uv lock --check` in uv 0.5.4. | **PASS** |
| **Unit Tests Implemented & Passing:** `uv run pytest database/tests kanban/tests mcp/tests agent/tests tests/test_workspace_layout.py -q --cov=database --cov=kanban --cov=mcp --cov=agent --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with `0` failures and `>=95%` branch coverage. | `docs/qa/KANBA-15/unit-test-results.txt` | `unit-test-results.txt`: lines 7-26 (9 passed, 100.00% coverage, 0 failures, Exit Code: 0). | **PASS** |
| **Build / Type / Lint Clean:** `uv sync --locked` exits `0`; `uv run lint-imports` exits `0` and reports `1 kept, 0 broken`; `cd /tmp && uv run --project /home/adamoutler/kanban python -c "import database, kanban, mcp, agent"` exits `0`. | `docs/qa/KANBA-15/build-check.txt` | `build-check.txt`: lines 20-24 (`uv sync --locked` exit 0), lines 26-50 (`lint-imports` exit 0, 1 kept, 0 broken), lines 52-55 (external `/tmp` import exit 0). | **PASS** |
| **No dash characters:** `grep -rn $'\u2014\|\u2013' database kanban mcp agent NOTICE` returns no matches. | `docs/qa/KANBA-15/build-check.txt` | `build-check.txt`: lines 57-59 (Exit code 1, zero matches found). | **PASS** |
| **Supply-Chain Dependency Sign-Off:** Permissive licenses, exact pinned versions and sha256 digests in `uv.lock`, and sign-offs from >=1 architect and >=2 engineers. | `docs/qa/KANBA-15/dependency-evaluation.md` | `dependency-evaluation.md`: Section 1 (cryptographic hashes), Section 2 (alternatives), Section 3.1 (`arch-reviewer`), Section 3.2 (`sec-eng`), Section 3.3 (`qa-eng`). | **PASS** |
| **Git Diff Complete:** Unified git diff captures 100% of ticket changes relative to initial baseline commit. | `docs/qa/KANBA-15/git-diff.patch` | Captures `.python-version`, `pyproject.toml`, `uv.lock`, `NOTICE`, all module manifests, code, and test files. | **PASS** |

---

## 3. Git Baseline & Change Audit

- **Baseline SHA:** `73f37dbe99008a02f7c1a1f5ddccc2cf59557c60` (`chore: initial spec and agent manifests`)
- **Git Patch:** `docs/qa/KANBA-15/git-diff.patch` contains the complete diff between the baseline commit and the workspace files.
- **Repository Hygiene:** Working tree is 100% clean on `main` branch.
