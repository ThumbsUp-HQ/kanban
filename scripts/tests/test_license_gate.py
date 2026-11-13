"""Unit tests for scripts.license_gate enforcing permissive Apache-2.0 governance."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.license_gate import (
    AllowlistError,
    Verdict,
    _Parser,
    classify,
    evaluate_atom,
    is_non_waivable,
    is_workspace_package,
    load_allowlist,
    main,
    run_license_gate,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "licenses"


# -----------------------------------------------------------------------------
# Case 1: Positive run
# -----------------------------------------------------------------------------
def test_positive_fixture_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """Positive test: fixture with MIT, BSD-3-Clause, Apache-2.0, MIT OR GPL-3.0 exits 0."""
    py_json = FIXTURES_DIR / "python_clean.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "SUMMARY python=4 node=2 violations=0" in captured.out
    assert "violations=0" in captured.out


def test_classify_positive_variants() -> None:
    """Verify individual permissive license expressions return Verdict.ALLOW."""
    assert classify("MIT") == Verdict.ALLOW
    assert classify("BSD-3-Clause") == Verdict.ALLOW
    assert classify("Apache-2.0") == Verdict.ALLOW
    assert classify("MIT OR GPL-3.0") == Verdict.ALLOW
    assert classify("Apache Software License; MIT License") == Verdict.ALLOW
    assert classify("Apache-2.0 OR BSD-2-Clause") == Verdict.ALLOW
    assert classify("MIT AND PSF-2.0") == Verdict.ALLOW


# -----------------------------------------------------------------------------
# Case 2: Negative / Security (Copyleft)
# -----------------------------------------------------------------------------
def test_negative_security_copyleft_violations(capsys: pytest.CaptureFixture[str]) -> None:
    """Negative test: fixture with AGPL-3.0, GPL-2.0-or-later, SSPL-1.0 exits 1 with violations."""
    py_json = FIXTURES_DIR / "python_security.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "python\tpkg-agpl\t1.0.0\tAGPL-3.0\tDENY" in captured.out
    assert "python\tpkg-gpl\t2.0.0\tGPL-2.0-or-later\tDENY" in captured.out
    assert "python\tpkg-sspl\t1.0.0\tSSPL-1.0\tDENY" in captured.out
    assert "SUMMARY python=3 node=2 violations=3" in captured.out


def test_gpl_allowlist_entry_yields_non_waivable_license(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An allowlist entry for a GPL package cannot waive copyleft and yields exit 1."""
    allowlist_file = tmp_path / "license-allowlist.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "pkg-gpl"
version = "2.0.0"
license = "GPL-2.0-or-later"
justification = "Attempting to waive copyleft which must never be allowed by policy."
""",
        encoding="utf-8",
    )

    py_json = FIXTURES_DIR / "python_security.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
            "--allowlist",
            str(allowlist_file),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "NON_WAIVABLE_LICENSE" in captured.err or "NON_WAIVABLE_LICENSE" in captured.out
    assert "python\tpkg-gpl\t2.0.0\tGPL-2.0-or-later\tNON_WAIVABLE_LICENSE" in captured.out


# -----------------------------------------------------------------------------
# Case 3: Negative LGPL and dynamic linkage
# -----------------------------------------------------------------------------
def test_lgpl_fails_without_allowlist(capsys: pytest.CaptureFixture[str]) -> None:
    """LGPL-3.0 package fails without an allowlist entry."""
    py_json = FIXTURES_DIR / "python_lgpl.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "python\tpkg-lgpl\t3.0.0\tLGPL-3.0\tDENY" in captured.out


def test_lgpl_passes_with_dynamic_linkage_allowlist(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """LGPL-3.0 package passes with a valid dynamic linkage allowlist entry."""
    allowlist_file = tmp_path / "license-allowlist.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "pkg-lgpl"
version = "3.0.0"
license = "LGPL-3.0"
linkage = "dynamic"
justification = "Loaded as a separate shared object; not statically linked. Verified."
""",
        encoding="utf-8",
    )

    py_json = FIXTURES_DIR / "python_lgpl.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
            "--allowlist",
            str(allowlist_file),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert "violations=0" in captured.out


def test_lgpl_static_linkage_causes_exit_3(tmp_path: Path) -> None:
    """Allowlist entry with linkage = 'static' causes exit 3."""
    allowlist_file = tmp_path / "license-allowlist.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "pkg-lgpl"
version = "3.0.0"
license = "LGPL-3.0"
linkage = "static"
justification = "Static linkage attempt which is strictly rejected by security rules."
""",
        encoding="utf-8",
    )

    py_json = FIXTURES_DIR / "python_lgpl.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
            "--allowlist",
            str(allowlist_file),
        ]
    )

    assert rc == 3


# -----------------------------------------------------------------------------
# Case 4: Boundary expressions
# -----------------------------------------------------------------------------
def test_boundary_expressions(capsys: pytest.CaptureFixture[str]) -> None:
    """Boundary test: empty/unknown fails, AND/parens logic verified."""
    py_json = FIXTURES_DIR / "python_boundary.json"
    node_json = FIXTURES_DIR / "node_clean.json"

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_json),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "python\tpkg-empty\t1.0.0\t\tUNKNOWN" in captured.out
    assert "python\tpkg-unknown\t1.0.0\tUNKNOWN\tUNKNOWN" in captured.out
    assert "python\tpkg-and-deny\t1.0.0\tMIT AND GPL-3.0\tDENY" in captured.out
    # Passing packages should not be listed as violations
    assert "pkg-and-allow" not in captured.out
    assert "pkg-paren-allow" not in captured.out
    assert "violations=3" in captured.out


def test_classify_unit_boundaries() -> None:
    """Unit test individual classify boundary cases."""
    assert classify("") == Verdict.UNKNOWN
    assert classify("   ") == Verdict.UNKNOWN
    assert classify("UNKNOWN") == Verdict.UNKNOWN
    assert classify("Custom") == Verdict.UNKNOWN
    assert classify("Apache-2.0 AND MIT") == Verdict.ALLOW
    assert classify("MIT AND GPL-3.0") == Verdict.DENY
    assert classify("(MIT OR Apache-2.0) AND BSD-3-Clause") == Verdict.ALLOW
    assert classify("(UNKNOWN OR GPL-3.0)") == Verdict.DENY
    assert classify("GPL-3.0 OR AGPL-3.0") == Verdict.DENY
    assert classify("UNKNOWN OR UNKNOWN") == Verdict.UNKNOWN
    assert classify("MIT AND UNKNOWN") == Verdict.UNKNOWN
    assert classify("GPL-3.0 WITH Autoconf-exception") == Verdict.DENY
    assert classify(")") == Verdict.UNKNOWN
    assert classify("(") == Verdict.UNKNOWN

    parser = _Parser(["ATOM"])
    assert parser.consume("MISMATCH") is None
    empty_parser = _Parser([])
    assert empty_parser.parse() == Verdict.UNKNOWN


# -----------------------------------------------------------------------------
# Case 5: Fail-closed collectors and missing LICENSE
# -----------------------------------------------------------------------------
def test_collector_subprocess_failure_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collector subprocess returning non-zero causes exit 3."""

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pip-licenses"],
            returncode=1,
            stdout="",
            stderr="Subprocess execution error",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    rc = main(["--node-json", str(FIXTURES_DIR / "node_clean.json")])
    assert rc == 3


def test_collector_subprocess_oserror_exits_3(monkeypatch: pytest.MonkeyPatch) -> None:
    """Collector subprocess raising OSError causes exit 3."""

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError

    monkeypatch.setattr(subprocess, "run", mock_run)
    rc = main(["--node-json", str(FIXTURES_DIR / "node_clean.json")])
    assert rc == 3


def test_collector_invalid_json_exits_3() -> None:
    """Collector emitting invalid JSON causes exit 3."""
    malformed = FIXTURES_DIR / "malformed.json"
    rc = main(["--python-json", str(malformed)])
    assert rc == 3


def test_missing_license_exits_1_with_message(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing LICENSE file causes exit 1 with LICENSE_MISSING_OR_NOT_APACHE2."""
    rc = run_license_gate(repo_root=tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "LICENSE_MISSING_OR_NOT_APACHE2" in captured.err


def test_invalid_license_content_exits_1(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """LICENSE file without Apache License Version 2.0 causes exit 1."""
    (tmp_path / "LICENSE").write_text("GNU General Public License v3", encoding="utf-8")
    rc = run_license_gate(repo_root=tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "LICENSE_MISSING_OR_NOT_APACHE2" in captured.err


def test_license_read_oserror_exits_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Root LICENSE raising OSError causes exit 1 with LICENSE_MISSING_OR_NOT_APACHE2."""
    lic_file = tmp_path / "LICENSE"
    lic_file.write_text("dummy", encoding="utf-8")

    def mock_read_text(*_args: object, **_kwargs: object) -> str:
        raise OSError

    monkeypatch.setattr(Path, "read_text", mock_read_text)
    rc = run_license_gate(repo_root=tmp_path)
    captured = capsys.readouterr()
    assert rc == 1
    assert "LICENSE_MISSING_OR_NOT_APACHE2" in captured.err


# -----------------------------------------------------------------------------
# Case 6: Boundary allowlist validations (Exit 3)
# -----------------------------------------------------------------------------
def test_allowlist_justification_short_exits_3(tmp_path: Path) -> None:
    """Allowlist justification under 20 characters causes exit 3."""
    allowlist_file = tmp_path / "short-justification.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "example"
version = "1.0.0"
license = "LGPL-3.0"
linkage = "dynamic"
justification = "Too short (18ch)!"
""",
        encoding="utf-8",
    )
    rc = main(["--allowlist", str(allowlist_file)])
    assert rc == 3


def test_allowlist_version_wildcard_exits_3(tmp_path: Path) -> None:
    """Allowlist entry with version wildcards or ranges causes exit 3."""
    allowlist_file = tmp_path / "wildcard-version.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "example"
version = "1.*"
license = "LGPL-3.0"
linkage = "dynamic"
justification = "Wildcard version attempt that must be rejected."
""",
        encoding="utf-8",
    )
    rc = main(["--allowlist", str(allowlist_file)])
    assert rc == 3


def test_allowlist_missing_field_exits_3(tmp_path: Path) -> None:
    """Allowlist entry missing a required field causes exit 3."""
    allowlist_file = tmp_path / "missing-field.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "example"
version = "1.0.0"
# missing license field
justification = "Valid length justification string for testing missing license."
""",
        encoding="utf-8",
    )
    rc = main(["--allowlist", str(allowlist_file)])
    assert rc == 3


def test_allowlist_invalid_ecosystem_exits_3(tmp_path: Path) -> None:
    """Allowlist entry with unknown ecosystem causes exit 3."""
    allowlist_file = tmp_path / "invalid-eco.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "cargo"
package = "example"
version = "1.0.0"
license = "LGPL-3.0"
linkage = "dynamic"
justification = "Cargo ecosystem attempt which is disallowed."
""",
        encoding="utf-8",
    )
    rc = main(["--allowlist", str(allowlist_file)])
    assert rc == 3


def test_allowlist_file_not_found_exits_3(tmp_path: Path) -> None:
    """Non-existent allowlist file causes exit 3."""
    missing = tmp_path / "non_existent.toml"
    rc = main(["--allowlist", str(missing)])
    assert rc == 3


def test_allowlist_lgpl_missing_linkage_exits_3(tmp_path: Path) -> None:
    """LGPL entry missing linkage field causes exit 3."""
    allowlist_file = tmp_path / "missing-linkage.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "python"
package = "example"
version = "1.0.0"
license = "LGPL-3.0"
justification = "LGPL entry missing required linkage field."
""",
        encoding="utf-8",
    )
    rc = main(["--allowlist", str(allowlist_file)])
    assert rc == 3


def test_allowlist_toml_syntax_error(tmp_path: Path) -> None:
    """Allowlist with invalid TOML syntax causes exit 3."""
    syntax_err = tmp_path / "syntax-error.toml"
    syntax_err.write_text("[[exception]\nunclosed = true\n", encoding="utf-8")
    rc = main(["--allowlist", str(syntax_err)])
    assert rc == 3


# -----------------------------------------------------------------------------
# Additional coverage & integration tests
# -----------------------------------------------------------------------------
def test_node_dependency_array_and_violations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Node dependencies with list licenses, violations, and allowlist waiver."""
    py_json = FIXTURES_DIR / "python_clean.json"
    node_file = tmp_path / "node_test.json"
    node_file.write_text(
        json.dumps(
            {
                "test-array@1.0.0": {
                    "licenses": ["MIT", "Apache-2.0"],
                },
                "test-none@1.0.0": {
                    "licenses": None,
                },
                "test-copyleft@2.0.0": {
                    "licenses": "GPL-3.0",
                },
                "test-lgpl@3.0.0": {
                    "licenses": "LGPL-2.1",
                },
                "@kanban/web@0.1.0": {
                    "licenses": "MIT",
                },
                "unscoped-pkg": {
                    "version": "1.2.3",
                    "licenses": "MIT",
                },
                "non-dict-entry": "invalid-entry-should-be-skipped",
            }
        ),
        encoding="utf-8",
    )

    allowlist_file = tmp_path / "allowlist.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "node"
package = "test-lgpl"
version = "3.0.0"
license = "LGPL-2.1"
linkage = "dynamic"
justification = "Node dynamically linked shared object reviewed by architect."
""",
        encoding="utf-8",
    )

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_file),
            "--allowlist",
            str(allowlist_file),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "node\ttest-none\t1.0.0\t\tUNKNOWN" in captured.out
    assert "node\ttest-copyleft\t2.0.0\tGPL-3.0\tDENY" in captured.out
    assert "test-lgpl" not in captured.out
    assert "@kanban/web" not in captured.out


def test_node_non_waivable_allowlist_entry(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Node dependency matching a non-waivable allowlist entry produces NON_WAIVABLE_LICENSE."""
    py_json = FIXTURES_DIR / "python_clean.json"
    node_file = tmp_path / "node_gpl.json"
    node_file.write_text(
        json.dumps(
            {
                "node-gpl@1.0.0": {"licenses": "GPL-3.0"},
            }
        ),
        encoding="utf-8",
    )
    allowlist_file = tmp_path / "allowlist.toml"
    allowlist_file.write_text(
        """
[[exception]]
ecosystem = "node"
package = "node-gpl"
version = "1.0.0"
license = "GPL-3.0"
justification = "Attempting to waive GPL in node which must fail."
""",
        encoding="utf-8",
    )

    rc = main(
        [
            "--python-json",
            str(py_json),
            "--node-json",
            str(node_file),
            "--allowlist",
            str(allowlist_file),
        ]
    )

    captured = capsys.readouterr()
    assert rc == 1
    assert "node\tnode-gpl\t1.0.0\tGPL-3.0\tNON_WAIVABLE_LICENSE" in captured.out


def test_collector_missing_files_exit_3(tmp_path: Path) -> None:
    """Passing non-existent paths to --python-json or --node-json causes exit 3."""
    missing = tmp_path / "does_not_exist.json"
    assert main(["--python-json", str(missing)]) == 3
    assert main(["--node-json", str(missing)]) == 3


def test_python_collector_subprocess_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python collector subprocess emitting invalid JSON causes exit 3."""

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pip-licenses"],
            returncode=0,
            stdout="invalid-json",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    assert main(["--node-json", str(FIXTURES_DIR / "node_clean.json")]) == 3


def test_python_collector_subprocess_not_array(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python collector subprocess emitting JSON object instead of array causes exit 3."""

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["pip-licenses"],
            returncode=0,
            stdout='{"not": "array"}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    assert main(["--node-json", str(FIXTURES_DIR / "node_clean.json")]) == 3


def test_node_collector_subprocess_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Node collector subprocess emitting invalid JSON causes exit 3."""
    py_json = FIXTURES_DIR / "python_clean.json"
    monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/local/bin/pnpm")

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["license-checker"],
            returncode=0,
            stdout="invalid-json",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    assert main(["--python-json", str(py_json)]) == 3


def test_node_collector_subprocess_not_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Node collector subprocess emitting JSON array instead of dict causes exit 3."""
    py_json = FIXTURES_DIR / "python_clean.json"
    monkeypatch.setattr(shutil, "which", lambda _cmd: "/usr/local/bin/pnpm")

    def mock_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["license-checker"],
            returncode=0,
            stdout="[1, 2, 3]",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    assert main(["--python-json", str(py_json)]) == 3


def test_normalization_and_atom_evaluation() -> None:
    """Test various normalized atom names and exceptions."""
    assert evaluate_atom("Apache Software License") == Verdict.ALLOW
    assert evaluate_atom("Python Software Foundation License") == Verdict.ALLOW
    assert evaluate_atom("Mozilla Public License 2.0 (MPL 2.0)") == Verdict.ALLOW
    assert evaluate_atom("PSF") == Verdict.ALLOW
    assert evaluate_atom("CMU") == Verdict.ALLOW
    assert evaluate_atom("ISC License") == Verdict.ALLOW
    assert evaluate_atom("The Unlicense") == Verdict.ALLOW
    assert evaluate_atom("PostgreSQL License") == Verdict.ALLOW
    assert evaluate_atom("Apache-2.0 WITH LLVM-exception") == Verdict.ALLOW
    assert evaluate_atom("Unknown-Proprietary") == Verdict.UNKNOWN


def test_workspace_package_detection() -> None:
    """Test workspace package and root project name detection."""
    assert is_workspace_package("kanban-database")
    assert is_workspace_package("kanban-core")
    assert is_workspace_package("kanban-mcp")
    assert is_workspace_package("kanban-agent")
    assert is_workspace_package("kanban-platform")
    assert is_workspace_package("kanban-monorepo")
    assert is_workspace_package("@kanban/web")
    assert not is_workspace_package("pydantic")
    assert not is_workspace_package("react")


def test_is_non_waivable() -> None:
    """Test identification of non-waivable copyleft licenses."""
    assert is_non_waivable("GPL-3.0")
    assert is_non_waivable("AGPL-3.0")
    assert is_non_waivable("SSPL-1.0")
    assert is_non_waivable("GNU General Public License")
    assert is_non_waivable("Server Side Public License")
    assert not is_non_waivable("LGPL-3.0")
    assert not is_non_waivable("GNU Lesser General Public License")
    assert not is_non_waivable("MIT")
    assert not is_non_waivable("Apache-2.0")


def test_allowlist_not_a_list(tmp_path: Path) -> None:
    """Allowlist where exception is not a list causes exit 3."""
    allowlist_file = tmp_path / "bad-shape.toml"
    allowlist_file.write_text("exception = 'not a list'\n", encoding="utf-8")
    with pytest.raises(AllowlistError):
        load_allowlist(allowlist_file)


def test_allowlist_entry_not_a_dict(tmp_path: Path) -> None:
    """Allowlist where an exception item is not a table causes exit 3."""
    allowlist_file = tmp_path / "bad-item.toml"
    allowlist_file.write_text("exception = ['string_item']\n", encoding="utf-8")
    with pytest.raises(AllowlistError):
        load_allowlist(allowlist_file)


def test_python_packages_skips_empty_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Python items without a name are skipped."""
    py_file = tmp_path / "empty_name.json"
    py_file.write_text(
        json.dumps(
            [
                {"Name": "", "Version": "1.0.0", "License": "MIT"},
                {"Name": "kanban-test", "Version": "1.0.0", "License": "MIT"},
            ]
        ),
        encoding="utf-8",
    )
    rc = main(
        [
            "--python-json",
            str(py_file),
            "--node-json",
            str(FIXTURES_DIR / "node_clean.json"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "SUMMARY python=0 node=2 violations=0" in captured.out


def test_main_oserror_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Main entrypoint handles unexpected OSError with returncode 3."""

    def mock_run_gate(*_args: object, **_kwargs: object) -> int:
        raise OSError

    monkeypatch.setattr("scripts.license_gate.run_license_gate", mock_run_gate)
    assert main([]) == 3
