"""Tests for scripts.check_no_dashes."""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_no_dashes import MAX_FILE_SIZE, collect_all_files, main


def test_positive_ascii_hyphens_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 1: Positive check that ASCII hyphens return 0 and empty stdout."""
    sample = tmp_path / "clean.txt"
    sample.write_text("line-one\nline-two with - standard hyphen\n", encoding="utf-8")

    exit_code = main([str(sample)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_negative_em_and_en_dashes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 2: Negative check that U+2014 and U+2013 on line 3 col 7 are reported."""
    # Test U+2014
    sample_em = tmp_path / "em_dash.txt"
    # Line 1, Line 2, Line 3 has 6 ASCII characters before dash (1-based index 7)
    sample_em.write_text("line 1\nline 2\n123456\u2014rest of line\n", encoding="utf-8")

    exit_code = main([str(sample_em)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert ":3:7:" in captured.out
    assert "U+2014" in captured.out

    # Test U+2013
    sample_en = tmp_path / "en_dash.txt"
    sample_en.write_text("line 1\nline 2\n123456\u2013rest of line\n", encoding="utf-8")

    exit_code_en = main([str(sample_en)])
    captured_en = capsys.readouterr()

    assert exit_code_en == 1
    assert ":3:7:" in captured_en.out
    assert "U+2013" in captured_en.out


def test_negative_invalid_utf8(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 3: Negative/security test asserting invalid UTF-8 returns 1."""
    invalid_file = tmp_path / "invalid.txt"
    invalid_file.write_bytes(b"\xff\xfe")

    exit_code = main([str(invalid_file)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "not valid UTF-8" in captured.out


def test_boundary_large_file_and_all_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test Case 4: Boundary test asserting 5 MiB + 1 byte file is skipped and --all scans scope."""
    # File of exactly 5 MiB + 1 bytes containing a dash
    large_file = tmp_path / "large.txt"
    large_file.write_bytes(b"A" * (MAX_FILE_SIZE + 1))

    exit_code = main([str(large_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "exceeding 5 MiB limit" in captured.err

    # Create directory tree: docs/a.md (hit) and other/b.md (hit, out of scope)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("Hit in docs: \u2014\n", encoding="utf-8")

    other_dir = tmp_path / "other"
    other_dir.mkdir()
    (other_dir / "b.md").write_text("Hit in other: \u2014\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    exit_code_all = main(["--all"])
    captured_all = capsys.readouterr()

    assert exit_code_all == 1
    assert "docs/a.md" in captured_all.out or "docs" in captured_all.out
    assert "other/b.md" not in captured_all.out


def test_boundary_empty_argument_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Test Case 5: Boundary test asserting empty argument list without --all returns 0."""
    exit_code = main([])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""
    assert captured.err == ""


def test_non_existent_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Additional edge case: check that a non-existent file path is safely handled."""
    fake_file = tmp_path / "does_not_exist.txt"
    exit_code = main([str(fake_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""


def test_collect_all_files_missing_directory(tmp_path: Path) -> None:
    """Edge case: collect_all_files handles missing directory."""
    files = collect_all_files(tmp_path / "empty_root")
    assert files == []


def test_main_with_default_sys_argv(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Edge case: main called with argv=None reads sys.argv and ignores unknown flags."""
    monkeypatch.setattr(sys, "argv", ["check_no_dashes.py", "--ignore-me"])
    exit_code = main(None)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out == ""


def test_module_main_execution() -> None:
    """Edge case: verify module execution via -m scripts.check_no_dashes exits cleanly."""
    res = subprocess.run(
        [sys.executable, "-m", "scripts.check_no_dashes"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
