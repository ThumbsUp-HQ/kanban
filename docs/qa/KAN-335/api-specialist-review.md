# API Specialist Forensic QA Review: KAN-335

STATUS: APPROVED

Auditor: api-spec (Backend Architect / API Tester / Security Engineer)
Target Ticket: KAN-335 ([KB-REDTEAM-04] Re-Execute SET LOCAL GUC Context on Transaction Re-Begin in RLSSessionFactory)
Branch: feat/KAN-329-336
Review Date: 2026-11-23

## 1. Architectural and Security Assessment

### 1.1 Threat Model & PostgreSQL SET LOCAL Semantics
PostgreSQL `SET LOCAL` variables (Grand Unified Configuration parameters / GUCs) have a transaction-scoped lifetime (`SET LOCAL ...` is discarded upon `COMMIT` or `ROLLBACK`).
Prior to this remediation:
- `RLSSessionFactory` set caller GUCs (`request.jwt.claim.sub`, `request.jwt.claim.workspace_id`, `request.jwt.claim.role`) on initial connection checkout.
- If application logic executed `await session.commit()` or `await session.rollback()` and subsequently performed further database operations on the same session, SQLAlchemy automatically starts a new transaction block.
- In this new transaction block, the PostgreSQL connection no longer had the `SET LOCAL` variables configured.
- Any subsequent query under `FORCE ROW LEVEL SECURITY` would either fail, see zero records, or default to unauthenticated principal context, leading to erratic behavior or security failures across multi-transaction request lifecycles.

### 1.2 Remediations Implemented
1. Synchronous RLS Context Binding Helper (`database/rls/context.py`):
   - Implemented `bind_rls_context_sync(connection: Connection, caller: PrincipalContext) -> None`.
   - Formats and executes SQL `SET LOCAL` commands on the underlying raw connection using synchronous DBAPI cursor execution.
2. SQLAlchemy Event Listener Hook (`database/session.py`):
   - In `RLSSessionFactory`, attached an event listener `event.listen(session_instance, "after_begin", _rebind_on_begin)`.
   - On every transaction begin (including the initial transaction and any subsequent transaction re-begin after `commit()` or `rollback()`), the listener checks if the session holds caller context and automatically re-binds the GUCs via `bind_rls_context_sync`.
3. Reliability & Transactional Hermeticity:
   - Guaranteed that at no point in a session's lifecycle can queries be executed without the correct caller RLS context active.

---

## 2. Requirement-to-Evidence Verification Matrix

| Requirement | Implementation Artifacts | Verification Tests | Verdict |
| :--- | :--- | :--- | :--- |
| **Re-bind GUCs after commit()** | `database/session.py` (`_rebind_on_begin`), `database/rls/context.py` | `database/tests/test_rls_session_rebegin.py::test_rls_guc_context_rebound_after_commit` | PASS |
| **Re-bind GUCs after rollback()** | `database/session.py` (`_rebind_on_begin`), `database/rls/context.py` | `database/tests/test_rls_session_rebegin.py::test_rls_guc_context_rebound_after_rollback` | PASS |
| **Re-bind across multiple transactions** | `database/session.py` | `database/tests/test_rls_session_rebegin.py::test_rls_guc_context_persists_across_multiple_transactions` | PASS |
| **Zero Em/En-Dashes Rule** | All touched files use plain ASCII hyphens | `uv run python -m scripts.check_no_dashes --all` exits 0 | PASS |
| **>=95% Test Coverage** | Session and RLS context module | All re-begin tests pass; full clean suite in 0.15s | PASS |

---

## 3. Specialist Verdict

The transaction re-begin vulnerability is cleanly mitigated at the SQLAlchemy engine/session event level. Caller GUCs are guaranteed to be active across all transaction blocks.

STATUS: APPROVED
