# API Specialist Gate Review: KANBA-145 (KB-P5-14)

- **Ticket**: `KANBA-145` (`KB-P5-14`: Tier B nsjail runner, seccomp-BPF profile, Unix-socket token-injecting egress proxy, CLONE_NEWUSER probe)
- **Reviewer**: `@arch-reviewer` (Systems/Backend Architect & API Specialist), independent audit
- **Branch / Commit audited**: `feat/KANBA-145` at `eb0bb29` (initial audit at `6ebd549`, changes requested, re-audited after fixes)

## Round 1 findings (all resolved in eb0bb29)
1. `_validate_path` accepted `%2f`, `%00`, `%5c` (decoded into real separators / NUL / backslash) and `fnmatch` `*` spanned `/`. Fixed: raw `%2f/%5c/%00/%2e/%25` rejected case-insensitively, NUL/backslash/CR/LF re-checked after decode, per-segment allowlist matching. Verified by direct probe of 10 hostile targets.
2. `communicate()` buffered unbounded child output on the host. Fixed: incremental reads capped at 64 KiB + 1 with process-group SIGKILL; proxy streams upstream body to 512 KiB.
3. Proxy header loop unbounded and 500 body echoed exception text. Fixed: request line <= 4096 (414), <= 64 headers / 16 KiB (431), handler wrapped in `asyncio.timeout` (408), fixed 500 text.

## Verified
- Seccomp profile: `SCMP_ACT_ERRNO` / errno 1, x86_64 + aarch64, `socket` allowed only for arg0 == AF_UNIX, `ioctl` limited to fd <= 2, 0 of the 23 forbidden syscalls in any ALLOW rule.
- Probe: nsjail uid 0, `(mode & 0o022) == 0`, 500ms dry run, fail-closed `SANDBOX_UNAVAILABLE_IN_STANDALONE`; runner raises before any spawn.
- Runner: argv-only, `--cgroup_mem_max 134217728`, `--keep_env=false`, token never in argv/env/stdin/mounts, token buffer zeroed in `finally`.
- Proxy: GET only (405), `/api/v1/` allowlist (403), max 10 requests (429), expiry (401), client Authorization/Cookie/Host/X-Forwarded/X-Kanban headers discarded, injected `Authorization` + `X-Kanban-Script-Depth: 1`, `follow_redirects=False`.
- `ScriptDepthGuardMiddleware`: 409 `SCRIPT_RECURSION_BLOCKED` for non-digit or >= 1 on execute, transitions and `/mcp/*`.
- Tests: 65/65 pass, 98.64% line+branch coverage on `kanban.sandbox` and `kanban.api.middleware.script_depth`; ruff, mypy --strict, lint-imports clean.

## Non-blocking follow-ups (to be ticketed)
- `GET /custom-fields` cached-only at depth >= 1 must be enforced by KANBA-143 (state: `scope["state"]["script_depth"]`).
- Real-binary smoke: `--disable_clone_newnet=false` flag form and OCI JSON passed to `--seccomp_policy` (nsjail expects Kafel) fail closed but need a Kafel export / real nsjail test before Tier B ships.
- Probe dry run uses `--chroot /` and `--time_limit 1`; spec says empty read-only root and 500ms.

**Verdict: APPROVED**
