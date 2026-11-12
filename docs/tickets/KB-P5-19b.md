---
id: KB-P5-19b
title: "[Phase 5 / API + MCP] project_repo_bindings, hardened :ro bare git mirror manager & /mcp/admin bind_project_repo"
epic: KB-E5
depends_on: [KB-P5-19a, KB-P4-10]
spec_sections: ["14.2", "14.3", "11.4", "2.4"]
gates: [reality-checker, api-specialist, ui-specialist]
new_dependencies: []
state: Backlog
---

> Split note: second half of manifest row `KB-P5-19` (see `KB-P5-19a`).

### User Story
As a **Project Admin connecting a source repository to workflow gates**, I need **a `project_repo_bindings` registry, a mirror manager that clones/fetches bare mirrors with hooks, local protocols, and SSRF paths disabled, and the `bind_project_repo` action on `/mcp/admin` tool 6** so that **agents only ever see a pinned commit of an admin-approved repository through read-only mounts, and a hostile remote URL or repository cannot execute code on the server**.

**Requirement Traceability:** `S14.2` (`repo_access_mode` `bare_git_tools` / `ro_vfs_mount`), `S14.3` item 3 (`:ro` repo, `.git/config` / `.git/hooks` masking, `head_commit` in context), `S11.4` tool 6 (`bind_project_repo` `:ro` Git mirror / VFS bindings), `S2.4` (`agent-runtime` with `:ro git-mirrors`) | Original requirement `#2`, `#12` | **Dependencies:** `KB-P5-19a`, `KB-P4-10`

### Scoped Technical Actions
1. **Target Files:**
   - `database/migrations/versions/p5_19b_project_repo_bindings.py`
   - `database/models/repo_binding.py`
   - `kanban/repos/mirror.py` (`MirrorManager`, `MirrorPolicy`, `GitCommandRunner` protocol + `ExecGitCommandRunner`)
   - `kanban/repos/url_policy.py` (`validate_remote_url()`)
   - `kanban/api/v1/repo_bindings.py`
   - `mcp/admin/tools/manage_cycles_and_modules.py` (edit: add actions `bind_project_repo`, `list_repo_bindings`, `refresh_repo_binding`, `unbind_project_repo`)
   - `agent/context/repo_context.py` (`resolve_repo_context(binding, ref) -> RepoContext` used by the KB-P5-19a builder)
2. **DDL (not defined in spec; defined here):**
   ```sql
   CREATE TABLE project_repo_bindings (
     id                    UUID PRIMARY KEY DEFAULT uuidv7(),
     workspace_id          UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
     project_id            UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
     slug                  TEXT NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
     remote_url            TEXT NOT NULL CHECK (char_length(remote_url) <= 2048),
     default_ref           TEXT NOT NULL DEFAULT 'main' CHECK (default_ref ~ '^[A-Za-z0-9._/-]{1,200}$' AND default_ref !~ '\.\.'),
     access_mode           TEXT NOT NULL CHECK (access_mode IN ('bare_git_tools','ro_vfs_mount')),
     credential_ciphertext BYTEA,           -- optional deploy key / token, envelope-encrypted via KB-P2-03
     credential_dek_kid    TEXT,
     last_fetched_commit   TEXT CHECK (last_fetched_commit ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),
     last_fetched_at       TIMESTAMPTZ,
     last_fetch_error      TEXT,
     created_by            UUID NOT NULL REFERENCES principals(id),
     UNIQUE (project_id, slug)
   );
   ```
   `ENABLE` + `FORCE ROW LEVEL SECURITY`; read requires `VIEW` on project, writes `PROJECT_ADMIN` `WITH CHECK`. Mirror path is derived, never stored from input: `/var/lib/kanban/git-mirrors/<workspace_id>/<binding_id>.git`.
3. **URL policy (`validate_remote_url`):** allow only `https://` and `ssh://` (plus scp-like `git@host:path` normalized to `ssh://`); reject `file://`, `ext::`, `fd::`, `git://`, `http://`, URLs with embedded credentials, leading `-` (option injection), whitespace/control chars. Resolve host and reject loopback, link-local (`169.254.0.0/16`, `fe80::/10`), RFC1918, and metadata addresses unless the CIDR is listed in workspace setting `allowed_git_cidrs`; when `air_gap_mode = TRUE`, only `allowed_git_cidrs` hosts are permitted. Resolution result is pinned for the clone via `-c http.curloptResolve=<host>:443:<ip>` (https) to prevent DNS rebinding.
4. **Mirror manager (`MirrorManager.clone_or_fetch(binding)`):** runs `git` via `asyncio.create_subprocess_exec` only (never shell) with argv prefix `("git", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never", "-c", "core.fsmonitor=false", "-c", "submodule.recurse=false", "-c", "transfer.fsckObjects=true")`; clone = `clone --mirror --no-local --no-hardlinks -- <url> <path>`, fetch = `--git-dir=<path> fetch --prune --no-tags origin`. Env is replaced (not inherited): `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`, `GIT_ALLOW_PROTOCOL=https:ssh`, `HOME=<tmp>`, `PATH=/usr/bin:/bin`, `GIT_SSH_COMMAND` unset (ssh via `core.sshCommand` set to `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=<binding known_hosts>`). Timeout `120s` (kill process group); mirror size `<= 2 GiB` after fetch else delete mirror and set `last_fetch_error='MIRROR_SIZE_LIMIT'`. Mirror directories are mode `0750` owned by the mirror service user and mounted `:ro` into `agent-runtime` (compose change documented, not executed here). Decrypted credentials live only in a `bytearray` passed via a `0600` temp file deleted in `finally` and zeroed.
   - `MirrorPolicy(allow_file_protocol: bool = False)`: `True` is only constructible in tests (constructor param, never read from config/env); a test asserts the API/service path always constructs `False`.
5. **`resolve_repo_context(binding, ref)`:** `git --git-dir=<mirror> rev-parse --verify --end-of-options <ref>^{commit}` -> 40/64-hex `head_commit`; returns `RepoContext(mount_path="/workspace/repo", access="read-only", head_commit, mirror_path, access_mode)`.
6. **REST:** `GET|POST /api/v1/projects/{project}/repo-bindings`, `POST /api/v1/repo-bindings/{id}/refresh`, `DELETE /api/v1/repo-bindings/{id}` (`409 REPO_BINDING_IN_USE` if referenced by an enabled hook's agent with `repo_access_mode != 'none'` in the project). Credentials are write-only (never serialized). Writes require `aal_level >= 2`.
7. **MCP:** tool 6 actions listed in item 1, `EntityResolver` for project key and binding slug, `InlineSafeDumper` output, `unbind_project_repo` requires `confirm: true`.

### Mandatory Feature Unit Tests
- **Test File(s):**
  - `kanban/tests/repos/test_url_policy.py`
  - `kanban/tests/repos/test_mirror_manager.py` (`FakeGitCommandRunner` asserting exact argv/env; plus 1 real-git test using a local bare repo in `tmp_path` with `MirrorPolicy(allow_file_protocol=True)`)
  - `kanban/tests/repos/test_repo_bindings_api.py` (clean-DB harness)
  - `mcp/tests/admin/test_bind_project_repo.py`
  - `agent/tests/context/test_repo_context.py`
- **Required Test Cases:**
  1. Positive: bind `https://git.example.internal/kanban.git` (resolver faked to an `allowed_git_cidrs` IP) -> `201`, clone argv equals the exact hardened prefix + `clone --mirror --no-local --no-hardlinks -- <url> <derived path>`; `resolve_repo_context` returns the 40-hex commit of the real-git fixture.
  2. Security (URL): `file:///etc`, `ext::sh -c id`, `--upload-pack=touch /tmp/x`, `https://user:pass@host/r.git`, `http://host/r.git`, `https://169.254.169.254/r.git`, `https://127.0.0.1/r.git`, `git://host/r` -> each `422 REPO_URL_REJECTED` with a distinct `reason`.
  3. Security (repo content): real-git fixture repo containing `.git/hooks/post-checkout` and a `post-merge` hook script that writes a canary file -> after clone + fetch the canary does not exist; env passed to runner contains no inherited variables (e.g. `LD_PRELOAD`, `GIT_DIR`).
  4. Security (API): `MEMBER` -> `404`; `aal_level=1` admin -> `403 AAL2_REQUIRED`; serializer never contains `credential_ciphertext`; ref `main; rm -rf /` and `../x` rejected by CHECK and Pydantic.
  5. Boundary: fake runner exceeding `120s` -> process group killed, `last_fetch_error='MIRROR_TIMEOUT'`; size `2 GiB + 1` -> mirror removed, `MIRROR_SIZE_LIMIT`; `air_gap_mode=TRUE` + non-allowlisted public host -> `422`.
  6. MCP: `bind_project_repo` with project `"KAN"` resolves; `unbind_project_repo` without `confirm` deletes nothing; DNS rebinding simulation (resolver returns allowed IP then `127.0.0.1`) -> clone uses pinned first IP via `http.curloptResolve`.
- Touched-module coverage `>= 95%` for `kanban.repos` and `agent.context.repo_context`.

### Scoped Definition of Done (Literal Pass Criteria for Reality-Checker)
- [ ] **File Existence & Implementation:** All target files exist; `MirrorManager.clone_or_fetch`, `validate_remote_url`, `resolve_repo_context` implemented; MCP tool 6 exposes the 4 actions.
- [ ] **Unit Tests Implemented & Passing:** `uv run pytest kanban/tests/repos mcp/tests/admin/test_bind_project_repo.py agent/tests/context/test_repo_context.py -q --cov=kanban.repos --cov=agent.context --cov-branch --cov-report=term-missing --cov-fail-under=95` exits `0`.
- [ ] **Build / Type / Lint Clean:** `uv run ruff check . && uv run mypy --strict database kanban mcp agent && uv run lint-imports` exits `0`; ruff rules `S602`, `S604`, `S605` produce `0` findings.
- [ ] **Schema Proof:** `schema-dump.sql` shows `project_repo_bindings` with all CHECKs and `relforcerowsecurity = t`.
- [ ] **Specialist Gates:** `api-specialist-review.md` and `ui-specialist-review.md` exist with approval lines.
- [ ] **Forensic Proof Packet Complete:** All files below exist in `docs/qa/<TICKET_ID>/`.

### Forensic Verification Proof (Passive Audit Bundle for Reality-Checker)
1. `docs/qa/<TICKET_ID>/git-diff.patch`
2. `docs/qa/<TICKET_ID>/unit-test-results.txt`
3. `docs/qa/<TICKET_ID>/build-check.txt`
4. `docs/qa/<TICKET_ID>/schema-dump.sql`
5. `docs/qa/<TICKET_ID>/git-argv-trace.txt` - recorded argv + env (credentials redacted) for clone, fetch, and rev-parse from the fake runner tests.
6. `docs/qa/<TICKET_ID>/contract-sample.json` - REST create/refresh/delete samples and each `422 REPO_URL_REJECTED` reason.
7. `docs/qa/<TICKET_ID>/mcp-transcript.yaml` - `bind_project_repo`, `list_repo_bindings`, `unbind_project_repo` (unconfirmed + confirmed).
8. `docs/qa/<TICKET_ID>/api-specialist-review.md` and `docs/qa/<TICKET_ID>/ui-specialist-review.md`.
9. `docs/qa/<TICKET_ID>/message-to-reality-checker.md` - states that `project_repo_bindings` DDL is defined here because the spec omits it.
- Screenshots: N/A - Non-UI Ticket.
