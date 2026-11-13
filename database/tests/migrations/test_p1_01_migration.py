"""Tests for Phase 1 Alembic baseline migration lifecycle and round-trip."""

import os
import shutil
import subprocess

import pytest

from database.tests.migration_harness import MigrationHarness


def dump_schema(db_name: str) -> str:
    """Dump database schema using pg_dump on host or inside test container."""
    pg_dump_bin = shutil.which("pg_dump")
    if pg_dump_bin:
        socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
        user = os.environ.get("KB_TEST_PGUSER", "kanban_test")
        cmd = [pg_dump_bin, "-h", socket_dir, "-U", user, "-d", db_name, "--schema-only"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return proc.stdout

    # Docker fallback: locate running pg-test container
    socket_dir = os.environ.get("KB_TEST_PGHOST", "/tmp/kb-pgsock")
    res = subprocess.run(
        ["docker", "ps", "--filter", "name=kanban-pg-test", "--format", "{{.ID}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    cid = res.stdout.strip().splitlines()[0] if res.stdout.strip() else None
    if not cid:
        res = subprocess.run(
            ["docker", "ps", "--filter", f"volume={socket_dir}", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        cid = res.stdout.strip().splitlines()[0] if res.stdout.strip() else None
    if not cid:
        filter_arg = "label=com.docker.compose.service=pg-test"
        res = subprocess.run(
            ["docker", "ps", "--filter", filter_arg, "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        cid = res.stdout.strip().splitlines()[0] if res.stdout.strip() else None
    if not cid:
        res2 = subprocess.run(
            ["docker", "ps", "--filter", "ancestor=pgvector/pgvector:pg16", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        cid = res2.stdout.strip().splitlines()[0] if res2.stdout.strip() else None
    if not cid:
        msg = "No running postgres container found for pg_dump fallback"
        raise RuntimeError(msg)

    cmd = ["docker", "exec", cid, "pg_dump", "-U", "kanban_test", "-d", db_name, "--schema-only"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def clean_schema_dump(sql: str) -> list[str]:
    """Strip SQL comment lines, blank lines, and pg_dump security tokens for stable diffs."""
    lines: list[str] = []
    for line in sql.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith(("--", "\\restrict", "\\unrestrict")):
            continue
        lines.append(trimmed)
    return lines


@pytest.mark.migration
async def test_08_migration_up_down_cycle() -> None:
    """Verify p1_01_baseline upgrade creates functions, downgrade removes them, and re-up works."""
    target_functions = {
        "uuidv7",
        "app_current_principal_id",
        "app_current_workspace_id",
        "set_updated_at",
    }

    async with MigrationHarness() as harness:
        assert harness.previous_of("p1_01_baseline") == "base"

        # Initially at base: functions must not exist
        procs_base = await harness.fetch(
            "SELECT proname FROM pg_proc WHERE proname = ANY($1)",
            list(target_functions),
        )
        assert len(procs_base) == 0

        # Upgrade to p1_01_baseline
        await harness.upgrade("p1_01_baseline")
        procs_up1 = await harness.fetch(
            "SELECT proname FROM pg_proc WHERE proname = ANY($1)",
            list(target_functions),
        )
        assert {r["proname"] for r in procs_up1} == target_functions

        # Downgrade to base
        await harness.downgrade("base")
        procs_down = await harness.fetch(
            "SELECT proname FROM pg_proc WHERE proname = ANY($1)",
            list(target_functions),
        )
        assert len(procs_down) == 0

        # Re-upgrade to p1_01_baseline
        await harness.upgrade("p1_01_baseline")
        procs_up2 = await harness.fetch(
            "SELECT proname FROM pg_proc WHERE proname = ANY($1)",
            list(target_functions),
        )
        assert {r["proname"] for r in procs_up2} == target_functions


@pytest.mark.migration
async def test_09_migration_roundtrip_schema_identity() -> None:
    """Verify upgrade head -> downgrade base -> upgrade head produces byte-identical schemas."""
    async with MigrationHarness() as harness:
        # 1. Upgrade to head
        await harness.upgrade("head")
        dump1 = dump_schema(harness.db_name)

        # 2. Downgrade to base
        await harness.downgrade("base")

        # 3. Upgrade back to head
        await harness.upgrade("head")
        dump2 = dump_schema(harness.db_name)

        clean1 = clean_schema_dump(dump1)
        clean2 = clean_schema_dump(dump2)

        assert clean1 == clean2
        assert len(clean1) > 0
