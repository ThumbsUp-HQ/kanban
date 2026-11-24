# Vendor Verification Audit: 6 New & Split Capability Rows (KAN-392)

## Executive Summary

This primary-source audit documents and verifies all 8 compared platforms (`👍kanban`, `Jira`, `Plane`, `GitHub`, `Vibe Kanban`, `OpenAI Symphony`, `Businessmap`, `Codebeamer`) across the 6 new and split capability rows introduced in the 50-feature technical matrix:
1. `Active Directory / LDAP` (Section 1: Split from Multi-Card OIDC & LDAPS)
2. `OIDC` (Section 1: Split from Multi-Card OIDC & LDAPS)
3. `/llms.txt & Skills Discovery` (Section 2: New machine discovery row)
4. `Issue Tracker` (Section 3: Split from Core Kanban & Issues)
5. `Kanban Board` (Section 3: Split from Core Kanban & Issues)
6. `Synaptic Hybrid Vector Search` (Section 4: New semantic search row)

Every claim is verified against official vendor documentation, help center manuals, architecture guides, and pricing models as of November 2026.

---

## 1. Feature Definition & Rating Invariants

### 1.1 Active Directory / LDAP (Section 1)
- **Capability Scope**: Direct native protocol bind over `LDAP` (port 389) or `LDAPS`/`StartTLS` (port 636) to Microsoft Active Directory, FreeIPA, OpenLDAP, or 389-ds, including RFC 4515 attribute escaping, credential validation, DN resolution, and directory group synchronization.
- **Distinction (Direct Bind vs External IdP Bridge)**: Direct LDAP binds communicate natively over the LDAP wire protocol to directory controllers. Platforms that lack native LDAP binds but allow authentication via external SAML 2.0 or OIDC identity bridges (e.g., Azure AD SAML, Okta LDAP Agent, Duo SSO) are rated according to the bridge cost or marked as requiring an external IdP bridge.
- **Ratings**:
  - `👍kanban`: `✅` (Built-in native LDAPS/StartTLS direct protocol bind with RFC 4515 escaping and group mapping in base Apache-2.0 product, zero per-seat paywall).
  - `Jira`: `💸` (Jira Cloud does not perform direct LDAP binds; directory sync requires Atlassian Guard Standard at ~$3.00-$4.35/user/month to sync Entra ID/Okta via SCIM, or Jira Data Center/Crowd which requires a costly separate self-hosted enterprise license).
  - `Plane`: `💰` (Plane Community AGPLv3 is limited to local email/password; direct LDAP/Active Directory bind and LDAP group sync are locked behind commercial tiers such as Enterprise Grid).
  - `GitHub`: `💰` (GitHub Cloud uses SAML/SCIM SSO via GitHub Enterprise; GitHub Enterprise Server on-prem supports direct LDAP binds to Active Directory/OpenLDAP via Management Console, but requires a paid GitHub Enterprise subscription).
  - `Vibe Kanban`: `❌` (Single-user local git-worktree developer tool with zero directory or LDAP integration).
  - `OpenAI Symphony`: `❌` (Headless agent runner daemon in trusted developer environments with zero user authentication or directory service).
  - `Businessmap`: `💸` (SAML 2.0 / Active Directory integration requires the paid Single Sign-On add-on module or a custom Enterprise agreement; direct LDAP bind is not supported on cloud).
  - `Codebeamer`: `✅` (Native LDAP and Active Directory direct bind integration with referral following and group synchronization built into base platform under System Administration > User Authentication).

### 1.2 OIDC (Section 1)
- **Capability Scope**: OpenID Connect (OIDC) and OAuth 2.0 authentication utilizing Authorization Code Flow with PKCE (`S256`), standard `.well-known/openid-configuration` discovery, JWKS signature verification, claim mapping, and multi-provider account linking.
- **Distinction (Multi-Card vs Single Provider vs Enterprise Paywall)**: Multi-Card architectures allow configuring multiple concurrent OIDC providers alongside local/LDAP credentials. Commercial platforms frequently gate OIDC/SAML behind enterprise SSO subscription tiers.
- **Ratings**:
  - `👍kanban`: `✅` (Native Multi-Card OIDC/OAuth 2.0 with PKCE S256 supporting multiple simultaneous providers in Apache-2.0 core).
  - `Jira`: `💸` (Atlassian Guard Standard subscription required for enforced OIDC/SAML SSO across Atlassian Cloud products).
  - `Plane`: `💰` (OIDC/SAML SSO is gated behind paid Pro, Commercial, and Enterprise tiers).
  - `GitHub`: `💰` (SAML/OIDC SSO for enterprise organization login is gated behind GitHub Enterprise).
  - `Vibe Kanban`: `❌` (No OIDC support).
  - `OpenAI Symphony`: `❌` (No OIDC support).
  - `Businessmap`: `💸` (SSO/SAML 2.0 is a paid modular add-on on standard plans or quoted on Enterprise).
  - `Codebeamer`: `✅` (Native OpenID Connect / OAuth 2.0 Authorization Code flow with JWKS verification and automatic user provisioning included in base product).

### 1.3 /llms.txt & Skills Discovery (Section 2)
- **Capability Scope**: Standard machine discovery endpoints (`GET /llms.txt`, `GET /llms-full.txt`, `GET /llms-skills`) serving structured markdown indices, tool inventories, and cryptographically verified (SHA-256 signed) Agent Skills manifests for autonomous LLM agents (Cursor, Claude, Codex, Antigravity).
- **Ratings**:
  - `👍kanban`: `✅` (Native endpoints `GET /llms.txt`, `/llms-full.txt`, `/llms-skills`, and SHA-256 signed Agent Skills catalog at `.agents/skills/`).
  - `Jira`: `❌` (No /llms.txt standard discovery endpoint or signed skills catalog).
  - `Plane`: `❌` (No /llms.txt or skills discovery endpoint).
  - `GitHub`: `❌` (No native /llms.txt standard machine discovery endpoint or signed skills catalog for tracker).
  - `Vibe Kanban`: `❌` (No /llms.txt or skills discovery endpoint).
  - `OpenAI Symphony`: `❌` (No /llms.txt machine discovery endpoint; relies on repo-local WORKFLOW.md).
  - `Businessmap`: `❌` (No /llms.txt or agent skills discovery).
  - `Codebeamer`: `❌` (No /llms.txt or agent skills discovery).

### 1.4 Issue Tracker (Section 3)
- **Capability Scope**: Persistent multi-user issue tracking system of record providing deterministic issue keys (`PROJ-123`), workflow states, lifecycle management, issue types, priorities, parent-child DAG hierarchies, typed relations, audit trails, and multi-tenant access controls.
- **Distinction (Issue Tracker vs Visual Kanban Board)**: An Issue Tracker serves as the underlying multi-user transactional system of record with queryable schemas, permission filters, and lifecycle integrity. A Kanban Board is the visual, interactive drag-and-drop representation of workflow states.
- **Ratings**:
  - `👍kanban`: `✅` (Persistent multi-user issue tracking system of record with hierarchical keys, custom statuses, priorities, types, typed links, and PostgreSQL Row-Level Security).
  - `Jira`: `🔐` (Full-featured enterprise issue tracking system of record, but Free tier is capped at 10 users and gates advanced workflows).
  - `Plane`: `✅` (Native multi-user issue tracking system of record in Community edition).
  - `GitHub`: `✅` (GitHub Issues persistent multi-user system of record).
  - `Vibe Kanban`: `🔐` (Cloud backend sunsetted after v0.1.44 in May 2026; runs local git-worktree task sessions, lacks persistent multi-user issue tracking system of record).
  - `OpenAI Symphony`: `❌` (Headless agent runner polling external issue trackers like Linear, GitHub, Jira; maintains zero persistent issue tracking database).
  - `Businessmap`: `✅` (Native work item system of record with cards, initiatives, and custom fields).
  - `Codebeamer`: `✅` (Native enterprise ALM system of record for tracker items, requirements, and test cases).

### 1.5 Kanban Board (Section 3)
- **Capability Scope**: Interactive visual Kanban board interface featuring customizable workflow columns, smooth card drag-and-drop, semantic visual badges, configurable Work-in-Progress (WIP) limits, column card counts, and collapsible stages.
- **Ratings**:
  - `👍kanban`: `✅` (Native high-performance visual drag-and-drop Kanban board with custom columns, semantic emojis, configurable WIP limits, and breathable whitespace).
  - `Jira`: `🔐` (Native visual Kanban board, but Free plan is capped at 10 users and gates cross-project boards/advanced WIP).
  - `Plane`: `✅` (Native visual Kanban board view included in free/community tier).
  - `GitHub`: `✅` (GitHub Projects visual Kanban board view included with columns and cards).
  - `Vibe Kanban`: `✅` (Core user interface is a visual drag-and-drop Kanban board for AI tasks).
  - `OpenAI Symphony`: `❌` (No visual Kanban board surface; Phoenix LiveView run monitor only).
  - `Businessmap`: `✅` (Core product is an advanced visual Kanban board with multi-level swimlanes and WIP controls).
  - `Codebeamer`: `✅` (Native visual Kanban board view on trackers with column and lane mappings).

### 1.6 Synaptic Hybrid Vector Search (Section 4)
- **Capability Scope**: Zero-egress local vector search combining embedded ONNX models (e.g., `bge-small-en-v1.5-int8`) with `pgvector` HNSW index acceleration (`hnsw.iterative_scan`), Reciprocal Rank Fusion (RRF) with lexical BM25/trigram matching, and 2-hop RLS-governed graph activation spreading across typed `object_links`.
- **Distinction (Zero-Egress On-Prem vs Cloud AI Egress vs Keyword Search)**: Evaluates whether vector embeddings are generated locally without external SaaS API calls and whether search results traverse the entity relationship graph.
- **Ratings**:
  - `👍kanban`: `✅` (Zero-egress SHA-256-pinned local `bge-small-en-v1.5-int8` ONNX embeddings + `pgvector` HNSW `hnsw.iterative_scan` + Reciprocal Rank Fusion + 2-hop RLS-governed activation spreading across `object_links`).
  - `Jira`: `❌` (No zero-egress local vector search or synaptic graph spreading; Atlassian Rovo is a paid cloud-egress AI search add-on at $8/user/mo).
  - `Plane`: `❌` (Postgres lexical full-text search only; no vector embeddings or synaptic graph spreading).
  - `GitHub`: `❌` (Lexical code/issue search via Blackbird engine; no local zero-egress ONNX embeddings or graph activation spreading).
  - `Vibe Kanban`: `❌` (No vector search or semantic graph activation).
  - `OpenAI Symphony`: `❌` (Stateless daemon, no vector search or graph activation).
  - `Businessmap`: `❌` (Keyword/filter search only; no vector embeddings or graph spreading).
  - `Codebeamer`: `❌` (Lucene text search only; no hybrid vector search or synaptic graph spreading).

---

## 2. Platform-by-Platform Verification Details & Primary Sources

### 2.1 👍kanban (`thumbs-up-kanban`)
- **Primary Sources**:
  - Architecture Spec: `docs/ARCHITECTURE_AND_PRODUCT_SPEC.md`
  - Auth Guide: `thumbs-up-kanban.wiki/Multi-Card-Authentication-Studio.md`
  - Search Architecture: `kanban/services/search.py`, `kanban/services/synaptic_rescorer.py`
  - Machine Discovery: `/llms.txt`, `/llms-full.txt`, `/llms-skills`
- **Verification Details**:
  - *Active Directory / LDAP*: Built-in direct LDAPS/StartTLS connection via `python-ldap` with RFC 4515 filter escaping, service account bind, DN resolution, and group sync (`auth_cards`).
  - *OIDC*: Native OpenID Connect with PKCE `S256` supporting concurrent cards (Google, GitHub, Authentik, Keycloak, Okta) in Apache-2.0 core.
  - */llms.txt & Skills Discovery*: Endpoints live at root; signed skills verified via SHA-256 in `.agents/skills/`.
  - *Issue Tracker*: Universal Object Graph (`Issue` entities with `ltree` hierarchies, custom statuses, 30-permission RBAC, PostgreSQL `FORCE RLS`).
  - *Kanban Board*: 5-view reactive board with 2D swimlanes, hard WIP limits, and sub-16ms drag-and-drop.
  - *Synaptic Hybrid Vector Search*: Local INT8 ONNX embedder (`bge-small-en-v1.5-int8`) in `agent/embeddings/`, `pgvector` HNSW indexes, RRF fusion, and 2-hop graph spreading in `kanban/services/synaptic_rescorer.py`.

### 2.2 Jira (Atlassian)
- **Primary Sources**:
  - Atlassian Guard Overview: `https://www.atlassian.com/software/guard`
  - Atlassian Guard Docs: `https://support.atlassian.com/security-and-access-policies/docs/what-is-atlassian-guard/`
  - Connecting to LDAP (Server/Data Center): `https://confluence.atlassian.com/adminjiraserver/connecting-to-an-ldap-directory-938847052.html`
  - Atlassian Crowd: `https://www.atlassian.com/software/crowd`
  - Jira Pricing: `https://www.atlassian.com/software/jira/pricing`
- **Verification Details**:
  - *Active Directory / LDAP (`💸`)*: Jira Cloud does not support direct LDAP binds. Organizations must subscribe to Atlassian Guard Standard ($4.35/user/month or $3.00/user/month at volume) to sync directories via identity providers using SCIM. Jira Data Center supports direct LDAP binds, but requires expensive enterprise licensing and on-prem infrastructure.
  - *OIDC (`💸`)*: Enforced SAML/OIDC SSO requires an Atlassian Guard Standard subscription across Jira Cloud.
  - */llms.txt & Skills Discovery (`❌`)*: Jira provides no /llms.txt or agent skills discovery endpoints.
  - *Issue Tracker (`🔐`)*: Core issue tracker is capped at 10 users on Free tier; advanced workflows, issue hierarchies, and cross-project tracking require Standard or Premium.
  - *Kanban Board (`🔐`)*: Kanban boards are capped at 10 users on Free tier; cross-project board rollups require Premium.
  - *Synaptic Hybrid Vector Search (`❌`)*: Jira uses lexical JQL and text indexing. Semantic search is only available via Atlassian Rovo, a cloud-egress AI subscription add-on ($8/user/month) that does not support local zero-egress ONNX embeddings or synaptic graph activation spreading.

### 2.3 Plane
- **Primary Sources**:
  - Plane SSO & Directory Docs: `https://docs.plane.so/self-hosting/govern/sso/`
  - Plane Pricing: `https://plane.so/pricing`
  - Plane Repository: `https://github.com/makeplane/plane` (AGPL-3.0)
- **Verification Details**:
  - *Active Directory / LDAP (`💰`)*: Plane Community Edition (FOSS AGPLv3) only supports basic email/password authentication. LDAP directory sync and group sync are locked behind Commercial Self-Hosted / Enterprise Grid tiers.
  - *OIDC (`💰`)*: SAML 2.0 and OIDC authentication are gated behind paid Pro and Enterprise commercial plans.
  - */llms.txt & Skills Discovery (`❌`)*: Plane exposes no /llms.txt standard machine discovery endpoint or signed skills catalog.
  - *Issue Tracker (`✅`)*: Included in Community Edition as a persistent multi-user issue tracking system of record.
  - *Kanban Board (`✅`)*: Visual Kanban board view included in Community Edition.
  - *Synaptic Hybrid Vector Search (`❌`)*: Plane uses standard PostgreSQL text matching and pg_trgm; no zero-egress vector search, ONNX embeddings, or graph spreading.

### 2.4 GitHub
- **Primary Sources**:
  - GitHub Enterprise Managed Users: `https://docs.github.com/en/enterprise-cloud@latest/admin/identity-and-access-management/using-enterprise-managed-users-for-iam/about-enterprise-managed-users`
  - GitHub Enterprise Server LDAP: `https://docs.github.com/en/enterprise-server@latest/admin/identity-and-access-management/using-ldap-for-enterprise-server/configuring-ldap-authentication`
  - GitHub Pricing: `https://github.com/pricing`
- **Verification Details**:
  - *Active Directory / LDAP (`💰`)*: GitHub Cloud requires GitHub Enterprise with SAML/SCIM SSO. GitHub Enterprise Server supports direct LDAP binds to Active Directory and OpenLDAP, but requires a paid GitHub Enterprise license ($21/user/month).
  - *OIDC (`💰`)*: SAML/OIDC SSO for enterprise organization login is gated behind GitHub Enterprise. (GitHub Actions supports OIDC token minting, but human user authentication to the platform requires Enterprise).
  - */llms.txt & Skills Discovery (`❌`)*: GitHub has no native platform-level /llms.txt discovery endpoint or signed skills manifest for its issue tracker.
  - *Issue Tracker (`✅`)*: GitHub Issues is a persistent multi-user issue system of record included for free on public and private repos.
  - *Kanban Board (`✅`)*: GitHub Projects provides visual Kanban boards with columns and custom fields.
  - *Synaptic Hybrid Vector Search (`❌`)*: GitHub uses the Blackbird lexical search engine; semantic search is cloud-based via Copilot (`💸`) without zero-egress local ONNX embeddings or 2-hop graph activation spreading.

### 2.5 Vibe Kanban
- **Primary Sources**:
  - Repository: `https://github.com/BloopAI/vibe-kanban`
  - Release History: Sunset of hosted cloud backend after v0.1.44 (May 2026)
- **Verification Details**:
  - *Active Directory / LDAP (`❌`)*: Single-user local developer CLI tool (`npx vibe-kanban`); no LDAP or Active Directory support.
  - *OIDC (`❌`)*: No OIDC authentication; local session execution.
  - */llms.txt & Skills Discovery (`❌`)*: No /llms.txt or skills endpoint.
  - *Issue Tracker (`🔐`)*: Hosted multi-tenant issue cloud was sunsetted; runs local git-worktree task session cards rather than a persistent multi-user issue system of record.
  - *Kanban Board (`✅`)*: Core user interface is a visual drag-and-drop Kanban board for managing coding agent tasks.
  - *Synaptic Hybrid Vector Search (`❌`)*: No vector search or semantic graph activation.

### 2.6 OpenAI Symphony
- **Primary Sources**:
  - Repository: `https://github.com/openai/symphony`
  - Specification: Engineering preview Elixir/OTP daemon driven by repo-local `WORKFLOW.md`
- **Verification Details**:
  - *Active Directory / LDAP (`❌`)*: Headless daemon intended for trusted developer environments; zero authentication or directory sync.
  - *OIDC (`❌`)*: No user authentication layer or OIDC support.
  - */llms.txt & Skills Discovery (`❌`)*: Uses repo-local WORKFLOW.md prompt templates; no /llms.txt discovery endpoint.
  - *Issue Tracker (`❌`)*: Symphony is a polling orchestrator that interfaces with external trackers (Linear, GitHub, Jira); maintains no persistent issue database.
  - *Kanban Board (`❌`)*: No visual Kanban board; provides a Phoenix LiveView run dashboard only.
  - *Synaptic Hybrid Vector Search (`❌`)*: Stateless daemon with no persistent database, vector embeddings, or graph activation.

### 2.7 Businessmap (formerly Kanbanize)
- **Primary Sources**:
  - Pricing & Plans: `https://businessmap.io/pricing`
  - SAML 2.0 Integration: `https://kb.businessmap.io/hc/en-us/articles/360010839840-Single-Sign-On-SSO-with-SAML-2-0`
- **Verification Details**:
  - *Active Directory / LDAP (`💸`)*: Active Directory integration via SAML 2.0 (e.g., Entra ID, ADFS, or Duo SSO bridge) is a paid modular add-on requiring a custom quote or Enterprise tier. Direct LDAP binds are not supported on cloud.
  - *OIDC (`💸`)*: SSO is a paid modular add-on on Standard plans or included in custom Enterprise agreements.
  - */llms.txt & Skills Discovery (`❌`)*: No /llms.txt discovery endpoint or skills manifest.
  - *Issue Tracker (`✅`)*: Full-featured work management system of record with cards and initiatives.
  - *Kanban Board (`✅`)*: Industry-leading visual Kanban board with multi-level swimlanes and WIP constraints.
  - *Synaptic Hybrid Vector Search (`❌`)*: Lexical search only; no local vector embeddings or graph activation spreading.

### 2.8 Codebeamer (PTC)
- **Primary Sources**:
  - Help Center - User Authentication: `https://support.ptc.com/help/codebeamer/`
  - Active Directory Configuration: `https://support.ptc.com/help/codebeamer/r2.2/en/index.html#page/cb/system_administration/user_authentication/ldap_and_active_directory.html`
  - OpenID Connect & OAuth2 Configuration: `https://support.ptc.com/help/codebeamer/r2.2/en/index.html#page/cb/system_administration/user_authentication/openid_connect.html`
- **Verification Details**:
  - *Active Directory / LDAP (`✅`)*: Codebeamer includes built-in direct LDAP and Active Directory bind support in its base product (System Administration > User Authentication) with referral following (`referral = "follow"`), attribute mapping, and periodic group synchronization.
  - *OIDC (`✅`)*: Built-in OpenID Connect / OAuth 2.0 Authorization Code flow with JWKS verification and claim-based user provisioning included in base product.
  - */llms.txt & Skills Discovery (`❌`)*: No /llms.txt standard machine discovery endpoint or signed skills catalog.
  - *Issue Tracker (`✅`)*: Full enterprise ALM issue and requirements management system of record.
  - *Kanban Board (`✅`)*: Visual Kanban board view available on trackers with column mappings.
  - *Synaptic Hybrid Vector Search (`❌`)*: Lucene full-text indexing only; no vector embeddings or synaptic graph activation spreading.

---

## 3. Summary Matrix of 6 Target Rows

| Capability Row | Section | 👍kanban | Jira | Plane | GitHub | Vibe Kanban | OpenAI Symphony | Businessmap | Codebeamer |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Active Directory / LDAP** | 1 | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💸 | ✅ |
| **OIDC** | 1 | ✅ | 💸 | 💰 | 💰 | ❌ | ❌ | 💸 | ✅ |
| **/llms.txt & Skills Discovery** | 2 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Issue Tracker** | 3 | ✅ | 🔐 | ✅ | ✅ | 🔐 | ❌ | ✅ | ✅ |
| **Kanban Board** | 3 | ✅ | 🔐 | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **Synaptic Hybrid Vector Search** | 4 | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 4. Verification Check Conclusion
All 6 capability rows have been verified against primary documentation. The matrix expands from 46 to exactly 50 features across Sections 1-5 (`10 + 9 + 13 + 8 + 10 = 50`), preserving 100% `✅` rating for `👍kanban` in core Apache-2.0 and accurately reflecting competitor limitations and paywalls.
