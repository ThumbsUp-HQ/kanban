# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Tests for agent-runner Dockerfile stage and reference docker-compose (KB-P5-22b, S2.4)."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_dockerfile_agent_runner_stage() -> None:
    """Validate Dockerfile contains agent-runner stage with zero EXPOSE and non-root USER."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.is_file(), "Dockerfile must exist at repo root"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "AS agent-runner" in content, "Dockerfile must define agent-runner stage"

    # Extract the agent-runner stage
    lines = content.splitlines()
    in_runner_stage = False
    runner_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("FROM ") and "AS agent-runner" in stripped:
            in_runner_stage = True
            runner_lines.append(stripped)
            continue
        if in_runner_stage and stripped.startswith("FROM "):
            # Next stage encountered
            break
        if in_runner_stage:
            runner_lines.append(stripped)

    stage_content = "\n".join(runner_lines)
    assert "USER 65532:65532" in stage_content, "agent-runner must run as non-root user 65532:65532"
    assert "ENTRYPOINT" in stage_content
    assert "kanban-agent-runner" in stage_content

    # Strict security invariant: ZERO EXPOSE directives in agent-runner stage
    for line in runner_lines:
        assert not line.startswith("EXPOSE"), (
            f"agent-runner stage must have ZERO inbound ports exposed, found: {line}"
        )


def test_docker_compose_runner_reference_spec() -> None:
    """Validate deploy/runner/docker-compose.runner.example.yml configuration."""
    compose_path = Path("deploy/runner/docker-compose.runner.example.yml")
    assert compose_path.is_file(), "Reference compose file must exist"

    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    assert "services" in data
    assert "agent-runner" in data["services"]

    svc = data["services"]["agent-runner"]
    assert svc.get("read_only") is True, "Service must specify read_only: true"
    assert svc.get("user") == "65532:65532", "Service must specify user: 65532:65532"
    assert "ALL" in svc.get("cap_drop", []), "Service must drop ALL capabilities"

    # Must not expose any inbound ports (outbound-only WSS daemon)
    assert "ports" not in svc, "Runner service must have ZERO exposed host ports"

    # Check volume mounts are read-only
    volumes = svc.get("volumes", [])
    found_ro_mount = False
    for vol in volumes:
        if isinstance(vol, str) and "/workspace/repos:ro" in vol:
            found_ro_mount = True
    assert found_ro_mount, "Must mount /workspace/repos as :ro"
