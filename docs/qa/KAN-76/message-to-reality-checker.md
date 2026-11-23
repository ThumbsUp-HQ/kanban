# Reality-Checker Verification Packet: KAN-76 (`[KB-DEVSECOPS-ATTEST-01]`)

## 1. Ticket Overview
- **Ticket ID**: `KAN-76`
- **Spec Section**: `[KB-DEVSECOPS-ATTEST-01]`
- **Title**: `[KB-DEVSECOPS-ATTEST-01] Add Cryptographic Commit Signature (SSH/GPG/Sigstore) & Live CI / SLSA Attestation Workflow Gates`
- **Git Branch**: `feat/KAN-76`
- **Browser Screenshots**: `N/A - Non-UI Ticket (Cryptographic Attestation, Backend Security & Workflow Gates)`
- **Worktree**: `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan76-5d4f2f85`

---

## 2. Requirements & Verification Traceability Matrix

### Problem 1: Project Git Truststore & Commit/Tag Signature Verifier
- **Requirements**:
  - Add `ssh_allowed_signers TEXT NULL`, `gpg_trusted_armored_keys TEXT NULL`, and `sigstore_trusted_identities_json JSONB NOT NULL DEFAULT '[]'::jsonb` to `project_repo_bindings`.
  - Create table `commit_attestations` with `FORCE ROW LEVEL SECURITY`.
  - Implement zero-shell `kanban/repos/signature_verifier.py` verifying `SSH`, `GPG`, and `Sigstore` signatures on commits and annotated tags.
  - Extend `BareGitRepoToolkit.repo_git_log` in `agent/tools/repo_tools.py` with `%G?`, `%GS`, `%GK` signature metadata.
- **Evidence**:
  - Migration file: `database/migrations/versions/p6_11_git_truststore_and_attestations.py`
  - SQL files: `database/migrations/sql/p6_11_git_truststore_and_attestations.up.sql` and `.down.sql`
  - ORM Models: `database/models/repo_binding.py`, `database/models/repos.py`, and `database/models/workflow.py`
  - Zero-shell verifier: `kanban/repos/signature_verifier.py` (uses direct `argv` array via `asyncio.create_subprocess_exec`, zero `shell=True`).
  - Repo toolkit: `agent/tools/repo_tools.py` lines 327-375 formatting with `%G?%x09%GS%x09%GK` and parsing signature status into `sig_status`, `signer`, and `key_fingerprint`.
  - Unit tests:
    - `kanban/tests/repos/test_commit_signature_verifier.py` (8/8 passed)
    - `agent/tests/tools/test_repo_tools_signatures.py` (2/2 passed)
    - `database/tests/test_p1_17_models.py` (6/6 passed)
    - `database/tests/migrations/test_p6_11_git_truststore_and_attestations_migration.py` (1/1 passed)

### Problem 2: Live CI Check-Run & DSSE / in-toto SLSA v1.0 Provenance Verifier
- **Requirements**:
  - Implement `kanban/workflows/attestation_gate.py` with DNS-pinned SSRF protection (`resolve_and_select_pinned_ip` + `PinnedIPTransport`).
  - Verify GitHub Check Runs / Workflow Runs, GitLab Pipelines, and Forgejo Commit Statuses.
  - Implement offline DSSE in-toto Statement v1 / SLSA v1.0 provenance parser and verify subject digest matches `head_sha`.
  - Fail closed with `409 AIR_GAP_EGRESS_BLOCKED` when `air_gap_mode=True`.
- **Evidence**:
  - Attestation gate module: `kanban/workflows/attestation_gate.py`
  - SSRF protection: lines 89-137 using `resolve_and_select_pinned_ip` and `PinnedIPTransport`.
  - Air gap enforcement: lines 84-88 raising `ProblemException(409, "AIR_GAP_EGRESS_BLOCKED", ...)` when `settings.air_gap_mode` is true.
  - DSSE parser & PAE builder: lines 294-430 parsing in-toto Statement v1 and DSSE envelopes, computing PAE bytes, and validating sha256 subject digests.
  - Unit tests: `kanban/tests/workflows/test_ci_and_slsa_attestation_gates.py` (8/8 passed).

### Problems 3 & 4: Deterministic Workflow Transition Gate Types
- **Requirements**:
  - Register deterministic gate types: `commit_signature`, `ci_check_run`, `slsa_provenance`.
  - Integrate into `TransitionEngine` in `kanban/workflows/engine.py`.
  - Block transitions with `409 PROVENANCE_ATTESTATION_FAILED` when unsigned, forged, red in CI, or digest mismatched.
- **Evidence**:
  - Gate types: `kanban/workflows/gate_types.py` (registered in `GateType` enum and `deterministic_gate_types` set).
  - Transition request schema: `kanban/api/v1/transitions.py` accepting `verification_proof: dict[str, Any] | None = None`.
  - Transition engine: `kanban/workflows/engine.py` invoking `_execute_deterministic_gate` during transition evaluations.
  - Test suites:
    - `test_case_1_positive_signed_commit_passing_ci_valid_slsa` (passed)
    - `test_case_2_negative_security_failures` (passed: covers unsigned commit rejection, red CI rejection, SLSA digest mismatch rejection, and air gap egress blocking).

---

## 3. Test & Verification Summary

1. **Unit & Integration Tests**:
   - `kanban/tests/repos/test_commit_signature_verifier.py`: 8 passed
   - `kanban/tests/workflows/test_ci_and_slsa_attestation_gates.py`: 8 passed
   - `agent/tests/tools/test_repo_tools_signatures.py`: 2 passed
   - `database/tests/test_p1_17_models.py`: 6 passed
   - `database/tests/migrations/test_p6_11_git_truststore_and_attestations_migration.py`: 1 passed
   - **Total**: 25 passed in under 4 seconds. Statement and branch coverage on touched modules: **96%**.
2. **Static Analysis & Linting**:
   - `make check`:
     - Ruff check: All checks passed!
     - Ruff format: 2281 files already formatted
     - Mypy: Success: no issues found in 1269 source files
     - Import contracts: 2 kept, 0 broken
   - `uv run kanban-ctl db check-migrations --static-only`: All 72 migrations valid, single head `p6_11_git_truststore_and_attestations`.
   - `uv run python -m scripts.check_no_dashes --all`: Zero em-dash or en-dash errors across all files.

---

## 4. QA Artifact Checklist
- `docs/qa/KAN-76/git-diff.patch` (full unified git diff)
- `docs/qa/KAN-76/unit-test-results.txt` (full pytest logs with coverage)
- `docs/qa/KAN-76/build-check.txt` (clean lint/format/mypy/contracts/migrations log)
- `docs/qa/KAN-76/contract-sample.json` (approved vs 409 error payloads)
- `docs/qa/KAN-76/api-specialist-review.md` (Security/API review, Status: APPROVED)
- `docs/qa/KAN-76/ui-specialist-review.md` (UI/UX review, Status: APPROVED)
- `docs/qa/KAN-76/message-to-reality-checker.md` (this file)
- `docs/qa/KAN-76/changed-files-manifest.txt` (SHA256 checksums verified with sha256sum -c)
