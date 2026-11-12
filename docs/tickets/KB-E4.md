---
id: KB-E4
title: '[Phase 4 / Epic] Three-Surface Intent MCP Server'
type: epic
children: [KB-P4-01, KB-P4-02a, KB-P4-02b, KB-P4-03, KB-P4-04, KB-P4-05, KB-P4-06, KB-P4-07, KB-P4-08, KB-P4-09a, KB-P4-09b,
  KB-P4-10, KB-P4-11, KB-P4-12, KB-P4-13, KB-P4-14, KB-P4-15, KB-P4-16]
spec_sections: ['3.5', '11.1', '11.2', '11.3', '11.4', '14.3', '15.5']
gates: [reality-checker]
state: Backlog
---

### Goal
Deliver the `mcp/` module: three Streamable HTTP surfaces (`/mcp/agent`, `/mcp/docs`, `/mcp/admin`) with separate tool registries, OAuth 2.1 + PKCE and surface-bound `kb_*` API keys, `EntityResolver`, `InlineSafeDumper` YAML with LOD tiers, the 8 agent tools, 6 docs tools, admin tools 1-6 and 10-12 (tools 7-9 land in Phase 5), the read-taint guard, two-stage `destructive_lifecycle`, and ephemeral `kb_agt_eph_*` read-only tokens. `mcp/` holds zero database credentials.

### Scope Summary
- Server skeleton and auth: KB-P4-01..KB-P4-03.
- `/mcp/agent`: KB-P4-04..KB-P4-07. `/mcp/docs`: KB-P4-08. `/mcp/admin`: KB-P4-09a / KB-P4-09b..KB-P4-12. Ephemeral tokens: KB-P4-13.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P4-01 | MCP server skeleton (3 Streamable HTTP mounts) | KB-P2-01 |
| KB-P4-02a / KB-P4-02b | MCP auth: OAuth 2.1 + PKCE and `kb_*` API keys | KB-P4-01, KB-P2-06 |
| KB-P4-03 | `EntityResolver`, `InlineSafeDumper` YAML, LOD tiers & `help` | KB-P4-01 |
| KB-P4-04 | `/mcp/agent`: `search_tickets` & `read_ticket` | KB-P4-03, KB-P3-17 |
| KB-P4-05 | `/mcp/agent`: `create_ticket` & `update_ticket` | KB-P4-04 |
| KB-P4-06 | `/mcp/agent`: `begin_work`, `transition_ticket`, `complete_work` | KB-P4-05 |
| KB-P4-07 | `/mcp/agent`: `link_objects`, `add_comment` + session read-taint guard | KB-P4-05, KB-P3-07 |
| KB-P4-08 | `/mcp/docs` 6 tools | KB-P4-03, KB-P3-15 |
| KB-P4-09a / KB-P4-09b | `/mcp/admin` tools 1-4 | KB-P4-03, KB-P2-10 |
| KB-P4-10 | `/mcp/admin` tools 5-6 | KB-P4-09a / KB-P4-09b |
| KB-P4-11 | `/mcp/admin` tools 10-11 | KB-P4-09a / KB-P4-09b, KB-P1-16 |
| KB-P4-12 | `/mcp/admin` tool 12: two-stage `destructive_lifecycle` | KB-P4-09a / KB-P4-09b, KB-P3-09a / KB-P3-09b |
| KB-P4-13 | Ephemeral `kb_agt_eph_*` read-only tokens | KB-P4-04, KB-P4-08 |
| KB-P4-14 | Hierarchical Scopable Keys: Global, Workspace, Project & Personal User keys + capability/tool narrowing | KB-P4-02a, KB-P2-11, KB-P2-05a |
| KB-P4-15 | Dynamic MCP Connection Scoping: Global (`/mcp/{s}`), Workspace (`/w/{slug}`) & Project (`/w/{slug}/p/{key}`) + headers | KB-P4-14, KB-P4-03, KB-P4-04, KB-P4-08 |
| KB-P4-16 | Headless CLI Device Approval (RFC 8628) + Scopable MCP Keys & Connected Apps Studio UI | KB-P4-14, KB-P4-15, KB-P4-02b, KB-P3-34 |

### Epic Definition of Done
- [ ] All 18 child tickets (`KB-P4-01` .. `KB-P4-16`, including `02a/b` and `09a/b`) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 5 (Phase 4): `/mcp/agent` (8 tools), `/mcp/docs` (6 tools), `/mcp/admin` (12 tools + 2-stage `destructive_lifecycle`), OAuth 2.1 + PKCE, `EntityResolver`, and `InlineSafeDumper` YAML.
- Note: admin tools 7, 8, 9 are delivered by KB-P5-13, KB-P5-17a / KB-P5-17b, KB-P5-05a / KB-P5-05b; this epic's exit covers tools 1-6 and 10-12.
