# Message to Reality Checker: KAN-75 Forensic QA Verification Packet

## 1. Ticket Overview
- **Ticket ID:** KAN-75
- **Title:** [KB-DEVSECOPS-BUS-01] Extract Shared DNS-Pinned SSRF Transport, Fix SSH known_hosts Mirror Bug, & Add Inbound/Outbound SCM Webhook Bus
- **Branch:** `feat/KAN-75-ssrf-scm-webhook-bus`
- **Workspace:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan75-f07352f0`

---

## 2. Definition of Done Compliance Matrix

| Requirement | Implementation Location | Test Verification | Status |
| :--- | :--- | :--- | :--- |
| **Problem 1: Shared SSRF Transport** | `kanban/security/ssrf.py` | `kanban/tests/security/test_shared_ssrf_transport.py` (12 passed), `kanban/tests/media_proxy/` (22 passed) | **VERIFIED (100% coverage)** |
| - Reject RFC1918, loopback, CGNAT, IMDS, NAT64 | `kanban/security/ssrf.py:is_public_global_ip` | `test_is_public_global_ip_rejects_non_public_ranges` | **VERIFIED** |
| - 2.0s DNS timeout, all-record verification | `kanban/security/ssrf.py:resolve_and_select_pinned_ip` | `test_resolve_and_select_pinned_ip_*` | **VERIFIED** |
| - 300..399 redirect blocking | `kanban/security/ssrf.py:validate_not_redirect` | `test_validate_not_redirect` | **VERIFIED** |
| **Problem 1: SSH known_hosts Mirror Bug** | `kanban/repos/mirror.py:362-370` | `kanban/tests/repos/test_mirror_ssh_known_hosts.py` (2 passed), `kanban/tests/repos/` (67 passed) | **VERIFIED (95% coverage)** |
| - Ephemeral known_hosts populated from binding | `kanban/repos/mirror.py:365-368` | `test_mirror_manager_writes_configured_ssh_known_hosts` | **VERIFIED** |
| **Problem 2: Schema & DB Migration** | `database/migrations/versions/p6_09_scm_webhooks_and_outbound_bus.py`, `database/migrations/sql/p6_09_*` | `database/tests/test_p1_17_models.py` (5 passed), `kanban-ctl db check-migrations --static-only` | **VERIFIED (100% valid)** |
| - 4 tables with FORCE RLS | `scm_artifacts`, `scm_webhook_deliveries`, `webhook_subscriptions`, `webhook_deliveries` | `database/models/webhooks.py` (100% coverage) | **VERIFIED** |
| - SECURITY DEFINER helpers | `get_repo_binding_for_webhook`, `find_repo_binding_by_url_for_webhook` | `p6_09_scm_webhooks_and_outbound_bus.up.sql` | **VERIFIED** |
| - System object_links link kinds | `IMPLEMENTED_IN_PR`, `REFERENCED_BY_COMMIT`, `TRACKED_ON_BRANCH` | `database/models/base.py`, `kanban/services/links.py` | **VERIFIED** |
| **Problem 2: Inbound SCM Webhooks Router** | `kanban/api/v1/webhooks_scm.py` | `kanban/tests/webhooks/test_inbound_scm_webhooks.py` (6 passed) | **VERIFIED (95% coverage)** |
| - GitHub, GitLab, Forgejo/Gitea support | `kanban/api/v1/webhooks_scm.py:receive_scm_webhook` | `test_github_pull_request_inbound_webhook`, `test_gitlab_inbound_webhooks`, `test_forgejo_inbound_webhooks` | **VERIFIED** |
| - Payload size limit <= 1 MiB | `kanban/api/v1/webhooks_scm.py:_validate_payload_size` | `test_inbound_scm_webhooks_security_and_limits` | **VERIFIED** |
| - HMAC signature / token verification | `kanban/api/v1/webhooks_scm.py:_verify_signature` | `test_inbound_scm_webhooks_security_and_limits` | **VERIFIED** |
| - Replay deduplication | `kanban/api/v1/webhooks_scm.py:receive_scm_webhook` | `test_github_pull_request_inbound_webhook` | **VERIFIED** |
| - Issue key parsing and object_links creation | `kanban/api/v1/webhooks_scm.py:_process_artifacts_and_links` | `test_github_pull_request_inbound_webhook`, `test_forgejo_inbound_webhooks` | **VERIFIED** |
| **Problem 3: Admin Webhooks CRUD API** | `kanban/api/v1/admin/webhooks.py` | `kanban/tests/webhooks/test_outbound_webhook_dispatcher.py` (8 passed), `kanban/tests/security/test_admin_routes_protected.py` | **VERIFIED (98% coverage)** |
| - Router-level require_admin_aal2 protection | `kanban/api/v1/admin/webhooks.py:35` | `test_admin_webhooks_crud`, `test_admin_routes_protected` | **VERIFIED** |
| - Full CRUD + deliveries listing | `kanban/api/v1/admin/webhooks.py` | `test_admin_webhooks_crud` | **VERIFIED** |
| - SSRF target validation on create and patch | `kanban/api/v1/admin/webhooks.py:_validate_target_url` | `test_admin_webhooks_ssrf_and_error_cases` | **VERIFIED** |
| - Envelope encrypted secret storage | `kanban/api/v1/admin/webhooks.py:create_subscription` | `test_admin_webhooks_crud` | **VERIFIED** |
| **Problem 4: Outbound Webhook Bus & Dispatcher** | `kanban/webhooks/outbound_dispatcher.py`, `database/outbox/relay.py` | `kanban/tests/webhooks/test_outbound_webhook_dispatcher.py` (8 passed) | **VERIFIED (96% coverage)** |
| - Workspace air_gap_mode enforcement | `kanban/webhooks/outbound_dispatcher.py:execute_delivery` | `test_outbound_webhook_dispatcher_airgap_and_dead_letter` | **VERIFIED** |
| - Payload signing (X-Kanban-Signature-256) | `kanban/webhooks/outbound_dispatcher.py:_build_signed_headers` | `test_outbound_webhook_dispatcher_success_and_signing` | **VERIFIED** |
| - Exponential backoff retry (max 5 -> dead_letter) | `kanban/webhooks/outbound_dispatcher.py:execute_delivery` | `test_outbound_webhook_dispatcher_airgap_and_dead_letter` | **VERIFIED** |
| - OutboxRelay event_hooks injection | `database/outbox/relay.py:add_event_hook` | `test_outbox_relay_event_hook_invocation` | **VERIFIED** |

---

## 3. Automated Validation Results
- **Make Check:** Passed cleanly (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`, `uv run python -m scripts.check_no_dashes --all`, `uv run kanban-ctl db check-migrations --static-only`). All 6 checks passed with returncode 0.
- **Unit Tests:** 57 tests passed in 18.13s (0 failures, 0 errors).
- **Branch Test Coverage Across Touched Modules:**
  - `database/models/webhooks.py`: **100%**
  - `kanban/security/ssrf.py`: **100%**
  - `kanban/api/v1/admin/webhooks.py`: **98%**
  - `kanban/webhooks/outbound_dispatcher.py`: **96%**
  - `kanban/api/v1/webhooks_scm.py`: **95%**
  - `kanban/repos/mirror.py`: **95%**
  - Combined touched module test coverage: **97%** (exceeds 95% threshold).

---

## 4. Verification Evidence Artifacts
- `docs/qa/KAN-75/git-diff.patch`: Full unified git diff against base commit `043991e3`.
- `docs/qa/KAN-75/build-check.txt`: Raw terminal output of `make check`.
- `docs/qa/KAN-75/unit-test-results.txt`: Full raw terminal output of pytest suite and coverage report.
- `docs/qa/KAN-75/contract-sample.json`: Representative request/response contract samples for inbound and outbound webhooks and admin APIs.
- `docs/qa/KAN-75/message-to-reality-checker.md`: This comprehensive verification dossier.
