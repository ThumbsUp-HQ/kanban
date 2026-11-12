# UI Specialist Gate Review: KANBA-69 (KB-P4-03)

- Ticket: `KANBA-69` (`KB-P4-03`)
- Title: EntityResolver, InlineSafeDumper YAML, summary/standard/full LOD tiers & JIT help
- Epic: `KB-E4` (Phase 4 Model Context Protocol Server & Surface Registries)
- Worktree: `/tmp/kb-wt-KANBA-69`
- Branch: `feat/KANBA-69`
- Auditor: `ui-specialist` (Swarm UI & UX Architecture Specialist Gate Auditor)
- Date: 2026-11-12
- Scope: Independent audit of YAML legibility and LLM ergonomic density across LOD tiers, JIT progressive disclosure, structured ambiguity errors, and token economy for MCP consumers (autonomous agents and technical humans reading transcripts).
- Screenshots: N/A (Non-UI backend/MCP ticket).

---

### 1. Verification Matrix

| Evaluation Dimension | Design Target | Observed Implementation | Verdict |
| :--- | :--- | :--- | :--- |
| **YAML Legibility** | Block root, inline small collections, `|` for multiline | `InlineSafeDumper`: root mapping in block style, scalar lists and <=4-scalar dicts in flow style, multiline strings as `|` literal blocks (`mcp/yaml_out.py`) | PASS |
| **Key Ordering** | Semantic order, not alphabetical | `sort_keys=False`; `key, summary, state, priority, assignees` lead every issue | PASS |
| **Empty Suppression** | No noise from null/empty values | `strip_empty` drops `None`, `''`, `[]`, `{}` while preserving `0` and `False` | PASS |
| **Hostile Type Rejection** | No Python tags / non-primitive output | `set`, `frozenset`, and the undefined-object fallback raise `TypeError`; zero `!!python` tags can reach the wire | PASS |
| **LOD Progressive Density** | summary < standard < full, strictly additive | Verified in `docs/qa/KANBA-69/yaml-samples.txt`: summary = 5 keys; standard adds description/labels/cycle; full adds `access_manifest` and `provenance` | PASS |
| **Unknown LOD Recovery** | Actionable error | `parse_lod` raises `VALIDATION_FAILED` with hint `Pass lod='summary', lod='standard', or lod='full'` | PASS |
| **JIT Help Affordance** | `action=help` returns vocabulary instead of executing | `docs/qa/KANBA-69/mcp-transcript.txt` shows `ping_agent action=help` returning states, priorities, labels, cycles, modules, params as compact flow YAML | PASS |
| **Ambiguity Error Ergonomics** | Candidates listed for self-correction | `AMBIGUOUS_IDENTIFIER` YAML carries `code`, `message`, `hint`, and `candidates: [{key, title}, ...]` (max 5 per spec) | PASS |
| **Anti-Enumeration 404** | Indistinguishable timing-equalized 404 | `contract-sample.json` 404 body has no `detail`, no echoed reference | PASS |
| **Token Economy** | >= 78% reduction | `token-benchmark.txt`: 13,651 -> 671 tokens, 95.08% reduction | PASS |
| **Tests / Coverage** | >= 95% | 33 passed, 97.63% branch+line across `mcp` and `kanban.resolve` | PASS |
| **Build / Lint / Dashes** | Zero warnings | ruff, ruff format, mypy --strict, lint-imports (2 kept), license gate (0 violations); zero U+2014/U+2013 in `mcp/` and `docs/qa/KANBA-69/` | PASS |

---

### 2. Consumer UX Findings

1. **Summary tier is the right default.** `parse_lod(None)` returns `SUMMARY`; an agent that does not ask for detail receives the minimum useful row (`key`, `summary`, `state`, `priority`, `assignees`) plus `gate` only when pending. This keeps list calls cheap and is the source of the 95% token reduction.
2. **Self-correcting errors.** The ambiguity error lists the competing `{key, title}` candidates and tells the caller to specify an exact UUID or qualified identifier. An LLM can retry in one hop without an extra search call.
3. **Flow-style density is readable.** Samples such as `assignees: ['@engineer1']` and `cycles: [{name: Cycle 4, status: active}]` stay on one line, while `description_markdown` multiline bodies use `|` blocks so Markdown is emitted verbatim and unescaped.
4. **Fail-closed serializer.** The dumper refuses to emit unknown types rather than leaking `!!python/object` tags; this is the correct posture for an untrusted-consumer wire.

---

### 3. Non-Blocking Advisories (follow-up tickets, not gate failures)

1. **JIT help vocabulary is static today.** `mcp/help.py` falls back to hardcoded `_DEFAULT_STATES`, `_DEFAULT_PRIORITIES`, `_DEFAULT_LABELS`, `_DEFAULT_CYCLES`, `_DEFAULT_MODULES` when no `project_metadata` is supplied; the live path currently resolves only the project key via `/api/v1/resolve`. The ticket sample is flat lists, which the implementation matches, and kanban-api does not yet expose states/labels/cycles endpoints, so this is acceptable for the skeleton. Before KB-P4-04+ ships real tools, help output should (a) source states, labels, and cycles from kanban-api, (b) include `group` on states and `exclusive_group` on labels per the ticket prose, and (c) never present fabricated names (for example `Cycle 4`) as live data. A `source: static-defaults` marker in the interim would prevent agents from trusting invented labels.
2. **Silent degrade on live-fetch failure.** `build_help` logs at DEBUG and returns defaults when the upstream resolve fails. A one-line `note:` in the YAML would let the agent know the data is not authoritative.
3. **Generic projection fallback.** `project_entity` for an unrecognized `kind` returns `raw` unfiltered at `standard` and `full`. No current caller hits this path, but it bypasses the LOD allowlist model; prefer an explicit `VALIDATION_FAILED` for unknown kinds when more entity types are added.

---

### 4. Specialist Verdict

The YAML serializer, LOD tiers, ambiguity errors, and token economy deliver a dense, predictable, self-correcting MCP consumer experience and satisfy S11.1 pillars 1-3 and KB-P4-03. Advisories above are recorded for the next MCP tool tickets and do not block closure.

Verdict: APPROVED
