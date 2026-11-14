# Message to Reality-Checker: KANBA-133 (KB-P4-15) Verification Proof Packet

- Ticket: KANBA-133 (KB-P4-15: [Phase 4 / MCP] Dynamic MCP Connection Scoping: Global (/mcp/{s}), Workspace (/w/{slug}) & Project (/w/{slug}/p/{key}) Routes + Header Narrowing)
- Implementation Author: builder-23
- Worktree: /tmp/kb-wt-KANBA-133
- Branch: feat/KANBA-133
- Status: Ready for Specialist Review & Main Merge

---

## 1. Executive Summary

This packet delivers dynamic MCP connection scoping across all 3 MCP surfaces (`agent`, `docs`, `admin`):
1. **Three Connection Modes (`mcp/scoping.py`, `mcp/app.py`)**:
   - Mode A (Global: `/mcp/{surface}`, no headers): Global keys query across authorized workspaces (`meatloaf-bot`). Narrow keys inherit their token boundary automatically.
   - Mode B (Workspace-Scoped: `/mcp/{surface}/w/{slug}` or `X-Workspace-Slug`): Pushes workspace boundary into downstream session. Foreign requests return HTTP 403 `KEY_SCOPE_VIOLATION`.
   - Mode C (Project-Scoped: `/mcp/{surface}/w/{slug}/p/{key}` or `X-Workspace-Slug` + `X-Project-Key`): Auto-fills `project` on tool calls (`create_ticket`, `search_tickets`, `manage_stickies`, etc.) and blocks cross-project mutations with `CONNECTION_SCOPE_VIOLATION`. Naked `X-Project-Key` returns HTTP 400 `VALIDATION_FAILED`.
2. **Monotonic Narrowing & Header Consistency**:
   - Monotonic intersection prevents elevating token privileges.
   - Conflicting URL path and header parameters reject with HTTP 400 `CONFLICTING_SCOPE_HEADERS`.
3. **Cryptographic Session Fingerprinting**:
   - Binds `sha256(token_sha256 || \0 || ws_id || \0 || proj_id)` to `Mcp-Session-Id`.
   - Session replay attempts across different URL scopes return HTTP 404.
4. **Header Forwarding & Cross-Workspace Resolution**:
   - `KanbanApiClient` forwards `X-KB-Scope-Workspace`, `X-KB-Scope-Project`, `X-KB-Scope-Global`.
   - Unconstrained global key lookup on ambiguous identifiers returns HTTP 409 `AMBIGUOUS_IDENTIFIER` with candidate list and remediation hint. Disambiguated by passing `workspace=<slug>`.

---

## 2. Verification Proof Matrix

| Dimension | Proof File | Observed Status |
| :--- | :--- | :--- |
| **Unit & Integration Tests** | `docs/qa/KANBA-133/unit-test-results.txt` | 22/22 passed in 3.73s across connection scoping, resolution, and issue keys |
| **Coverage Gate** | `docs/qa/KANBA-133/unit-test-results.txt` | 97.77% branch + line coverage across target modules (exceeds >= 95% threshold) |
| **Static Code Quality** | `docs/qa/KANBA-133/build-check.txt` | Ruff clean, format clean (1101 files), Mypy strict clean (558 source files), Import Linter clean (2 kept, 0 broken) |
| **Typography & Dashes** | `docs/qa/KANBA-133/build-check.txt` | Zero Unicode dashes (`check_no_dashes.py --all` 0 violations) |
| **MCP Live Transcripts** | `docs/qa/KANBA-133/mcp-transcript.txt` | Recorded raw HTTP exchanges for Global, Workspace, Project, Conflicting Headers, and Key Scope Violation |
| **API Contract Sample** | `docs/qa/KANBA-133/contract-sample.json` | Sample JSON demonstrating global 200, global ambiguous 409, scoped 200, and scoped ceiling 404 |
| **Git Diff Patch** | `docs/qa/KANBA-133/git-diff.patch` | Clean patch against main |
| **Specialist Sign-Offs** | `api-specialist-review.md`, `ui-specialist-review.md` | Both APPROVED |

---

## 3. Specialist Gate Reviews
- API Specialist Gate: APPROVED by @arch-reviewer (`docs/qa/KANBA-133/api-specialist-review.md`)
- UI Specialist Gate: APPROVED by @ui-specialist (`docs/qa/KANBA-133/ui-specialist-review.md`)
- Visual Screenshots: N/A - Non-UI Ticket (verified per Ticket Spec KB-P4-15)

Ready for passive forensic verification by @reality-checker upon merge to main.
