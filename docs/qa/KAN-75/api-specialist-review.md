# API and Security Specialist Review: KAN-75

- **Ticket:** KAN-75 ([KB-DEVSECOPS-BUS-01]) - Extract Shared DNS-Pinned SSRF Transport, Fix SSH known_hosts Mirror Bug, & Add Inbound/Outbound SCM Webhook Bus
- **Reviewer:** API & Security Specialist Reviewer (`api-spec`)
- **Review Date:** 2026-11-22
- **Branch:** `feat/KAN-75-ssrf-scm-webhook-bus`
- **Commit Under Audit:** `05bda78a` (`feat(webhooks): extract shared SSRF transport, fix known_hosts mirror bug, add SCM inbound/outbound bus (KAN-75)`)
- **Target Worktree:** `/home/adamoutler/.gemini/antigravity-cli/worktrees/ceecd8ef-f0c3-4c2c-b75c-e6eb23e99760/swarm-b-kan75-f07352f0`
- **Status:** APPROVED

---

## 1. Executive Security & Architecture Evaluation

Ticket KAN-75 extracts a centralized, DNS-pinned, SSRF-resistant HTTP transport, resolves a critical SSH `known_hosts` mirror isolation bug, and establishes bidirectional SCM webhook automation with row-level security and air-gap protection.

Audited implementations across the four problem areas:
1. **Shared DNS-Pinned SSRF Transport & SSH known_hosts Security (`kanban/security/ssrf.py` & `kanban/repos/mirror.py`):**
   - Extracted unified SSRF defenses into `kanban/security/ssrf.py`.
   - `is_public_global_ip` strictly rejects RFC1918 private ranges, loopback (`127.0.0.0/8`, `::1`), link-local/APIPA (`169.254.0.0/16`, `fe80::/10`), cloud metadata/IMDS (`169.254.169.254`), CGNAT (`100.64.0.0/10`), and NAT64 prefixes (`64:ff9b::/96`).
   - `resolve_and_select_pinned_ip` enforces a strict 2.0-second DNS timeout, verifies every resolved record against public IP criteria, and pins outbound connections directly to the validated IP to defend against DNS rebinding.
   - Blocks HTTP redirect responses (`300..399`) across all webhook and proxy transports to eliminate redirect-based intranet pivoting.
   - In `kanban/repos/mirror.py`, ensures administrator-configured `ssh_known_hosts` on repository bindings are written into the ephemeral environment, neutralizing SSH man-in-the-middle attacks.
2. **SCM Inbound Webhook Bus & Schema Migration (`p6_09`):**
   - Migration `p6_09_scm_webhooks_and_outbound_bus` creates `scm_artifacts`, `scm_webhook_deliveries`, `webhook_subscriptions`, and `webhook_deliveries` with `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.
   - Introduces system link kinds (`IMPLEMENTED_IN_PR`, `REFERENCED_BY_COMMIT`, `TRACKED_ON_BRANCH`) into `object_links`.
   - Inbound router `kanban/api/v1/webhooks_scm.py` receives webhooks for GitHub, GitLab, and Forgejo/Gitea.
   - Enforces a 1 MiB hard ceiling on raw payloads (`PAYLOAD_TOO_LARGE`).
   - Employs constant-time signature verification (`hmac.compare_digest`) rejecting unauthorized payloads with 401 `INVALID_SIGNATURE`.
   - Prevents delivery replays via atomic deduplication on delivery identifiers.
   - Safely parses issue keys from branch names, pull request titles, and commit messages, generating `scm_artifacts` and typed `object_links`.
3. **Administration Webhook Management API (`kanban/api/v1/admin/webhooks.py`):**
   - All routes are strictly protected at the router level by `Depends(require_admin_aal2)`.
   - Implements full CRUD and delivery inspection for webhook subscriptions.
   - Enforces SSRF target validation on subscription creation and patching.
   - Stores webhook secrets securely utilizing KMS envelope encryption.
4. **Outbound Webhook Bus & Dispatcher (`kanban/webhooks/outbound_dispatcher.py`):**
   - Evaluates workspace `air_gap_mode` prior to dispatch, preventing data exfiltration in restricted deployments.
   - Signs outbound payloads with `X-Kanban-Signature-256`, `X-Kanban-Timestamp`, and `X-Kanban-Delivery-Id`.
   - Implements bounded exponential backoff retry logic (up to 5 attempts before marking `dead_letter`).
   - Hooks into `OutboxRelay` via dependency injection without breaking architectural layering constraints (`agent -> mcp -> kanban -> database`).

---

## 2. Wire Contracts & Security Invariants

### A. HTTP Request & Error Contracts
- Inbound SCM webhooks return HTTP 200 with delivery ID, links created, and linked issue keys.
- Payload larger than 1 MiB returns HTTP 413 `PAYLOAD_TOO_LARGE`.
- Missing or invalid signatures return HTTP 401 `INVALID_SIGNATURE`.
- Outbound webhooks include SHA-256 HMAC headers and timestamps.

### B. Tenancy & Anti-Enumeration
- Webhook subscriptions and deliveries enforce strict workspace isolation via Row-Level Security.
- Webhook endpoints leak no internal network topology or tenant information.

---

## 3. Unit Test Coverage & Verification Metrics

- **Backend Pytest Results:** 57 passed in 18.13s (`test_shared_ssrf_transport.py`, `test_mirror_ssh_known_hosts.py`, `test_inbound_scm_webhooks.py`, `test_outbound_webhook_dispatcher.py`, `test_admin_routes_protected.py`, `test_p1_17_models.py`, `test_media_proxy_api.py`, `test_ssrf_and_rebinding.py`).
- **Module Coverage on Touched Code:**
  - `database/models/webhooks.py`: 100%.
  - `kanban/security/ssrf.py`: 100%.
  - `kanban/api/v1/admin/webhooks.py`: 98%.
  - `kanban/webhooks/outbound_dispatcher.py`: 96%.
  - `kanban/api/v1/webhooks_scm.py`: 95%.
  - `kanban/repos/mirror.py`: 95%.
  - Total touched module coverage: 97% (exceeds 95% project requirement).
- **Static Quality Checks:**
  - `ruff check`: All checks passed (0 errors).
  - `ruff format --check`: 2235 files formatted.
  - `mypy`: 0 issues found in 1243 source files.
  - `lint-imports`: 2 kept, 0 broken contracts.
  - `check-migrations`: Valid single head `p6_09_scm_webhooks_and_outbound_bus`.
  - `check_no_dashes`: Clean across repository (0 violations).

---

## 4. Final Verdict

- **Result:** APPROVED.
- **Handoff:** Handing off directly to `@ui-spec` for UI Specialist review and routing to `@merge-ci`.
