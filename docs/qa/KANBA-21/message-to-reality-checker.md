# Verification Packet: KANBA-21 (KB-P0-04)

## Target Ticket
- Ticket ID: `KANBA-21`
- Epic: `KB-E0` (Phase 0 / Foundation)
- Title: `[Phase 0 / Governance] Apache-2.0 license gate for uv.lock and pnpm-lock.yaml`
- Traceability: Spec Section 2.5 (permissive-only supply chain matrix) and Section 15.4 (gate 1)

## Summary of Implementation
1. Automated License Gate Script (`scripts/license_gate.py`):
   - Implements `classify(license_expr: str) -> Verdict` with normalization for canonical SPDX identifiers and long-name aliases.
   - Enforces fail-closed semantics: return code 0 on clean scan, 1 on copyleft/unknown violations, 3 on collector or parse errors.
   - Respects SPDX boolean algebra (`OR`, `AND`, nested parentheses).
   - Enforces non-waivable copyleft restrictions (`GPL`, `AGPL`, `SSPL` can never be waived by allowlist entries).
   - Validates dynamic linkage requirement for `LGPL*` licenses.
   - Checks root `LICENSE` precondition (must declare Apache License Version 2.0).

2. License Allowlist Specification (`license-allowlist.toml`):
   - Created with schema documentation header and zero exception entries.
   - Strict loader validation: rejects missing fields, short justifications (< 20 characters), version wildcards/ranges, and non-dynamic LGPL linkages with exit code 3.

3. Monorepo Build and Dependency Pinnings:
   - Root `pyproject.toml` and `uv.lock`: Added `pip-licenses==5.5.5` to dev dependency group.
   - Root `package.json` and `pnpm-lock.yaml`: Added `license-checker: 25.0.1` to devDependencies.
   - Root `Makefile`: Added target `license` invoking `uv run python -m scripts.license_gate`.

4. Mandatory Feature Unit Tests & Fixtures:
   - Test suite: `scripts/tests/test_license_gate.py` with 36 tests.
   - Test fixtures in `scripts/tests/fixtures/licenses/` covering positive, security copyleft, LGPL linkage, boundary expressions, and fail-closed collectors.
   - Code coverage: 97.00% branch and line coverage (exceeds 95% mandate).

5. Dependency Evaluation:
   - Authored `docs/qa/KANBA-21/dependency-evaluation.md` synthesizing formal evaluations from:
     * Test and Build Quality Engineer (`qa-eng` / Message #28)
     * Application and Supply-Chain Security Engineer (`sec-eng` / Message #29)
     * Systems and Backend Architect (`arch-reviewer` / Message #30)

## Literal Proof Artifacts in `docs/qa/KANBA-21/`
- `unit-test-results.txt`: Full pytest run showing 36 passed tests, 97.00% branch coverage, EXIT_CODE=0.
- `build-check.txt`: Full output of `make check` (ruff, mypy, lint-imports, check_no_dashes), EXIT_CODE=0.
- `license-gate-run.txt`: Full output of `make license` on real repository tree (python=54 node=1 violations=0), EXIT_CODE=0.
- `license-gate-negative.txt`: Full output of negative gate run against AGPL fixture demonstrating exit code 1.
- `dependency-evaluation.md`: Pinned package hashes, supply-chain boundaries, and tri-agent approvals.
- `git-diff.patch`: Complete unified git diff for ticket KANBA-21.
- Screenshots: N/A (Non-UI ticket).
