# Copyright 2026 Kanban Platform Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Shared pytest configuration and fixtures for performance and SLA benchmarks.

NOTE: As per KANBA-162 / Pytest 9.2+ standards, non-top-level conftest files
MUST NOT declare pytest_plugins. Root conftest already declares pg_harness.
"""

# ruff: noqa: TC002
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom performance marks."""
    config.addinivalue_line(
        "markers",
        "perf: Performance and SLA budget tests.",
    )
    config.addinivalue_line(
        "markers",
        "container: Container integration tests requiring Docker daemon.",
    )
