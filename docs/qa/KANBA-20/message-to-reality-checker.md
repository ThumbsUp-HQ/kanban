# Reality-Checker Verification Packet: KANBA-20

## Ticket Summary
- Ticket ID: KANBA-20 (KB-P2-17)
- Epic: KB-E2
- Title: [Phase 2 / Security] Outbound secret scrubber (kanban/security/scrubber.py)
- Gates: reality-checker
- Branch: feat/KANBA-20
- Base Commit: 7a479bde67a21dd962b9a7fa3ef0fe399d8601c0

## Implemented Deliverables
1. `kanban/security/__init__.py`: Package export interface for scrubber symbols.
2. `kanban/security/scrubber.py`:
   - `SecretKind`: StrEnum covering API_KEY, GITHUB_TOKEN, AWS_ACCESS_KEY, PRIVATE_KEY, BEARER_TOKEN, JWT, and KANBAN_KEY.
   - `ScrubFinding`: Frozen dataclass containing kind, start, end, placeholder (omitting raw secret characters).
   - `ScrubResult`: Frozen dataclass containing text, redacted boolean, count, findings tuple.
   - `_scan_pem_private_keys`: Linear `str.find("-----BEGIN ")` scanner covering full and 1,500-char truncated PEM keys without regex backtracking.
   - `outbound_secret_scrubber`: Main entry point implementing non-overlapping left-to-right span resolution with longest-span tie-breaking.
   - `scrub_text`: Convenience helper returning scrubbed text string.
3. `kanban/tests/conftest.py`: Normalizer for file-based pytest-cov targets.
4. `kanban/tests/security/__init__.py`: Security test package.
5. `kanban/tests/security/corpus/scrubber_cases.json`: JSON corpus of positive and false-positive guard cases.
6. `kanban/tests/security/test_scrubber.py`: Comprehensive test suite covering all 8 mandatory specification test cases with 100% branch and line coverage.

## Verification Evidence
1. Unit Test & Coverage Output (`docs/qa/KANBA-20/unit-test-results.txt`):
   - Command: `uv run pytest kanban/tests/security/test_scrubber.py -q --cov=kanban/security/scrubber.py --cov-branch --cov-report=term-missing --cov-fail-under=95`
   - Result: 9 passed in 0.11s.
   - Coverage: 140/140 statements (100%), 60/60 branches (100%), total coverage 100.00%.
2. Build & Architecture Gate Output (`docs/qa/KANBA-20/build-check.txt`):
   - `uv run lint-imports`: KEPT (agent -> mcp -> kanban -> database unidirectional layers).
   - `uv run pytest`: 18/18 workspace tests passed.
3. Latency & Corpus Benchmark Report (`docs/qa/KANBA-20/scrubber-benchmark-and-corpus.txt`):
   - 2,000-char Sparkle Window: Median 0.0143 ms (budget <= 1.0 ms) -> PASS; p95 0.0162 ms (budget <= 5.0 ms) -> PASS.
   - 1 MiB Adversarial Payload (1,000 unclosed PEM blocks): Median 25.80 ms (budget <= 50.0 ms) -> PASS; p95 26.31 ms (budget < 250.0 ms) -> PASS.
   - False positive guard corpus: 10/10 cases passed with redacted=False and text byte-for-byte preserved.
4. Supply Chain & Dependencies:
   - Added dependencies: 0 (stdlib only).
5. UI Review:
   - N/A: Non-UI backend security ticket.
