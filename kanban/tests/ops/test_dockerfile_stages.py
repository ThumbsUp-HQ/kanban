# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Test Dockerfile targets and stages consistency."""

from __future__ import annotations

import re
from pathlib import Path


def test_dockerfile_stages_exist_and_match_compose() -> None:
    """Verify Dockerfile contains sandbox, standalone, agent-runner, and runtime-slim stages."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Dockerfile must exist at repository root"
    content = dockerfile_path.read_text(encoding="utf-8")

    stages = re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", content, re.MULTILINE)
    assert "web-builder" in stages
    assert "py-builder" in stages
    assert "runtime-slim" in stages
    assert "agent-runner" in stages
    assert "sandbox" in stages
    assert "standalone" in stages

    # Verify sandbox runs as non-root UID 10001
    assert "USER 10001:10001" in content
    assert "kanban.sandbox.worker" in content
