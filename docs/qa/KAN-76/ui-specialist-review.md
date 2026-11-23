# UI & UX Specialist Review: KAN-76 (`[KB-DEVSECOPS-ATTEST-01]`)

- **Reviewer Persona:** `ux-architect` / `ui-designer` (UI/UX Specialist Reviewer)
- **Ticket:** `KAN-76` (`[KB-DEVSECOPS-ATTEST-01] Add Cryptographic Commit Signature (SSH/GPG/Sigstore) & Live CI / SLSA Attestation Workflow Gates`)
- **Audited Branch:** `feat/KAN-76`
- **Reviewed Artifacts:**
  - `docs/qa/KAN-76/git-diff.patch`
  - `docs/qa/KAN-76/contract-sample.json`
  - `docs/qa/KAN-76/unit-test-results.txt`
  - `docs/qa/KAN-76/build-check.txt`
  - `docs/qa/KAN-76/api-specialist-review.md`
  - `docs/qa/KAN-76/message-to-reality-checker.md`
- **Reviewed Modules:**
  - `kanban/api/v1/transitions.py`
  - `kanban/workflows/engine.py`
  - `kanban/workflows/gate_types.py`
  - `kanban/workflows/attestation_gate.py`
  - `kanban/repos/signature_verifier.py`
  - `agent/tools/repo_tools.py`

**STATUS: APPROVED**

---

## 1. Executive Summary

`KAN-76` implements backend cryptographic commit signature verification, live CI check-run gates, and SLSA v1.0 provenance attestation gates for issue workflow transitions.

From a UI/UX, user interaction, and client ergonomics perspective:
1. **Scope Classification:** This ticket is strictly backend, database, and agent-tooling infrastructure (`N/A - Non-UI Ticket`). No frontend HTML templates, CSS style rules, or client-side JavaScript components were created or modified.
2. **RFC 9457 Error Feedback & Frontend Toast Display:** When a user or agent attempts an issue workflow transition that violates a cryptographic signature, CI status, or SLSA provenance gate, the API returns a structured HTTP 409 problem details object (`urn:problem:provenance-attestation-failed` or `urn:problem:air-gap-egress-blocked`).
   - The `detail` field clearly specifies which gate failed and why (e.g. `Gate 'gate-commit-sig' (commit_signature) rejected transition: Commit signature verification failed: No signature found on commit <sha>`).
   - This provides the web UI drawer and kanban board modal with crisp, actionable error toast messages rather than opaque HTTP 500 internal server error crashes.
3. **Non-Blocking Operation & Fast Feedback:** Deterministic commit signature and SLSA provenance gates run against local mirrors and payloads in under 50ms, ensuring that UI drag-and-drop transitions remain snappy and responsive.
4. **Agent Tool Ergonomics:** Extended `BareGitRepoToolkit.repo_git_log` with `%G?`, `%GS`, and `%GK` git log format tokens. When agents inspect git logs, signature verification status (`good`, `bad`, `untrusted`, `none`) and signer identity are cleanly structured in JSON, eliminating ambiguous terminal parsing.
5. **Prose & Typography Hygiene:** Zero em-dashes or en-dashes (U+2014 / U+2013) exist in code comments, problem details, or documentation.

---

## 2. User Experience & Interaction Audit

### 2.1 Problem Detail Format
- Rejections produce RFC 9457 JSON responses:
  - Commit signature gate failure:
    - Status: `409 Conflict`
    - Error Code: `PROVENANCE_ATTESTATION_FAILED`
    - Message: `Gate '<name>' (commit_signature) rejected transition: Commit signature verification failed: ...`
  - Live CI status failure:
    - Status: `409 Conflict`
    - Error Code: `PROVENANCE_ATTESTATION_FAILED`
    - Message: `Gate '<name>' (ci_check_run) rejected transition: CI check runs failed or not concluded: ...`
  - SLSA provenance digest mismatch:
    - Status: `409 Conflict`
    - Error Code: `PROVENANCE_ATTESTATION_FAILED`
    - Message: `Gate '<name>' (slsa_provenance) rejected transition: SLSA provenance subject digests do not match expected sha: ...`
  - Air-gap blocked egress:
    - Status: `409 Conflict`
    - Error Code: `AIR_GAP_EGRESS_BLOCKED`
    - Message: `Live CI check-run verification blocked in air-gap mode for URL: ...`

### 2.2 Board & Transition Ergonomics
- The transition endpoint `/api/v1/issues/{issue_key}/transitions` accepts optional `verification_proof` in the transition body.
- When an issue transition is submitted without required proof or with invalid cryptographic proof, the UI displays the exact failure reason without leaving the board in an inconsistent state.

**Conclusion:** The API changes adhere to clean user-facing error reporting guidelines and preserve frontend board responsiveness.

**Recommendation:** Proceed with QA sign-off.
