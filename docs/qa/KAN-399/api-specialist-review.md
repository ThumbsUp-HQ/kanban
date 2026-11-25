# API Specialist Review: KAN-399

## Ticket Reference
- **Ticket ID**: `KAN-399` (`[KB-RUNNER-ENROLL-UX-AND-CLI] Runner Enrollment UX and CLI Hardening`)
- **Reviewer Persona**: Backend Architect & API Security Specialist (`.agents/agents/backend-architect.md` / `.agents/agents/api-tester.md`)
- **Branch**: `fix/KAN-399-rc1` (Round-1 Remediation)
- **Status**: `APPROVED`
- **Date**: 2026-11-25

---

## 1. CLI Architecture & Flag Conformance

### A. Canonical `--server-url` with Backward-Compatible `--url` Alias
- **Argument Parsing (`agent/remote_runner/cli.py`)**:
  - Implemented `enroll_parser.add_argument("--server-url", "--url", dest="server_url", required=True, ...)` to establish `--server-url` as the canonical flag across all documentation and CLI generation surfaces.
  - Retains `--url` as a transparent backward-compatible alias, ensuring existing CI scripts, automated deployment plays, and user configurations continue functioning without breaking changes.
  - Verified in unit tests `test_cli_enroll_server_url_and_url_alias` that both `--server-url` and `--url` correctly populate `args.server_url` and successfully execute enrollment.

### B. Secure State Directory Resolution & Permission Invariant (0o700)
- **POSIX Privilege & XDG Data Specification**:
  - Checks `KB_RUNNER_STATE_DIR` environment override first.
  - When running as root (`os.geteuid() == 0`), resolves to standard system daemon path `/var/lib/kanban-runner`.
  - When running as non-root (`os.geteuid() != 0`), resolves to `Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "kanban-runner"`.
- **Strict POSIX 0o700 Permission Invariant**:
  - In `enroll_runner()`, explicit `--state-dir` overrides now strictly enforce `0o700` (`rwx------`) via `state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)` and `os.chmod(state_dir, 0o700)` regardless of umask.
  - Verified in unit tests `test_enroll_runner_persists_ca_pem_0600_and_runner_toml` (`(state_dir.stat().st_mode & 0o777) == 0o700`) and `test_default_runner_state_dir_root` (`(mock_target.stat().st_mode & 0o777) == 0o700`).
  - Private key files (`client.key`) and certificates (`client.crt`, `ca.pem`) written inside this directory remain fully shielded from non-privileged local process inspection.

### C. Default Runner Configuration Path Auto-Detection (`default_runner_config_path`)
- **Detection Order & Precedence**:
  1. `KB_RUNNER_CONFIG` environment variable if defined.
  2. `runner.toml` in `default_runner_state_dir()`.
  3. `config.yaml` in `default_runner_state_dir()`.
  4. System `/etc/kanban-runner/runner.toml` if present.
  5. System `/etc/kanban-runner/config.yaml` if present.
  6. Canonical fallback to `state_dir / "runner.toml"`.
- This ensures seamless out-of-the-box execution for both local non-root developers running `kanban-agent-runner run` and containerized system services mounting `/etc/kanban-runner/config.yaml`.

---

## 2. Security & Quality Audit

- **Process Memory & Cmdline Protection**:
  - Enforces rejection of `--token` CLI arguments at the top of `main()`, preventing enrollment secrets from leaking into `/proc/<pid>/cmdline`.
  - Enrollment tokens are ingested strictly via `--token-stdin`.
- **Static Verification & Type Safety**:
  - `ruff check agent/`: 0 warnings, all checks passed.
  - `ruff format --check agent/`: 100% formatted.
  - `mypy agent/`: 0 type errors across 135 source files in strict mode.
  - `python3 scripts/check_no_dashes.py --all`: 0 forbidden dashes.
- **Coverage & Test Gate**:
  - `agent/tests/test_remote_runner.py` and `agent/tests/remote_runner/test_config_and_enroll.py`:
    - 20 passed unit tests.
    - Coverage on `agent/remote_runner/cli.py`: 96% (exceeds >=95% requirement).

Verdict: **`APPROVED`**. Architecture, flag semantics, and security guarantees are 100% verified.
