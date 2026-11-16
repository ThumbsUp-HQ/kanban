# Message to Reality-Checker: KANBA-141 (KB-P4-07) Forensic QA Packet

- **Ticket**: `KANBA-141` (`KB-P4-07`: `[Phase 4 / MCP] /mcp/agent tools: link_objects & add_comment + session read-taint exfiltration guard`)
- **Epic**: `KB-E4`
- **Spec Sections**: 11.2 (item 8), 3.5 (Read-Taint High-Water Mark), 12.1 (link_kind), 7.2 (8k/8m limits)
- **Status**: Complete, Tested, and Ready for Specialist Review & Forensic Certification

---

## 1. Executive Summary

This deliverable implements the MCP agent session read-taint exfiltration guard alongside the `/mcp/agent` tools `add_comment` and `link_objects`:

1. **Database Schema & Row Level Security (`database/migrations/versions/p4_07_mcp_read_taint.py`, `database/models/mcp_read_taint.py`)**:
   - `mcp_read_taint` table with composite primary key `(taint_key, project_id)`.
   - `taint_key BYTEA(32)` storing SHA-256 digests of session IDs (expires with session idle TTL 3600s) and subject credentials (expires 8h after read).
   - `key_kind` CHECK constraint (`session`, `credential`).
   - `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with workspace-scoped tenant isolation.
   - Clean rollback migration SQL and idempotent DDL.

2. **Session Read-Taint Security Guard (`kanban/security/read_taint.py`)**:
   - `TaintRecorder`: Fast async dependency that monitors incoming requests carrying `X-KB-MCP-Session`. Inspects outgoing response payloads across issues, search results, comments, links, and issue trees, upserting read taints into `mcp_read_taint` for all distinct returned project IDs. Rejects `mcp-gateway` requests lacking `X-KB-MCP-Session` with HTTP 400.
   - `TaintGuard`: Write guard dependency protecting all 7 MCP write endpoints (issues PATCH, issue-trees POST, begin-work POST, transition POST, complete-work POST, comments POST, links POST). Executes set-containment query: `Audience(P_target) <= Audience(P_tainted)` in PostgreSQL. If any broader-audience project is targeted, writes are blocked with HTTP 409 (`cross-scope-taint`), error code `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, and an autonomous session commits `MCP_TAINT_BLOCKED` to `activity_records`.

3. **MCP Agent Tools (`mcp/surfaces/agent/add_comment.py`, `mcp/surfaces/agent/link_objects.py`)**:
   - `add_comment`: Validates 1..65,536 byte Markdown bodies, handles `@mentions` with `MENTION_ACCESS_WARNING` (requiring `ack_mentions: true` override), supports threaded `reply_to`, and provides JIT `help` documentation.
   - `link_objects`: Resolves human-readable issue keys and doc identifiers, validates `BLOCKS`, `RELATES_TO`, `DUPLICATES`, and `VERIFIED_BY_DOC` relationship kinds, enforces self-link prevention (`VALIDATION_FAILED`), translates link matrix rejections (`LINK_TYPE_NOT_ALLOWED`), and supports `action: remove`.

4. **MCP Token Budget Conformance (`mcp/tests/test_schema_budget.py`)**:
   - All 9 `/mcp/agent` tools list schema payload audited at 7,037 raw UTF-8 bytes (~1,759 approximate tokens), well within the <= 1,850 token budget ceiling defined in S11.1.

---

## 2. Forensic Verification Proof Matrix

| # | Artifact | Description / Proof Summary | Status |
| :- | :--- | :--- | :-: |
| 1 | `docs/qa/KANBA-141/git-diff.patch` | Unified git diff across all 35 modified/created repository files | **PASS** |
| 2 | `docs/qa/KANBA-141/unit-test-results.txt` | 24 passed in 10.64s; 96% statement & branch coverage | **PASS** |
| 3 | `docs/qa/KANBA-141/build-check.txt` | Ruff clean (0 errors), Ruff format clean (15 files), Mypy strict clean (724 files), Lint-imports clean (2/2 kept) | **PASS** |
| 4 | `docs/qa/KANBA-141/schema-dump.sql` | PostgreSQL DDL dump of `mcp_read_taint` table, triggers, and FORCE RLS policies | **PASS** |
| 5 | `docs/qa/KANBA-141/mcp-transcript.txt` | Raw HTTP transcript captured via `KB_MCP_TRANSCRIPT_PATH` demonstrating `read_ticket SEC-1` with canary `CANARY-7f3a`, followed by `add_comment PUB-1` blocked with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`, session-escape retry blocked, and clean credential permitted | **PASS** |
| 6 | `docs/qa/KANBA-141/taint-canary-db-proof.txt` | SQL query outputs confirming 0 comments containing `CANARY-7f3a` in DB, 2 `MCP_TAINT_BLOCKED` activity records, and session/credential taint keys | **PASS** |
| 7 | `docs/qa/KANBA-141/schema-budget.txt` | Per-tool character and token counts confirming 1,759 tokens <= 1,850 ceiling | **PASS** |
| 8 | `docs/qa/KANBA-141/api-specialist-review.md` | API Specialist review and approval (assigned to @api-specialist) | Pending Review |
| 9 | `docs/qa/KANBA-141/ui-specialist-review.md` | UI Specialist review and approval (assigned to @ui-specialist) | Pending Review |
| 10 | Screenshots | N/A - Non-UI Ticket (MCP / Security Infrastructure) | **N/A** |

---

## 3. Unit Test & Coverage Details

- **Test Command**:
  ```bash
  uv run pytest kanban/tests/security/test_read_taint.py mcp/tests/agent/test_add_comment.py mcp/tests/agent/test_link_objects.py mcp/tests/test_schema_budget.py -v --cov=mcp.surfaces.agent.add_comment --cov=mcp.surfaces.agent.link_objects --cov=kanban.security.read_taint --cov=database.models.mcp_read_taint --cov-branch --cov-report=term-missing
  ```
- **Results**: 24 passed in 10.64 seconds.
- **Coverage Breakdown**:
  - `database/models/mcp_read_taint.py`: **100%**
  - `kanban/security/read_taint.py`: **95%**
  - `mcp/surfaces/agent/add_comment.py`: **100%**
  - `mcp/surfaces/agent/link_objects.py`: **94%**
  - **Overall Target Coverage**: **96%** (exceeds >= 95% threshold).

---

## 4. Invariant Compliance Checklist

- [x] **Universal Object Graph & FORCE RLS**: `mcp_read_taint` enforces workspace tenancy, foreign keys to `projects`, and explicit row-level security.
- [x] **Zero Plaintext Token Leakage**: All session tokens and subject credentials hashed via SHA-256 before storage in mutable BYTEA(32).
- [x] **Autonomous Audit Ledger Commitment**: `TaintGuard` commits `MCP_TAINT_BLOCKED` events via independent audit session before raising HTTP 409 exception.
- [x] **No Em-Dashes or Fluff**: External documentation conforms to technical ASCII standard.
- [x] **No Premature Closure**: Ticket remains open for specialist review and reality-checker forensic certification.
