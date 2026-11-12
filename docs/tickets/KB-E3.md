---
id: KB-E3
title: '[Phase 3 / Epic] Domain REST/Realtime API & Plane-Parity Web UI'
type: epic
children: [KB-P3-01a, KB-P3-01b, KB-P3-02, KB-P3-03, KB-P3-04, KB-P3-05, KB-P3-06, KB-P3-07, KB-P3-08, KB-P3-09a, KB-P3-09b,
  KB-P3-10a, KB-P3-10b, KB-P3-11, KB-P3-12, KB-P3-13, KB-P3-14, KB-P3-15, KB-P3-16, KB-P3-17, KB-P3-30, KB-P3-31, KB-P3-32,
  KB-P3-33, KB-P3-34, KB-P3-35, KB-P3-36, KB-P3-37, KB-P3-38, KB-P3-39, KB-P3-40, KB-P3-41, KB-P3-42, KB-P3-43, KB-P3-44,
  KB-P3-45, KB-P3-46, KB-P3-47, KB-P3-48, KB-P3-49, KB-P3-50, KB-P3-51, KB-P3-52]
spec_sections: ['2.3', '3.4', '4.3', '5.1', '5.2', '5.3', '5.4', '6.1', '6.2', '6.3', '6.4', '7.1', '7.2', '8.1', '8.2', '11.2',
  '15.5']
gates: [reality-checker]
state: Backlog
---

### Goal
Deliver the domain REST, WebSocket and SSE APIs for projects, issues, comments, links, cycles, modules, views, docs, pages, stickies and search (3A), and the Plane-parity React SPA with breathable tokens, `<EmojiHint>`, 5 board views, the `960px` ticket drawer with all 17 features `8a`-`8q`, ProseMirror Markdown editor, safe Mermaid/SVG/media rendering, Docs and Stickies surfaces (3B).

### Scope Summary
- 3A backend tickets KB-P3-01a / KB-P3-01b..KB-P3-17 (`kanban/api/v1/*`, realtime hub, search).
- 3B frontend tickets KB-P3-30..KB-P3-52 (`kanban/web/src/*`), each passing the UI Specialist Gate with annotated desktop/tablet/mobile Playwright screenshots.

### Child Tickets
| ID | Title | Deps |
| :-- | :-- | :-- |
| KB-P3-01a / KB-P3-01b | Project architect API | KB-P2-11 |
| KB-P3-02 | Issues CRUD API with ETag | KB-P3-01a / KB-P3-01b, KB-P2-13 |
| KB-P3-03 | Assignees API + access-filtered autocomplete | KB-P3-02 |
| KB-P3-04 | Created-by admin override endpoint | KB-P3-02, KB-P1-07 |
| KB-P3-05 | Comments API with safe mentions | KB-P3-02 |
| KB-P3-06 | Subscriptions & notifications | KB-P3-05, KB-P1-18 |
| KB-P3-07 | Object links API | KB-P3-02, KB-P1-11 |
| KB-P3-08 | Make a copy API | KB-P3-07 |
| KB-P3-09a / KB-P3-09b | Archive, auto-archive job, delete with blast radius & trash | KB-P3-02 |
| KB-P3-10a / KB-P3-10b | Cycles & modules API | KB-P3-01a / KB-P3-01b |
| KB-P3-11 | Views & query engine | KB-P3-02, KB-P1-10 |
| KB-P3-12 | Fractional board rank & move API with WIP limits | KB-P3-02 |
| KB-P3-13 | Activity feed API (4 tabs) | KB-P3-05 |
| KB-P3-14 | Docs & pages API | KB-P2-13, KB-P1-09 |
| KB-P3-15 | Stickies API + promotion heuristic + promote-to-doc | KB-P3-14, KB-P3-07 |
| KB-P3-16 | Realtime WebSocket/SSE hub | KB-P1-18, KB-P2-02 |
| KB-P3-17 | Search API | KB-P3-02, KB-P3-14 |
| KB-P3-30 | Breathable design tokens & theming | KB-P0-03 |
| KB-P3-31 | `<EmojiHint>` component + emoji registry | KB-P3-30 |
| KB-P3-32 | Playwright E2E harness with annotated screenshots | KB-P0-03 |
| KB-P3-33 | API client, TanStack Query & realtime client | KB-P3-02, KB-P3-16 |
| KB-P3-34 | App shell: sidebar, topbar, breadcrumb, pills, Cmd+K | KB-P3-31, KB-P3-33 |
| KB-P3-35 | Multi-card login & first-boot setup screens | KB-P3-34, KB-P2-10, KB-P2-12 |
| KB-P3-36 | Admin Auth Studio UI | KB-P3-35 |
| KB-P3-37 | Board view with Pragmatic DnD & virtualization | KB-P3-34, KB-P3-12 |
| KB-P3-38 | List & Table views | KB-P3-34, KB-P3-11 |
| KB-P3-39 | Calendar & Timeline (Gantt) views | KB-P3-38 |
| KB-P3-40 | Filters/display bar, 2D swimlanes, bulk bar & keyboard map | KB-P3-37, KB-P3-38 |
| KB-P3-41 | Ticket drawer shell + zero-remount full screen | KB-P3-34, KB-P3-02 |
| KB-P3-42 | Properties rail (8b-8i) | KB-P3-41, KB-P3-03, KB-P3-04, KB-P3-10a / KB-P3-10b |
| KB-P3-43 | Overflow actions: copy, archive, delete, subscribe, link | KB-P3-41, KB-P3-08, KB-P3-09a / KB-P3-09b, KB-P3-06 |
| KB-P3-44 | Activity tabs & comment composer | KB-P3-41, KB-P3-13, KB-P3-05 |
| KB-P3-45 | ProseMirror editor core + Markdown serializer + `sourceSlice` | KB-P3-30 |
| KB-P3-46 | Clipboard auto-convert paste + `🧼` pill | KB-P3-45, KB-P2-15 |
| KB-P3-47 | Mermaid Web Worker renderer | KB-P3-45, KB-P3-48 |
| KB-P3-48 | Client safe SVG + `<MediaViewport>` + lightbox | KB-P3-45, KB-P2-16 |
| KB-P3-49 | Effective Access Inspector popover | KB-P3-34, KB-P2-11 |
| KB-P3-50 | Docs tab (tree, page editor, outline, versions) | KB-P3-45, KB-P3-14 |
| KB-P3-51 | Stickies grid, promotion banner & promoted stub | KB-P3-45, KB-P3-15 |
| KB-P3-52 | Standalone status panel | KB-P3-34, KB-P0-09 |

### Epic Definition of Done
- [ ] All 40 child tickets (KB-P3-01a / KB-P3-01b .. KB-P3-52) are in state `Done`, each closed only after a local `reality-checker` grade-A `READY` certification recorded in its `docs/qa/<TICKET_ID>/` bundle.
- [ ] Every child ticket tagged `[UI]` has `docs/qa/<TICKET_ID>/ui-specialist-review.md`; every child tagged `[API]` has both `api-specialist-review.md` and `ui-specialist-review.md`; every child tagged `[DEP]` has `dependency-evaluation.md`.
- [ ] Phase-level CI is green via Dash (`status` / `wait` / `logs`) on the `main` commit that closes the last child ticket, with all CI jobs passing and `--cov-fail-under=95` / `vitest` `95%` thresholds enforced.
- [ ] Zero open tickets labeled as gaps discovered during this phase remain unlinked to a follow-up ticket.

### Exit Criteria (Spec S15.5)
- Spec S15.5 item 4 (Phase 3): Spatial tokens, 21-emoji `<EmojiHint>` system, 5 board views, `960px` Drawer + Full Screen (`8a`-`8q`), `beautiful-mermaid` Worker, `<MediaViewport>`, and `Docs` + `Stickies` (`💡📄`).
