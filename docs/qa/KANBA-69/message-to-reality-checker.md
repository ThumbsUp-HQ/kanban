# Message to Reality-Checker: KANBA-69 (KB-P4-03)

### Ticket Overview
- Ticket ID: `KANBA-69` (`KB-P4-03`)
- Epic: `KB-E4` (Phase 4 MCP Server)
- Title: `[Phase 4 / MCP] EntityResolver, InlineSafeDumper YAML, summary/standard/full LOD tiers & JIT help`
- Branch: `feat/KANBA-69` in `/tmp/kb-wt-KANBA-69`
- Author: `builder-19`

### Verification Summary
1. **Resolution Service & HTTP Route**:
   - `kanban/resolve/service.py`: `ResolutionService` implements resolution for `project`, `issue`, `state`, `user`, `cycle`, `module`, `label`, and extensible `register_provider("hook", ...)`.
   - Direct RFC 4122 UUID fast-path with RLS enforcement.
   - `me` keyword resolves to caller's principal ID.
   - `404 Not Found` timing-equalized via `timing_floor` for missing or unreadable entities (preventing principal enumeration).
   - `409 Conflict` with `candidates` list (up to 5 items) returned on ambiguous references.
   - `MODULES_DISABLED` returned when resolving module on projects with `modules_enabled=False`.
   - Input length validation (<= 200 chars) and ASCII control-character rejection (HTTP 422).
   - `kanban/api/v1/resolve.py`: `GET /api/v1/resolve` endpoint mounted in `build_v1_router()` with 25.0ms timing floor.

2. **Client-side EntityResolver**:
   - `mcp/resolver.py`: Request-scoped memoization cache `_cache: dict[tuple[str, str, str | None], ResolvedRef]` and batch resolution via `resolve_many()`.

3. **InlineSafeDumper & YAML Formatter**:
   - `mcp/yaml_out.py`: Clean, human-legible, token-dense YAML serializer.
   - `strip_empty=True` prunes empty collections and nulls while strictly preserving boolean `False` and integer `0`.
   - Small mappings and scalar lists (<= 4 items) serialized as compact inline flow style (`[a, b]`, `{k: v}`).
   - Multiline strings use `|` literal block style.
   - Non-primitive types raise `TypeError`; zero `!!python` object tags permitted.

4. **LOD (Level of Detail) Projections**:
   - `mcp/lod.py`: `Lod` enum (`summary | standard | full`).
   - Field projections for `issue`, `doc`, `sticky`, and `project`.
   - Provenance (`created_by`, `updated_at`, etc.) and access manifests only exposed at `full` tier.

5. **Token Efficiency Benchmark**:
   - `mcp/bench/token_benchmark.py` running on `mcp/tests/fixtures/issues_raw_rest.json` (20 issues):
     * Raw REST JSON tokens: 13,651
     * LOD summary YAML tokens: 671
     * Measured token reduction: 95.08% (exceeds >= 78% requirement)
   - Logged to `docs/qa/KANBA-69/token-benchmark.txt`.

6. **JIT Help & MCP Protocol Integration**:
   - `mcp/help.py`: `build_help()` retrieves live project workflow states, cycles, modules, priorities, and labels.
   - `mcp/protocol.py`: Progressive disclosure intercept for `identifier="help"` or `action="help"`.
   - Ambiguous tool invocations return `AMBIGUOUS_IDENTIFIER` with candidates list in YAML.
   - Session transcript captured in `docs/qa/KANBA-69/mcp-transcript.txt`.

7. **Test Coverage & Verification**:
   - 33 passing tests in 2.33s across 5 test suites.
   - Branch and line coverage: 97.63% (exceeds >= 95% threshold).
   - Static analysis: Ruff clean, Ruff format clean, Mypy strict clean across 68 files, Import Linter clean (2 kept, 0 broken), License check clean (110 Python, 1 Node, 0 violations), Dash check clean (0 non-ASCII dashes).
