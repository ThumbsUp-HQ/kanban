# UI Specialist Gate Review: KANBA-144 (KB-P5-05b)

- **Auditor**: `@ui-specialist` (Swarm UI & UX Architecture Specialist Gate)
- **Worktree**: `/tmp/kb-wt-KANBA-144`
- **Branch**: `feat/KANBA-144`
- **Ticket**: `KANBA-144` (`KB-P5-05b`: `[Phase 5 / API + MCP] AI provider & budget admin REST API + /mcp/admin manage_ai_and_agent_runners (providers + budgets actions)`)

---

### 1. Executive Summary & Verification Matrix

A comprehensive UI/UX consumer contract audit was conducted for `KANBA-144` in `/tmp/kb-wt-KANBA-144`. `KB-P5-05b` establishes the administrative REST API and MCP Tool 9 interfaces consumed by the AI Settings Workspace & Project configuration panels and LLM agent orchestration harnesses. The wire payloads, error diagnostics, write-only key ergonomics, and LOD projections were audited against Spec Sections 10.2, 11.4, and 6.1.

| Verification Dimension | Specification Target | Observed Status | Verdict |
| :--- | :--- | :--- | :--- |
| **Write-Only Key Ergonomics** | Never echo raw secret key; return `api_key_set: bool` | Verified: `api_key_set: true/false` returned; raw keys and `wrapped_*` fields completely omitted | PASS |
| **Air-Gap Egress Feedback** | Actionable diagnostic on cloud egress denial | Returns HTTP 409 `AIR_GAP_EGRESS_DENIED` with explicit message regarding prohibited cloud outbound | PASS |
| **SSRF / Host Validation** | Clear guidance on illegal base URL | Returns HTTP 422 `INVALID_BASE_URL` highlighting loopback/metadata restrictions | PASS |
| **Timing-Equalized 404** | Anti-enumeration defense for unreadable/absent IDs | Returns identical 404 `NOT_FOUND` shape with 25.0ms timing floor | PASS |
| **LOD Output Structure** | Dense `summary`, operational `standard`, full `full` | MCP Tool 9 yields clean YAML without null fields across all 3 tiers | PASS |
| **Deferred Tool Action Guidance** | Structured feedback for future capabilities | Returns structured `ACTION_NOT_AVAILABLE` with roadmap ticket references (`KB-P5-16`, `KB-P5-22`) | PASS |
| **Screenshots Compliance** | N/A - Non-UI Ticket | Confirmed Non-UI ticket (API & MCP layer; Admin UI out of scope); verified in `contract-sample.json` | PASS |
| **Typography Compliance** | Plain ASCII hyphens `-` only | Strictly plain ASCII hyphens used throughout all code, schemas, and reviews | PASS |

---

### 2. Frontend Consumer Contract & Ergonomics Analysis

1. **Write-Only Key Custody (`ProviderConfigPublic`):**
   - The frontend Admin UI needs to indicate whether an API key is currently configured without ever displaying or fetching the actual secret.
   - The schema provides `api_key_set: bool`:
     ```json
     {
       "id": "01932c56-789a-7bc0-81d2-abcdef012345",
       "provider_kind": "openai",
       "display_name": "Production OpenAI",
       "api_key_set": true,
       "is_enabled": true
     }
     ```
   - In the frontend form:
     - When `api_key_set: true`, the input displays a password placeholder (`●●●●●●●● (configured)`) with a `[Clear Key]` toggle.
     - Submitting `PATCH` with omitted `api_key` preserves the existing key (`api_key_set: true`).
     - Submitting `PATCH` with `"api_key": null` clears the key (`api_key_set: false`).
     - Submitting a new string updates the key without ever reading back raw ciphertext.
   - This contract eliminates accidental client-side secret leakage or clipboard exposure.

2. **Air-Gap Outbound Egress Prevention (`AIR_GAP_EGRESS_DENIED`):**
   - When air-gap mode is active in the workspace, configuring or enabling an external cloud provider (`openai`, `gemini`) returns:
     ```json
     {
       "type": "https://errors.kanban.local/ai/air-gap-egress-denied",
       "title": "Air Gap Egress Denied",
       "status": 409,
       "detail": "Outbound cloud egress to provider 'openai' is denied under air-gap mode",
       "code": "AIR_GAP_EGRESS_DENIED"
     }
     ```
   - The UI can display a dedicated air-gap warning badge advising the administrator to select a local LLM runner (`ollama` or `fixture`).

3. **SSRF Link-Local / Metadata Protection (`INVALID_BASE_URL`):**
   - Attempting to configure cloud metadata addresses (e.g. `http://169.254.169.254`) yields an immediate, readable validation error:
     ```json
     {
       "type": "https://errors.kanban.local/validation-error",
       "title": "Invalid Base URL",
       "status": 422,
       "detail": "base_url must not target link-local or metadata address '169.254.169.254'",
       "code": "INVALID_BASE_URL"
     }
     ```
   - This clear error message maps directly to form field validation markers in the frontend settings view.

4. **MCP Tool 9 Ergonomics (`manage_ai_and_agent_runners`):**
   - Output utilizes compact YAML formatting via `InlineSafeDumper` with `strip_nulls=True`, avoiding token bloat when consumed by autonomous agents.
   - The `summary` LOD focuses on operational metrics (`token_cap`, `tokens_used`, `tokens_reserved`), minimizing agent context window consumption.
   - Actions reserved for future milestones (`mint_runner_enrollment_token`, `upsert_agent_definition`, `list_agent_definitions`) yield actionable `ACTION_NOT_AVAILABLE` faults, allowing orchestrators to adapt gracefully.

---

### 3. Verdict

**Verdict: APPROVED**
The REST API schemas and MCP Tool 9 interfaces provide clean, predictable, and secure contracts for frontend and agent consumers. Ready for production verification.
