---
id: KB-E5
title: '[Phase 5 / Epic] AI Providers, Sparkle, Scripted Fields & ScriptRunner Agent Gates'
type: epic
children: [KB-P5-01, KB-P5-02, KB-P5-03, KB-P5-04, KB-P5-05a, KB-P5-05b, KB-P5-06, KB-P5-07, KB-P5-08, KB-P5-09, KB-P5-10,
  KB-P5-11, KB-P5-12, KB-P5-13, KB-P5-14, KB-P5-15, KB-P5-16, KB-P5-17a, KB-P5-17b, KB-P5-18, KB-P5-19a, KB-P5-19b, KB-P5-20,
  KB-P5-21, KB-P5-22a, KB-P5-22b, KB-P5-23, KB-P5-24, KB-P5-25, KB-P5-26, KB-P5-27]
spec_sections: ['8.2', '9.1', '9.2', '9.3', '10.1', '10.2', '11.4', '13.1', '13.2', '13.3', '14.1', '14.2', '14.3', '14.4',
  '15.3', '15.5']
gates: [reality-checker]
state: Backlog
---

### Goal
Deliver the `agent/` runtime and its `kanban/` integrations: Ollama/Gemini/OpenAI providers behind a router with circuit breakers, air-gap enforcement and budgets; embeddings; the `< 150ms` Sparkle FIM pipeline and editor plugin with the 6-row right-click matrix; admin-only custom scripted fields with `manifest_sha256` AAL2 escalation on Tier A `Wasmtime` and Tier B `nsjail`; the ScriptRunner workflow hook engine with async agent gates across `in_app_sdk`, `cli_pipe` (`agy -p`, `codex -p`) and `remote_runner` harnesses; and the `kanban-agent validate-*` CLI workbench.

### Scope Summary
- Providers and budgets: KB-P5-01..KB-P5-06.
- Sparkle: KB-P5-07..KB-P5-10.
- Custom fields and sandboxes: KB-P5-11..KB-P5-15.
- Workflow gates and harnesses: KB-P5-16..KB-P5-25.
- AI workbench extras: KB-P5-26, KB-P5-27.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P5-01 | `OllamaProvider` | KB-P0-12 |
| KB-P5-02 | `GeminiProvider` | KB-P0-12 |
| KB-P5-03 | `OpenAIProvider` | KB-P0-12 |
| KB-P5-04 | Provider router, circuit breakers & `📴` air-gap enforcement | KB-P5-01, KB-P5-02, KB-P5-03 |
| KB-P5-05a / KB-P5-05b | `BudgetEnforcer`, provider config API & admin MCP tool 9 | KB-P5-04, KB-P4-09a / KB-P4-09b |
| KB-P5-06 | Embeddings pipeline (`object_embeddings` + ONNX) | KB-P1-18, KB-P0-12 |
| KB-P5-07 | Sparkle FIM backend endpoint | KB-P5-06, KB-P5-04, KB-P2-17 |
| KB-P5-08 | Sparkle editor plugin (state machine, caret portal, ghost text) | KB-P5-07, KB-P3-45 |
| KB-P5-09 | Surgical right-click accept matrix | KB-P5-08 |
| KB-P5-10 | `kanban-agent validate-sparkle` | ` cursor marker, `--as-user` RLS scope, report output; tests. |
| KB-P5-11 | Custom field definitions & admin-only gate | KB-P1-14 |
| KB-P5-12 | `manifest_sha256` escalation approvals (AAL2) | KB-P5-11, KB-P2-05a / KB-P2-05b |
| KB-P5-13 | Tier A `Wasmtime` runner + custom field execution API + admin MCP tool 7 | KB-P5-12, KB-P4-09a / KB-P4-09b |
| KB-P5-14 | Tier B `nsjail` runner, seccomp profile & token-injecting egress proxy | KB-P5-13 |
| KB-P5-15 | Custom fields UI (rail display + admin editor) | KB-P5-13, KB-P3-42 |
| KB-P5-16 | `agent_definitions` registry & CLI flag validation | KB-P1-14, KB-P2-11 |
| KB-P5-17a / KB-P5-17b | Workflow hook DDL, sync validator/mutator pipeline & admin MCP tool 8 | KB-P5-13, KB-P5-16, KB-P4-09a / KB-P4-09b |
| KB-P5-18 | Async agent gate state machine | KB-P5-17a / KB-P5-17b, KB-P4-06 |
| KB-P5-19a / KB-P5-19b | Transition context/verdict schemas & `bind_project_repo` | KB-P5-18, KB-P4-13 |
| KB-P5-20 | `in_app_sdk` harness with read-only repo tools | KB-P5-19a / KB-P5-19b, KB-P5-04 |
| KB-P5-21 | `cli_pipe` harness (`agy -p`, `codex -p`) | KB-P5-19a / KB-P5-19b, KB-P5-14 |
| KB-P5-22a / KB-P5-22b | `remote_runner`: `kanban-agent-runner` daemon & WSS protocol | KB-P5-19a / KB-P5-19b, KB-P5-05a / KB-P5-05b |
| KB-P5-23 | `kanban-agent validate-transition` | KB-P5-20, KB-P5-21, KB-P0-13 |
| KB-P5-24 | Workflow Transition Studio UI | KB-P5-17a / KB-P5-17b, KB-P3-34 |
| KB-P5-25 | Gate states on cards, drawer & activity | KB-P5-18, KB-P3-37, KB-P3-44 |
| KB-P5-26 | Sticky -> Doc AI structuring + `validate-sticky-promo` | KB-P3-15, KB-P5-04, KB-P0-13 |
| KB-P5-27 | `kanban-agent validate-qa-packet` | KB-P0-13, KB-P5-04 |

### Epic Definition of Done
- [ ] All 27 child tickets (KB-P5-01 .. KB-P5-27) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 6 (Phase 5): `OpenAI`/`Ollama`/`Gemini` adapters, Sparkle right-click engine, Tier A `Wasmtime` + Tier B `nsjail`, `${context} | agy -p` / `codex -p` & remote `WSS` workflow gates, and `kanban-agent validate-*` local CLI testbench.
