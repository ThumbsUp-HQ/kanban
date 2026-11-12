# Shared Brief for Ticket Drafters

You are drafting granular Kanban tickets for the Security-First, Agent-First Kanban platform in `/home/adamoutler/kanban`. Tickets will be executed by fast (Flash-class) implementer models and audited by a passive `reality-checker` on a fast model. Do NOT write application code. Do NOT call any kanban MCP tools (the MCP is pinned to an unrelated project). Your only output is Markdown files.

## Read first (mandatory)
1. `docs/tickets/BACKLOG_MANIFEST.md` - your assigned rows define scope, deps, spec sections, tags. Do not change scope boundaries between tickets; only elaborate.
2. `.agents/skills/kanban-ticket/SKILL.md` - the mandatory ticket template. Use its section headings verbatim.
3. `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` - read the spec sections cited by each of your rows (use `grep -n '^##'` to locate, then read only the needed ranges). Pull exact numbers, names, DDL columns, flags, limits, and file paths from the spec into the ticket. Do not invent conflicting values.
4. `AGENTS.md` - project gates.

## Output
- One file per ticket: `docs/tickets/<LOCAL_ID>.md` (e.g. `docs/tickets/KB-P1-05.md`).
- File starts with YAML frontmatter:
  ```yaml
  ---
  id: KB-P1-05
  title: "[Phase 1 / Database] issues table, sequence allocation & build_markdown_tsvector()"
  epic: KB-E1
  depends_on: [KB-P1-04]
  spec_sections: ["12.2"]
  gates: [reality-checker]        # add ui-specialist and/or api-specialist per tags
  new_dependencies: []            # list packages if [DEP]
  state: Backlog
  ---
  ```
- Body = the kanban-ticket template filled in completely:
  - `### User Story` with persona, `**Requirement Traceability:**` (spec section numbers + original requirement numbers like `#1`, `#8b`, `#13j` where applicable) and `**Dependencies:**` listing local IDs.
  - `### Scoped Technical Actions` with exact target file paths (follow layout in spec S2.1: `database/`, `kanban/`, `kanban/web/src/...`, `mcp/`, `agent/`, `deploy/`, `tests/` or module-local `tests/`), exact symbols/endpoints/DDL/limits, error handling and security invariants. Include short code/DDL/schema snippets where they remove ambiguity.
  - `### Mandatory Feature Unit Tests` with exact test file paths and at least 3 enumerated cases (positive, negative/security, boundary); AI-touching tickets use `FixtureLLMProvider`/`FixtureCLIRunner`; DB tickets use the clean-DB `SAVEPOINT` harness from KB-P0-05; touched-module coverage `>= 95%`.
  - `### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)` checkboxes: literal, verifiable, no adjectives, only artifacts from THIS ticket and its deps (no cross-ticket bleed). Include the exact test command (e.g. `uv run pytest database/tests/test_issues.py -q --cov=database --cov-report=term-missing`) and build/type command (`uv run mypy --strict database`, `uv run ruff check .`, `pnpm --dir kanban/web typecheck`, etc.).
  - `### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)` listing exact files under `docs/qa/<TICKET_ID>/` (keep the literal placeholder `<TICKET_ID>`; it is replaced with the real board key at creation). Include `git-diff.patch`, `unit-test-results.txt`, `build-check.txt`, plus ticket-specific artifacts (e.g. `schema-dump.sql`, `contract-sample.json`, `cli-run.txt`, `screenshots/*.png`). Non-UI tickets must state `Screenshots: N/A - Non-UI Ticket`. `[UI]` tickets require `ui-specialist-review.md` + annotated desktop/tablet/mobile Playwright screenshots. `[API]` tickets require both `api-specialist-review.md` and `ui-specialist-review.md`. `[DEP]` tickets require `dependency-evaluation.md` (license = permissive, pinned version + hash, alternatives considered, architect + engineer sign-off).
- Sizing: one Flash session, roughly 2-8 source files, `<= ~600` LOC production code. If a row is clearly too big, split into `<ID>a`/`<ID>b` files and say so in your final message. Don't make tickets thin either: each must be a meaningful, independently verifiable unit.
- Style: plain ASCII hyphens only. Zero em-dashes and en-dashes. No marketing adjectives. Literal, testable language.

## When done
1. Run `grep -n '[\u2014\u2013]' docs/tickets/<your files>` and fix any hits (must be zero).
2. Verify each file has all 5 template headings: `grep -c '^### ' docs/tickets/<ID>.md` should be `>= 5`.
3. Reply with: list of files written, any splits, any spec ambiguities or conflicts you found (with spec line numbers), and any cross-ticket dependency corrections you recommend. Keep the reply under 300 words.
