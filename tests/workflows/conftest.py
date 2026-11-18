# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pytest fixtures for workflow E2E integration tests.

NOTE: As per KANBA-162 / Pytest 9.2+ standards, non-top-level conftest files
MUST NOT declare pytest_plugins. Root conftest already declares pg_harness.
"""

from __future__ import annotations

from kanban.tests.api.conftest import (
    ApiEnv,
    SeededUser,
    api_env,
    as_principal,
    contract_recorder,
    make_module,
    make_project,
    make_user,
)

__all__ = [
    "ApiEnv",
    "SeededUser",
    "api_env",
    "as_principal",
    "contract_recorder",
    "make_module",
    "make_project",
    "make_user",
]
