# API Specialist Review: KAN-355

**Ticket:** `KAN-355` (`[KB-DOCS-FEATURE-05] Author Autonomous Agent Lease Fencing, Workpad Rework Breaker, and Secret Push-Protection Guide (KAN-69, KAN-71, KAN-72)`)
**Reviewer:** `@api-spec` (Backend Architect & API Specialist)
**Status:** `APPROVED`

---

## 1. Scope Evaluation

This ticket authors the architectural reference and implementation guide for autonomous agent safety: atomic PostgreSQL issue leases with monotonic fencing tokens, dedicated issue workpads, rework circuit breakers, and pre-persistence Shannon entropy secret push-protection (`thumbs-up-kanban.wiki/Agent-Lease-Fencing-Workpads-and-Push-Protection.md` and `kanban/tests/test_docs_agent_safety_guide.py`), documenting features shipped under `KAN-69`, `KAN-71`, and `KAN-72`.

The chapter provides comprehensive, rigorous technical coverage of:
1. **PostgreSQL Issue Leases & Monotonic Fencing Tokens (`KAN-69`):**
   - Columns on `issues` (`fencing_token`, `lease_expires_at`, `leased_by_principal_id`) and index `ix_issues_lease_expires_at` (migration `p6_05_issue_leases_and_fencing`).
   - Atomic Compare-And-Swap (CAS) lease acquisition query with monotonic `fencing_token = fencing_token + 1`.
   - CAS validation: Rejection of stale agent writes with `409 LEASE_CONFLICT`.
   - Dead agent failover via automatic 15-minute lease expiry.
2. **Dedicated Issue Workpads & Rework Circuit Breakers (`KAN-71`):**
   - Database table `issue_workpads` with RLS inheritance (migration `p6_10_issue_workpads_and_rework_breaker`).
   - `update_workpad` MCP tool schema on `/mcp/agent` within token budget (1,674 tokens).
   - Payload bounds: 65,536 bytes (`WORKPAD_PAYLOAD_TOO_LARGE`) and UTF-16 surrogate rejection (`INVALID_UTF8_SURROGATE`).
   - Per-issue rework loop circuit breaker: Tracking `rework_rejection_streak` against `max_rework_attempts` (default: 3). Tripped breaker blocks agent transitions with `409 REWORK_LOOP_LIMIT_EXCEEDED`.
   - Human reset route: `POST /api/v1/issues/{key}/reset-rework-breaker` (agent callers rejected with `403 FORBIDDEN`).
3. **Synchronous Pre-Persistence Secret Push-Protection (`KAN-72`):**
   - Fail-closed scanning in `kanban/security/push_protection.py` before PostgreSQL persistence, search TSV indexing, vector embedding, or audit ledger hashing.
   - Token-level Shannon entropy detector ($H \ge 4.5$ bits/char on candidate tokens $\ge 20$ chars spanning mixed character classes).
   - High-precision regex catalog covering private keys, GitHub/GitLab PATs, AWS access keys, Slack tokens, OpenAI/Anthropic keys, JWTs, and database DSNs.
   - Deterministic exemption engine protecting UUIDs, hexadecimal digests (commit SHAs, SHA-256), Base62 fractional rank keys, and clean URLs.

---

## 2. API Contract & Invariant Verification

- **MCP & REST Protocol Parity:** Tool arguments, schemas, rate limits (`MCP_TOOLS_CALL_RATE_LIMIT`), and HTTP error codes match runtime implementations.
- **Fail-Closed Security Guarantee:** Accurately documents pre-persistence rejection (`HTTP 422 ProblemException`) preventing secrets from entering PostgreSQL tables or audit chains.

---

## 3. Verdict

**`APPROVED`** (Concurrency control protocols, MCP tool schemas, circuit breaker semantics, and cryptographic push protection verified).
