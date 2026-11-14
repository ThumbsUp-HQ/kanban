# Forensic QA Handoff: KANBA-142 (KB-P5-05a)

## Ticket Overview
- **Ticket ID:** `KANBA-142` (`KB-P5-05a`)
- **Title:** `[Phase 5 / Database + Agent] ai_provider_configs (KMS-wrapped keys), ai_token_ledgers & atomic BudgetEnforcer`
- **Spec Sections:** S10.1 (per-project KMS-wrapped API keys), S10.2 (BudgetEnforcer, ai_token_ledgers daily/monthly caps)
- **Gates:** `reality-checker`
- **Target Branch:** `feat/KANBA-142`

---

## Implemented Components

### 1. Database Migrations & Schemas
- `database/migrations/versions/p5_05a_ai_providers_and_ledgers.py`: Alembic revision linked to down revision `p6_01_import_entity_mappings`.
- `database/migrations/sql/p5_05a_ai_providers_and_ledgers.up.sql`:
  - `ai_provider_configs`: Stores LLM provider configurations with envelope-encrypted API keys (`wrapped_api_key`, `api_key_nonce`, `wrapped_dek`, `dek_kid`). Column privileges explicitly revoked from `kanban_app` and `app_rls_reader`.
  - `ai_token_ledgers`: Tracks daily and monthly token allocations with `CHECK (tokens_used + tokens_reserved <= token_cap)` and `UNIQUE NULLS NOT DISTINCT (workspace_id, project_id, provider_config_id, period_kind, period_start)`.
  - `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` on both tables with admin-only policies and service principal access for ledger updates.
  - `ai_provider_secret(p_config_id UUID)`: Security Definer unwrap function granted strictly to `"agent-runtime"` with tenant workspace isolation.
  - `app_agent_runtime_principal()`: Resolves `svc-agent-runtime` service principal.
- `database/migrations/sql/p5_05a_ai_providers_and_ledgers.down.sql`: Fully reversible teardown.

### 2. SQLAlchemy ORM Models
- `database/models/ai.py`: Implements `AIProviderConfig` and `AITokenLedger`.
- `database/models/__init__.py`: Exports both models.
- `database/tests/test_p1_17_models.py`: Model table parity count updated from 62 to 64.

### 3. AI Provider Configuration Service
- `kanban/ai_config/service.py`:
  - `AIProviderConfigService`: create, update, disable, delete, get, list.
  - Envelope encryption via `kanban/security/envelope.py` using fresh DEK per row, AAD = `config_id || workspace_id || provider_kind`.
  - Plaintext key accepted as `bytearray`, zeroed in-place (`for idx in range(len(api_key)): api_key[idx] = 0`).
  - Air-gap enforcement: saving `openai` or `gemini` under `air_gap_mode=True` raises `AirGapViolation(code="AIR_GAP_EGRESS_DENIED")`.
  - `to_public_dict()`: returns `api_key_set: bool`, zero secret leakage.
  - `base_url` validation: scheme, no userinfo/query/fragment, HTTPS required for non-loopback.

### 4. Token Budget Enforcer
- `agent/budget.py`:
  - `BudgetEnforcer`: implements atomic reserve, settle, and release protocol.
  - Single-statement atomic update with fail-closed rollback raising `BudgetExceeded(code="AI_BUDGET_EXCEEDED", period="daily"|"monthly")`.
  - `settle()`: moves tokens from reserved to used; overages recorded and log `AI_BUDGET_OVERAGE`.
  - `release()`: restores reserved tokens to zero on provider failure.
  - UTC period boundaries (`daily` at `YYYY-MM-DD`, `monthly` at `YYYY-MM-01`).

### 5. Documentation Manifests
- `database/GEMINI.md`: Updated model count (64) and migration manifest.
- `agent/GEMINI.md`: Added Token Budget Enforcer section.

---

## Mandatory Feature Test Verification

All 10 required test cases are implemented and passing across 3 test files:

| Test Case | Description | File | Result |
| :--- | :--- | :--- | :--- |
| Case 1 | Positive: create config with key, ciphertext present, to_public_dict has api_key_set: true, unwrap yields key | `kanban/tests/ai_config/test_service.py` & `database/tests/test_ai_tables.py` | PASSED |
| Case 2 | Security: kanban_app SELECT wrapped_api_key fails closed; non-admin sees 0 rows | `database/tests/test_ai_tables.py` | PASSED |
| Case 3 | Security: GCM tag tamper (flip 1 byte) raises EnvelopeIntegrityError | `kanban/tests/ai_config/test_service.py` | PASSED |
| Case 4 | Security: save gemini/openai with air_gap_mode=TRUE raises AirGapViolation | `kanban/tests/ai_config/test_service.py` | PASSED |
| Case 5 | Security: plaintext bytearray is all zero bytes after create() returns | `kanban/tests/ai_config/test_service.py` | PASSED |
| Case 6 | Budget positive: reserve 64, settle 48 (cassette) -> tokens_used=48, tokens_reserved=0 | `agent/tests/test_budget.py` | PASSED |
| Case 7 | Budget negative: cap 100, used 90, reserve 11 -> AI_BUDGET_EXCEEDED; daily unchanged | `agent/tests/test_budget.py` | PASSED |
| Case 8 | Concurrency (@pytest.mark.committed_db): 50 concurrent reserve(10) against cap 200 -> exactly 20 succeed | `agent/tests/test_budget.py` | PASSED |
| Case 9 | Fault: release() restores reserved to 0; overage cassette logs AI_BUDGET_OVERAGE | `agent/tests/test_budget.py` | PASSED |
| Case 10 | Boundary: reserve exactly to cap succeeds; cap+1 fails; 00:00:00Z uses new daily row | `agent/tests/test_budget.py` | PASSED |

### Coverage Gate
- Required: `>= 95%` line + branch
- Achieved:
  - `agent/budget.py`: 100% coverage
  - `database/models/ai.py`: 100% coverage
  - `kanban/ai_config/service.py`: 99% coverage
  - Total Target Coverage: 99.10% (347 statements, 2 missed, 98 branches, 2 partial)

---

## Forensic Audit Artifacts in `docs/qa/KANBA-142/`
1. `git-diff.patch`: Unified diff of all changes against base commit.
2. `unit-test-results.txt`: Raw output and exit code 0 of DoD pytest command.
3. `build-check.txt`: Raw output of mypy --strict, ruff check, and lint-imports (all exit code 0).
4. `schema-dump.sql`: pg_dump of ai_provider_configs and ai_token_ledgers plus \df+ ai_provider_secret.
5. `migration-roundtrip.txt`: Full output of upgrade head / downgrade -1 / upgrade head.
6. `concurrency-proof.txt`: Raw output of pytest -s for test_08 printing workers=50 successes=20 failures=30 total_allocated=200.
7. Screenshots: N/A (Non-UI ticket).
