"""Pytest configuration for kanban module tests."""

from typing import Any
import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Normalize file-based --cov targets to package module specs for coverage.py."""
    cov_plugin = config.pluginmanager.get_plugin("_cov")
    if cov_plugin and getattr(cov_plugin, "cov_controller", None):
        ctrl = cov_plugin.cov_controller
        for cov_obj in (getattr(ctrl, "cov", None), getattr(ctrl, "combining_cov", None)):
            if cov_obj is None:
                continue
            inorout = getattr(cov_obj, "_inorout", None)
            if inorout is None:
                continue
            import coverage.inorout

            normalized: list[str] = []
            changed = False
            for pkg in inorout.source_pkgs:
                if isinstance(pkg, str) and pkg.endswith(".py"):
                    normalized.append(pkg[:-3].replace("/", "."))
                    changed = True
                else:
                    normalized.append(pkg)
            if changed:
                inorout.source_pkgs = normalized
                inorout.source_pkgs_unmatched = list(normalized)
                inorout.source_pkgs_match = coverage.inorout.ModuleMatcher(
                    normalized, "source_pkgs", "Source imports", inorout._debug
                )
