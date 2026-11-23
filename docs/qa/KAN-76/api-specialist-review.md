# API & Security Specialist Review: KAN-76 (`[KB-DEVSECOPS-ATTEST-01]`)

- **Reviewer Persona:** `security-engineer` / `backend-architect` / `api-tester` (API & Security Specialist Reviewer)
- **Ticket:** `KAN-76` (`[KB-DEVSECOPS-ATTEST-01] Add Cryptographic Commit Signature (SSH/GPG/Sigstore) & Live CI / SLSA Attestation Workflow Gates`)
- **Audited Branch:** `feat/KAN-76`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-76/git-diff.patch`
  - `docs/qa/KAN-76/contract-sample.json`
  - `docs/qa/KAN-76/unit-test-results.txt`
  - `docs/qa/KAN-76/build-check.txt`
  - `docs/qa/KAN-76/message-to-reality-checker.md`
- **Reviewed Source & Test Files:**
  - `database/migrations/versions/p6_11_git_truststore_and_attestations.py`
  - `database/migrations/sql/p6_11_git_truststore_and_attestations.up.sql`
  - `database/migrations/sql/p6_11_git_truststore_and_attestations.down.sql`
  - `database/models/repo_binding.py`
  - `database/models/repos.py`
  - `database/models/workflow.py`
  - `kanban/repos/signature_verifier.py`
  - `kanban/workflows/attestation_gate.py`
  - `kanban/workflows/gate_types.py`
  - `kanban/workflows/engine.py`
  - `kanban/issues/proof.py`
  - `agent/tools/repo_tools.py`
  - `kanban/tests/repos/test_commit_signature_verifier.py`
  - `kanban/tests/workflows/test_ci_and_slsa_attestation_gates.py`
  - `agent/tests/tools/test_repo_tools_signatures.py`
  - `database/tests/test_p1_17_models.py`
  - `database/tests/migrations/test_p6_11_git_truststore_and_attestations_migration.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-76` introduces cryptographic commit signature verification (SSH, GPG, and Sigstore/Cosign), live CI pipeline status gates (GitHub Check Runs, GitLab Pipelines, Forgejo Commit Statuses), and DSSE in-toto SLSA v1.0 provenance attestation gates into the workflow transition engine.

The changes address four core architectural challenges:
1. **Zero-Shell Subprocess Execution:** `kanban/repos/signature_verifier.py` interacts directly with the local read-only bare git mirror using explicit `argv` argument lists via `asyncio.create_subprocess_exec` and `execve`. It completely rejects `shell=True`, eliminating shell-injection attack vectors. Temporary keyrings and allowedSigners files are created with mode `0o600` in dedicated temporary directories and wiped in `finally:` blocks.
2. **SSRF Mitigation with DNS-Pinned Transport:** Live CI check run queries via `kanban/workflows/attestation_gate.py` pass through the hardened `kanban/security/ssrf.py` stack using `resolve_and_select_pinned_ip` and `PinnedIPTransport`. DNS resolution is validated against private/loopback/cloud metadata IP blocks before connection, and the TLS SNI header matches the original hostname.
3. **Air-Gap Mode Fail-Closed Invariant:** When `settings.air_gap_mode` is enabled, the live CI attestation gate halts immediately and raises HTTP 409 `AIR_GAP_EGRESS_BLOCKED`, preventing unauthorized outbound network egress attempts.
4. **Deterministic Workflow Transition Gates:** Transition engine (`kanban/workflows/engine.py`) evaluates `commit_signature`, `ci_check_run`, and `slsa_provenance` synchronously or asynchronously during issue transitions. Failures halt transitions immediately with HTTP 409 `PROVENANCE_ATTESTATION_FAILED` and clear diagnostic context.
5. **Database Model Parity & Row Level Security:** Migration `p6_11_git_truststore_and_attestations` provisions `commit_attestations` with strict `FORCE ROW LEVEL SECURITY` and tenancy binding. ORM models in `database/models/repo_binding.py` maintain full parity with the migration schema.

---

## 2. Security Architecture & Threat Model Audit

### 2.1 Subprocess Injection & Execution Safety
- `kanban/repos/signature_verifier.py`:
  - Uses `asyncio.create_subprocess_exec("git", *args, ...)` exclusively.
  - Zero usage of `shell=True` or string interpolation into shell commands.
  - In `_verify_ssh`: temporary `allowed_signers` file is written with mode `0o600` via `tempfile.NamedTemporaryFile`. Git config override `-c gpg.ssh.allowedSignersFile=...` is passed as a distinct argument in `argv`.
  - In `_verify_gpg`: an ephemeral `GNUPGHOME` directory is created via `tempfile.TemporaryDirectory` with mode `0o700`. The public armored keys are imported via `gpg --batch --import`, and git is run with `GNUPGHOME` strictly scoped to that ephemeral directory.
  - In `_verify_sigstore`: uses `cosign verify-blob` with `--certificate-identity` and `--certificate-oidc-issuer` in distinct `argv` parameters.
  - Tag verification: supports both lightweight commits (`git verify-commit`) and annotated tags (`git verify-tag`), avoiding type confusion errors.

### 2.2 SSRF & Network Transport Integrity
- `kanban/workflows/attestation_gate.py`:
  - Parses CI run URLs strictly with `urllib.parse.urlsplit` and verifies scheme is `https`.
  - Validates target host against DNS-pinning resolver `resolve_and_select_pinned_ip`. Private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.169.254) are rejected with `SSRF_HOST_BLOCKED`.
  - HTTP requests are dispatched over `httpx.AsyncClient(transport=PinnedIPTransport(pinned_ip, host), timeout=10.0)`.
  - Air-gap setting `settings.air_gap_mode` check takes precedence prior to DNS resolution, immediately raising `AIR_GAP_EGRESS_BLOCKED`.

### 2.3 DSSE in-toto SLSA v1.0 Provenance Parser
- Supports both raw in-toto Statement v1 format (`_type: "https://in-toto.io/Statement/v1"`, `predicateType: "https://slsa.dev/provenance/v1"`) and DSSE envelopes (`payloadType: "application/vnd.in-toto+json"`).
- Normalizes base64-encoded payloads safely.
- In `_build_pae`: implements the Pre-Authentication Encoding (PAE) format according to DSSE specification: `PAE(payload_type, payload) = "DSSEv1" + len(payload_type) + payload_type + len(payload) + payload`.
- Validates subject digest sha256 against `expected_sha`. Tampered or mismatched digests result in immediate rejection.

### 2.4 Workflow Engine Integration
- `kanban/workflows/gate_types.py` registers:
  - `GateType.COMMIT_SIGNATURE = "commit_signature"`
  - `GateType.CI_CHECK_RUN = "ci_check_run"`
  - `GateType.SLSA_PROVENANCE = "slsa_provenance"`
- `kanban/workflows/engine.py` invokes `_execute_deterministic_gate` during transition evaluations.
- When an attestation gate fails, it raises `ProblemException(status=409, code="PROVENANCE_ATTESTATION_FAILED", detail=...)`.

---

## 3. Database Schema & Migration Review

- Migration: `database/migrations/versions/p6_11_git_truststore_and_attestations.py`
  - Drops and updates constraints `ck_workflow_hook_invocations_kind` and auto-generated `workflow_hook_invocations_hook_kind_check` to permit new hook kinds.
  - Adds truststore columns to `project_repo_bindings`:
    - `ssh_allowed_signers TEXT NULL`
    - `gpg_trusted_armored_keys TEXT NULL`
    - `sigstore_trusted_identities_json JSONB NOT NULL DEFAULT '[]'::jsonb`
  - Creates table `commit_attestations` with columns `(id, workspace_id, repo_binding_id, commit_sha, sig_scheme, signer_identity, key_fingerprint, verified, verified_at, details_json)`.
  - Enables and forces Row Level Security (`ALTER TABLE commit_attestations ENABLE ROW LEVEL SECURITY; ALTER TABLE commit_attestations FORCE ROW LEVEL SECURITY;`).
  - Migration downgrade test verified clean upgrade -> downgrade -> re-upgrade cycle.

---

## 4. Test Coverage & Verification

All test suites execute hermetically against local test databases and fixtures:
1. `kanban/tests/repos/test_commit_signature_verifier.py`: 8 passed (covers SSH valid/invalid/missing/tampered, GPG valid/invalid/missing, Sigstore identity matching, and tag verification).
2. `kanban/tests/workflows/test_ci_and_slsa_attestation_gates.py`: 8 passed (positive multi-gate pass, negative security failures for unsigned commits, red CI, mismatched SLSA digests, air-gap egress blocking, and direct verifier tests).
3. `agent/tests/tools/test_repo_tools_signatures.py`: 2 passed (verifies `%G?`, `%GS`, `%GK` output formatting and signature extraction in `BareGitRepoToolkit.repo_git_log`).
4. `database/tests/test_p1_17_models.py`: 6 passed (verifies ORM schema parity and roundtrip persistence for `CommitAttestation`).
5. `database/tests/migrations/test_p6_11_git_truststore_and_attestations_migration.py`: 1 passed (full migration upgrade/downgrade validation).

Total: 25/25 tests passing. Statement and branch coverage on touched modules exceeds 95%. Static analysis, type checking (mypy), and no-dashes checks pass with 0 errors.

**Recommendation:** Proceed with QA packet sign-off and ticket completion.
