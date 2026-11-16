# API Specialist Gate Review: KANBA-141
**Auditor:** API Specialist (`backend-architect` / `api-tester`)
**Status:** **APPROVED**
**Date:** 2026-11-15

---

## 1. REST Endpoint Surface & Taint Subsystem Analysis
- **`TaintRecorder` & Read Endpoint Wiring:**
  - Applied to read endpoints returning issues, search results, comments, issue trees, and links.
  - Rejects requests from `mcp-gateway` service principal lacking `X-KB-MCP-Session` with `400 MISSING_MCP_SESSION`.
  - Computes SHA-256 digests (`32 bytes`) for both `session` (TTL: 3,600s) and `credential` (TTL: 8h) taint keys.
  - Upserts into `mcp_read_taint` updating `expires_at` on every read of distinct project IDs. Unreadable or masked rows are never tainted.
- **`TaintGuard` & Write Endpoint Interception:**
  - Wired into all mutating endpoints: `issues.py` (PATCH), `comments.py` (POST), `links.py` (POST/DELETE), `issue_workflow.py` (begin-work, transition, complete-work), and `issue_trees.py` (POST).
  - Evaluates set-containment audience query in SQL: rejects writes where `Audience(Target) ⊄ Audience(Tainted)`.
  - On blocked writes, raises `409 CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED` (`urn:kanban:problem:cross-scope-taint`) with `tainted_by` source project list and human fallback hint.
  - Commits `MCP_TAINT_BLOCKED` security event to immutable `activity_records` ledger with session key hash, tool name, and source/target project UUIDs.

## 2. MCP Agent Surface Tools
- **`add_comment` Tool (`mcp/surfaces/agent/add_comment.py`):**
  - Accepts human-readable issue identifier (e.g. `KAN-142` or UUID), `body_markdown` (bounded to 1..65,536 bytes), optional `reply_to`, and `ack_mentions` flag.
  - Validates body size boundaries strictly via RPC (`VALIDATION_FAILED` on >65,536 bytes).
  - Handles mention warnings gracefully: upstream 409 maps to `MENTION_ACCESS_WARNING`, requiring `ack_mentions: true` to proceed.
- **`link_objects` Tool (`mcp/surfaces/agent/link_objects.py`):**
  - Resolves source and target objects via `EntityResolver`.
  - Validates `link_type` against allowlist (`BLOCKS`, `BLOCKED_BY`, `RELATES_TO`, `DUPLICATES`, `DUPLICATED_BY`, `VERIFIED_BY_DOC`).
  - Rejects self-links with `VALIDATION_FAILED` and invalid matrix combinations with `LINK_TYPE_NOT_ALLOWED`.
  - Supports both `action: add` and `action: remove` with clean idempotency.
- **Schema Token Budget Conformance:**
  - Audited via `mcp/tests/test_schema_budget.py`: all 9 agent tools consume 7,037 bytes / ~1,759 tokens, well within the 1,850 token ceiling mandated by S11.1.

## 3. Database Schema, DDL & Security Invariants
- **`mcp_read_taint` Table (`database/migrations/sql/p4_07_mcp_read_taint.up.sql`):**
  - Primary key `(taint_key, project_id)` with `CHECK (octet_length(taint_key) = 32)`.
  - Constraint `key_kind IN ('session', 'credential')`.
  - Cascade deletion on project/workspace delete.
  - PostgreSQL Row Level Security: `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with workspace-scoped SELECT, UPDATE, DELETE policies.

## 4. Test Verification & Forensic Proof
- **Automated Tests:** 24 unit, API, and MCP integration tests pass in 6.79s (`EXIT_CODE=0`).
- **Coverage:** 96% line + branch coverage across target modules (`mcp_read_taint: 100%`, `add_comment: 100%`, `read_taint: 95%`, `link_objects: 94%`).
- **Forensic Verification:**
  - `taint-canary-db-proof.txt` indisputably demonstrates 0 leaked comments containing `CANARY-7f3a` in `PUB-1`, with dual `MCP_TAINT_BLOCKED` activity entries logged.
  - `schema-budget.txt` verifies 1,759 <= 1,850 token compliance.
  - Zero lint/mypy/import-linter violations across 724 source files.

## Conclusion
The session read-taint exfiltration guard and `/mcp/agent` tools meet all architectural, security, and protocol requirements of KB-P4-07, S3.5, and S11.2.

**STATUS: APPROVED**
