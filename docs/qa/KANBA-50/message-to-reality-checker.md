# Message to Reality-Checker: Forensic Verification Proof for KANBA-50

## Ticket Metadata
- **Ticket ID:** KANBA-50 (`KB-P5-27`)
- **Title:** [Phase 5 / Agent CLI] kanban-agent validate-qa-packet: local passive forensic reality-checker validator over docs/qa/<ID>/ + ticket YAML/MD
- **Epic:** KB-E15 (Agent & Automation Runtime)
- **Gates:** reality-checker
- **Screenshots:** N/A - Non-UI Ticket

---

## Executive Summary

`KANBA-50` implements the local, passive forensic `reality-checker` validation engine and CLI command `kanban-agent validate-qa-packet`.

This implementation guarantees:
1. **Zero Command/Network Execution Invariant:** Operates strictly in passive read-only audit mode over filesystem evidence. Symlinks escaping the target bundle are rejected with `PROOF_SYMLINK_ESCAPE` before reading. Special device files (FIFOs, sockets, block/char devices) are rejected with `PROOF_INVALID_ENTRY`. File reads are capped at 2 MiB per file and 16 MiB per bundle (`PROOF_BUNDLE_TOO_LARGE`). PNG screenshots are inspected via passive stdlib byte header inspection (`89 50 4E 47 0D 0A 1A 0A` + IHDR `width x height`) without decoding untrusted image payloads.
2. **Dual-Format Ticket Parsing:** Seamlessly parses both YAML ticket specifications (`examples/tickets/kan-142.yaml`) and Markdown ticket documents containing YAML frontmatter (`docs/tickets/KB-*.md`), extracting ID, title, epic, specialist gates, dependencies, and Definition of Done criteria.
3. **Seven Deterministic Structural Checks:**
   - `CORE_ARTIFACTS_PRESENT`: Verifies `git-diff.patch`, `unit-test-results.txt`, and `build-check.txt` exist and are non-empty.
   - `UNIT_TESTS_EXIT_ZERO`: Verifies zero failure/error exit markers and presence of passing summary.
   - `BUILD_CHECK_CLEAN`: Verifies zero unhandled error exit markers in build logs.
   - `UI_SPECIALIST_GATE`: Verifies `ui-specialist-review.md` has explicit APPROVED verdict and `screenshots/` has >= 3 valid PNGs across desktop, tablet, and mobile viewports (or respects non-UI ticket declaration).
   - `API_SPECIALIST_GATE`: Verifies dual approval from both API and UI specialist reviews.
   - `DEPENDENCY_EVALUATION_GATE`: Verifies `dependency-evaluation.md` references permissive license, SHA-256 hash, and specialist sign-offs.
   - `NO_RAW_SECRETS_IN_PROOF`: Scans all text artifacts via `outbound_secret_scrubber`, failing if unredacted live secrets appear, and sanitizing before LLM prompt assembly.
4. **Hard Anti-Fantasy Approval Invariant (Code-Enforced):** Even if an LLM hallucinates `readiness: READY`, the code automatically forces `readiness = NEEDS_WORK` with `policy_override = "FANTASY_APPROVAL_BLOCKED"` if ANY deterministic check failed, or grade is not A, or critical issues exist, or any DoD item is not passed.
5. **Standardized S15.3 CLI Reporting:** Emits all 4 standardized sections (Rendered Context, Tool Trace, Latency/Tokens, Schema/Policy Status) with deterministic exit codes: 0 for full pass, 2 for gate/policy failure, 1 for runtime error.

---

## Traceability & Definition of Done Checklist

| DoD Criterion | Verification Status | Forensic Evidence Reference |
| :--- | :--- | :--- |
| **File Existence & Implementation** | PASS | `agent/qa_validator/schemas.py`, `agent/qa_validator/bundle_inspector.py`, `agent/qa_validator/auditor.py`, `agent/schemas/kb-qa-verdict-v1.json`, `agent/cli_commands/validate_qa_packet.py`, `examples/qa_packets/kan-142-ready/`, `examples/qa_packets/kan-142-missing-ui-review/`, 3 cassettes under `tests/fixtures/ai/`, registered in `agent/cli.py` |
| **Unit Tests & Coverage** | PASS (97.08% >= 95%) | `docs/qa/KANBA-50/unit-test-results.txt` (42 passed in 3.10s, 0 failures) |
| **Build / Type / Lint Clean** | PASS | `docs/qa/KANBA-50/build-check.txt` (ruff 0 errors, ruff format 0 diffs, mypy 0 issues in 44 files, lint-imports 1 kept 0 broken, check_no_dashes 0 violations, make license 0 violations) |
| **CLI Validation** | PASS | `docs/qa/KANBA-50/cli-run.txt` (all 4 runs (a)-(d) executed with expected exit codes 0, 2, 2, 0) |
| **JSON Schema Validation** | PASS | `docs/qa/KANBA-50/report-sample.json` (captured `--report json` for both READY and FANTASY_APPROVAL_BLOCKED runs) |
| **Unified Git Diff** | PASS | `docs/qa/KANBA-50/git-diff.patch` |
| **Screenshots** | N/A | Non-UI Ticket (declared on ticket) |

---

## Detailed Test Case Coverage Matrix

1. **Test Case 1 (Positive S15.3 run):** `test_case_1_positive_s15_3_example_4` validates `kan-142-ready` with `qa_packet_grade_a_ready.yaml` exits 0 with all 4 sections rendered.
2. **Test Case 2 (Positive Markdown frontmatter):** `test_case_2_positive_markdown_frontmatter_ticket` validates reading `docs/tickets/KB-P5-27.md` directly.
3. **Test Case 3 (Negative specialist gates):** `test_case_3_negative_specialist_gates_enforced` validates missing `ui-specialist-review.md` triggers gate failure and `FANTASY_APPROVAL_BLOCKED`.
4. **Test Case 4 (Anti-fantasy invariant):** `test_case_4_anti_fantasy_invariant` verifies `qa_packet_fantasy_approval.yaml` downgrades to `NEEDS_WORK` with exit 2.
5. **Test Case 5 (Security symlink escape & secret leak):** `test_case_5_security_symlink_and_secret` verifies symlink `/etc/passwd` rejected with `PROOF_SYMLINK_ESCAPE` and raw tokens trigger `NO_RAW_SECRETS_IN_PROOF` and get scrubbed.
6. **Test Case 6 (Passive guarantee):** `test_case_6_passive_guarantee_zero_subprocesses` spies on subprocess invocations and verifies exactly 0 subprocess calls are made during validation; `pytest-socket` `--disable-socket` passes.
7. **Test Case 7 (Boundary & JSON Schema):** `test_case_7_boundary_and_json_schema` verifies file > 2 MiB rejected with `PROOF_BUNDLE_TOO_LARGE`, `--deterministic-only` performs 0 provider calls, and output validates against `kb-qa-verdict-v1.json`.

---

## Raw Artifacts Index (`docs/qa/KANBA-50/`)
- `git-diff.patch`: Unified git diff of branch `feat/KANBA-50`
- `unit-test-results.txt`: DoD pytest command output with line + branch coverage
- `build-check.txt`: Raw outputs of all static quality gates
- `cli-run.txt`: Raw outputs of CLI invocations (a)-(d)
- `report-sample.json`: Captured JSON report samples
- `message-to-reality-checker.md`: This verification document
