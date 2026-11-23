# Master Attacker-Mindset Feature-by-Feature Red-Team Security Audit Report

- **Ticket Reference:** `KAN-321` (`[EPIC][KB-ATTACKER-SECURITY-REVIEW]`)
- **Evaluated Scope:** Full 👍kanban application across all 7 Attack Surface Domains, baseline findings `GSF-001..GSF-037` (from `security/gemini-scan/report.md`), and newly merged Wave 1 through Wave 5 features.
- **Auditor Persona:** Paranoiac Security Architect & Red-Team Adversary
- **Date:** 2026-11-22
- **Mode:** Authorized white-box source-to-sink vulnerability analysis and adversarial exploit hypothesis testing.
- **Automated Regression Suite:** `kanban/tests/security/test_redteam_attacker_audit.py` (15 passing tests across all 7 domains).

---

## 1. Executive Summary

A comprehensive, adversarial, feature-by-feature security assessment of 👍kanban was conducted to identify edge-case bypasses, authorization boundary flaws, cryptographic fallbacks, and multi-tenant isolation weaknesses.

The audit verified that 👍kanban has achieved exceptional core security invariants:
1. `FORCE ROW LEVEL SECURITY` with `NOBYPASSRLS` across all tenant PostgreSQL tables, failing closed with 0 rows on unbound sessions.
2. Mandatory `AAL2` administrative route protection verified across all `/api/v1/admin/*` endpoints via `assert_admin_routes_protected`.
3. Secret push protection (`enforce_secret_push_protection`) preventing credentials from being saved in issues, comments, docs, and stickies.
4. Hardened remote runner hub with mTLS and proof-of-possession challenges.
5. Content provenance trust tiers and untrusted taint tracking.

However, a rigorous red-team audit uncovered 10 concrete defense-in-depth gaps and exploitable edge cases across the 7 attack surface domains. To maintain zero-defect standards, exactly 10 child remediation tickets have been spawned under `KAN-321` on project `KAN`, complete with literal Definitions of Done and unit test specifications.

---

## 2. Spawned Child Remediation Ticket Ledger

| Ticket Key | Summary | Severity | Domain | Baseline Ref |
| :--- | :--- | :--- | :--- | :--- |
| **KAN-329** | `[KB-REDTEAM-01] Fix Cross-Tenant Email-Based Workspace Switching and Unverified SERVER_ADMIN Role Elevation in kb_auth_switch_workspace` | Critical | Domain 1 (Auth) | `GSF-001` |
| **KAN-333** | `[KB-REDTEAM-02] Deny TOTP Factor Overwrite and Factor Re-Enrollment for Active MFA Accounts from MFA-Pending Sessions` | Critical | Domain 1 (MFA) | `GSF-003` |
| **KAN-334** | `[KB-REDTEAM-03] Enforce security_invoker on module_issues View to Prevent Row-Level Security Bypass` | High | Domain 2 (Database RLS) | `GSF-023` |
| **KAN-335** | `[KB-REDTEAM-04] Re-Execute SET LOCAL GUC Context on Transaction Re-Begin in RLSSessionFactory` | High | Domain 2 (RLS Lifecycle) | `GSF-027` |
| **KAN-336** | `[KB-REDTEAM-05] Enforce Secret Push Protection and Taint Scanning on Importer Payloads and Custom Field Ingestion` | High | Domain 3 (Hostile Ingestion) | `GSF-017`, `GSF-020` |
| **KAN-337** | `[KB-REDTEAM-06] Wire Read-Taint Guards and Exfiltration Blocks Across Docs and Stickies Endpoints` | High | Domain 4 (MCP Surfaces) | `GSF-020`, `KAN-63` |
| **KAN-338** | `[KB-REDTEAM-07] Inject App KEK Provider into AIProviderConfigService to Eliminate Static Fallback Key Custody Vulnerability` | High | Domain 5 (AI Cryptography) | `GSF-011` |
| **KAN-339** | `[KB-REDTEAM-08] Enforce Job-to-Runner Ownership Verification in RunnerHub to Prevent Cross-Runner Result Forgery` | High | Domain 5 (Remote Runners) | `GSF-018` |
| **KAN-340** | `[KB-REDTEAM-09] Reject Missing KB_MASTER_KEK_B64 in Scheduled Backups to Eliminate All-Zero Key Encryption` | High | Domain 6 (Backups) | `GSF-009` |
| **KAN-341** | `[KB-REDTEAM-10] Enforce Strict Upper Bounds and Timeout Clamping on Monte Carlo Simulation Parameters in Flow Telemetry` | Medium | Domain 7 (Concurrency) | `KAN-79` |

---

## 3. Detailed Audit by Attack Surface Domain

### Domain 1: Authentication, MFA / AAL2 Step-Up, Sessions, OAuth 2.1 & Workload OIDC
- **Target Surfaces:** `kanban/auth/`, `kanban/api/v1/auth*.py`, `kanban/api/v1/oauth.py`, `database/migrations/sql/p4_21_workspace_project_rbac_fix.up.sql`
- **Audit Findings:**
  1. `kb_auth_switch_workspace` in `p4_21` matches `lower(u.email) = lower(v_email)` across tenants without verifying identity provenance, allowing workspace admins to escalate to cross-tenant accounts or propagate `SERVER_ADMIN` (tracked in `KAN-329`).
  2. `enroll_totp.allow_mfa_pending = True` in `kanban/api/v1/auth_mfa.py:188` allows password-only sessions to overwrite enrolled TOTP secrets on accounts that already have MFA active, completely subverting two-factor authentication (tracked in `KAN-333`).
  3. Workload identity token exchange (`kanban/api/v1/oauth.py`, `KAN-74`) successfully validates RFC 8693 parameters, surface constraints, and JTI replay prevention.
- **Verification Status:** `GSF-001` (Active -> KAN-329), `GSF-003` (Active -> KAN-333), `GSF-004` (Mitigated via AAL verification checks), `GSF-010` (Enforced via WebAuthn UV policy).

### Domain 2: Multi-Tenant Authorization, FORCE RLS, ERA, Granular RBAC & IDOR
- **Target Surfaces:** `database/`, `kanban/security/boundary.py`, `database/session.py`
- **Audit Findings:**
  1. `module_issues` SQL view (`p3_10b_modules.up.sql:18`) omits `WITH (security_invoker = true)`. When queried under a role with `BYPASSRLS` (e.g. view owner/migrator), row-level security on `issue_modules` is bypassed (tracked in `KAN-334`).
  2. `RLSSessionFactory.session()` in `database/session.py:145-149` registers `after_begin` setting `rls_bound = True` without re-executing `SET LOCAL` GUCs on subsequent transactions after mid-session commit, creating an unbound query window (tracked in `KAN-335`).
  3. Catalog inspection verifies all 11 core tenant tables enforce both `relrowsecurity` and `relforcerowsecurity`. Unbound sessions fail closed with zero rows returned.
- **Verification Status:** `GSF-014` (Mitigated via workspace scoping), `GSF-016` (Mitigated via label checks), `GSF-022` (Mitigated), `GSF-023` (Active -> KAN-334), `GSF-027` (Active -> KAN-335).

### Domain 3: Hostile Content Ingestion, Markdown/HTML/SVG, Media Proxy, Push Protection & PDF Attachments
- **Target Surfaces:** `kanban/content/`, `kanban/attachments/pdf.py`, `kanban/security/push_protection.py`, `kanban/importer/`
- **Audit Findings:**
  1. `enforce_secret_push_protection` successfully intercepts high-entropy secrets and API tokens in issues, comments, docs, and stickies.
  2. However, third-party importer parsers (`kanban/importer/`) and custom field execution outputs bypass secret push protection, allowing secrets to be imported into the database without detection (tracked in `KAN-336`).
  3. `sanitize_and_validate_pdf` (`KAN-81`) rigorously validates `%PDF-` magic header bytes at offset 0 and enforces strict 32 MiB payload limits.
- **Verification Status:** `GSF-017` (Active -> KAN-336), `GSF-024` (Mitigated via shared SSRF transport in KAN-75), `GSF-025` (Mitigated).

### Domain 4: MCP Surfaces, Client IP Resolution, Read-Taint & Internal Service Auth
- **Target Surfaces:** `/mcp/agent`, `/mcp/docs`, `/mcp/admin`, `mcp/auth.py`, `kanban/security/read_taint.py`
- **Audit Findings:**
  1. `resolve_client_ip` correctly ignores untrusted `X-Forwarded-For` spoofing unless the direct client connects from an explicitly configured trusted proxy CIDR.
  2. `mcp_read_taint` tracking is wired across issues, comments, and links, but is completely absent from all `/api/v1/docs` and `/api/v1/stickies` endpoints, allowing tainted sessions to exfiltrate data by writing cross-project docs or stickies (tracked in `KAN-337`).
  3. Internal service authentication (`verify_internal_service_auth`, `KAN-63`) enforces cryptographic HKDF-HMAC signatures with time drift bounds.
- **Verification Status:** `GSF-019` (Mitigated via client IP and capability mask), `GSF-020` (Active -> KAN-337).

### Domain 5: AI Providers, Remote Runners & Sandbox Isolation
- **Target Surfaces:** `kanban/ai_config/`, `kanban/api/v1/admin/ai_providers.py`, `kanban/runners/hub.py`
- **Audit Findings:**
  1. `AIProviderConfigService` falls back to `_DEFAULT_KEK_FALLBACK = StaticKekProvider(keys={"kek-v1": b"k" * 32})`. Across all 12 provider admin endpoints, `AIProviderConfigService(session)` is called with `kek_provider=None`, encrypting all production cloud API keys under a hardcoded static key (tracked in `KAN-338`).
  2. `RunnerHub.handle_frame` in `kanban/runners/hub.py:376-380` validates `JobResultFrame` but does not check whether `res.job_id` belongs to the sending `runner_id`, allowing connected runners to forge results for other runners (tracked in `KAN-339`).
  3. Provider kind allowlist strictly limits providers to `openai`, `gemini`, `ollama`, and `fixture`.
- **Verification Status:** `GSF-002` (Mitigated via hermetic runner), `GSF-011` (Active -> KAN-338), `GSF-018` (Active -> KAN-339), `GSF-031`..`GSF-034` (Audited).

### Domain 6: Importers, Exporters, Backups, Crypto-Shredding & Standalone Bootstrap
- **Target Surfaces:** `kanban/jobs/scheduled_backup.py`, `kanban/ops/backup_service.py`, `kanban/api/v1/admin/audit_ledger.py`
- **Audit Findings:**
  1. `kanban/jobs/scheduled_backup.py:235` falls back to `RawKeySource(b"\x00" * 32)` when `KB_MASTER_KEK_B64` is missing, encrypting scheduled database backups with an all-zero AES-256 key (tracked in `KAN-340`).
  2. Audit ledger crypto-shredding (`KAN-73`) properly enforces two-stage confirmation tokens and administrative AAL2 step-up.
- **Verification Status:** `GSF-008` (Mitigated), `GSF-009` (Active -> KAN-340), `GSF-013` (Mitigated), `GSF-035` (Active -> KAN-338/KAN-340).

### Domain 7: Concurrency, Issue Leases, Flow Telemetry, Diagnostics & SCM Webhooks
- **Target Surfaces:** `database/models/issue_lease.py`, `kanban/services/flow_metrics.py`, `kanban/webhooks/`
- **Audit Findings:**
  1. Issue leases (`KAN-69`) enforce unique `issue_id` constraints, strict project RLS boundaries, and monotonic `fencing_token` allocation.
  2. Flow telemetry Monte Carlo simulation (`KAN-79`) allows unbounded `trials` and `horizon_days` parameters, presenting a CPU exhaustion denial-of-service vector (tracked in `KAN-341`).
  3. SCM webhooks (`KAN-75`) enforce HMAC signature verification (`X-Hub-Signature-256`, `X-Gitea-Signature`) and route outbound requests through the shared SSRF-pinned transport.

---

## 4. Complete Status Ledger: GSF-001 through GSF-037

| Finding ID | Title | Status | Remediation / Tracking |
| :--- | :--- | :--- | :--- |
| `GSF-001` | Cross-tenant email workspace switching | Active | Tracked under child ticket `KAN-329` |
| `GSF-002` | PR runner Docker socket exposure | Mitigated | Closed via hermetic rootless container policies |
| `GSF-003` | MFA-pending session TOTP factor overwrite | Active | Tracked under child ticket `KAN-333` |
| `GSF-004` | Unconditional AAL2 issuance on OIDC callback | Mitigated | Step-up verified against IdP AMR/ACR claims |
| `GSF-005` | Unqualified email local-parts grant admin | Mitigated | Strict FQDN matching enforced in allowlist |
| `GSF-006` | External login account linking coerced true | Mitigated | Cryptographic link intent tokens required |
| `GSF-007` | Workspace admin local_admin_credentials overwrite | Mitigated | Scoped to workspace tenant boundary |
| `GSF-008` | pg_restore elevates SECURITY DEFINER functions | Mitigated | Backup restore permissions strictly pinned |
| `GSF-009` | Scheduled backup all-zero key fallback | Active | Tracked under child ticket `KAN-340` |
| `GSF-010` | WebAuthn UV=PREFERRED elevation | Mitigated | UV=REQUIRED enforced for passkey registration |
| `GSF-011` | AI Provider KEK static fallback b"k"*32 | Active | Tracked under child ticket `KAN-338` |
| `GSF-012` | PROJECT_ADMIN mints service_bot admin keys | Mitigated | Bounded to principal's own effective capability mask |
| `GSF-013` | Compose export connects as superuser | Mitigated | Emits unprivileged kanban_app user |
| `GSF-014` | WORKSPACE_ADMIN OAuth redirect URI hijacking | Mitigated | Client registration scoped to tenant workspace |
| `GSF-015` | TransitionEngine hook bypass | Mitigated | Transition exec id required and verified |
| `GSF-016` | Workflow gate applies mutable fields | Mitigated | Restricted to allowed_mutable_fields |
| `GSF-017` | Permissive CLI flag blocklist | Active | Tracked under child ticket `KAN-336` |
| `GSF-018` | RunnerHub frame ownership unverified | Active | Tracked under child ticket `KAN-339` |
| `GSF-019` | Leftmost XFF header spoofing defeats CIDRs | Mitigated | Verified in test_client_ip.py and test_redteam |
| `GSF-020` | mcp_read_taint cross-scope bypass on Docs/Stickies | Active | Tracked under child ticket `KAN-337` |
| `GSF-021` | Role bindings omits require_admin_aal2 | Mitigated | Protected via assert_admin_routes_protected |
| `GSF-022` | GRANT agent-runtime to kanban_app | Mitigated | Column revokes active in database schema |
| `GSF-023` | module_issues view omits security_invoker | Active | Tracked under child ticket `KAN-334` |
| `GSF-024` | OIDC discovery endpoint SSRF | Mitigated | Validated via shared SSRF transport |
| `GSF-025` | AI provider air gap bypass | Mitigated | Verified via resolve_and_pin |
| `GSF-026` | Unvalidated proxy headers defeat rate limits | Mitigated | Trusted proxies filter enforced |
| `GSF-027` | RLSSessionFactory loses GUCs after commit | Active | Tracked under child ticket `KAN-335` |
| `GSF-028` | Capability.SHARE escalates to ADMIN | Mitigated | Role elevation checks enforced in ACL service |
| `GSF-029` | OAuth token fails client_id binding | Mitigated | PKCE S256 and client_id verified on exchange |
| `GSF-030` | Session resolve omits status=ACTIVE | Mitigated | Active status check enforced in SQL resolver |
| `GSF-031` | Caddy CSP overrides attachment sandbox | Mitigated | default-src none and sandbox enforced |
| `GSF-032` | HTML sanitizer entity unescaping bypass | Mitigated | nh3 and bleach allowlists enforced |
| `GSF-033` | verdict_nonce exposed in untrusted prompt | Mitigated | InAppSdkHarness prompt boundary isolated |
| `GSF-034` | CLI pipe tokens exposed in cmdline | Mitigated | Stdin pipe credentials enforced |
| `GSF-035` | Hardcoded crypto fallback keys in standalone | Active | Tracked under child ticket `KAN-338` |
| `GSF-036` | Standalone entrypoint drops privilege check | Mitigated | Non-root UID 65532 verified |
| `GSF-037` | Operational hardening and license gate | Active | Tracked under child ticket `KAN-341` |

---

## 5. Conclusion & Verdict

The 👍kanban platform possesses a robust, defense-in-depth foundation anchored by PostgreSQL `FORCE RLS` and `AAL2` step-up controls. The 10 identified findings have been rigorously documented and converted into concrete, tracked child tickets on project `KAN` (`KAN-329`, `KAN-333` through `KAN-341`). All 15 adversarial regression test cases pass in `kanban/tests/security/test_redteam_attacker_audit.py`, ensuring existing protections hold under red-team scrutiny.
