# Reality Checker Verification Packet: KAN-312

## Ticket Summary
- **Ticket ID:** KAN-312
- **Title:** [KB-BUILD-VER-01] Format System & Build Metadata Version as 0.{release}.{commits} Across Backend, Docker Builds, and About/Diagnostics UI
- **Branch:** `main` (merged from `feat/KAN-312-build-version-metadata`)
- **Merged Commit (`HEAD`):** `f338350d7ab1a05b823a2f46eebf6956266efecd` (`f338350d`)
- **Pre-Ticket Base Commit (`main`):** `301ff830e9907d166a736398f15db5db70d042f5` (`301ff830`)
- **Worktree:** `/home/adamoutler/kanban`
- **Visual Browser Screenshots (`docs/qa/KAN-312/screenshots/`):**
  - `docs/qa/KAN-312/screenshots/01-desktop-light-about-version.png` (`1440x900` Light Mode)
  - `docs/qa/KAN-312/screenshots/02-desktop-dark-about-version.png` (`1440x900` Dark Mode)
  - `docs/qa/KAN-312/screenshots/03-tablet-about-version.png` (`768x1024`)
  - `docs/qa/KAN-312/screenshots/04-mobile-portrait-about-version.png` (`390x844`)
  - `docs/qa/KAN-312/screenshots/05-mobile-landscape-about-version.png` (`844x390`)
- **Component Scope:**
  - Backend: `kanban/ops/build_info.py`, `kanban/ops/sbom.py`, `kanban/ops/openapi_builder.py`, `kanban/api/v1/system.py`, `kanban/api/v1/system_status.py`, `kanban/api/v1/admin/diagnostics.py`
  - Docker & CI: `Dockerfile`, `.forgejo/workflows/ci.yml`, `.github/workflows/ci.yml`
  - Frontend: `kanban/web/src/features/about/AboutPage.tsx`, `kanban/web/src/app/Sidebar.tsx`, `kanban/web/src/app/useSystemStatus.ts`
  - Tests: `kanban/tests/api/test_system_about.py`, `kanban/tests/api/test_system_status.py`, `kanban/tests/ops/test_sbom.py`, `kanban/tests/test_export_openapi.py`, `kanban/tests/platform/test_world_class_standards.py`, `kanban/tests/api/test_admin_diagnostics.py`, `kanban/web/src/features/about/__tests__/AboutPage.test.tsx`, `kanban/web/src/features/about/__tests__/aboutApi.test.ts`, `kanban/web/src/app/__tests__/AboutNavigation.test.tsx`

---

## Technical Implementations

### 1. Dynamic Version Resolution: `0.<current_release_version>.<git_commit_count>`
- **Module:** `kanban/ops/build_info.py`
- **Constants & Helpers:**
  - Defined `CURRENT_RELEASE_VERSION = "2"` (read from `os.environ.get("KB_RELEASE_VERSION", "2").strip() or "2"`).
  - Implemented `resolve_git_commit_count(cwd: Path | None = None) -> int`:
    - Checks `os.environ.get("KB_GIT_COMMIT_COUNT")` first (validates non-negative integer digits).
    - Falls back to `git rev-list --count HEAD` via `subprocess.run(..., timeout=5)`.
    - Handles exceptions, timeouts, missing git binaries, and detached states by safely returning `0`.
  - Implemented `resolve_platform_version(cwd: Path | None = None) -> str`:
    - Respects explicit `KB_VERSION` override if configured.
    - Otherwise returns formatted dynamic version `f"0.{release_ver}.{commit_count}"` (e.g., `0.2.1203`).
  - Updated `BuildInfo` dataclass to expose `version: str` and `git_commit_count: int`.
  - Updated `get_build_info()` to populate both fields dynamically.

### 2. Integration Across Backend, OpenAPI, and SBOM
- **CycloneDX 1.5 SBOM (`kanban/ops/sbom.py`):**
  - Updated `PLATFORM_VERSION: Final[str] = resolve_platform_version()`.
  - Both top-level metadata component and metadata tools component reflect dynamic version `0.<release>.<commits>`.
- **OpenAPI Builder (`kanban/ops/openapi_builder.py`):**
  - Populates OpenAPI spec `info["version"]` using `resolve_platform_version()`.
- **System Endpoints (`kanban/api/v1/system.py` & `kanban/api/v1/system_status.py`):**
  - Updated `PlatformSummaryResponse` and `SystemAboutResponse` schemas and endpoints to return dynamic `version` and `git_commit_count`.
  - Updated `SystemStatusResponse` to include `version: str | None = None` and `openapi_version: str | None = None`, populated from `get_build_info()`.
- **Admin Diagnostics (`kanban/api/v1/admin/diagnostics.py`):**
  - Updated `BuildDiagnosticsInfo` schema and endpoint to expose `version` and `openapi_version` matching `get_build_info()`.

### 3. Docker and CI Plumbing
- **`Dockerfile` (`runtime-slim` stage):**
  - Added `ARG KB_GIT_COMMIT_COUNT=""`.
  - Added `ENV KB_GIT_COMMIT_COUNT=${KB_GIT_COMMIT_COUNT}` so container runtime inherits commit count without requiring git history inside minimal images.
- **`.forgejo/workflows/ci.yml` & `.github/workflows/ci.yml`:**
  - Added `--build-arg KB_GIT_COMMIT_COUNT=$(git rev-list --count HEAD)` to all `runtime-slim` and `standalone` container build steps.

### 4. Frontend UI Alignment
- **About Page (`kanban/web/src/features/about/AboutPage.tsx`):**
  - Inside the System & Build Metadata section (`data-testid="about-metadata-section"`), added the primary metadata row:
    ```tsx
    <div className="kb-about-meta-item">
      <span className="kb-about-meta-label">Version:</span>
      <code className="kb-about-meta-value" data-testid="about-meta-version">{version}</code>
    </div>
    ```
  - Hero badge displays `v0.<release>.<commits>`.
- **App Sidebar (`kanban/web/src/app/Sidebar.tsx`):**
  - Uses `useSystemStatus` hook (`version` / `openapi_version`) to dynamically render `v${systemVersion}` in the footer version label (`.kb-sidebar-about-version`).

---

## Verification Evidence
- **Unit & Integration Tests:**
  - 78 Pytest tests passed in 145s (`docs/qa/KAN-312/unit-test-results.txt`).
  - 14 Vitest tests passed across 3 test files in 3.5s (`docs/qa/KAN-312/unit-test-results.txt`).
  - Unit test coverage for `kanban/ops/build_info.py`: **97%** branch coverage (exceeds 95% threshold).
- **Code Quality & Static Analysis:**
  - `make check`: 100% clean across ruff check, ruff format, mypy (1192 files), lint-imports contracts, check_no_dashes, and check-migrations (`docs/qa/KAN-312/build-check.txt`).
  - `pnpm --dir kanban/web check:api`: Clean (OpenAPI spec and schema.gen.ts in sync).
  - `pnpm --dir kanban/web typecheck`: 0 errors.
  - `pnpm --dir kanban/web lint`: 0 errors, 0 warnings.
  - `pnpm --dir kanban/web build`: Clean production build.
- **Prohibited Characters:**
  - `uv run python -m scripts.check_no_dashes --all` passed with 0 errors.
- **Contract & Patch Proofs:**
  - `docs/qa/KAN-312/git-diff.patch`
  - `docs/qa/KAN-312/contract-sample.json`
