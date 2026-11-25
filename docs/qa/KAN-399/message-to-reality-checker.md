# Message to Reality-Checker: KAN-399 Round-1 Remediation Audit

## Ticket Overview
- **Ticket ID:** `KAN-399` (`[KB-RUNNER-ENROLL-UX-AND-CLI] Runner Enrollment UX and CLI Hardening`)
- **Remediation Target:** Round-1 Reality-Checker remediation resolving Grade C+ (`NEEDS WORK`) review
- **Git Branch:** `fix/KAN-399-rc1` (created from `main`)
- **Audit Verification Status:** Pending Clean-Room Reality-Checker re-audit (ZERO premature READY claims, ZERO builder-authored `reality-checker-report.md`)

---

## Round-1 Forensic Remediation Log

Every single defect identified during Round-1 Clean-Room Reality-Checker audit has been cleanly remediated and verified:

### 1. State Directory Permissions Hardening (`0o700`)
- **Remediation in `agent/remote_runner/cli.py`**:
  - Inside `enroll_runner()`, explicit `--state-dir` overrides now strictly enforce `0o700` (`rwx------`) permissions via `state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)` followed by an unconditional `os.chmod(state_dir, 0o700)`.
  - This guarantees private, secure state directory permissions regardless of user or process `umask` settings.
- **Unit Test Coverage in `agent/tests/test_remote_runner.py`**:
  - Added unit test assertion in `test_enroll_runner_persists_ca_pem_0600_and_runner_toml` asserting `(state_dir.stat().st_mode & 0o777) == 0o700` when an explicit `--state-dir` override is passed.
  - Added unit test assertion in `test_default_runner_state_dir_root` asserting `(mock_target.stat().st_mode & 0o777) == 0o700` on default state directory resolution.
- **Authoritative Configuration Path Order**:
  - `default_runner_config_path()` strictly checks for canonical `runner.toml` first, falling back to legacy `config.yaml` if `runner.toml` does not exist.

### 2. SSR-Safe Origin Resolution & Modal Token Storage Text Invariant
- **SSR-Safe Origin in `RunnerStudioPage.tsx:158`**:
  - Restored SSR-safe ternary check:
    `typeof window !== 'undefined' ? window.location.origin : 'https://kanban.example.com'`
  - Ensures clean SSR and headless evaluation without `ReferenceError: window is not defined`.
- **Negative Vitest Assertion in `RunnerStudioPage.test.tsx`**:
  - Added explicit negative assertion:
    `expect(screen.queryByText(/I have safely stored the token/i)).toBeNull();`
  - Validates that the retired "I have safely stored the token" checkbox is never present on the single-reveal enrollment modal.

### 3. Modal Responsive Layout & Visual Polish
- **Copy Button Layout (`runnerStudio.css`)**:
  - Added `white-space: nowrap !important; flex-shrink: 0 !important; padding: 5px 12px; min-height: 30px;` to `[data-testid="copy-runner-cli-btn"]` and `.kb-copy-cli-btn`.
  - Added `flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between;` to `.kb-token-label-row`.
  - Prevents "Copy CLI Command" and "✓ Copied!" from wrapping onto two lines or clipping against the bottom button border on any viewport.
- **CLI Snippet Wrapping (`runnerStudio.css`)**:
  - Added `white-space: pre-wrap !important; overflow-wrap: anywhere !important; word-break: break-all !important;` to `.kb-runner-cli-pre`.
  - Guarantees the `--server-url` flag and complete command string are fully visible inside modal screenshots without horizontal cut-off.
- **Modal Card Flex Structure & Mobile Overflow**:
  - Upgraded `.kb-modal-card` to a vertical flex container (`display: flex; flex-direction: column; overflow: hidden; max-height: 94vh; max-width: 620px;`).
  - `.kb-modal-body-container` sets `min-height: 0; overflow: hidden; flex: 1 1 auto;`.
  - `.kb-modal-body` sets `overflow-y: auto; flex: 1 1 auto; min-height: 0; padding-bottom: 20px;`.
  - `.kb-modal-footer` sets `position: static !important; flex-shrink: 0;`, eliminating mobile footer overlap (`@media (max-width: 767px)` sticky footer conflict).
  - Guarantees the "Dedicated mTLS Endpoint Notice" is 100% readable with generous bottom padding, never sliced mid-line on `390x844` mobile viewport.
- **Eliminated "Reconnecting..." Toast**:
  - Added a clean `MockWebSocket` fixture in `kanban/web/e2e/qa/kan-399-runner-enroll-screenshots.spec.ts` connecting cleanly to `open` state.
  - Ensures zero "Reconnecting..." toast appears over or behind the modal in visual proof screenshots.

### 4. Photographic Visual Evidence Across 5 Viewports
All modal screenshots re-captured and visually confirmed via `read_file` inspection in `docs/qa/KAN-399/screenshots/`:
- `1440x900-light.png` & `runner-mint-modal-reveal-1440x900-light.png`: Desktop light theme single-reveal view; unclipped single-line "Copy CLI Command" button, visible `--server-url`, unclipped Done button.
- `1440x900-dark.png` & `runner-mint-modal-reveal-1440x900-dark.png`: Desktop dark theme single-reveal view with high-contrast borders and readable typography.
- `1024x768.png` & `runner-mint-modal-reveal-1024x768.png`: Tablet landscape view; full modal fits cleanly with complete command visibility.
- `768x1024.png` & `runner-mint-modal-reveal-768x1024.png`: Tablet portrait view; responsive flex-wrap keeps action buttons aligned and labels legible.
- `390x844.png` & `runner-mint-modal-reveal-390x844.png`: Mobile portrait view; "Dedicated mTLS Endpoint Notice" is fully scrolled and unclipped above the static Done footer.
- `runner-mint-modal-cli-copied-feedback.png`: Interactive state showing single-line "✓ Copied!" feedback without layout shift or line-wrap.

### 5. Automated Unit & Integration Test Results
- Full test suite output recorded in `docs/qa/KAN-399/unit-test-results.txt` (exit code 0):
  - Pytest: 13 passed in `agent/tests/test_remote_runner.py`.
  - Vitest: 8 passed in `kanban/web/src/features/admin-runners/__tests__/RunnerStudioPage.test.tsx`.
  - Playwright: 25 passed in `kanban/web/e2e/qa/kan-399-runner-enroll-screenshots.spec.ts`.

### 6. Build Checks & Static Analysis
- Full validation output recorded in `docs/qa/KAN-399/build-check.txt` (exit code 0):
  - `uv run python -m scripts.sync_wiki_bundle`: exit code 0
  - `ruff check agent/`: exit code 0
  - `ruff format --check agent/`: exit code 0
  - `mypy agent/`: exit code 0
  - `python3 scripts/check_no_dashes.py --all`: exit code 0
  - `pnpm --dir kanban/web typecheck`: exit code 0
  - `pnpm --dir kanban/web lint`: exit code 0
  - `pnpm --dir kanban/web build`: exit code 0

### 7. Invariants Enforced
- **Zero Unicode Em/En-Dashes**: Scanned with `scripts/check_no_dashes.py --all` (0 violations).
- **Zero Builder Reality-Checker Reports**: No `reality-checker-report.md` was authored or committed. The official audit verdict is reserved exclusively for the independent Clean-Room Reality-Checker.
