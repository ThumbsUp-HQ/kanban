#!/usr/bin/env bash
# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
#
# Production Container Cold-Boot Smoke Gate (KANBA-223)
# Validates kanban-ctl --help, vitest meta-assertion harness,
# and Playwright RBAC / Zero-Mock / Visual-Regression specs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== Stage 1: kanban-ctl CLI cold-boot --help ==="
cd "${REPO_ROOT}"
PYTHON_BIN="python3"
if [ -x "${REPO_ROOT}/.venv/bin/python" ]; then
  PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
fi
"${PYTHON_BIN}" -m kanban.cli.ctl --help > /dev/null
echo "kanban-ctl --help exited 0 cleanly."

echo "=== Stage 2: Vitest Gate Auditor Meta-Assertion Harness ==="
cd "${REPO_ROOT}/kanban/web"
npx vitest run e2e/support/gateAuditor.unit.test.ts
echo "Vitest meta-assertion tests passed."

echo "=== Stage 3: Playwright Automated Smoke & Visual Gate ==="
export E2E_PORT="${E2E_PORT:-4193}"
cd "${REPO_ROOT}/kanban/web"
npx playwright test \
  e2e/qa/kanba-223-smoke-coldboot.spec.ts \
  e2e/qa/kanba-223-rbac-missing-controls.spec.ts \
  e2e/qa/kanba-223-closed-loop-persist.spec.ts \
  e2e/qa/kanba-223-visual-contrast-overflow.spec.ts \
  --project=desktop \
  --workers=4

echo "Running 390x844 mobile visual & overflow gate sweep..."
npx playwright test \
  e2e/qa/kanba-223-visual-contrast-overflow.spec.ts \
  --project=mobile \
  --workers=2

echo "=== Stage 4: Plain ASCII Hyphens Validation ==="
cd "${REPO_ROOT}"
"${PYTHON_BIN}" -m scripts.check_no_dashes --all
echo "check_no_dashes passed with 0 violations."

echo "=== KANBA-223 Cold-Boot Smoke Gate: ALL CHECKS PASSED ==="
