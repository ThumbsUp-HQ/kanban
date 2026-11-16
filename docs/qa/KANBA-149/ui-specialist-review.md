# UI & UX Specialist Review: KANBA-149

**Auditor:** UI Specialist (`ux-architect` / `ui-designer`)  
**Date:** 2026-11-15  
**STATUS: APPROVED**

---

## 1. Executive Summary & Scope
Ticket `KANBA-149` (`KB-P5-17b`) implements the **Workflow Hook Management REST API, Synchronous Dry-Run Simulator, and `/mcp/admin` Tool 8 (`manage_workflow_interceptors`)**.

This ticket provides the direct backend endpoints and contracts consumed by the Admin Workflow Transition Studio UI (`/projects/:projectKey/settings/workflows` from `KB-P5-24` / `KANBA-158`), including `WorkflowStudioPage.tsx`, `TransitionRuleCard.tsx`, `HookPipelineRow.tsx`, `AttachHookDialog.tsx`, and `DryRunDrawer.tsx`.

---

## 2. API Contract & UI Ergonomics Audit

### A. Transition Rule Grouping & List Ergonomics (`GET .../workflow-hooks`)
- **Structure Alignment:**
  - Returns grouped transitions (`from_state`, `to_state`, `active_hook_count`, `hooks: [...]`) matching `TransitionRule` in `kanban/web/src/features/workflows/api.ts`.
  - Exposes presentation fields needed for S14.4 card badges and labels:
    `id`, `name`, `from_state`, `to_state`, `hook_kind`, `sort_rank`, `failure_policy`, `manifest_sha256`, `is_enabled`, `allowed_mutable_fields`, `wasm_module_sha256`, `agent_definition_id`, and `agent_slug`.
  - Seamlessly feeds `TransitionRuleCard` arrow bars and hook count indicators (`[ In Progress ] ========( 2 Active Hooks )========> [ In QA ]`).

### B. Atomic Hook Reordering & Drag-and-Drop Safety (`POST .../reorder`)
- **Payload Shape:**
  - Consumes `{ transition: { from_state, to_state }, ordered_hook_ids: string[] }`.
  - On mismatch or partial payload, emits `422` with RFC-7807 problem details: `code: "REORDER_SET_MISMATCH"`.
  - This allows `HookPipelineRow` optimistic drag-and-drop / keyboard move handlers to immediately revert to previous state and render an accessible `role="alert"` toast without page reloads.

### C. Sample-Ticket Dry-Run Panel Ergonomics (`POST .../dry-run`)
- **Interactive Drawer Support:**
  - Evaluates sync validators and mutators inside an isolated `SAVEPOINT` guaranteed to roll back (verified by `dry-run-rowcounts.txt` showing 0 rowcount delta across all tables).
  - Returns `{ steps: DryRunStepResult[], would_commit: boolean }` where each step contains:
    `order`, `name`, `hook_kind`, `result` (`allowed`, `mutated`, `rejected`, `error`, `skipped_async`), `reason`, `field_updates`, `duration_us`, and `cli_command`.
  - For `skipped_async` agent interceptors, `cli_command` is populated with a ready-to-run CLI invocation:
    `kanban-agent validate-transition --project KAN --from "In Progress" --to "In QA" --agent reality-checker`
    directly supporting `DryRunDrawer.tsx`'s 1-click clipboard copy feature.

### D. Security & Access Control UI Consistency
- Non-admin callers receive `404 Not Found`, ensuring anti-enumeration parity (S3.4) and preventing UI leak of workflow structures to unauthorized members.
- Un-elevated write operations return `403 AAL2_REQUIRED`, seamlessly triggering the frontend AAL2 verification dialog.

---

## 3. Administrative MCP Tool 8 Ergonomics
- `manage_workflow_interceptors` exposes all 9 actions with human-friendly entity resolution.
- Destructive `detach` enforces two-stage confirmation requiring `confirm: true`, returning a preview with `requires_confirmation: true` when unconfirmed.
- Safe YAML formatting using `InlineSafeDumper` prevents scalar breakouts and preserves clean terminal rendering.

---

## 4. Final Verdict
The REST endpoints, dry-run simulator, error envelopes, and MCP tool 8 contracts perfectly satisfy all UI data and interaction requirements defined in S14.4 and implemented in `KANBA-158`.

STATUS: APPROVED
