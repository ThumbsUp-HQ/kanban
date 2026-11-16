---
name: kanban-ticket
description: System-level standard for authoring and refining tightly scoped Kanban tickets with mandatory feature unit testing, literal Definitions of Done, and passive forensic Verification Proof packets for reality-checker.
---

# Kanban Ticket Skill

## Overview

This skill defines the mandatory structure and scoping rules for creating and updating Kanban tickets across **Claude Code**, **OpenAI Codex**, and **Gemini CLI / Antigravity**. Every ticket must be **atomic**, **tightly scoped**, **unit-tested**, and **forensically auditable** by the `reality-checker` sub-agent running on a fast, lightweight model (e.g., Gemini Flash, Claude Haiku, or GPT-4o-mini / Codex fast tier) **without requiring `reality-checker` to run commands, execute tests, or visit live websites**.

Use this skill together with [`kanban-agent-manager`](../kanban-agent-manager/SKILL.md).

---

## Core Principles for Scoped Tickets

0. **Deduplicate & Consult Specialists Before Creating Tickets**:
   - **Search First (`search_tickets`)**: Always search `Backlog`, `Todo`, and `In Progress` before creating a new ticket. If an existing ticket already covers the target area or upcoming feature, **update that ticket in-place (`update_ticket`)** instead of creating a duplicate.
   - **Consult Domain Specialists in Parallel**: Consult relevant specialists (UX/Frontend, Backend, Security) on fast models before finalizing ticket specifications.
   - **Do Not Auto-Start Implementation**: When asked to create or update tickets, stop once the tickets are created/updated and wait for explicit instruction to begin implementation.
1. **Single-Ticket Boundary (No Cross-Ticket Bleed)**:
   - A ticket's **Definition of Done** and **Verification Proof** must only test artifacts, files, and behaviors that exist after completing *that specific ticket* (and its explicit prerequisites).
   - Never require an early ticket to pass end-to-end checks against components built in later tickets.
2. **Literal, Non-Rhetorical Specifications**:
   - Because `reality-checker` compares ticket quotes directly against forensic evidence, avoid figures of speech, marketing adjectives ("blazingly fast", "bulletproof", "luxury"), or ambiguous goals.
   - Specify exact file paths, function/class names, HTTP status codes, byte limits, and CLI flags.
3. **Mandatory Feature Unit Testing (`>=95%` Project Coverage Standard)**:
   - Every feature or code ticket must require **unit tests specifically exercising the new/modified logic** introduced in that ticket, running rapidly against a clean isolated database state per test (`SAVEPOINT` / template DB) and using deterministic pluggable AI fixtures (`FixtureLLMProvider`) whenever AI agents are exercised.
   - Any ticket introducing or modifying an AI agent workflow MUST also expose/verify local manual CLI validation given explicit input parameters.
   - Specify the exact test file path(s) and the positive, negative, and boundary test cases required.
   - *Note on Coverage*: Individual tickets require passing unit tests (`>=95%` target on touched modules); project-wide **`>=95%` coverage** enforcement is verified by CI and dedicated coverage sub-agents rather than asking `reality-checker` to compute global repo percentages manually.
4. **Passive Forensic Verification Proof (`docs/qa/<TICKET_ID>/`)**:
   - `reality-checker` does **not** run shell commands or visit URLs.
   - Therefore, the **Verification Proof** section of every ticket must mandate a self-contained forensic proof directory at `docs/qa/<TICKET_ID>/` containing raw, unedited outputs (diffs, source snapshots, full test runner stdout/stderr, static analysis outputs, and screenshots for UI tickets) that `reality-checker` can inspect directly by reading the files.

---

## Mandatory Ticket Template

Every ticket created or updated in Plane MUST use the following Markdown structure:

```markdown
### User Story
As a **[persona/role]**, I need **[specific capability or component]** so that **[concrete engineering or user outcome]**.

**Requirement Traceability:** `[REQ-IDs]` | **Dependencies:** `[Prerequisite Ticket IDs or None]`

### Scoped Technical Actions
1. **Target Files:** `[exact/path/to/file1]`, `[exact/path/to/file2]`
2. **[Action 1]:** [Exact functions, types, endpoints, or configuration to implement]
3. **[Action 2]:** [Exact error handling, security invariants, and bounds]

### Mandatory Feature Unit Tests
- **Test File(s):** `[exact/path/to/test_file]`
- **Required Test Cases:**
  1. [Positive case verifying primary feature contract]
  2. [Negative/security case verifying rejection of invalid/hostile input]
  3. [Edge/boundary case verifying timeouts, size caps, or state transitions]

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** The target file(s) `[exact/path/to/file]` exist and implement `[exact symbols/endpoints]` as specified in Scoped Technical Actions.
- [ ] **Unit Tests Implemented & Passing:** The unit test file `[exact/path/to/test_file]` implements all required test cases and passes with `0` failures.
- [ ] **Build / Type / Lint Clean:** `[exact build/typecheck command]` exits with code `0` and `0` errors.
- [ ] **Forensic Proof Packet Complete:** All required raw proof files are written to `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries) so `reality-checker` can audit the ticket without executing commands:
1. `docs/qa/<TICKET_ID>/git-diff.patch` - Complete unified `git diff` showing all code and test additions/modifications for `<TICKET_ID>`.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - Full, unedited console output (`stdout`/`stderr` and exit code) of running `[exact unit test command]`.
3. `docs/qa/<TICKET_ID>/build-check.txt` - Full, unedited console output of `[exact build/typecheck/syntax command]`.
4. `[Ticket-Specific Artifact]` - e.g., `docs/qa/<TICKET_ID>/screenshots/*.png` (for UI tickets) or `docs/qa/<TICKET_ID>/contract-sample.json` (for API/wire tickets).
5. `docs/qa/<TICKET_ID>/ui-specialist-review.md` *(Mandatory for all UI and API tickets)* - Raw audit and sign-off from the project-local UI specialist (`.agents/agents/ui-designer.md` or `.agents/agents/ux-architect.md`).
6. `docs/qa/<TICKET_ID>/api-specialist-review.md` *(Mandatory for all API and MCP tickets)* - Raw audit and sign-off from the project-local API specialist (`.agents/agents/backend-architect.md` or `.agents/agents/api-tester.md`).
7. `docs/qa/<TICKET_ID>/message-to-reality-checker.md` *(Optional)* - Clarifies any architectural context or non-applicable UI sections (e.g., explaining why a pure internal database migration ticket has no browser screenshots).
```

---

## Guidelines for Adjusting Existing Tickets

When auditing or adjusting existing tickets on a Kanban board:
1. **Check for Unscoped DoD Items**: Remove or rewrite any DoD criterion that depends on future tickets or requires manual interactive hardware unless mocked/stubbed in unit tests.
2. **Add Explicit Unit Test Requirements**: Ensure every code ticket names the exact unit test file (`*.test.ts`, `test_*.py`, `*Tests.cs`) and enumerates the test cases to be written.
3. **Standardize the Proof Folder Path**: Ensure every ticket explicitly specifies `docs/qa/<TICKET_ID>/` and lists the exact filenames (`git-diff.patch`, `unit-test-results.txt`, etc.) that `reality-checker` will inspect.
4. **Clarify UI vs. Non-UI Evidence**: For backend, CLI, or engine-only tickets, explicitly state in the ticket's **Forensic Verification Proof** that **visual browser screenshots are NOT applicable (`N/A - Non-UI Ticket`)**, preventing `reality-checker` from issuing an automatic fail for missing screenshots on a pure backend/engine module.
