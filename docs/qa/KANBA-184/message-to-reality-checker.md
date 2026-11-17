# Forensic QA Packet for Reality-Checker: KANBA-184

**Ticket:** KANBA-184 (OAuth 2.1 RFC 7591 Dynamic Client Registration, RFC 9728 Protected-Resource Metadata, and Scoped MCP Authority)  
**Co-delivered Backend Invariants:** KANBA-183 (OIDC/LDAP form alias normalization, API problem formatting, workspace RLS execution, custom fields redaction)  
**Author:** Backend & MCP OAuth Implementation Engineer  
**Status:** Verification Packet Assembled (Ready for Forensic Certification)

---

## 1. Executive Summary & Verification Matrix

| Requirement | Implementation Surface | Evidence Artifact |
|---|---|---|
| RFC 7591 Dynamic Registration (`POST /oauth/register`) | `kanban/api/v1/oauth.py`, `kanban/oauth/server.py` | `docs/qa/KANBA-184/oauth-mcp-transcript.json`, `docs/qa/KANBA-184/unit-test-results.txt` |
| Interactive Login Redirect (302) & Consent Screen | `kanban/api/v1/oauth.py`, `kanban/oauth/server.py` | `kanban/tests/oauth/test_oauth_flow.py::test_case_09`, `test_case_10` |
| Scoped Resource Indicators & Bare `/mcp` | `kanban/oauth/server.py`, `kanban/security/mcp_keys.py`, `mcp/app.py`, `mcp/auth.py` | `mcp/tests/test_connection_scoping.py::test_bare_mcp_routing_and_unauthorized_metadata` |
| RFC 9728 Discovery (`/.well-known/oauth-protected-resource`) | `kanban/app.py`, `mcp/app.py`, `mcp/metadata.py` | `kanban/tests/mcp/test_live_mcp_mount.py::test_rfc9728_protected_resource_metadata_endpoints` |
| Row-Level Security (`kanban_app`) & Workspace Slugs | `database/migrations/sql/p4_18_oauth_mcp_scoping.up.sql`, `kanban/api/deps.py`, `kanban/auth/sessions/resolver.py` | `kanban/tests/api/test_workspaces_api.py`, `kanban/tests/security/test_mcp_scopable_keys.py` |
| KANBA-183 Backend Parity (OIDC/LDAP aliases, workspace API, custom field redaction) | `kanban/auth/oidc/config.py`, `kanban/auth/ldap/config.py`, `kanban/api/problems.py`, `kanban/api/v1/workspaces.py`, `kanban/custom_fields/service.py` | `kanban/tests/auth/test_auth_use_cases.py`, `kanban/tests/custom_fields/test_custom_fields_api.py` |

---

## 2. Forensic Proof Artifacts

1. **Unit & Integration Test Log:**
   - Location: `docs/qa/KANBA-184/unit-test-results.txt`
   - Result: 174 passed in 15.44s (100% pass rate across OAuth, security, MCP, workspaces, custom fields, and auth).

2. **Static Analysis & Architecture Layer Contracts:**
   - Location: `docs/qa/KANBA-184/build-check.txt`
   - `uv run ruff check kanban/ mcp/ database/`: All checks passed!
   - `uv run lint-imports`: Analyzed 912 files, 3132 dependencies. Contracts: 2 kept, 0 broken.

3. **Automated OAuth Transcript:**
   - Location: `docs/qa/KANBA-184/oauth-mcp-transcript.json`
   - Traces live ASGI discovery, dynamic registration, login redirect, and consent evaluation.

4. **API Specialist Review:**
   - Location: `docs/qa/KANBA-184/api-specialist-review.md`
   - Complete security, architectural, and RFC standards review by Backend Architect.

---

## 3. Strict Boundary Compliance

- Zero modifications to `kanban/web/` (reserved exclusively for the concurrent frontend agent).
- Zero Kanban tickets closed.
- Zero sub-agents spawned.
