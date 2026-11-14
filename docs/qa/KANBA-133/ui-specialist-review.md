# UI Specialist Gate Review: KANBA-133 (KB-P4-15) - Dynamic MCP Connection Scoping

- Ticket: KANBA-133 (KB-P4-15)
- Title: Dynamic MCP Connection Scoping: Global (/mcp/{s}), Workspace (/w/{slug}) & Project (/w/{slug}/p/{key}) Routes + Header Narrowing
- Status: APPROVED
- Reviewer: ui-specialist (Swarm UI & UX Architecture Specialist Gate)

---

## 1. Consumer Ergonomics & Developer Experience Verification

1. **Zero-Script Repo Config & IDE Ergonomics (Spec S11.1, S11.3)**:
   - Evaluated the URL path and header scoping interfaces from the perspective of IDE and agent configuration files (`.gemini/settings.json`, `mcp_config.json`, Claude Desktop config).
   - In standard multi-repo developer workflows, a developer or CI job can pin an entire workspace or project simply by setting the connection URL:
     ```json
     {
       "mcpServers": {
         "kanban": {
           "url": "https://kanban.example.com/mcp/agent/w/my-team/p/CORE",
           "headers": {
             "Authorization": "Bearer ${KANBAN_API_KEY}"
           }
         }
       }
     }
     ```
   - Alternatively, developers can specify headers alongside the short base URL:
     ```json
     {
       "mcpServers": {
         "kanban": {
           "url": "https://kanban.example.com/mcp/agent",
           "headers": {
             "Authorization": "Bearer ${KANBAN_API_KEY}",
             "X-Workspace-Slug": "my-team",
             "X-Project-Key": "CORE"
           }
         }
       }
     }
     ```
   - Both forms are completely declarative and require zero wrapper scripts or client-side filter logic.

2. **Parameter Auto-Fill & Invisible Defaults (Spec S11.1 Mode C)**:
   - When connected via project-scoped mode (`/w/kanban/p/KANBA`), tools accepting an optional `project` parameter (`create_ticket`, `search_tickets`, `begin_work`, `manage_stickies`, etc.) automatically default `project = "KANBA"` when omitted by the AI agent.
   - This eliminates prompt engineering overhead: agents no longer need special prompting to remember the active project identifier.

3. **Error Remediation & Progressive Disclosure**:
   - In ambiguous cross-workspace lookups (HTTP 409 `AMBIGUOUS_IDENTIFIER`), the response structure provides human-legible candidate rows and an actionable remediation hint:
     `"pass workspace=<slug> or connect via /mcp/agent/w/<slug>"`.
   - In cross-project mutation violations (`CONNECTION_SCOPE_VIOLATION`), the error explains the exact pinned scope and suggests either reconnecting to the target project or running in Global mode.
   - These self-describing messages guide both human operators and autonomous agents to correct their queries without confusion.

4. **Screenshots Gate Assessment**:
   - Per ticket specification (KB-P4-15 Section 4 / Verification Proof 8), screenshots are marked: `N/A - Non-UI Ticket (UI delivered in KB-P4-16)`.
   - Visual board and drawer presentation will be verified in KB-P4-16.

---

## 2. Verdict

APPROVED. The URL and header connection scoping models provide clean, intuitive ergonomics for IDE configurations and autonomous multi-workspace agents.
