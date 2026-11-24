# API & Backend Specialist Gate Review: KAN-390

## Review Overview
- **Ticket ID:** KAN-390
- **Feature Name:** [KB-MCP-MINT-MODAL-SIMPLIFY] Move Capability Ceiling into Advanced & Merge Key Type + Scope Tier into Single Unified Selector in Mint New MCP Access Key Modal
- **Auditor Role:** Backend & API Architecture Specialist
- **Specification:** [`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`](file:///home/adamoutler/kanban/docs/ARCHITECTURE_AND_PRODUCT_SPEC.md) Section 3 (Multi-Surface MCP Architecture) & Section 6 (UI/UX Engineering Standards)
- **Verdict:** APPROVED (N/A - Pure Frontend Form Simplification)

---

## 1. Scope of Review
- **Backend & API Impact:** None.
- **REST / WebSocket / MCP Schemas:** Zero modifications to existing REST endpoints (`/api/v1/auth/mcp-keys`), bitmask values, or MCP protocol handlers.
- **Payload Integrity:** The unified selector (`mint-key-scope-type-select`) cleanly translates composite options (`${owner_kind}:${scope_tier}`) into exact backend request parameters (`owner_kind: 'personal_user' | 'service_bot'`, `scope_tier: 'workspace' | 'project' | 'global'`, and `allowed_projects: ['...']`).
- **Capability Ceiling Default Invariant:** Moving `capability-preset-select` inside `<AdvancedSection>` preserves default `capability_mask` (`31`) when collapsed and sends exact bitmask values (`1`, `3`, `31`, `255`, or custom) when modified.
- **Security & Authorization Controls:** Non-server-admin users are strictly prevented from viewing or selecting `service_bot:global`. Project-scoped keys mandate explicit `project_ref` and `allowed_projects` parameters.

---

## 2. Invariant Verification
- **AAL2 & CSRF Invariants:** All administrative key minting and revocation requests preserve required step-up AAL2 and CSRF token defenses.
- **Zero Schema Drift:** No OpenAPI or database migration changes introduced.
- **Supply Chain & Licensing:** Zero new dependencies introduced. All code adheres to Apache-2.0.

---

## 3. Certification
This change is purely a frontend form simplification and progressive disclosure refactoring structured around the 4 plain-English questions with a live plain-language key summary. All backend contracts and security invariants remain 100% intact. Approved for merge.
