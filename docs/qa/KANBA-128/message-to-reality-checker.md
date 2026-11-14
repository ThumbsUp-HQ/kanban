# Message to Reality-Checker: KANBA-128 (KB-P6-02) Verification Proof Packet

- Ticket: KANBA-128 (KB-P6-02: [Phase 6 / Cutover] Cutover runbook (docs/CUTOVER.md) & scripted parity + zero-invalid-link verifier)
- Implementation Author: builder-17
- Worktree: /tmp/kb-wt-KANBA-128
- Branch: feat/KANBA-128
- Status: Ready for Forensic QA Audit & Main Merge

---

## 1. Executive Summary

This packet delivers the scripted cutover verification engine, operator CLI, and cutover runbook for thumbs-up-kanban:
1. `kanban/importer/cutover_verifier.py`: Verification engine implementing all 6 non-bypassable checks:
   - Check 1 (`entity_count_and_key_parity`): Verifies 1:1 entity parity across issues, states, cycles, modules, comments, and asserts issue_seq_counter >= max(sequence_id) without gaps or missing keys.
   - Check 2 (`zero_invalid_object_links`): Verifies audit_object_links() == 0 and FLAGGED_INVALID rows == 0.
   - Check 3 (`activity_hash_chain_intact`): Verifies verify_activity_chain() across all monthly partitions.
   - Check 4 (`canonical_markdown_purity`): Asserts 0 *_html/*_ast columns in database schema and scans imported markdown outside code fences for unconverted block/script HTML residue.
   - Check 5 (`qa_proof_bundle_continuity`): Verifies completed issues or issues referencing docs/qa/ have non-empty git-diff.patch, unit-test-results.txt, and build-check.txt.
   - Check 6 (`rls_enforcement_active`): Asserts relrowsecurity and relforcerowsecurity on all public tenant tables and verifies kanban_app has rolsuper=false and rolbypassrls=false.
2. `kanban/cli/verify_cutover.py`: Subcommand `kanban-ctl cutover verify` supporting `--bundle-dir`, `--workspace`, `--project`, `--qa-root`, `--pre-cutover-exempt-keys`, and `--json-out`. Exits 0 on all pass, 2 on check failure, 1 on runtime error.
3. `docs/CUTOVER.md`: Comprehensive 7-phase operator runbook with < 5 minute rollback plan and zero unicode dashes.
4. Test suite: 14 test cases covering positive verification, edge cases, parity failures, corrupted bundles, invalid links, markdown purity, and CLI execution.

---

## 2. Verification Proof Matrix

| Dimension | Proof File | Observed Status |
| :--- | :--- | :--- |
| **Unit & Integration Tests** | `docs/qa/KANBA-128/unit-test-results.txt` | 14/14 passed in 2.69s across verifier and CLI |
| **Coverage Gate** | `docs/qa/KANBA-128/unit-test-results.txt` | 95.63% total coverage (cutover_verifier: 95%, verify_cutover: 97%) |
| **Static Code Quality** | `docs/qa/KANBA-128/build-check.txt` | Ruff clean, format clean (379 files), Mypy strict clean (2 source files), Import Linter clean (2 kept, 0 broken) |
| **Supply Chain & Typography** | `docs/qa/KANBA-128/build-check.txt` | license_gate 0 violations (python=115, node=1), check_no_dashes 0 violations |
| **CLI Host Proof** | `docs/qa/KANBA-128/cli-run.txt` | Captured passing run (exit 0) and simulated failure run (exit 2) |
| **JSON Audit Output** | `docs/qa/KANBA-128/cutover-report.json` | Full structured JSON report for passing fixture run |
| **Specialist Gates** | Board consultations #890, #892 | Systems Architect (@arch-reviewer) confirmed semantics |
| **Automated QA Gate** | `validate-qa-packet` | Grade A, READY |

---

Ready for passive forensic verification by @reality-checker upon main merge by @builder-w00.
