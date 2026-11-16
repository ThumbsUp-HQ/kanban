# 👍kanban Security Architecture and STRIDE Threat Model

## Priority #0 Security Philosophy

👍kanban is engineered with an uncompromising, security-first architecture. We operate under root-level security principles:
1. Every input is hostile.
2. Every external dependency is untrusted.
3. Every component boundary must fail closed.
4. Database Row-Level Security (FORCE RLS) is the absolute authorization bedrock.
5. All sensitive operations must leave immutable forensic audit trails.

---

## 1. Network Trust Boundaries

The system architecture partitions operations across five distinct network trust boundaries:

```
[ External Wire / Browsers / Agents ]
                 |
                 v
        +------------------+
        |   1. edge_net    |  TLS termination, CSRF validation, WebAuthn Relying Party
        +------------------+
                 |
                 v (Unix socket / HTTP)
        +------------------+
        |   2. app_net     |  Uvicorn (UID 65532, setpriv drop), FastAPI, RLS session binding
        +------------------+
          |              |
          | (Unix socket)| (nsjail CLI / IPC)
          v              v
+------------------+   +------------------+
|   3. data_net    |   |  4. sandbox_net  |  Tier B nsjail containers, network-isolated,
| PostgreSQL Unix  |   |                  |  MS_RDONLY repo mounts, secret whiteouts
| socket, FORCE RLS|   +------------------+
+------------------+
          |
          v (Outbound TLS via Outbound Secret Scrubber)
+------------------+
|5. egress_llm_net |  OpenAI, Gemini, Ollama API egress
+------------------+
```

### 1.1 `edge_net` (Edge & Ingestion Boundary)
- Hostile wire: TLS 1.3 termination, strict Content-Security-Policy (CSP), and secure cookies.
- Request ID stamping (`X-Request-ID`) on every inbound request.
- Rate limiting per client IP and authenticated principal.
- Multi-Card authentication: WebAuthn/Passkeys (`rp.name = "👍kanban"`), LDAP over TLS, TOTP, and verified OIDC claims (zero implicit account auto-merging).

### 1.2 `app_net` (Application Boundary)
- Fast execution under least-privilege non-root execution: dropped privileges via `setpriv --reuid=65532 --inh-caps=-all --no-new-privs`.
- Safe typing, zero compiler/linter warnings, and strict RFC 7807 problem documents.
- Explicit session binding: Every request entering FastAPI resolves `PrincipalContext` and binds session parameters to PostgreSQL before execution.

### 1.3 `data_net` (Database Boundary)
- Dedicated PostgreSQL connection via local Unix domain socket (`listen_addresses = ''`, zero `host` entries in `pg_hba.conf`).
- Two-tier database roles:
  - `kanban_migrator`: Used exclusively for schema migrations, table creation, and system DDL.
  - `kanban_app`: Used for all application queries. Stripped of `SUPERUSER`, `CREATEDB`, `CREATEROLE`, and `BYPASSRLS` privileges (`rolbypassrls = false`).
- 100% of public tenant tables enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.

### 1.4 `sandbox_net` (Execution Sandbox Boundary)
- Isolated sandbox runner (`TierBNsjailRunner`) executing in Linux user namespaces with `CLONE_NEWUSER`, `CLONE_NEWPID`, `CLONE_NEWNS`, and `CLONE_NEWNET`.
- Zero network egress inside sandboxes (`--disable_clone_newnet=false`, zero network interfaces except loopback).
- Workspaces mounted with `MS_RDONLY | MS_NOEXEC | MS_NOSUID | MS_NODEV`.
- Secret whiteout masks applied over sensitive filesystem paths (`.env`, `.git/config`, `id_rsa.pem`, `tls.key`).

### 1.5 `egress_llm_net` (AI Provider Egress Boundary)
- Strictly gated outbound calls to external LLM providers.
- Scanned by `OutboundSecretScrubber` before dispatch, stripping API keys (`sk-...`, `ghp_...`, `AKIA...`), session HMACs, and private PEM keys.
- Deterministic response fixtures supported for fully offline verification.

---

## 2. STRIDE Threat Matrix (Spec S3.5)

| Threat Category | Spec Row | Attack Vector | Security Countermeasure & Invariant |
| :--- | :--- | :--- | :--- |
| **Spoofing / Tampering** | Row 1 | Indirect Prompt Injection & Cross-Project Exfiltration | Ingestion pruner strips hidden-DOM elements (`display:none`, `opacity:0`, HTML comments, Unicode tags `U+E0000..U+E007F`, zero-width characters). Read-Taint High-Water Mark blocks exfiltration into broader audience scopes with `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`. Outbound secret scrubber redacts credentials. |
| **Denial of Service / SSRF** | Row 2 | Hostile Media, SVG, Mermaid & SSRF Attacks | Hostile SVG sanitization and billion-laughs DAG depth limit (depth <= 5, expanded nodes <= 500). Download sandboxing headers (`default-src 'none'; sandbox`, `nosniff`, `attachment`). Media proxy SSRF defense (blocking loopback, RFC1918, cloud metadata 169.254.169.254, DNS-rebind socket pinning, air-gap mode). Image pixel decompression bomb threshold (max 40,000,000 pixels). |
| **Elevation of Privilege** | Row 3 | CLI Pipe & Sandbox Command Injection | Zero-shell `execve` argv dispatch (never `/bin/sh` or shell invocation). True random delimiter wrapping (`<<<UNTRUSTED_TICKET_DATA_{nonce}>>>`). Execution `verdict_nonce` validation rejecting forged approvals. Banned flags (`--yolo`, `--full-auto`, `--allow-all-tools`) rejected. Codex `-s read-only` enforcement. Nsjail `:ro` mounts with secret whiteout masks. |
| **Information Disclosure / Tampering** | Row 4 | Standalone `docker run` Misconfiguration | Zero hardcoded secrets in Dockerfile/ENV. Keyring file mode `0600` fail-closed. Zero default users on fresh database (no default admin/admin). Single-use `kb_setup_*` token stored only as SHA-256 with 60-minute expiry. Unix socket-only PostgreSQL (`listen_addresses = ''`). Uvicorn `setpriv` capability drop. Fail-closed `SANDBOX_UNAVAILABLE_IN_STANDALONE` when user namespaces are unavailable. |

---

## 3. Authorization Bedrock: RLS and On-Behalf-Of (OBO) Equations

### 3.1 Universal Object Graph
Every entity (`Issue`, `Doc`, `Page`, `Sticky`, `View`, `Comment`, `Attachment`) is registered in the central `objects` catalog with:
- Canonical UUID `id`
- Scope identifiers: `workspace_id`, `project_id`
- Creator: `created_by_id`
- Object kind: `object_kind`

### 3.2 Effective Resource Access (ERA) Computation
Access rights are evaluated dynamically by combining:
1. Workspace Role Bindings: `WORKSPACE_ADMIN`, `MEMBER`, `GUEST`
2. Project Role Bindings: `PROJECT_ADMIN`, `COLLABORATOR`, `VIEWER`
3. Resource ACL Entries: Explicit `ALLOW` or `DENY` capability masks (`VIEW`, `EDIT`, `DELETE`, `ADMIN`, `SHARE`)
4. Explicit Sharing Audience: `Audience` principals list

```
EffectiveAccess(principal, resource) =
    (HasRole(principal, resource.workspace, WORKSPACE_ADMIN) OR
     HasRole(principal, resource.project, PROJECT_ADMIN) OR
     (ExplicitACL(principal, resource) == ALLOW))
    AND NOT (ExplicitACL(principal, resource) == DENY)
```

### 3.3 Zero-Context Fail-Closed Invariant
When the database session executes under `kanban_app` without an explicitly bound workspace and principal:
```sql
SELECT count(*) FROM <table>; -- Returns 0 rows across ALL tenant tables
```
Unset session variables (`app.workspace_id = ''`) cause RLS policy evaluation to resolve to `FALSE`, preventing cross-tenant data leakage.

### 3.4 Anti-Enumeration Discipline (Spec S3.4)
To eliminate side-channel enumeration of private resources:
- All unreadable objects return uniform RFC 7807 `404 NOT_FOUND` responses.
- Responses for unreadable objects and non-existent objects are byte-identical (excluding variable headers such as `X-Request-ID` and `Date`).
- Timing floors (`timing_floor(floor_ms=25.0)`) normalize response latency to prevent timing side-channel attacks.

---

## 4. MCP Read-Taint High-Water Mark Invariant

When an AI agent or MCP client accesses sensitive resources via `/mcp/agent`:
1. Every read operation records the target object's `audience_principals` in `mcp_read_taint`.
2. The session accumulates a high-water mark of accessed scopes.
3. Subsequent write operations (`add_comment`, `create_ticket`, `update_ticket`, `transition_ticket`, `link_objects`) compare target scope against accumulated taint.
4. If writing to a broader audience than previously read data, the system blocks the action:
   - Returns error code `CROSS_SCOPE_TAINT_CONFIRMATION_REQUIRED`.
   - Emits an immutable `MCP_TAINT_BLOCKED` event to the activity ledger.
5. Taint tracking is keyed by both `Mcp-Session-Id` and client credential fingerprint (`key_fingerprint`), preventing bypass via session reconnection.

---

## 5. Security Verification and Audit Commands

Run the comprehensive security test suite locally to verify compliance:

```bash
# 1. Run the entire STRIDE security regression suite
uv run pytest tests/security -v

# 2. Verify PostgreSQL RLS catalog compliance
uv run pytest database/tests/test_p1_14_rls_catalog.py -v

# 3. Check architectural boundaries and import restrictions
uv run lint-imports

# 4. Run static type checking across all packages
uv run mypy --strict database kanban mcp agent

# 5. Run linter and formatting checks
uv run ruff check .
uv run ruff format --check .

# 6. Verify absence of forbidden unicode dashes (plain ASCII hyphens only)
python3 scripts/check_no_dashes.py --all
```

---

## 6. Vulnerability Disclosure Policy

Security vulnerabilities should be reported directly to the security team:
- Email: `security@hackedyour.info`
- PGP Fingerprint: Available upon request
- Response SLA: Initial triage within 24 hours

Do not open public GitHub issues for suspected security vulnerabilities.
