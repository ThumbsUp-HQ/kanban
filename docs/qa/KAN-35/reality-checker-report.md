# Integration Agent Reality-Based Report

## 🔍 Reality Check Validation
**Commands Executed**: Strictly read-only passive forensic clean-room audit (zero shell commands executed, zero URLs visited, zero files modified). Inspected all verification packet files in `/home/adamoutler/kanban/docs/qa/KAN-35/`, all 6 PNG screenshots in `/home/adamoutler/kanban/docs/qa/KAN-35/screenshots/`, and cross-checked source and test files listed in `changed-files-manifest.txt` at `/home/adamoutler/kanban` (`main` commit `23ae056d`).
**Evidence Captured**:
- `docs/qa/KAN-35/message-to-reality-checker.md` (184 lines)
- `docs/qa/KAN-35/changed-files-manifest.txt` (45 lines)
- `docs/qa/KAN-35/unit-test-results.txt` (53 lines: 65 backend Pytest tests in 19.26s, 117 frontend Vitest tests across 5 suites in 11.20s)
- `docs/qa/KAN-35/build-or-typecheck.txt` (63 lines: Mypy clean in 8 files, `tsc -b --noEmit` FAILED with exit code 1 at `src/features/views/viewRegistry.tsx(740,9): error TS2322`, ESLint clean, Ruff clean, `lint-imports` 2 kept / 0 broken, empty `ZERO-DASHES AUDIT` section)
- `docs/qa/KAN-35/live-fullstack-proof.txt` (117 lines: zero `mockApi`, zero `page.route`, zero `context.route`, R2 live container `kanban-liveqa-2` at commit `23ae056d`)
- `docs/qa/KAN-35/api-specialist-review.md` (`STATUS: APPROVED` by `api-spec-2`)
- `docs/qa/KAN-35/ui-specialist-review.md` (`STATUS: APPROVED` by `ui-spec-2`)
- `docs/qa/KAN-35/git-diff.patch` (inspected lines 1-100 confirming `build-or-typecheck.txt` exit-code-1 failure was committed in the patch)
- 6 PNG screenshots in `docs/qa/KAN-35/screenshots/`
**QA Cross-Validation**: **CHALLENGED**. Both `api-specialist-review.md` (line 93) and `ui-specialist-review.md` (line 64), as well as `message-to-reality-checker.md` (lines 111 and 176), claim `pnpm --filter @kanban/web run typecheck` (`tsc -b --noEmit`) passed with `0 errors`. However, the committed raw log `docs/qa/KAN-35/build-or-typecheck.txt` (lines 10-20) shows `tsc -b --noEmit` FAILED with `error TS2322` (`ELIFECYCLE Command failed with exit code 1`). Although `/home/adamoutler/kanban/kanban/web/src/features/views/viewRegistry.tsx` line 797 now contains `as StateGroup`, no passing `tsc -b --noEmit` output was regenerated and committed. In addition, `message-to-reality-checker.md`, `api-specialist-review.md`, and `ui-specialist-review.md` cite exact unit-test coverage percentages (e.g., `100%`, `97%`, `95%`, `90%`, `96.06%`, `97.05%`, `97.43%`) that are completely absent from `docs/qa/KAN-35/unit-test-results.txt` (which ran without `--cov` or `--coverage`).

## 📸 Complete System Evidence
**Visual Documentation**:
- Full system screenshots:
  - `docs/qa/KAN-35/screenshots/live-kan35-board-before-mutation-desktop-light.png` (1440x900 light)
  - `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-desktop-light.png` (1440x900 light)
  - `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-desktop-dark.png` (1440x900 dark)
  - `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-tablet-light.png` (768x1024 light)
  - `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-mobile-light.png` (390x844 light)
- User journey evidence:
  - `live-kan35-board-before-mutation-desktop-light.png` -> `live-kan35-board-after-realtime-desktop-light.png` -> `live-kan35-drawer-realtime-comment-desktop-light.png`
- Cross-browser comparison: Chromium/Playwright only (no Firefox or WebKit cross-browser screenshots captured).

**What System Actually Delivers**:
- Baseline board (`live-kan35-board-before-mutation-desktop-light.png`) shows `Backlog 2` (`KAN-1`, `KAN-7`), `Todo 1` (`KAN-6`), and `In Progress 4` (`KAN-5`, `KAN-2`, `KAN-3`, `KAN-4`), with `Done` partially visible off the right scroll edge.
- Post-mutation light and dark desktop screenshots (`live-kan35-board-after-realtime-desktop-light.png` and `live-kan35-board-after-realtime-desktop-dark.png`) show `In Progress 5` with `KAN-8` (`Realtime Agent Ticket`, high-priority lightning icon) rendered at the bottom of the column with zero error modals and clean dark-mode contrast.
- Drawer screenshot (`live-kan35-drawer-realtime-comment-desktop-light.png`) shows `KAN-8` (`State: In Progress`, `Priority: High`, `Created by: @member`) with Activity entries (`comment created`, `issue state changed`, `issue rank moved`, `issue created`) and the live MCP comment `"Realtime comment from MCP agent (R2 verified)"`. Behind the drawer, the List View shows `Todo 2` (`KAN-6` + `KAN-9`), though no dedicated standalone List View screenshot was captured.
- Tablet screenshot (`live-kan35-board-after-realtime-tablet-light.png`, 768x1024) reveals top-right header overflow clipping: only the left half of the yellow warning icon is visible at the right edge while the `[x]` status button, shield icon, notification bell, and `M` avatar are clipped off-screen.
- Mobile screenshot (`live-kan35-board-after-realtime-mobile-light.png`, 390x844) renders the header icons (`hamburger`, `< Work Items`, search, warning, `[x]`, shield, bell, `M`) and `Backlog 2` column cleanly within `scrollWidth: 390`.

## 🧪 Integration Testing Results
**End-to-End User Journeys**: PASS (with minor visual/artifact caveats). `docs/qa/KAN-35/live-fullstack-proof.txt` demonstrates zero-mock (`0` `mockApi`, `0` `page.route`, `0` `context.route`) live execution on `kanban-liveqa-2` (`http://localhost:18952`, commit `23ae056d`):
- `@member` (`WORKSPACE_MEMBER`) minted a scoped `/mcp/agent` key and executed `create_ticket` (`KAN-8`, `KAN-9`), `transition_ticket` (`KAN-8`), and `add_comment` (`KAN-8`) with `0` `outbox_events_select_rls` errors.
- Keyboard `Alt+ArrowRight` optimistic move on `KAN-8` (`Backlog` -> `Todo`, `POST /api/v1/issues/KAN-8/move` -> 200) succeeded with `app-error-modal=0`, `pageErrors=0`, `consoleErrors=0`, and `0` `TypeError` crashes; subsequent MCP transition to `In Progress` and MCP comment rendered live with `docLoads=2` and unchanged `bootId=dvp2puu9vz6`.
- Delivery-time RLS and `Last-Event-ID` SSE replay (`p4_22_outbox_replay_reader`): `/ws` returned `NOT_FOUND` for `project:PRIV`, `project:<PRIV_UUID>`, and `project:DOESNOTEXIST`, leaked `0` frames during `@admin` `PRIV-1` mutations, and `GET /sse?channels=workspace:<WS_UUID>,project:KAN` with `Last-Event-ID: 1` replayed `KAN` events while withholding `PRIV` events (IDs 17, 18, 26).
**Cross-Device Consistency**: CONDITIONAL / PARTIAL FAIL. Desktop (1440x900 light/dark) and Mobile (390x844) are clean, but Tablet (768x1024) clips the top-right header action icons off the right edge (`live-kan35-board-after-realtime-tablet-light.png`).
**Performance Validation**: Measured test execution timings only: Pytest 65 tests in 19.26s (`unit-test-results.txt`); Vitest 117 tests across 5 suites in 11.20s (`unit-test-results.txt`). Page load times and WebSocket frame latency metrics in milliseconds were not recorded in `live-fullstack-proof.txt` or a `test-results.json` file.
**Specification Compliance**: PARTIAL FAIL ON VERIFICATION GATES. Code inspection confirms all 5 scoped fixes are implemented in `database/outbox/broker.py`, `kanban/services/realtime_outbox.py`, `kanban/app.py`, `kanban/ops/compose_export.py`, `database/migrations/sql/p4_22_outbox_replay_reader.up.sql`, `kanban/realtime/rls_filter.py`, `kanban/realtime/replay.py`, `kanban/realtime/hub.py`, `kanban/api/sse.py`, `kanban/web/src/api/realtime.ts`, `kanban/web/src/features/board/boardApi.ts`, `kanban/web/src/features/board/BoardView.tsx`, and `kanban/web/src/features/views/viewRegistry.tsx`. However, the QA evidence packet fails compliance because `build-or-typecheck.txt` contains a failed `tsc -b --noEmit` run, `unit-test-results.txt` omits `--cov`/`--coverage` proof for the `>=95%` coverage requirement and omits `kanban/web/src/realtime/index.test.tsx`, and `hub.py:545` has a WebSocket replay channel normalization defect.

## 📊 Comprehensive Issue Assessment
**Issues from QA Still Present**:
1. Stale/failing TypeScript typecheck log committed in `docs/qa/KAN-35/build-or-typecheck.txt` (lines 10-20 show `error TS2322` at `src/features/views/viewRegistry.tsx(740,9)` and `ELIFECYCLE Command failed with exit code 1`), even though `viewRegistry.tsx` line 797 was later patched with `as StateGroup`.
2. Empty `ZERO-DASHES AUDIT (NO EN/EM DASHES)` output in `docs/qa/KAN-35/build-or-typecheck.txt` (lines 62-63 have no output).

**New Issues Discovered**:
1. **Unsubstantiated Coverage Claims & Missing Test File in `unit-test-results.txt`**: `message-to-reality-checker.md` (lines 95-108, 174), `api-specialist-review.md` (lines 71-74), and `ui-specialist-review.md` (lines 76-80) claim specific coverage percentages (`90%`-`100%`), including `kanban/realtime/hub.py: 90%` (below the `>=95%` gate), with zero `--cov` / `--coverage` output in `docs/qa/KAN-35/unit-test-results.txt`. In addition, `unit-test-results.txt` omitted `kanban/web/src/realtime/index.test.tsx` (listed in `changed-files-manifest.txt`), and `api-specialist-review.md` line 74 inaccurately reported `src/api/realtime.test.ts` as `21/21 passed` instead of `44` tests.
2. **Tablet Viewport (768x1024) Top-Right Header Clipping**: `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-tablet-light.png` shows the top-right header controls (`[x]`, shield, bell, `M` avatar) clipped off the right edge of the 768px viewport.
3. **WebSocket `last_event_id` Replay Channel Key Mismatch (`kanban/realtime/hub.py:545`)**: In `RealtimeHub.handle_subscribe`, `replay_events` is called with `channels=successful_channels` (which contains raw client channel strings such as `project:KAN` or `issue:KAN-8`, unlike `kanban/api/sse.py:190` which passes `list(conn.subscribed_channels)` including `canonical_ch`). Because `OutboxReplayer._match_channel` (`kanban/realtime/replay.py:123-147`) only checks canonical UUID channels (`issue:<uuid>`, `doc:<uuid>`, `project:<uuid>`, `workspace:<uuid>`), WebSocket resume with `last_event_id` on human-readable keys alone will silently drop replayed events.
4. **Incomplete Artifact Manifest**: `docs/qa/KAN-35/changed-files-manifest.txt` does not list `live-fullstack-proof.txt`, `api-specialist-review.md`, `ui-specialist-review.md`, or `screenshots/*.png`, and there is no standalone screenshot of the List View live sync (`KAN-9`).

**Critical Issues**:
1. **Failing Typecheck Artifact & Unverified Typecheck Gate**: `docs/qa/KAN-35/build-or-typecheck.txt` records `tsc -b --noEmit` failing with exit code 1, directly contradicting specialist and handoff claims of `0 errors`.
2. **Missing Raw Coverage Proof & Sub-95% Reported Hub Coverage**: No raw coverage output exists in `docs/qa/KAN-35/unit-test-results.txt` to substantiate the `>=95%` coverage gate, and `kanban/realtime/hub.py` is reported at `90%` in `message-to-reality-checker.md`.

**Medium Issues**:
1. Tablet (768x1024) top-right header clipping visible in `live-kan35-board-after-realtime-tablet-light.png`.
2. `RealtimeHub.handle_subscribe` (`kanban/realtime/hub.py:545`) passes `successful_channels` instead of `list(conn.subscribed_channels)` to `OutboxReplayer.replay_events`, breaking WebSocket `last_event_id` replay when subscribing solely by human-readable key.
3. Missing `src/realtime/index.test.tsx` execution in `unit-test-results.txt`, empty `ZERO-DASHES AUDIT` output in `build-or-typecheck.txt`, and inaccurate test count (`21/21` vs `44`) in `api-specialist-review.md`.

## 🎯 Realistic Quality Certification
**Overall Quality Rating**: B-
**Design Implementation Level**: Good
**System Completeness**: 92% (core 5-problem realtime pipeline and RC1 optimistic move fix are implemented and proven on live R2 container, but verification artifacts and edge cases have gaps)
**Production Readiness**: NEEDS WORK

## 🔄 Deployment Readiness Assessment
**Status**: NEEDS WORK

**Required Fixes Before Production**:
1. Regenerate `docs/qa/KAN-35/build-or-typecheck.txt` at the exact final HEAD commit so `pnpm --filter @kanban/web run typecheck` (`tsc -b --noEmit`) shows 0 errors (replacing the currently committed `error TS2322` / exit code 1 failure) and `python3 -m scripts.check_no_dashes --all` includes its actual passing stdout output.
2. Regenerate `docs/qa/KAN-35/unit-test-results.txt` with `--cov` (Pytest) and `--coverage` (Vitest), including `kanban/web/src/realtime/index.test.tsx`, proving `>=95%` coverage on all touched modules (including raising `kanban/realtime/hub.py` from the reported `90%` to `>=95%`), and correct the misquoted test count in `api-specialist-review.md`.
3. Fix `RealtimeHub.handle_subscribe` in `kanban/realtime/hub.py:540-547` so `self._replayer.replay_events` receives the resolved canonical channels (matching `kanban/api/sse.py:190`), and add a unit/integration test verifying WebSocket `last_event_id` replay using only human-readable channel keys (e.g., `project:KAN`).
4. Fix the Tablet (`768x1024`) topbar header layout overflow clipped in `docs/qa/KAN-35/screenshots/live-kan35-board-after-realtime-tablet-light.png`, capture updated tablet and standalone List View (`KAN-9`) screenshots, and update `changed-files-manifest.txt`.

**Timeline for Production Readiness**: 1 targeted revision cycle (approximately 0.5-1 day to fix `hub.py` replay channel set, tablet header clipping, and regenerate clean typecheck/coverage/screenshot artifacts).
**Revision Cycle Required**: YES

## 📈 Success Metrics for Next Iteration
**What Needs Improvement**:
- Verification packet hygiene: never commit stale or failing command logs (`build-or-typecheck.txt`) alongside claims of `0 errors`, and never claim coverage percentages without attaching raw `--cov` / `--coverage` output.
- WebSocket `last_event_id` replay parity with SSE (`canonical_ch` inclusion in `hub.py`).
- Tablet (`768x1024`) header responsiveness so status, shield, bell, and avatar controls remain unclipped.
**Quality Targets**:
- `tsc -b --noEmit`: 0 errors (exit code 0) verified in `build-or-typecheck.txt`.
- `>=95%` statement/line coverage verified in raw Pytest and Vitest output across all touched files including `kanban/realtime/hub.py` and `kanban/web/src/realtime/index.test.tsx`.
- Zero clipped UI controls at 1440x900, 768x1024, and 390x844 viewports.
**Evidence Requirements**:
- Updated `docs/qa/KAN-35/build-or-typecheck.txt` showing exit code 0 for `tsc -b --noEmit` and populated `check_no_dashes` output.
- Updated `docs/qa/KAN-35/unit-test-results.txt` with raw coverage tables (`>=95%`) and `src/realtime/index.test.tsx` included.
- Updated tablet screenshot (`768x1024`) proving unclipped top-right header controls, plus standalone List View live sync screenshot and WebSocket `last_event_id` human-readable key replay test output.

---
**Integration Agent**: RealityIntegration
**Assessment Date**: 2026-11-20
**Evidence Location**: docs/qa/KAN-35/
**Re-assessment Required**: After fixes implemented
