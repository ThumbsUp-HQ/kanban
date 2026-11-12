# Forensic Audit Context: KANBA-71 (KB-P5-16)

## Overview and Scope
- Ticket: `KANBA-71` (`KB-P5-16`: `[Phase 5 / Database + API] agent_definitions registry, CLI binary allowlist & banned-flag validation (save + runtime)`)
- Worktree: `/tmp/kb-wt-KANBA-71` on branch `feat/KANBA-71`
- Module Coverage: `kanban.agents` at 97.76% (exceeds >= 95.00% mandate)

## Architectural and Security Invariants
1. **Module Hierarchy and Clean Imports**:
   - `agent -> mcp -> kanban -> database` layer contract is strictly respected (`lint-imports`: 2 kept, 0 broken).
   - Shared CLI policy (`kanban/agents/cli_policy.py`) resides in `kanban/` so that both save-time validation (`kanban.api`) and runtime execution (`agent/` in future tickets) can import it without circular dependencies.
2. **Double-Gated Privilege Enforcement**:
   - CLI flags are validated twice: first at ingestion/PATCH via Pydantic validator (`validate_cli_args`), and second immediately prior to runtime invocation via `assert_runtime_argv(record)` to defeat out-of-band database tampering.
3. **Database Constraints and FORCE RLS**:
   - `agent_definitions` enforces `FORCE ROW LEVEL SECURITY`.
   - `agent_def_harness_fields`: Exactly enforces field presence and mutual exclusion by harness type.
   - `agent_def_mcp_tools_subset`: Enforces subset of 4 allowed tools (`search_tickets`, `read_ticket`, `search_knowledge`, `read_doc`).
   - `agent_def_args_is_array`: Enforces JSON array type for `cli_args_json`.
   - Table count parity: `test_p1_17_models.py` updated to 38 tables, matching database introspection exactly.

## Unspecified CLI Binary Paths Documentation
As noted in `KB-P5-16.md`:
- The binary identifiers `agy`, `codex`, `gemini-cli`, and `claude-code` are defined by the DDL CHECK constraint `agent_definitions_cli_binary_allowlist_id_check`.
- Absolute executable paths for `agy` (`/usr/local/bin/agy`) and `codex` (`/usr/local/bin/codex`) are specified by S14.3.
- Paths for `gemini-cli` and `claude-code` are unspecified in product architecture spec S14.2 / S14.3. In `kanban/agents/cli_policy.py`, canonical paths `/usr/local/bin/gemini` and `/usr/local/bin/claude` were selected following the `/usr/local/bin` installation convention established for `agy` and `codex`. When dedicated CLI packages are finalized in Phase 5 harness integration, these absolute paths can be reconciled or configured via environment overrides if necessary.
