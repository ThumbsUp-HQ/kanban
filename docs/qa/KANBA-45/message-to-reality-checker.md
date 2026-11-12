# Forensic Verification Handoff: KANBA-45 (KB-P5-04)

## Ticket Overview
- Ticket ID: `KANBA-45` (`KB-P5-04`)
- Title: [Phase 5 / Agent] Provider router, per-(workspace, provider) circuit breakers & air-gap enforcement
- Author: `builder-19`
- Branch: `feat/KANBA-45`
- Worktree: `/tmp/kb-wt-KANBA-45`
- Applicable Spec Sections: `S10.2`, `S15.2`, `S15.3`

---

## Scoped Definition of Done Audit Matrix

| Requirement | Implementation Detail | Audit Artifact | Status |
|:---|:---|:---|:---:|
| **File Existence & Implementation** | `agent/providers/circuit_breaker.py`, `agent/providers/air_gap.py`, `agent/providers/router.py` | `git-diff.patch` | PASS |
| **Cassettes Present** | All 6 router cassettes created under `tests/fixtures/ai/` | `tests/fixtures/ai/router_*.yaml` | PASS |
| **Unit Tests Passing & Coverage** | 30 unit tests covering all 12 mandatory cases; 98.91% branch+statement coverage (>= 95% mandate); zero live sockets | `unit-test-results.txt` | PASS |
| **Build, Type, Lint & Layer Clean** | `mypy --strict agent` (0 errors), `ruff check agent` (0 errors), `ruff format --check` (clean), `lint-imports` (1 kept, 0 broken) | `build-check.txt` | PASS |
| **CLI Validation** | (a) Gemini with `--air-gap` exits 2 with `AIR_GAP_EGRESS_DENIED`<br>(b) Router with `--route fixture,fixture` and fault 503 cassette exits 0 with route trace | `cli-run.txt` | PASS |
| **Breaker State Transitions Trace** | Pytest -s trace of case 2 showing state transitions with fake-clock timestamps | `breaker-state-trace.txt` | PASS |
| **Supply Chain & Dependencies** | No new runtime dependencies; 0 license violations across 92 Python packages and 1 Node package | `scripts.license_gate` | PASS |
| **Zero Non-ASCII Dashes** | Repository-wide verification of zero U+2014 or U+2013 unicode characters | Verification script | PASS |

---

## Key Technical Decisions & Invariants
1. **Per-(Workspace, Provider) 3-State Breaker**:
   - States: `CLOSED`, `OPEN`, `HALF_OPEN`.
   - Threshold: 5 consecutive availability failures trips to `OPEN`.
   - Cooldown: 30s default; extended by `Retry-After` header on 429 up to 300s cap.
   - Half-Open Probe: Exactly 1 probe call admitted after cooldown. Success resets failures to 0 (`CLOSED`); failure restarts cooldown (`OPEN`).
   - Content/policy errors (`ProviderSchemaError`, `ProviderSafetyBlock`, `ProviderRefusal`, `ProviderPolicyError`) do not increment failure counter.
2. **Fail-Closed Air-Gap Guard**:
   - Unknown or `None` air-gap mode treated as `True` (fail-closed).
   - Only `ollama` (local loopback/CIDR pinned) and `fixture` permitted under air-gap.
   - `gemini` and `openai` rejected with `AIR_GAP_EGRESS_DENIED` before DNS resolution or transport.
3. **Residency-Locked Provider Routing**:
   - Priority-ordered candidates; first healthy candidate locks the request's residency tier.
   - Failover candidates must strictly match the residency tier (cloud never fails over across vendor tiers; air-gapped workloads never fail over to cloud).
   - Max 3 attempts per request.
   - Streaming failover allowed strictly before first chunk; faults during streaming propagate immediately without multi-model generation mixing.
   - TTFT deadline enforced with `asyncio.timeout`; breaches invoke `aclose()` and count as availability failure.

---

## Raw Audit Artifacts Location (`docs/qa/KANBA-45/`)
1. `docs/qa/KANBA-45/git-diff.patch`
2. `docs/qa/KANBA-45/unit-test-results.txt`
3. `docs/qa/KANBA-45/build-check.txt`
4. `docs/qa/KANBA-45/breaker-state-trace.txt`
5. `docs/qa/KANBA-45/cli-run.txt`
6. `docs/qa/KANBA-45/message-to-reality-checker.md`
