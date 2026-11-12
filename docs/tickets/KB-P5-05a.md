---
id: KB-P5-05a
title: '[Phase 5 / Database + Agent] ai_provider_configs (KMS-wrapped keys), ai_token_ledgers & atomic BudgetEnforcer'
epic: KB-E5
depends_on: [KB-P5-04, KB-P4-09a, KB-P4-09b, KB-P2-03, KB-P1-17]
spec_sections: ['10.1', '10.2']
gates: [reality-checker]
new_dependencies: []
state: Backlog
---

> Split note: manifest row `KB-P5-05` is split into `KB-P5-05a` (storage + enforcement, this ticket) and `KB-P5-05b` (REST API + `/mcp/admin` tool 9 providers/budgets actions) to stay within one fast-model session.

### User Story
As an **AI/LLM systems engineer accountable for spend and secret custody**, I need **provider configuration rows whose API keys are envelope-encrypted at rest, plus daily/monthly `ai_token_ledgers` caps enforced by an atomic `BudgetEnforcer` reserve/settle protocol** so that **no concurrent burst of agent calls can exceed a cap and no plaintext provider key ever lands in Postgres, logs, or API responses**.

**Requirement Traceability:** `S10.1 (per-project KMS-wrapped API keys)`, `S10.2 (BudgetEnforcer, ai_token_ledgers daily/monthly caps)`, original requirement `#2` | **Dependencies:** `KB-P5-04`, `KB-P4-09`, `KB-P2-03` (`kanban/security/envelope.py`), `KB-P1-17` (models + RLS session)

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/<rev>_ai_providers_and_ledgers.py` (new Alembic revision)
   - `database/models/ai.py` (new: `AIProviderConfig`, `AITokenLedger`)
   - `kanban/ai_config/service.py` (new: `AIProviderConfigService` create/update/disable/list, key wrap/unwrap)
   - `agent/budget.py` (new: `BudgetEnforcer`)
   - `database/GEMINI.md`, `agent/GEMINI.md` (update)
2. **DDL (spec defines names only; columns below are this ticket's contract):**
   ```sql
   CREATE TABLE ai_provider_configs (
       id               UUID PRIMARY KEY DEFAULT uuidv7(),
       workspace_id     UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
       project_id       UUID REFERENCES projects(id) ON DELETE CASCADE,  -- NULL = workspace default
       provider_kind    TEXT NOT NULL CHECK (provider_kind IN ('openai','ollama','gemini','fixture')),
       display_name     TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 80),
       base_url         TEXT,
       model_allowlist  TEXT[] NOT NULL CHECK (cardinality(model_allowlist) BETWEEN 1 AND 32),
       residency_tier   TEXT NOT NULL CHECK (residency_tier ~ '^[a-z0-9:._-]{1,64}$'),
       priority         SMALLINT NOT NULL DEFAULT 100,
       settings_json    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- non-secret settings only (CIDRs, region, timeouts)
       wrapped_api_key  BYTEA,          -- AES-256-GCM ciphertext||tag
       api_key_nonce    BYTEA,
       wrapped_dek      BYTEA,          -- DEK wrapped by KMS / MASTER_KEK
       dek_kid          TEXT,
       is_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
       created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
       updated_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
       CHECK ((wrapped_api_key IS NULL) = (wrapped_dek IS NULL))
   );
   CREATE TABLE ai_token_ledgers (
       id                 UUID PRIMARY KEY DEFAULT uuidv7(),
       workspace_id       UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
       project_id         UUID REFERENCES projects(id) ON DELETE CASCADE,
       provider_config_id UUID NOT NULL REFERENCES ai_provider_configs(id) ON DELETE CASCADE,
       period_kind        TEXT NOT NULL CHECK (period_kind IN ('daily','monthly')),
       period_start       DATE NOT NULL,
       token_cap          BIGINT NOT NULL CHECK (token_cap >= 0),
       tokens_reserved    BIGINT NOT NULL DEFAULT 0 CHECK (tokens_reserved >= 0),
       tokens_used        BIGINT NOT NULL DEFAULT 0 CHECK (tokens_used >= 0),
       CHECK (tokens_used + tokens_reserved <= token_cap),
       UNIQUE NULLS NOT DISTINCT (workspace_id, project_id, provider_config_id, period_kind, period_start)
   );
   ```
   - Both tables: `ENABLE` + `FORCE ROW LEVEL SECURITY`; `SELECT` policy requires `workspace_id = current_setting('app.workspace_id', true)::uuid` AND caller holds workspace/project `ADMIN` capability (via `effective_resource_access`, bit per KB-P1-14 helpers); `INSERT/UPDATE/DELETE` `WITH CHECK` same admin predicate. Ledger `UPDATE` additionally permitted for the `svc-agent-runtime` service principal (budget accounting only).
   - Column-level privilege: `REVOKE SELECT (wrapped_api_key, api_key_nonce, wrapped_dek) ON ai_provider_configs FROM kanban_app`; unwrap path uses a `SECURITY DEFINER` function `ai_provider_secret(config_id UUID) RETURNS TABLE(wrapped_api_key BYTEA, api_key_nonce BYTEA, wrapped_dek BYTEA, dek_kid TEXT)` granted only to the `agent-runtime` DB role, with `SET search_path = pg_catalog, public` and an internal RLS-equivalent workspace check.
3. **`AIProviderConfigService` (`kanban/ai_config/service.py`):** wraps keys with `kanban/security/envelope.py` (fresh DEK per row, AAD = `config_id || workspace_id || provider_kind`); plaintext key accepted as `bytearray`, zeroed (`for i in range(len(b)): b[i] = 0`) after wrapping; `to_public_dict()` returns `api_key_set: bool` and never ciphertext, nonce, DEK or kid. Saving `openai`/`gemini` while workspace/project `air_gap_mode` is TRUE raises `AirGapViolation(code="AIR_GAP_EGRESS_DENIED")` (reuses `AirGapGuard` semantics; enforced in service, not only in router). `base_url` validated with the same rules as KB-P5-01/KB-P5-03 settings.
4. **`BudgetEnforcer` (`agent/budget.py`):**
   - `reserve(workspace_id, project_id, provider_config_id, estimate_tokens) -> Reservation` executes a single statement per active period (`daily` + `monthly`) inside one transaction:
     `UPDATE ai_token_ledgers SET tokens_reserved = tokens_reserved + :n WHERE <key> AND tokens_used + tokens_reserved + :n <= token_cap RETURNING id`; zero rows for either period -> rollback and raise `BudgetExceeded(code="AI_BUDGET_EXCEEDED", period=...)`. Missing ledger row for a period means no cap for that period (explicit, documented).
   - `settle(reservation, actual_tokens)` moves `min(actual, estimate)` from reserved to used and releases the remainder; `actual > estimate` records the overage into `tokens_used` (never blocked post-hoc) and logs `AI_BUDGET_OVERAGE`.
   - `release(reservation)` on provider failure returns the full estimate.
   - Period boundaries computed in UTC.

### Mandatory Feature Unit Tests
- **Test File(s):** `database/tests/test_ai_tables.py`, `kanban/tests/ai_config/test_service.py`, `agent/tests/test_budget.py`
- **Cassettes (under `tests/fixtures/ai/`):** `budget_usage_48_tokens.yaml` (FixtureLLMProvider stream reporting `usage.total_tokens: 48`), `budget_usage_overage.yaml` (reports `120` against estimate `64`)
- **Required Test Cases:**
  1. Positive: create config with key -> row has ciphertext, `to_public_dict()` has `api_key_set: true`, no key material; unwrap through `ai_provider_secret` yields the original key.
  2. Security: `kanban_app` `SELECT wrapped_api_key` -> permission denied; non-admin principal sees `0` rows (clean-DB `SAVEPOINT` harness from KB-P0-05).
  3. Security: GCM tag tamper (flip 1 byte of `wrapped_api_key`) -> unwrap raises `EnvelopeIntegrityError`.
  4. Security: save `gemini` config with `air_gap_mode=TRUE` -> `AIR_GAP_EGRESS_DENIED`.
  5. Security: plaintext `bytearray` is all zero bytes after `create()` returns.
  6. Budget positive: reserve 64, settle 48 (cassette) -> `tokens_used=48`, `tokens_reserved=0`.
  7. Budget negative: cap 100, used 90, reserve 11 -> `AI_BUDGET_EXCEEDED`; daily OK but monthly exhausted -> exceeded with `period="monthly"`, daily row unchanged (rollback).
  8. Concurrency (`@pytest.mark.committed_db`): 50 concurrent `reserve(10)` against cap `200` -> exactly 20 succeed; `tokens_used + tokens_reserved == 200`.
  9. Fault: provider failure -> `release()` restores reserved to `0`; overage cassette -> `tokens_used=120` and `AI_BUDGET_OVERAGE` logged.
  10. Boundary: reserve exactly to cap succeeds; `cap + 1` fails; period rollover at `00:00:00Z` uses a new daily row.
- **Coverage:** `>= 95%` line + branch for `kanban/ai_config/service.py`, `agent/budget.py`, `database/models/ai.py`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** migration, `database/models/ai.py`, `kanban/ai_config/service.py`, `agent/budget.py` exist and implement the tables, `ai_provider_secret()`, `AIProviderConfigService`, `BudgetEnforcer` as specified.
- [ ] **Schema Proof:** `schema-dump.sql` contains both tables, `FORCE ROW LEVEL SECURITY` for both, the column `REVOKE`, and `ai_provider_secret` as `SECURITY DEFINER`.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest database/tests/test_ai_tables.py kanban/tests/ai_config/test_service.py agent/tests/test_budget.py -q -p no:cacheprovider --cov=kanban.ai_config.service --cov=agent.budget --cov=database.models.ai --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0` with all 10 cases present.
- [ ] **Migration Reversible:** `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run mypy --strict database kanban agent`, `uv run ruff check .`, `uv run lint-imports` each exit `0`.
- [ ] **Forensic Proof Packet Complete:** All files below exist.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
The implementing sub-agent MUST populate `docs/qa/<TICKET_ID>/` with the following raw, unedited artifacts (no summaries) so `reality-checker` can audit the ticket without executing commands:
1. `docs/qa/<TICKET_ID>/git-diff.patch` - Complete unified `git diff`.
2. `docs/qa/<TICKET_ID>/unit-test-results.txt` - Full output and exit code of the DoD pytest command.
3. `docs/qa/<TICKET_ID>/build-check.txt` - Full output of mypy, ruff, lint-imports.
4. `docs/qa/<TICKET_ID>/schema-dump.sql` - `pg_dump --schema-only -t ai_provider_configs -t ai_token_ledgers` plus `\df+ ai_provider_secret` output.
5. `docs/qa/<TICKET_ID>/migration-roundtrip.txt` - Full output of the upgrade/downgrade/upgrade command.
6. `docs/qa/<TICKET_ID>/concurrency-proof.txt` - pytest `-s` output of case 8 printing successes, failures and final ledger totals.
7. Screenshots: N/A - Non-UI Ticket.
