# API Specialist Review: KANBA-124 (KB-P3-43)

- **Reviewer:** Backend Architect / API Specialist (`backend-architect`)
- **Ticket ID:** `KANBA-124` (`KB-P3-43`)
- **Component:** Ticket Header & Overflow Actions API Clients (`actionsApi.ts`)
- **Audit Date:** 2026-11-12
- **Audit Status:** APPROVED (Grade A)

---

## Technical Audit Findings

### 1. Concurrency Control with `Kb-Blast-Hash` (Spec S12.3)
- The delete action dispatches `DELETE /api/v1/issues/{issue_ref}` with the required `Kb-Blast-Hash: <blast_hash>` header obtained from `fetchDeletePreview`.
- When the far endpoint returns `412 BLAST_RADIUS_CHANGED`, the client parses the RFC 7807 response, displays an inline warning banner informing the user that the graph changed, and invalidates the preview query to fetch the new `blast_hash` and updated counts.
- Re-confirmation requires the user to explicitly acknowledge the revised graph impacts with the new hash.

### 2. Server-Authoritative Canonical URL (Spec S7.2 8m)
- The Link and Object Graph surface does not attempt to client-side guess or string-interpolate canonical URLs. It calls `GET /api/v1/objects/{object_ref}/canonical-url` which returns the authoritative `{ url, markdown }`.
- Global keyboard chord `Cmd/Ctrl+Shift+C` copies `[KEY](canonical_url)` with live screen-reader feedback (`aria-live="polite"`).

### 3. Masked Restricted Endpoint Isolation (Spec S7.2 8m)
- When inbound or outbound links return endpoints marked with `restricted: true`, the UI strictly renders `🔒 Restricted Object`.
- Zero IDs, database UUIDs, titles, or entity keys are rendered or leaked into DOM attributes.

### 4. Subscription & Granular Mute Allowlist (Spec S7.2 8l)
- The subscription toggle uses `PUT /api/v1/issues/{issue_ref}/subscription` to subscribe, `DELETE` to unsubscribe, and `PATCH` with `{ muted_event_types: string[] }` for individual notification silencing.
- The 7 event types conform strictly to the server allowlist: `COMMENT_CREATED`, `ISSUE_STATE_CHANGED`, `ISSUE_FIELD_CHANGED`, `ISSUE_DESCRIPTION_CHANGED`, `ISSUE_LABELS_CHANGED`, `ASSIGNEE_ADDED`, `ASSIGNEE_REMOVED`.

### 5. Type Safety & Invariants
- Zero `any` types across `actionsApi.ts`. All endpoints use strictly typed OpenAPI wrapper `untypedApiFetch<T>`.
- Error mapping handles RFC 7807 problem details gracefully.

---

## Verdict
APPROVED without reservations. Meets all API contracts, security boundaries, and concurrency requirements.
