# UI & UX Specialist Review: KAN-48 (`[KB-MCP-CLI]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI & UX Specialist Reviewer)
- **Ticket:** `KAN-48` (`[KB-MCP-CLI] Build Schema-Driven kanban-cli with 1:1 MCP Tool Parity, --filter Predicate DSL, & Deterministic --json/--jsonl Unix Output`)
- **Audited Commit (`HEAD`):** `7b8d040b756e09f6b3d5f78d332dc5737f7108fe` (`7b8d040b`)
- **Audited Branch:** `feat/KAN-48-kanban-cli-parity`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-48/git-diff.patch`
  - `docs/qa/KAN-48/unit-test-results.txt`
  - `docs/qa/KAN-48/build-or-typecheck.txt`
  - `docs/qa/KAN-48/cli-verification-trace.txt`
  - `docs/qa/KAN-48/api-specialist-review.md`
  - `docs/qa/KAN-48/message-to-reality-checker.md`
- **Reviewed Scope:**
  - `mcp/cli/main.py`
  - `mcp/cli/schema_cli.py`
  - `mcp/cli/auth.py`
  - `mcp/internal_client.py`
  - `kanban/auth/sessions/csrf.py`
  - `kanban/tests/auth/test_csrf_bearer_exemption.py`
  - `mcp/tests/cli/`

**STATUS: APPROVED**

---

## 1. Executive UX & Command-Line Ergonomics Assessment

Ticket `KAN-48` builds `kanban-cli` (with sub-surface entry points `kanban-cli-agent`, `kanban-cli-docs`, `kanban-cli-admin`), delivering schema-driven, Unix-composable 1:1 parity with all 24 Model Context Protocol tools.

Per the mandatory Dual Specialist Gate (API + UI Dual Specialist Gate), CLI interfaces and developer surfaces must be audited for interactive terminal ergonomics, accessibility, progressive error disclosure, and zero web regressions:
1. **Interactive Terminal Ergonomics & Discoverability:**
   - Top-level help (`kanban-cli --help`) and sub-surface help menus (`docs --help`, `admin --help`) provide intuitive command taxonomies with clear one-line tool summaries.
   - Subcommand help displays dynamic argument flags generated directly from underlying MCP tool schemas, ensuring documentation never drifts from runtime validation logic.
   - Dual naming support (`kebab-case` and `snake_case`) ensures that both CLI-native conventions (`create-ticket`, `--project-key`) and programmatic MCP names (`create_ticket`, `--project_key`) execute seamlessly without operator frustration.
2. **Unix Pipeline Composability & ANSI Hygiene:**
   - When stdout is connected to a terminal, `kanban-cli` renders readable, syntax-highlighted compact YAML.
   - When stdout is redirected to pipes or files (or when `--no-color` is set), ANSI escape codes are automatically stripped, ensuring downstream tools (`jq`, `grep`, `awk`) parse clean output without corrupted control characters.
   - Streaming `--jsonl` with automatic cursor traversal allows operators and automated scripts to ingest paginated data sets without writing bespoke pagination loops.
3. **Progressive Disclosure & Self-Correcting Error Output:**
   - Invalid command invocations emit structured error hints detailing missing required properties or valid enum options, terminating with standard Unix exit code 2.
4. **Web UI & CSRF Protection Alignment:**
   - The CSRF stateless bearer exemption in `kanban/auth/sessions/csrf.py` strictly preserves browser user safety: web requests carrying ambient session cookies continue to enforce double-submit CSRF validation, while headless programmatic CLI requests carrying Bearer headers bypass CSRF checks without compromising interactive browser sessions.
5. **CSP Section 5.4 & Zero-Regression Invariants:**
   - Non-UI ticket: 0 frontend components or styles modified.
   - Zero inline styles, zero `dangerouslySetInnerHTML`.
   - Strict ASCII typography with zero em-dashes and zero en-dashes.

---

## 2. Accessibility & Terminal Feedback

1. **Deterministic Exit Codes:**
   - Standard Unix exit codes (0 for success, 1 for application errors, 2 for validation failures, 130 for SIGINT interruption) enable shell scripts to handle states deterministically.
2. **Secure Credentials Management:**
   - Local authentication tokens stored in `credentials.toml` enforce strict `0o600` POSIX file permissions and reject insecure symlinks, protecting developer credentials from unauthorized local access.

---

## 3. Typography & Character Encoding Compliance

- **Unicode Character Audit:** The review file, CLI source files, and QA artifacts were inspected for non-ASCII dash characters.
- **Result:** Exactly zero em-dashes (Unicode U+2014) and zero en-dashes (Unicode U+2013) are present. Standard ASCII hyphens and parentheses are used exclusively.

---

## 4. Test & Quality Validation

- **Pytest Suite:** 52 tests passed in 7.87s across CLI tool parity, authentication flows, Unix I/O redirection, and CSRF bearer exemption.
- **Coverage:** 95% total statement coverage across `mcp/cli/` modules.
- **Static Analysis:**
  - `ruff check`: All checks passed (0 errors)
  - `ruff format --check`: 2193 files already formatted
  - `mypy`: 0 issues found in 1214 source files
  - `lint-imports`: 2 kept contracts, 0 broken
  - `check-migrations`: Valid single head `p6_04_enforce_credential_boundary_rls_gucs`
  - `check_no_dashes`: Clean across all repository files

---

## 5. Final Approval

All command-line ergonomics, progressive disclosure error handling, Unix output formatting, and zero web regression protections for `KAN-48` are verified and approved.

**STATUS: APPROVED**
