# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Pluggable agent execution harnesses (KB-P5-22a, KB-P5-21, KB-P5-20)."""

from agent.harnesses.remote_runner import (
    RemoteRunnerHarness,
    register_remote_runner_harness,
)

__all__ = [
    "RemoteRunnerHarness",
    "register_remote_runner_harness",
]
