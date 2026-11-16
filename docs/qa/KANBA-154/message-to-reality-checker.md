# Message to Reality-Checker: Forensic Verification Packet for KANBA-154

## Executive Overview
- **Ticket:** `KANBA-154` (`docs/tickets/KB-P5-19b.md`): `[Phase 5 / API + MCP] project_repo_bindings, hardened :ro bare git mirror manager & /mcp/admin bind_project_repo`
- **Scope:**
  - Database schema & migrations: `database/migrations/versions/p5_19b_project_repo_bindings.py`, SQL up/down scripts, `database/models/repo_binding.py`.
  - SSRF URL Policy & DNS Pinned Resolver: `kanban/repos/url_policy.py`.
  - Hardened Bare Git Mirror Manager: `kanban/repos/mirror.py`.
  - Project Repo Bindings REST API: `kanban/api/v1/repo_bindings.py` mounted in `kanban/api/v1/__init__.py`.
  - Entity Resolver integration: `kanban/resolve/service.py` (`repo_binding` kind).
  - MCP Admin Tool 6 actions: `mcp/surfaces/admin/manage_cycles_and_modules.py` and `mcp/admin/tools/manage_cycles_and_modules.py`.
  - Agent Context Resolution: `agent/context/repo_context.py` (`resolve_repo_context`).
  - Comprehensive Unit & Integration Tests: 64 passed in 5.16s, 95.96% branch + statement coverage.

---

## Architectural Note on Specification & DDL Provisioning
The authoritative specification (`docs/ARCHITECTURE_AND_PRODUCT_SPEC.md` S14.3) details the git mirror manager requirements and `/mcp/admin` tool bindings, but omitted the explicit table DDL for `project_repo_bindings`. In strict adherence to KB-P5-19b:
1. `project_repo_bindings` was implemented with strict schema constraints:
   - `id UUID PRIMARY KEY DEFAULT uuidv7()`
   - `workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`
   - `project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE`
   - `slug TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')`
   - `remote_url TEXT NOT NULL CHECK (char_length(remote_url) <= 2048)`
   - `default_ref TEXT NOT NULL DEFAULT 'main' CHECK (default_ref ~ '^[A-Za-z0-9._/-]{1,200}$' AND default_ref !~ '\.\.')`
   - `access_mode TEXT NOT NULL CHECK (access_mode IN ('bare_git_tools','ro_vfs_mount'))`
   - `credential_ciphertext BYTEA` & `credential_dek_kid TEXT` for envelope encryption (KB-P2-03)
   - `last_fetched_commit TEXT CHECK (last_fetched_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$')`
   - `UNIQUE (project_id, slug)`
2. Full PostgreSQL 16 security:
   - `ENABLE ROW LEVEL SECURITY` & `FORCE ROW LEVEL SECURITY`.
   - Granular RLS policies: SELECT requires project VIEW capability (1); INSERT, UPDATE, DELETE require PROJECT_ADMIN or ADMIN capability (64).
   - Grants restricted to `kanban_app` and `app_rls_reader`.

---

## Core Security Invariants Verified

1. **SSRF Defense & DNS Rebinding Immunity (S14.3, S3.4):**
   - Disallowed schemes (`file://`, `ext::`, `fd::`, `git://`, `http://`, `ftp://`, etc.) rejected with `422 REPO_URL_REJECTED`.
   - Embedded user/password credentials in remote URLs rejected.
   - Loopback (`127.0.0.0/8`, `::1`, `::ffff:127.0.0.1`), metadata/link-local (`169.254.169.254`, `fe80::/10`, `fd00:ec2::/26`), RFC1918 private networks, and multicast/reserved ranges blocked unless explicitly permitted by `allowed_git_cidrs`.
   - **DNS Rebinding Defense:** Initial DNS resolution pins the validated IP; subsequent git invocations enforce `-c http.curloptResolve=<host>:<port>:<pinned_ip>` so attackers cannot rebind hostnames to `127.0.0.1` after validation.

2. **Hardened Bare Git Sandbox Isolation (S14.3):**
   - Subprocess invocations use `asyncio.create_subprocess_exec` (`shell=False`, zero `/bin/sh`).
   - Hardened base argv overrides:
     - `core.hooksPath=/dev/null` (prevents repository hooks from executing during clone/fetch).
     - `protocol.file.allow=never` (prevent local file protocol access).
     - `protocol.ext.allow=never` (prevent external command execution via git transport).
     - `core.fsmonitor=false`
     - `submodule.recurse=false`
     - `transfer.fsckObjects=true`
   - Environment dictionary is completely replaced:
     - `GIT_CONFIG_NOSYSTEM=1`
     - `GIT_CONFIG_GLOBAL=/dev/null`
     - `GIT_TERMINAL_PROMPT=0`
     - `GIT_ALLOW_PROTOCOL=https:ssh`
     - `HOME=/tmp/...`
     - `PATH=/usr/bin:/bin`
   - Resource limits enforced:
     - 2 GiB repository size limit (`MirrorSizeLimitError`, repository deleted on breach).
     - 120s timeout limit (`MirrorTimeoutError`).
   - Credential zeroization:
     - Credentials decrypted in mutable `bytearray`, written to temporary 0600 config/key files, and zeroized/deleted in `finally` blocks.

3. **Multi-Card Auth & AAL2 Step-Up (S3.4, S11.4):**
   - Mutating REST endpoints (`POST`, `POST /refresh`, `DELETE`) enforce `_require_aal2` (raises `403 AAL2_REQUIRED` for AAL1 sessions).
   - Member access without project admin role returns `404 Not Found` (anti-enumeration defense).
   - Delete endpoint prevents unbinding if active `workflow_transition_hooks` depend on repository access (`409 REPO_BINDING_IN_USE`).

4. **MCP Admin Tool 6 Actions:**
   - `bind_project_repo`: binds repository, clones initial bare mirror, records commit.
   - `list_repo_bindings`: supports `summary` and `full` LOD tiers.
   - `refresh_repo_binding`: pulls latest updates with `--prune`.
   - `unbind_project_repo`: 2-stage confirmation (`confirm: true` parameter required).

---

## Test Verification & Quality Gates
- **Unit Tests:** `uv run pytest kanban/tests/repos mcp/tests/admin/test_bind_project_repo.py agent/tests/context/test_repo_context.py`
  - Results: **64 passed in 5.16s** (`EXIT_CODE=0`).
  - Total line + branch coverage: **95.96%** (exceeds 95% threshold).
    - `agent/context/repo_context.py`: 100%
    - `kanban/repos/url_policy.py`: 97%
    - `kanban/repos/mirror.py`: 95%
    - `kanban/api/v1/repo_bindings.py`: 95%
- **Ruff & Format:** Clean (0 findings).
- **Mypy Strict:** Clean (`Success: no issues found in 816 source files`).
- **Import Linter:** Clean (`2 contracts kept, 0 broken`).
- **Security Check:** 0 occurrences of `shell=True` across the entire scoped codebase.

All proof files are populated in `docs/qa/KANBA-154/` and synchronized to `/home/adamoutler/kanban/docs/qa/KANBA-154/`.
