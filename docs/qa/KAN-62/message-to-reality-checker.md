# Reality-Checker Verification Packet: KAN-62

**Ticket ID:** `KAN-62` (`[KB-AI-BENCHMARK-01]`)
**Title:** Multi-Provider In-Transition AI Agent Benchmark & Live Validation: Gemma 3/4, Granite 3.3, Nemotron 3, Google Gemini, and OpenAI
**Branch:** `main` (commit `435b7873c875`)
**Container Environment:** `http://127.0.0.1:18962` (container: `kanban-liveqa-2`, `KB_GIT_COMMIT=435b7873c875`)
**Live Stack Status:** `OVERALL LIVE_STACK_VERDICT: PASS`

---

## 1. Executive Summary & Verification Highlights

This packet provides forensic verification for ticket **KAN-62** integrated on `main` at commit `435b7873c875`, incorporating empirical data from zero-mock live container execution on `kanban-liveqa-2` (`http://127.0.0.1:18962`, embedded PostgreSQL 16 + FORCE RLS).

All benchmark evaluations, Round 1 (`2f84e8757f56`) and Round 2 (`435b7873c875`) UI/UX polish remediations, and documentation synchronization deliverables have been completed, verified, and certified:

1. **Multi-Model Benchmark & Live In-Transition Evaluation**:
   - Executed 14 real HTTP 202 transition evaluations on `In Progress -> Done` (`require-ai-qa-on-done`, `fail_closed: true`) against live edge engines and cloud APIs via `GateWorkerRunner`, plus Round 2 live re-verification at commit `435b7873c875` (`@done-qa-gatekeeper`, `ollama/gemma4:e2b`, Positive `KAN-1` -> `Done` in `13,499 ms`, Negative `KAN-2` -> vetoed `In Progress` in `5,648 ms`):
     * **Fast GPU Ollama (`192.168.1.115:11434`) `gemma3:4b`**: Positive `approve` (`Done`, 31,431 ms); Negative `reject` (vetoed in `In Progress`, 16,630 ms).
     * **Fast GPU Ollama (`192.168.1.115:11434`) `granite3.3:2b`**: Positive `timed_out` at 20,000 ms (fail-closed); Negative `reject` (vetoed in `In Progress`, 12,691 ms).
     * **AI Supercomputer Ollama (`192.168.1.101:11434`) `gemma4:e2b`**: Positive `approve` (`Done`, 19,892 ms initial / 13,499 ms Round 2); Negative `reject` (vetoed in `In Progress`, 5,213 ms initial / 5,648 ms Round 2).
     * **AI Supercomputer Ollama (`192.168.1.101:11434`) `nemotron-3-super:latest`**: 5s cutoff triggered `GATE_TIMEOUT` at 6,023 ms (fail-closed); 45s cutoff returned Positive `approve` (31,940 ms) and Negative `reject` (26,502 ms).
     * **Google Gemini (`AQ.Ab8R...REDACTED`) `gemini-2.5-flash-lite`**: Positive `approve` (`Done`, 3,215 ms); Negative `reject` (vetoed in `In Progress`, 1,594 ms).
     * **OpenAI (`sk-proj-...REDACTED`) `gpt-4o-mini`**: Positive `approve` (`Done`, 3,846 ms); Negative `reject` (vetoed in `In Progress`, 2,224 ms).

2. **Round 2 UI/UX Polish Verification (`435b7873c875`)**:
   - Verified `PropertiesRail.css` & `IssueSurface.css` right-rail `State` `<select>` fix (`label` column `96px`, `min-width: 108px`, `padding-right: 20px`, `box-sizing: border-box`, `gap: 6px`).
   - Live DOM bounding-box audit on `KAN-2` at `1440x900` (`67-qa-gate-negative-saturn-ice-cream-vetoed.png`): `selectRect.right = 1416 <= 1424` (`scrollWidth = 111 === clientWidth = 111`), proving the **entire right border and dropdown chevron (`v`) are completely visible inside the 1440px viewport** alongside the `🛑🤖` badge.
   - Verified `AttachHookDialog` `Allowed Mutable Fields` unclipped above footer (`65`), formatted HTML `<h2>`/`<h3>` + bullet lists (`66`), `evaluating gate via in_app_sdk (ollama/gemma4:e2b)`, and `Comments (1)`.

3. **Negative Discrimination, Cutoff Enforcement & Secret Custody**:
   - Canary ticket `KAN-2` ("Build a rocket ship and serve ice cream on Saturn") was rejected by 100% of tested models, remaining safely in `In Progress`.
   - Strict 5000 ms cutoff against `nemotron-3-super:latest` cleanly timed out at 6,023 ms (`GATE_TIMEOUT`), retaining card in `In Progress` with zero hung worker threads.
   - Secret scan verified `0` occurrences of raw Gemini `AQ.` or OpenAI `sk-proj-` keys across `docs/qa/`, `thumbs-up-kanban.wiki/`, `kanban/`, `agent/`, and `docker logs kanban-liveqa-2`.

4. **Documentation Center Synchronization**:
   - Benchmark matrices, latency tables, and sequence diagrams synchronized in `Scripted-Workflows-and-Transition-Helpers.md`, `Multi-Provider-AI-Engine-and-Runners.md`, and `wikiManifest.ts` (`28` chapters, `71` images).
   - All 6 embedded visual artifacts (`62-*.png`..`67-*.png`) pass media audit validation (`kanban/tests/docs/test_wiki_media_audit.py`: 13/13 passed).

---

## 2. Test Suite & Coverage Evidence

- **Python Unit Tests (`unit-test-results.txt` Section 1):** `265 passed in 8.14s` (`0` warnings), **97% aggregate coverage** (`>= 95%` per module, including `agent/gates/runner.py` at `96%`, `agent/gates/worker.py` at `97%`, `agent/harnesses/in_app_sdk.py` at `95%`, `agent/providers/gemini.py` at `95%`, `agent/providers/ollama.py` at `96%`, `agent/providers/openai_provider.py` at `98%`, `agent/providers/schema_utils.py` at `97%`, `kanban/ai_config/service.py` at `96%`, `kanban/security/scrubber.py` at `100%`).
- **Async Gate & Media Audit (`unit-test-results.txt` Section 2):** `31 passed in 5.99s` (`18 passed` in `kanban/tests/workflows/test_async_gate.py` + `13 passed` in `kanban/tests/docs/test_wiki_media_audit.py`).
- **Frontend Vitest (`unit-test-results.txt` Section 3):** `5 files, 125 passed in 3.14s` (`DocsCenter`, `ActivityEventRow`, `SafeMarkdownPreview`, `useGateRealtimeSync`).
- **Static Gates (`build-or-typecheck.txt`):** `check-migrations` OK (`p4_24_agent_safe_sequences`), `ruff check` & `ruff format` clean (`2059 files already formatted`), `mypy` (`Success: no issues found in 1186 source files`), `lint-imports` (`Analyzed 1001 files, 3597 dependencies; Contracts: 2 kept, 0 broken`), `eslint` (`0 errors, 0 warnings`), `tsc -b && vite build` (`✓ built in 1.28s`), and `check_no_dashes` (`0` unicode em/en-dashes).

---

## 3. Artifact Index in `docs/qa/KAN-62/`

- `gemma-and-provider-harness-report.md`: Complete benchmark report with detailed latency, hardware, and accuracy findings.
- `live-fullstack-proof.txt`: Zero-mock live execution telemetry against `kanban-liveqa-2` (`:18962`).
- `unit-test-results.txt`: Verbatim execution outputs for Python pytest (`265 passed`, `31 passed`) and Vitest (`125 passed`).
- `build-or-typecheck.txt`: Verbatim static checks (`ruff`, `mypy`, `lint-imports`, `eslint`, `tsc -b`, `vite build`, `check_no_dashes`).
- `git-diff.patch`: Complete git diff patch from `02c9314c..435b7873c875`.
- `wiki-diff.patch`: Complete wiki diff patch.
- `api-specialist-review.md`: Dual-specialist API and architecture audit signoff (STATUS: APPROVED, commit `435b7873c875`).
- `ui-specialist-review.md`: Dual-specialist UI and layout audit signoff (STATUS: APPROVED, commit `435b7873c875`).
- `screenshots/62-ai-provider-gemini-top-key-probe.png`: Gemini provider registration with masked key and probed models.
- `screenshots/63-ai-provider-ollama-probed-models.png`: Fast GPU Ollama provider registration with probed models.
- `screenshots/64-agent-qa-done-definition.png`: Agent definition registration drawer with probed model quick-picks.
- `screenshots/65-workflow-attach-qa-done-gate.png`: `AttachHookDialog` configuring `require-ai-qa-on-done` with `Allowed Mutable Fields` unclipped above footer.
- `screenshots/66-qa-gate-positive-approved-done.png`: Positive evaluation result (`KAN-1` transitioned to `Done`, `✅🤖 Approved`, formatted HTML headings).
- `screenshots/67-qa-gate-negative-saturn-ice-cream-vetoed.png`: Negative evaluation result (`KAN-2` vetoed in `In Progress`, `🛑🤖 Rejected`, unclipped right-rail `State` `<select>` chevron & border).
- `screenshots/live-qa-gate-positive-tablet.png` & `live-qa-gate-positive-mobile.png`: Positive evaluation tablet & mobile screenshots.
- `screenshots/live-qa-gate-negative-tablet.png` & `live-qa-gate-negative-mobile.png`: Negative evaluation tablet & mobile screenshots.
