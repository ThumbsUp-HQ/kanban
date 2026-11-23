# API and Security Specialist Review: KAN-338

- **Ticket:** KAN-338 ([KB-REDTEAM-07]) - Inject App KEK Provider into AIProviderConfigService to Eliminate Static Fallback Key Custody Vulnerability
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-23
- **Branch:** `feat/KAN-337-341`
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan337-341-814e49d3`
- **Status:** APPROVED

---

## 1. Executive Security Evaluation

Ticket KAN-338 remediates red-team vulnerability GSF-011 by eliminating static fallback key custody in the AI provider subsystem:
1. **Purged Insecure Fallback:** Permanently removed hardcoded `_DEFAULT_KEK_FALLBACK = b"\x00" * 32` from `kanban/ai_config/service.py`.
2. **Fail-Closed Secret Custody:** Updated `AIProviderConfigService.__init__` to require explicit or loaded `KekProvider`. Both `_seal_key_material` and `_unwrap_key_material` explicitly check `if self._kek is None: raise RuntimeError("No KEK provider configured...")`.
3. **Application State KEK Resolution:** Implemented `_get_kek_provider(request)` in `kanban/api/v1/admin/ai_providers.py`, dynamically resolving the cryptographic key custody provider from `request.app.state.kek_provider` or loading runtime `KeyMaterial`. If no valid master KEK exists, administrative requests fail closed with `500 KEK_PROVIDER_UNAVAILABLE`.
4. **All 11 Admin Routes Injected:** Wired `_get_kek_provider` dependency into all provider creation, update, retrieval, deletion, testing, and reordering routes.

---

## 2. API Contract & Coverage Metrics

- **Unit Test Suite:** `kanban/tests/security/test_ai_provider_kek_enforcement.py`
  - `test_case_1_static_fallback_kek_eliminated`: PASSED
  - `test_case_2_seal_and_unwrap_fail_closed_without_kek`: PASSED
  - `test_case_3_injected_kek_provider_seals_and_unwraps_cleanly`: PASSED
  - `test_case_4_get_kek_provider_resolution_and_fail_closed`: PASSED
- **Existing Regression Suite:** `kanban/tests/api/admin/test_ai_providers_api.py` (10 passed) remains 100% green.
- **Coverage:** `>=95%` unit test coverage on new and modified cryptographic service paths.
- **Dashes & Linter Invariants:** Zero em-dashes and zero en-dashes; `make check` passes with 0 errors.

**Recommendation:** APPROVED for merge.
