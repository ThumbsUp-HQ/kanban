# API Specialist Gate Review: KANBA-146 (KB-P5-15)

- **Ticket**: `KANBA-146` (`KB-P5-15`: `[Phase 5 / Web UI] Custom fields UI: 🧪 rail display with refresh, admin definition editor & AAL2 approval flow`)
- **Reviewer**: API Specialist (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Worktree**: `/tmp/kb-wt-KANBA-146`
- **Branch**: `feat/KANBA-146`

## REST & Execution Wire Contract Audit

1. **Endpoint Consumption Alignment**:
   - `GET /api/v1/projects/{project}/custom-fields`: Correctly retrieves project-scoped definitions visible to caller.
   - `GET /api/v1/issues/{issue_key}/custom-fields`: Retrieves cached execution results (`last_latency_ms`, `tier`, `token_scope`, `credential_mode`).
   - `POST /api/v1/issues/{issue_key}/custom-fields/{field_id}/execute`: Triggers on-demand re-execution with in-flight deduplication.
   - `POST|PATCH /api/v1/projects/{project}/custom-fields`: Enforces admin-only mutation with cryptographic `manifest_sha256` recalculation.
   - `POST /api/v1/custom-fields/{field_id}/approval-requests` and `POST /api/v1/custom-field-approvals/{approval_id}/approve`: Implements two-stage escalation approval flow.

2. **Error Code Mapping & Sanitization**:
   - Explicitly maps server error codes without exposing raw server detail strings:
     - `SCRIPT_TIMEOUT` -> `Timed out`
     - `SCRIPT_FUEL_EXHAUSTED` -> `Compute limit reached`
     - `APPROVAL_REVOKED` -> `Approval revoked - admin re-sign required`
     - `SANDBOX_UNAVAILABLE_IN_STANDALONE` -> `Tier B unavailable in standalone`
     - Fallback / Unknown -> `Unavailable`
   - Zero raw HTML sinks; no `dangerouslySetInnerHTML` in client bundles.

3. **AAL2 Step-Up & Re-auth Flow**:
   - Verifies handling of HTTP 403 with code `AAL2_REQUIRED`.
   - Triggers WebAuthn/TOTP step-up authentication and safely retries the approval operation.
   - Handles HTTP 409 `MANIFEST_MISMATCH` by disabling approval action and notifying admin of script drift.

4. **Anti-Enumeration Integrity**:
   - Non-admin callers attempting to access `/projects/:projectKey/settings/custom-fields` receive a uniform 404 response (`not-found-view`), preventing enumeration of admin endpoints.

VERDICT: APPROVED
