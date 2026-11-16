# UI & UX Specialist Review: KANBA-141

**Auditor:** UI Specialist (`ux-architect` / `ui-designer`)  
**Date:** 2026-11-15  
**STATUS: APPROVED**

---

## 1. Executive Summary & Scope
Ticket `KANBA-141` (`KB-P4-07`) implements the `/mcp/agent` tools `add_comment` and `link_objects` alongside the session read-taint exfiltration guard (`mcp_read_taint` DDL, `TaintRecorder`, and `TaintGuard`). 

While this is an API & MCP foundation ticket without net-new React UI components, its contracts directly govern how frontend ticket screens, activity streams, comment feeds, and object-link graphs receive and render agent actions, as well as how error states are conveyed to operators.

---

## 2. DTO & Payload Ergonomics Audit

### A. `add_comment` Tool & Comment Feeds
- **Identifier & Payload Cleanliness:**
  - Accepts standard human-readable ticket keys (e.g., `KAN-142`) and maps cleanly into `issue_comments`.
  - Normalizes Markdown body content (`1..65,536` bytes) and enforces UTF-8 cleanliness without dangerous HTML markup or hidden injection vectors.
  - Returns compact, UI-friendly summary references: `{status: "commented", key: "KAN-142", comment: "KAN-142#c-0196ed41"}`, aligning directly with comment permalink anchors in the web interface.
- **Mention Access Warning Pattern (`MENTION_ACCESS_WARNING`):**
  - When an agent mentions a user without view permissions on the ticket, the tool refuses to leak content without explicit operator confirmation (`ack_mentions: true`).
  - The payload cleanly isolates forbidden handles, allowing future UI agent dialogs or toast notices to prompt the user clearly.

### B. `link_objects` Tool & Relationship Visualizations
- **Entity Resolution & Human Keys:**
  - Resolves source and target objects interchangeably via canonical keys (`KAN-142`, `KAN-150`) or UUIDs.
  - Emits normalized relation tuples: `{status: "linked", link: {source: "KAN-142", type: "BLOCKS", target: "KAN-150"}}`.
  - Adheres strictly to the link type matrix (`BLOCKS`, `RELATES_TO`, `DUPLICATES`, `VERIFIED_BY_DOC`) and returns `LINK_TYPE_NOT_ALLOWED` or `VALIDATION_FAILED` on self-links, protecting graph renderers and Mermaid diagrams from self-referential cycles.

### C. Session Read-Taint Guard & Operator Guidance
- **Error Semantics & Human Hand-Off:**
  - When cross-scope data exfiltration is detected, the guard rejects the write with HTTP `409` (`CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`).
  - The error payload provides clear structural metadata:
    - `tainted_by: [SEC]` identifies the narrow-audience source project.
    - `hint: "Ask a human to perform this write in the web UI."` provides explicit, non-deadlock guidance.
  - Since direct human sessions in the web UI are not subject to agent session read-taint, users can readily review and apply the change in the web UI without impedance.
- **Audit Ledger Visibility:**
  - Every blocked exfiltration attempt writes an `MCP_TAINT_BLOCKED` record to `activity_records`, ensuring administrative and security dashboards can display visual security alerts with actor, tool, source, and target details.

---

## 3. Schema Budget & Agent UX
- The `/mcp/agent` surface tools register at 7,037 bytes (~1,759 tokens), remaining comfortably within the 1,850 token budget ceiling defined in S11.1.
- Concise tool descriptions and JIT help parameters ensure lean prompts and responsive agent behavior in both IDE extensions and in-browser agent runners.

---

## 4. Final Verdict
The DTO shapes, error codes, and security hints for `add_comment`, `link_objects`, and the read-taint guard provide an ergonomic, predictable, and resilient foundation for client-side rendering and human-agent collaboration.

STATUS: APPROVED
