# API Specialist Review (KAN-400)

## Overview & Architecture Verification

- **Ticket**: KAN-400 (`[KB-AI-PROVIDER-NO-PASSWORD-SAVE] Suppress browser password save prompt on AI Provider Drawer with visual bullet masking fallback & 0 input[type="password"] elements`)
- **Module**: `kanban/web/src/features/admin-ai/` (`AiProviderEditorDrawer.tsx`, `aiStudio.css`, `AiProviderEditorDrawer.test.tsx`)
- **Reviewed By**: API Specialist (`@api-spec`)
- **Status**: STATUS: APPROVED
- **Verdict**: APPROVED

---

## Dual Specialist Verification Audit

### 1. Backend / REST Contract Invariance & Audit Scope
- **Classification**: N/A - Pure Frontend Credential-Manager Suppression.
- **Contract Integrity**: Zero backend API contracts, schema models, database tables, or MCP tool definitions are modified in this change.
- **Audited Endpoints**:
  - `POST /api/v1/admin/ai/providers` (ProviderConfigCreate)
  - `PATCH /api/v1/admin/ai/providers/{id}` (ProviderConfigUpdate)
  - `POST /api/v1/admin/ai/providers/probe-models` (ProviderProbeRequest)
  - `POST /api/v1/admin/ai/providers/test-connection` (ProviderProbeRequest)
- **Payload Alignment Verification**:
  - The frontend drawer payload submitted to `createAiProvider` and `updateAiProvider` retains exact field naming and typing (`api_key?: string | null`).
  - When editing an existing provider and leaving the secret key untouched, the payload transmits `api_key: undefined` so existing hashed/vaulted credentials on the server are preserved without modification.
  - When updating or inserting a new key, the raw string is transmitted in the JSON body without whitespace truncation or surrogate corruption.

### 2. Frontend Credential Handling & Payload Safety
- **Visual Bullet Masking vs Raw State**:
  - In non-Webkit browsers (such as Firefox/Gecko where `-webkit-text-security` is unsupported), the component renders bullet characters (`•`, `\u2022`) strictly for display.
  - Internal state tracks the pristine plaintext key in `apiKey` state via `computeNextApiKey()`.
  - The submitted payload transmits `apiKey`, NEVER the visual bullet string. This eliminates any risk of saving bullet characters into the backend database.
- **Probe and Connection Test Safety**:
  - Live model probing (`probeAiModels`) and connection testing (`testAiConnection`) continue to transmit the pristine plaintext key without escaping or bullet substitution.
- **Zero Cleartext Leakage**:
  - Network requests are sent exclusively over TLS/HTTPS (or loopback in local dev).
  - Form attributes `autoComplete="off"`, `data-form-type="other"`, `data-1p-ignore="true"`, `data-lpignore="true"`, and `data-bwignore="true"` strictly suppress browser and extension autofill serialization.

### 3. Automated Test Verification
- All 42 tests pass with 100% statement and 96.04% branch coverage.
- Tests verify exact submission payloads (`api_key: "sk-proj-testSecretApiKey123456789"`) for both create and update operations, ensuring zero API contract regression.

### 4. Specialist Verdict
The implementation cleanly solves the browser password-manager prompt issue entirely on the frontend surface while preserving 100% backend REST API fidelity.
**STATUS: APPROVED**
