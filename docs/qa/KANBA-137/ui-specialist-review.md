# UI Specialist Gate Review: KANBA-137 (KB-P4-10)

- **Ticket**: `KANBA-137` (`KB-P4-10`: `[Phase 4 / MCP] /mcp/admin tools 5-6: architect_project (declarative plan/apply) & manage_cycles_and_modules`)
- **Reviewer**: `@ui-specialist` (UI & UX Architecture Specialist Gate)
- **Worktree**: `/tmp/kb-wt-KANBA-137`
- **Branch**: `feat/KANBA-137`
- **Verdict**: **APPROVED**

---

## 1. Executive Summary & Review Scope

As UI & UX Architecture Specialist Gate Reviewer, I have evaluated the client-facing MCP contracts, agent ergonomics, data projections, and diagnostic clarity for `KANBA-137` (`KB-P4-10`).

Per ticket specification:
> "7. `docs/qa/<TICKET_ID>/ui-specialist-review.md`"
> "8. Screenshots: N/A - Non-UI Ticket."

This ticket delivers administrative tools on `/mcp/admin` along with their supporting backend endpoints. Although direct web frontend components are not introduced in this ticket, the administrative tool outputs, summary representations, and error structures directly drive autonomous agent interactions and client administration tooling.

---

## 2. Agent Ergonomics & Interface Alignment Audit

### 2.1 Progressive Disclosure & Level of Detail (LOD)
- **`architect_project` Projections**:
  - In `summary` mode (the default), `plan` outputs a concise YAML diff highlighting newly created, updated, removed, or migrated states, priorities, labels, and module configurations:
    ```yaml
    project: ARC
    plan_sha256: 434fba50fcccd705c9c28958e6ad074edafd0b3391ed693828967cf3aedf9b73
    changes:
      project: {create: true, identifier: ARC, name: Architect Project}
      states:
        create: [Backlog, Todo, In Progress, Done, Cancelled]
      priorities:
        create: [Urgent, High, Medium, Low]
    ```
  - In `full` mode, the complete nested definition for each entity is serialized, allowing inspection of color hex codes, sort orders, and soft/hard WIP limits.
  - Roundtrip integrity: Calling `get` and piping the output into `plan` produces an empty changes block, confirming zero-mutation stability.

- **`manage_cycles_and_modules` Projections**:
  - `list_cycles` summary projection: Outputs `name`, `status`, `start_date`, and `end_date` without dumping raw database foreign keys or description text.
  - `list_modules` summary projection: Outputs `name`, `status`, and `lead_id`.
  - `list_views` summary projection: Outputs `name`, `layout`, and `group_by`.
  - `rollover` summary projection: Returns `status: rolled_over`, `from: <cycle_name>`, `to: <cycle_name>`, and `moved: <count>`.

### 2.2 Entity Resolution & Frictionless Ergonomics
- The `manage_cycles_and_modules` tool provides flexible entity resolution across cycles, modules, and saved views. Autonomous agents and human admins can specify entities using their natural names (`cycle: "Cycle 1"`, `target_cycle: "Cycle 2"`, `module: "Core"`, `view: "Backlog View"`) or raw UUIDs. The tool automatically handles name-to-UUID resolution, eliminating the multi-step lookup pattern that frequently causes agent context bloat.

### 2.3 Actionable Error Diagnostics & Guardrails
- **`STATE_IN_USE`**: When attempting to remove a workflow state that still contains active issues, the error response includes an actionable diagnostic hint (`hint: 'Specify state_migrations: {"Old State": "New State"}'`). This guides the agent directly toward resolving the conflict in one turn without guessing parameter names.
- **`PLAN_STALE`**: Clear conflict diagnostics inform the caller that the live project state has changed since the plan hash was computed, preventing accidental overwrites in multi-agent environments.
- **`MODULES_DISABLED`**: Cleanly surfaces when module management is attempted on a project where modules are turned off.
- **`INVALID_TRANSITION`**: Explicitly communicates illegal cycle status jumps (e.g. attempting to complete an upcoming cycle).

---

## 3. Typography & Formatting Standards
- Zero non-ASCII dash characters (`U+2014` or `U+2013`) exist across all tool descriptions, schemas, help texts, and error payloads. Standard ASCII hyphens `-` are used exclusively.

---

## 4. Verdict

The administrative tool schemas, summary projections, error diagnostics, and safety mechanisms for `KANBA-137` (`KB-P4-10`) satisfy all agent ergonomics and architectural standards.

**Verdict: APPROVED**
