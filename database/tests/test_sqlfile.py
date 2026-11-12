"""Unit tests for Alembic SQL file execution helper and validation."""

import pytest

from database.migrations.sqlfile import NAME_PATTERN, execute_sql_file


def test_07_negative_sqlfile_path_validation() -> None:
    """Verify execute_sql_file rejects path traversal and invalid filename patterns."""
    with pytest.raises(ValueError, match="Invalid SQL file name"):
        execute_sql_file("../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid SQL file name"):
        execute_sql_file("p1_01_baseline.sql")

    with pytest.raises(ValueError, match="Invalid SQL file name"):
        execute_sql_file("invalid_name.up.sql")

    with pytest.raises(ValueError, match="Invalid SQL file name"):
        execute_sql_file("/absolute/path/p1_01_test.up.sql")

    with pytest.raises(FileNotFoundError, match="SQL file not found"):
        execute_sql_file("p9_99_missing.up.sql")


def test_name_pattern_conformance() -> None:
    """Verify regex pattern accepts conforming names and rejects non-conforming ones."""
    assert NAME_PATTERN.match("p1_01_baseline.up.sql") is not None
    assert NAME_PATTERN.match("p1_01_baseline.down.sql") is not None
    assert NAME_PATTERN.match("p2_14a_custom_fields.up.sql") is not None
    assert NAME_PATTERN.match("p0_05_harness.down.sql") is not None

    assert NAME_PATTERN.match("baseline.up.sql") is None
    assert NAME_PATTERN.match("p1_01_baseline.sql") is None
    assert NAME_PATTERN.match("p1_1_short.up.sql") is None
    assert NAME_PATTERN.match("p1_01_UPPERCASE.up.sql") is None
