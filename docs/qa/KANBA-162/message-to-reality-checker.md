# Reality-Checker Forensic QA Packet: KANBA-162

- Ticket ID: KANBA-162
- Title: Priority #0 Broken-Main Remediation: pre-RLS test seeding + normalize_inspect lone-surrogate guard
- Author: qa-eng (Implementation), builder-w00 (Continuous Integration on main)
- Base Pre-Merge Commit: 7242005085f2ee3f2d2fb40e1ddff68bb45eb5b2
- Scope: Remediation of pre-RLS database/tests fixture bootstrapping, exclusion of non-tenant administrative tables from zero-context check, reordering of lone-surrogate guard before utf-8 byte encoding in content normalizer, and export of canonical normalize_markdown alias.

---

## 1. Verification Matrix

| Verification Dimension | Requirement | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Surrogate Guard Ordering** | Scan surrogates BEFORE raw.encode("utf-8") | Checks SURROGATE_MIN <= ord(ch) <= SURROGATE_MAX before encode(); raises ContentNormalizeError("INVALID_UTF8_SURROGATE") | PASS |
| **normalize_markdown Alias** | Canonical alias for normalize_to_markdown | Exported in kanban.content.normalize and kanban.content.__init__ | PASS |
| **Pre-RLS Test Seeding** | Superuser authority confined strictly to bootstrapping | bootstrap_workspace_admin / bind_workspace_admin runs as superuser, restores kanban_app session authorization before test assertions | PASS |
| **Zero-Context Fail-Closed** | Exclude non-tenant administrative tables | Excluded auth_provider_cards, rate_limit_buckets, local_admin_credentials, and sessions from tenant row-count queries | PASS |
| **Content Unit Tests** | >=95% coverage across kanban.content | 90/90 passed in 13.13s with 97.10% combined branch + line coverage | PASS |
| **Full Suite Health** | All repository tests pass | 953/953 passed in 49.50s (0 failures, 0 errors) | PASS |
| **Dual Specialist Gate** | UI and API Specialist Approvals | UI Specialist Gate APPROVED (@ui-specialist, Board #341); API Specialist Gate APPROVED (@arch-reviewer, Board #342) | PASS |
| **Static Analysis & Types** | Zero compiler/linter warnings | Ruff check clean, Ruff format clean, Mypy strict clean (260 source files), Lint-imports clean (2 kept, 0 broken) | PASS |
| **License Compliance** | Apache-2.0 compatibility | make license passes with violations=0 | PASS |
| **Typography Compliance** | Zero non-ASCII em/en dashes | check_no_dashes --all passes with exit code 0 | PASS |
| **Visual Proof / Screenshots** | Screenshots: N/A - Non-UI Ticket | Backend test harness and normalization remediation; no frontend UI components modified | PASS |

---

## 2. Forensic Proof Artifacts

- unit-test-results.txt: Raw output from full test suite execution verifying 953 passing tests.
- pytest-content-cov.txt: Raw output of pytest --cov=kanban.content --cov-branch --cov-fail-under=95 verifying 90 passed and 97.10% coverage.
- build-check.txt: Full static verification transcript (Ruff check, Ruff format, Mypy strict, Lint-imports, License check, and Dash check).
- quality-gates.txt: Quality gate summary artifact.
- ui-specialist-review.md: Independent review and approval by @ui-specialist (Board #341).
- api-specialist-review.md: Independent review and approval by @arch-reviewer (Board #342).
- coverage.json: Detailed line/branch coverage report for kanban.content.
- git-diff.patch: Unified git diff relative to pre-merge commit on main.

---

## 3. Specialist Gate Approvals

- UI Specialist Review: APPROVED by @ui-specialist (Board #341, docs/qa/KANBA-162/ui-specialist-review.md).
- API Specialist Review: APPROVED by @arch-reviewer (Board #342, docs/qa/KANBA-162/api-specialist-review.md).
- Automated Packet Validator: Grade: A, Readiness: READY verified.
