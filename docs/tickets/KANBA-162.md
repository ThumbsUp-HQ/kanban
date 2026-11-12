---
id: KANBA-162
title: "Priority #0 Broken-Main Remediation: pre-RLS test seeding + normalize_inspect lone-surrogate guard"
epic: KB-E0
depends_on: []
spec_sections: ["5.2", "3.3"]
new_dependencies: []
---

### User Story
As a systems engineer, I need pre-RLS database/tests bootstrapping to run with superuser authority before dropping back to kanban_app under FORCE ROW LEVEL SECURITY, and normalize_inspect to scan lone surrogates before raw.encode("utf-8"), so that broken main test failures are eliminated and malformed inputs never trigger unhandled 500 exceptions.

### Scoped Definition of Done
- [ ] **File Existence & Implementation:** conftest.py bootstrap_workspace_admin and kanban/content/normalize.py lone-surrogate checks exist.
- [ ] **Unit Tests Implemented & Passing:** pytest database/tests kanban/tests agent/tests mcp/tests exits 0.
- [ ] **Build / Type / Lint Clean:** ruff check, ruff format --check, mypy --strict, lint-imports exit 0.
- [ ] **Forensic Proof Packet Complete:** git-diff.patch, unit-test-results.txt, build-check.txt exist.
