"""Workspace layout and boundary contract test suite."""

import importlib
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MEMBER_MODULES = ["database", "kanban", "mcp", "agent"]
MEMBER_PACKAGES = {
    "kanban-database": "database",
    "kanban-core": "kanban",
    "kanban-mcp": "mcp",
    "kanban-agent": "agent",
}

REQUIRED_HEADINGS = [
    "## Responsibility",
    "## Depends On",
    "## Depended On By",
    "## Inbound Contracts",
    "## Outbound Contracts",
    "## Performance Budgets",
    "## Failure Modes",
]


def test_member_packages_importable_and_version() -> None:
    """Test Case 1: Positive check that all member packages import and export version 0.0.0."""
    for module_name in MEMBER_MODULES:
        mod = importlib.import_module(module_name)
        assert hasattr(mod, "__version__"), f"Module {module_name} missing __version__ attribute"
        assert mod.__version__ == "0.0.0", (
            f"Module {module_name} version is {mod.__version__}, expected 0.0.0"
        )


def test_workspace_layout_and_manifests() -> None:
    """Test Case 2: Positive check of module files, 7 manifest headings, and symlinks."""
    for module_name in MEMBER_MODULES:
        module_dir = REPO_ROOT / module_name
        assert module_dir.is_dir(), f"Expected directory {module_dir} to exist"

        pyproject_path = module_dir / "pyproject.toml"
        assert pyproject_path.is_file(), f"Missing pyproject.toml in {module_name}"

        init_path = module_dir / "__init__.py"
        assert init_path.is_file(), f"Missing __init__.py in {module_name}"

        gemini_path = module_dir / "GEMINI.md"
        assert gemini_path.is_file(), f"Missing GEMINI.md in {module_name}"

        gemini_content = gemini_path.read_text(encoding="utf-8")
        for heading in REQUIRED_HEADINGS:
            assert heading in gemini_content, f"Heading '{heading}' missing from {gemini_path}"

        agents_link = module_dir / "AGENTS.md"
        assert os.path.islink(agents_link), (  # noqa: PTH114  # literal specification compliance with KB-P0-01.md
            f"Expected {agents_link} to be a symlink"
        )
        readlink_val = os.readlink(agents_link)  # noqa: PTH115  # literal specification compliance with KB-P0-01.md
        assert readlink_val == "GEMINI.md", (
            f"Symlink {agents_link} targets {readlink_val}, expected GEMINI.md"
        )


def test_import_linter_negative_contract_violation(tmp_path: Path) -> None:
    """Test Case 3: Negative/security test asserting reverse imports fail lint-imports."""
    # Create throwaway package tree where database imports kanban
    db_pkg = tmp_path / "database"
    db_pkg.mkdir()
    (db_pkg / "__init__.py").write_text("import kanban\n", encoding="utf-8")

    kb_pkg = tmp_path / "kanban"
    kb_pkg.mkdir()
    (kb_pkg / "__init__.py").write_text('__version__ = "0.0.0"\n', encoding="utf-8")

    cfg_file = tmp_path / "importlinter.ini"
    cfg_file.write_text(
        """[importlinter]
root_packages =
    database
    kanban

[importlinter:contract:1]
name = Forbidden reverse dependency database -> kanban
type = layers
layers =
    kanban
    database
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path)

    lint_bin = shutil.which("lint-imports") or "lint-imports"
    result = subprocess.run(
        [lint_bin, "--config", str(cfg_file)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )

    assert result.returncode != 0, (
        f"Expected non-zero exit code on reverse import violation, got {result.returncode}"
    )
    has_broken = (
        "BROKEN" in result.stdout
        or "broken" in result.stdout
        or "is not allowed to import" in result.stdout
    )
    assert has_broken


def test_uv_lock_workspace_sources_and_python_version() -> None:
    """Test Case 4: Boundary test asserting workspace sources and requires-python >=3.12,<3.13."""
    lock_path = REPO_ROOT / "uv.lock"
    assert lock_path.is_file(), "uv.lock does not exist"

    lock_data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock_data.get("package", [])

    for pkg in packages:
        name = pkg.get("name")
        if name in MEMBER_PACKAGES:
            source = pkg.get("source", {})
            is_workspace = (
                source.get("workspace") is True
                or "editable" in source
                or source.get("editable") == MEMBER_PACKAGES[name]
            )
            assert is_workspace, f"Package {name} has non-workspace source: {source}"

    root_pyproject_path = REPO_ROOT / "pyproject.toml"
    assert root_pyproject_path.is_file(), "Root pyproject.toml does not exist"

    pyproject_data = tomllib.loads(root_pyproject_path.read_text(encoding="utf-8"))
    requires_python = pyproject_data.get("project", {}).get("requires-python")
    expected_python = ">=3.12,<3.13"
    assert requires_python == expected_python, (
        f"Expected requires-python to be '{expected_python}', got {requires_python}"
    )


def test_license_and_notice_exist() -> None:
    """Test Case 5: Boundary test asserting LICENSE header contains Apache License."""
    license_path = REPO_ROOT / "LICENSE"
    assert license_path.is_file(), "LICENSE file does not exist"

    lines = [
        line.strip()
        for line in license_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert lines, "LICENSE file is empty"
    assert "Apache License" in lines[0], (
        f"Expected 'Apache License' in first non-empty line, got {lines[0]}"
    )

    notice_path = REPO_ROOT / "NOTICE"
    assert notice_path.is_file(), "NOTICE file does not exist"
    notice_text = notice_path.read_text(encoding="utf-8").strip()
    assert len(notice_text) > 0, "NOTICE file is empty"
    assert "Kanban Platform" in notice_text, "NOTICE missing Kanban Platform attribution"
