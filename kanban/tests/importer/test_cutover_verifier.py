# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for cutover verification engine (KB-P6-02)."""

# ruff: noqa: E501, PLC0415, TC002, ANN401

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.tests.conftest import bootstrap_workspace_admin
from kanban.api.deps import PrincipalContext
from kanban.cli.verify_cutover import (
    _get_admin_dsn,
    _run_cutover_verify,
    register_cutover_subparsers,
)
from kanban.importer.cutover_verifier import (
    CheckResult,
    CutoverAuditReport,
    scan_markdown_for_html_residue,
    verify_cutover,
)
from kanban.importer.plane_client import PlaneClient
from kanban.importer.plane_importer import PlaneImporter

FIXTURE_DIR = Path("tests/fixtures/plane_export_kanba").resolve()


def _populate_qa_bundle(bundle_dir: Path) -> None:
    """Create non-empty QA proof bundle files."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "git-diff.patch").write_text(
        "diff --git a/test b/test\n+line\n", encoding="utf-8"
    )
    (bundle_dir / "unit-test-results.txt").write_text("33 passed in 1.2s\n", encoding="utf-8")
    (bundle_dir / "build-check.txt").write_text("All checks passed!\n", encoding="utf-8")


@pytest.fixture
async def setup_cutover_env(
    db_session: AsyncSession, tmp_path: Path
) -> tuple[AsyncSession, PrincipalContext, Path, Path]:
    """Provision workspace 'kanban', admin caller, QA root, and import fixture bundle."""
    ws_id, admin_id = await bootstrap_workspace_admin(db_session, slug="kanban")

    await db_session.execute(
        text(
            "SELECT set_config('app.current_workspace_id', :ws, true), "
            "set_config('app.current_principal_id', :pid, true), "
            "set_config('app.aal_level', '2', true)"
        ),
        {"ws": str(ws_id), "pid": str(admin_id)},
    )

    caller = PrincipalContext(
        principal_id=admin_id,
        workspace_id=ws_id,
        aal_level=2,
    )
    blob_dir = tmp_path / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)

    qa_root = tmp_path / "docs_qa"
    qa_root.mkdir(parents=True, exist_ok=True)

    # Ingest the fixture bundle so project KANBA and all issues exist
    client = PlaneClient()
    bundle = client.load_bundle_from_dir(FIXTURE_DIR)
    importer = PlaneImporter(session=db_session, caller=caller, blob_store_root=blob_dir)
    await importer.run_import(bundle, dry_run=False)

    return db_session, caller, qa_root, tmp_path


@pytest.mark.asyncio
async def test_case_01_positive_cutover_verification(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test Case 1: Positive end-to-end verification succeeds with all 6 checks passing."""
    session, _caller, qa_root, _tmp_path = setup_cutover_env

    # Populate QA proof bundle for completed issue KANBA-19
    _populate_qa_bundle(qa_root / "KANBA-19")

    # Historical bootstrap issues 1, 2, 3, 5 are exempt
    exempt_keys = ["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"]

    report = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=exempt_keys,
    )

    assert report.overall_passed is True
    assert len(report.checks) == 6
    assert all(chk.passed for chk in report.checks)
    assert report.summary["passed_checks"] == 6
    assert report.summary["failed_checks"] == 0


@pytest.mark.asyncio
async def test_case_02_parity_failure_detection(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test Case 2: Missing issue (e.g. KANBA-4) triggers KEY_PARITY_MISMATCH."""
    session, caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    # Delete issue KANBA-4 to simulate missing key from snapshot
    await session.execute(
        text("DELETE FROM issues WHERE workspace_id = :ws AND sequence_id = 4"),
        {"ws": caller.workspace_id},
    )

    report = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )

    assert report.overall_passed is False
    c1 = next(chk for chk in report.checks if chk.name == "entity_count_and_key_parity")
    assert c1.passed is False
    assert c1.error_code == "KEY_PARITY_MISMATCH"
    assert "Missing 1 issue keys" in (c1.detail or "")


@pytest.mark.asyncio
async def test_case_03_invalid_link_detection(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test Case 3: FLAGGED_INVALID or broken link triggers INVALID_OBJECT_LINKS_DETECTED."""
    session, caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    # Soft-delete an endpoint past trash retention -> triggers SOFT_DELETED_ENDPOINT and FLAGGED_INVALID
    source_id = (
        await session.execute(
            text("SELECT source_id FROM object_links WHERE workspace_id = :ws LIMIT 1"),
            {"ws": caller.workspace_id},
        )
    ).scalar_one()

    await session.execute(
        text(
            "UPDATE objects SET deleted_at = clock_timestamp() - interval '45 days' WHERE id = :id"
        ),
        {"id": source_id},
    )
    await session.flush()

    report = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )

    assert report.overall_passed is False
    c2 = next(chk for chk in report.checks if chk.name == "zero_invalid_object_links")
    assert c2.passed is False
    assert c2.error_code == "INVALID_OBJECT_LINKS_DETECTED"


@pytest.mark.asyncio
async def test_case_04_qa_proof_bundle_check(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test Case 4: Missing or 0-byte proof bundle file triggers MISSING_QA_PROOF_BUNDLE."""
    session, _caller, qa_root, _ = setup_cutover_env

    # Case 4a: Directory missing entirely
    report_missing = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )
    assert report_missing.overall_passed is False
    c5_a = next(chk for chk in report_missing.checks if chk.name == "qa_proof_bundle_continuity")
    assert c5_a.passed is False
    assert c5_a.error_code == "MISSING_QA_PROOF_BUNDLE"

    # Case 4b: Empty / 0-byte file
    bundle_dir = qa_root / "KANBA-19"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "git-diff.patch").write_text("", encoding="utf-8")  # 0 bytes
    (bundle_dir / "unit-test-results.txt").write_text("passed\n", encoding="utf-8")
    (bundle_dir / "build-check.txt").write_text("clean\n", encoding="utf-8")

    report_empty = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )
    assert report_empty.overall_passed is False
    c5_b = next(chk for chk in report_empty.checks if chk.name == "qa_proof_bundle_continuity")
    assert c5_b.passed is False
    assert "0 bytes" in (c5_b.detail or "")


@pytest.mark.asyncio
async def test_case_05_markdown_purity_check(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test Case 5: HTML residue outside code blocks fails, while inside code blocks passes."""
    session, caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    # 1. First test code fence scanner directly
    clean_markdown = """
# Heading
Here is safe prose.
```html
<script>alert("safe in code fence")</script>
<iframe src="test"></iframe>
```
More safe prose.
"""
    assert scan_markdown_for_html_residue(clean_markdown) == []

    tainted_markdown = """
# Heading
Prose with evil payload:
<script>alert("evil outside code fence")</script>
Done.
"""
    findings = scan_markdown_for_html_residue(tainted_markdown)
    assert len(findings) == 1

    # 2. Inject tainted description in DB
    await session.execute(
        text(
            "UPDATE issues SET description_markdown = :desc "
            "WHERE workspace_id = :ws AND sequence_id = 19"
        ),
        {
            "ws": caller.workspace_id,
            "desc": "Bypassed normalizer: <script>evil()</script>",
        },
    )

    report = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )

    assert report.overall_passed is False
    c4 = next(chk for chk in report.checks if chk.name == "canonical_markdown_purity")
    assert c4.passed is False
    assert c4.error_code == "HTML_RESIDUE_DETECTED"


@pytest.mark.asyncio
async def test_edge_cases_workspace_and_project_not_found(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test nonexistent workspace or project returns immediate failure report."""
    session, _, qa_root, _ = setup_cutover_env

    # Unknown workspace
    rep1 = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="nonexistent-workspace",
        project_identifier="KANBA",
        qa_root=qa_root,
    )
    assert rep1.overall_passed is False
    assert rep1.checks[0].error_code == "WORKSPACE_NOT_FOUND"

    # Unknown project
    rep2 = await verify_cutover(
        session=session,
        bundle_dir=FIXTURE_DIR,
        workspace_slug="kanban",
        project_identifier="UNKNOWN_PROJ",
        qa_root=qa_root,
    )
    assert rep2.overall_passed is False
    assert rep2.checks[0].error_code == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_case_sequence_counter_lower_than_max(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
    tmp_path: Path,
) -> None:
    """Test project issue_seq_counter < max(sequence_id) triggers KEY_PARITY_MISMATCH."""
    session, _caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    # Create a bundle with a higher sequence number than current issue_seq_counter (19)
    custom_bundle = tmp_path / "custom_bundle"
    custom_bundle.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copytree(FIXTURE_DIR, custom_bundle, dirs_exist_ok=True)

    issues_data = json.loads((custom_bundle / "issues.json").read_text(encoding="utf-8"))
    # Add an issue with sequence_id 99 for KANBA
    issues_data.append(
        {
            "id": "plane-issue-99",
            "sequence_id": 99,
            "name": "Unimported Future Issue",
            "project": "plane-proj-kanba",
            "state_id": "plane-state-done",
        }
    )
    (custom_bundle / "issues.json").write_text(json.dumps(issues_data), encoding="utf-8")

    report = await verify_cutover(
        session=session,
        bundle_dir=custom_bundle,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
        pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
    )

    assert report.overall_passed is False
    c1 = next(chk for chk in report.checks if chk.name == "entity_count_and_key_parity")
    assert c1.passed is False
    assert c1.error_code == "KEY_PARITY_MISMATCH"


@pytest.mark.asyncio
async def test_case_forbidden_html_columns_in_catalog(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test presence of *_html or *_ast column in public schema fails canonical_markdown_purity."""
    session, _caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    await session.execute(text("ALTER TABLE issues ADD COLUMN legacy_desc_html text"))
    try:
        report = await verify_cutover(
            session=session,
            bundle_dir=FIXTURE_DIR,
            workspace_slug="kanban",
            project_identifier="KANBA",
            qa_root=qa_root,
            pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
        )
        assert report.overall_passed is False
        c4 = next(chk for chk in report.checks if chk.name == "canonical_markdown_purity")
        assert c4.passed is False
        assert c4.error_code == "HTML_RESIDUE_DETECTED"
        assert "forbidden HTML/AST columns" in (c4.detail or "")
    finally:
        await session.execute(text("ALTER TABLE issues DROP COLUMN legacy_desc_html"))


@pytest.mark.asyncio
async def test_case_corrupted_bundle_dir(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
    tmp_path: Path,
) -> None:
    """Test corrupted or unreadable bundle directory returns BUNDLE_LOAD_ERROR."""
    session, _, qa_root, _ = setup_cutover_env
    bad_dir = tmp_path / "bad_bundle"
    bad_dir.mkdir(parents=True, exist_ok=True)
    (bad_dir / "project.json").write_text("{bad json", encoding="utf-8")

    report = await verify_cutover(
        session=session,
        bundle_dir=bad_dir,
        workspace_slug="kanban",
        project_identifier="KANBA",
        qa_root=qa_root,
    )
    assert report.overall_passed is False
    assert report.checks[0].error_code == "BUNDLE_LOAD_ERROR"


@pytest.mark.asyncio
async def test_case_cli_execute_verify(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
    tmp_path: Path,
) -> None:
    """Test full CLI _execute_verify execution with JSON report generation."""
    from kanban.cli.verify_cutover import _execute_verify

    _, _, qa_root, _ = setup_cutover_env
    json_report = tmp_path / "cli_report.json"

    # 1. Success case: overall_passed = True
    with patch("kanban.cli.verify_cutover.verify_cutover", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = CutoverAuditReport(
            overall_passed=True,
            workspace_slug="kanban",
            project_identifier="KANBA",
            checks=[CheckResult(name="check1", passed=True, detail="ok")],
            summary={"total_checks": 6, "passed_checks": 6, "failed_checks": 0},
        )
        with patch("kanban.cli.verify_cutover.create_async_engine") as mock_engine_factory:
            from unittest.mock import MagicMock

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_factory = MagicMock(return_value=mock_session)
            mock_engine = AsyncMock()
            mock_engine_factory.return_value = mock_engine

            with patch(
                "kanban.cli.verify_cutover.async_sessionmaker", return_value=mock_session_factory
            ):
                code = await _execute_verify(
                    bundle_path=FIXTURE_DIR,
                    workspace_slug="kanban",
                    project_identifier="KANBA",
                    qa_root=qa_root,
                    exempt_keys=["KANBA-1"],
                    json_out=str(json_report),
                )
                assert code == 0
                assert json_report.is_file()
                data = json.loads(json_report.read_text(encoding="utf-8"))
                assert data["overall_passed"] is True

    # 2. Failure case: overall_passed = False
    with patch("kanban.cli.verify_cutover.verify_cutover", new_callable=AsyncMock) as mock_verify:
        mock_verify.return_value = CutoverAuditReport(
            overall_passed=False,
            workspace_slug="kanban",
            project_identifier="KANBA",
            checks=[CheckResult(name="check1", passed=False, error_code="ERR", detail="failed")],
            summary={"total_checks": 6, "passed_checks": 5, "failed_checks": 1},
        )
        with patch("kanban.cli.verify_cutover.create_async_engine") as mock_engine_factory:
            from unittest.mock import MagicMock

            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.__aexit__.return_value = None
            mock_session_factory = MagicMock(return_value=mock_session)
            mock_engine = AsyncMock()
            mock_engine_factory.return_value = mock_engine

            with patch(
                "kanban.cli.verify_cutover.async_sessionmaker", return_value=mock_session_factory
            ):
                code = await _execute_verify(
                    bundle_path=FIXTURE_DIR,
                    workspace_slug="kanban",
                    project_identifier="KANBA",
                    qa_root=qa_root,
                    exempt_keys=["KANBA-1"],
                    json_out=None,
                )
                assert code == 2


@pytest.mark.asyncio
async def test_verifier_branch_coverage(
    setup_cutover_env: tuple[AsyncSession, PrincipalContext, Path, Path],
) -> None:
    """Test edge case branches: seq_counter < max_seq, role escalation, and check errors."""
    session, _caller, qa_root, _ = setup_cutover_env
    _populate_qa_bundle(qa_root / "KANBA-19")

    # 1. Branch: issue_seq_counter < max_imported_seq with zero missing keys
    orig_execute = session.execute

    async def mock_execute_seq_counter(statement: Any, *args: Any, **kwargs: Any) -> Any:
        stmt_str = str(statement)
        if "FROM projects WHERE" in stmt_str:
            # Return row with issue_seq_counter = 1
            proj_res = await orig_execute(statement, *args, **kwargs)
            row = proj_res.mappings().one()
            return _MockMappingResult(
                [
                    {
                        "id": row["id"],
                        "issue_seq_counter": 1,
                        "modules_enabled": row["modules_enabled"],
                    }
                ]
            )
        return await orig_execute(statement, *args, **kwargs)

    with patch.object(session, "execute", side_effect=mock_execute_seq_counter):
        report_seq = await verify_cutover(
            session=session,
            bundle_dir=FIXTURE_DIR,
            workspace_slug="kanban",
            project_identifier="KANBA",
            qa_root=qa_root,
            pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
        )
        assert report_seq.overall_passed is False
        c1 = next(chk for chk in report_seq.checks if chk.name == "entity_count_and_key_parity")
        assert c1.passed is False
        assert "less than max imported sequence ID" in (c1.detail or "")

    # 2. Branch: kanban_app has dangerous rolsuper=True
    async def mock_execute_bad_role(statement: Any, *args: Any, **kwargs: Any) -> Any:
        stmt_str = str(statement)
        if "FROM pg_roles" in stmt_str:
            return _MockMappingResult(
                [{"rolname": "kanban_app", "rolsuper": True, "rolbypassrls": False}]
            )
        return await orig_execute(statement, *args, **kwargs)

    with patch.object(session, "execute", side_effect=mock_execute_bad_role):
        report_role = await verify_cutover(
            session=session,
            bundle_dir=FIXTURE_DIR,
            workspace_slug="kanban",
            project_identifier="KANBA",
            qa_root=qa_root,
            pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
        )
        assert report_role.overall_passed is False
        c6 = next(chk for chk in report_role.checks if chk.name == "rls_enforcement_active")
        assert c6.passed is False
        assert c6.error_code == "RLS_ENFORCEMENT_INACTIVE"
        assert "dangerous privileges" in (c6.detail or "")

    # 3. Branch: exceptions in individual checks (Check 2, 3, 4, 5, 6 error codes)
    error_queries = [
        ("audit_object_links", "LINK_AUDIT_ERROR"),
        ("verify_activity_chain", "ACTIVITY_CHAIN_ERROR"),
        ("information_schema.columns", "MARKDOWN_PURITY_ERROR"),
        ("JOIN workflow_states", "QA_PROOF_CHECK_ERROR"),
        ("FROM pg_class", "RLS_CATALOG_CHECK_ERROR"),
    ]

    for trigger_phrase, expected_code in error_queries:

        async def mock_execute_raise(
            statement: Any, *args: Any, trigger: str = trigger_phrase, **kwargs: Any
        ) -> Any:
            if trigger in str(statement):
                msg = "Simulated query failure"
                raise RuntimeError(msg)
            return await orig_execute(statement, *args, **kwargs)

        with patch.object(session, "execute", side_effect=mock_execute_raise):
            rep = await verify_cutover(
                session=session,
                bundle_dir=FIXTURE_DIR,
                workspace_slug="kanban",
                project_identifier="KANBA",
                qa_root=qa_root,
                pre_cutover_exempt_keys=["KANBA-1", "KANBA-2", "KANBA-3", "KANBA-5"],
            )
            assert rep.overall_passed is False
            err_chk = next(chk for chk in rep.checks if chk.error_code == expected_code)
            assert err_chk.passed is False


class _MockMappingResult:
    """Mock helper for mappings().all() / mappings().one_or_none()."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _MockMappingResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def one(self) -> dict[str, Any]:
        return self._rows[0]

    def one_or_none(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> Any:
        return next(iter(self._rows[0].values()))


def test_cli_subparsers_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test register_cutover_subparsers and argument defaults."""
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    register_cutover_subparsers(sub)

    args = parser.parse_args(
        [
            "cutover",
            "verify",
            "--bundle-dir",
            str(tmp_path),
            "--workspace",
            "ws",
            "--project",
            "PRJ",
        ]
    )
    assert args.bundle_dir == str(tmp_path)
    assert args.workspace == "ws"
    assert args.project == "PRJ"
    assert args.qa_root == "./docs/qa"
    assert args.pre_cutover_exempt_keys == ""
    assert args.json_out is None

    # Test DSN with env var
    monkeypatch.setenv("KANBAN_ADMIN_DATABASE_URL", "postgresql+asyncpg://admin@localhost/test")
    assert _get_admin_dsn() == "postgresql+asyncpg://admin@localhost/test"

    monkeypatch.delenv("KANBAN_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.setenv("KANBAN_DATABASE_URL", "postgresql+asyncpg://db@localhost/test")
    assert _get_admin_dsn() == "postgresql+asyncpg://db@localhost/test"

    monkeypatch.delenv("KANBAN_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    default_dsn = _get_admin_dsn()
    assert "/kanban" in default_dsn
    assert "postgresql+asyncpg://" in default_dsn

    # Test socket path branches
    monkeypatch.setenv("KB_TEST_PGHOST", "/var/custom/socket")
    assert "host=/var/custom/socket" in _get_admin_dsn()
    monkeypatch.delenv("KB_TEST_PGHOST", raising=False)

    with patch.object(
        Path, "is_dir", autospec=True, side_effect=lambda self: str(self) == "/run/postgresql"
    ):
        assert "host=/run/postgresql" in _get_admin_dsn()

    with patch.object(
        Path, "is_dir", autospec=True, side_effect=lambda self: str(self) == "/tmp/kb-pgsock"
    ):
        assert "host=/tmp/kb-pgsock" in _get_admin_dsn()

    with patch.object(Path, "is_dir", autospec=True, return_value=False):
        assert "host=/run/postgresql" in _get_admin_dsn()


def test_cli_runner_success(tmp_path: Path) -> None:
    """Test _run_cutover_verify success path delegating to _execute_verify."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # 1. With exempt keys
    args = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="kanban",
        project="KANBA",
        qa_root=str(tmp_path / "qa"),
        pre_cutover_exempt_keys="KANBA-1, KANBA-2",
        json_out=None,
    )

    with patch("kanban.cli.verify_cutover._execute_verify", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = 0
        code = _run_cutover_verify(args)
        assert code == 0
        mock_exec.assert_awaited_once()

    # 2. Without exempt keys
    args_no_exempt = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="kanban",
        project="KANBA",
        qa_root=str(tmp_path / "qa"),
        pre_cutover_exempt_keys="",
        json_out=None,
    )
    with patch("kanban.cli.verify_cutover._execute_verify", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = 0
        assert _run_cutover_verify(args_no_exempt) == 0

    # 3. With source_project argument in merge mode
    args_source = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="kanban",
        project="KAN",
        source_project="KANBA",
        qa_root=str(tmp_path / "qa"),
        pre_cutover_exempt_keys="",
        json_out=None,
    )
    with patch("kanban.cli.verify_cutover._execute_verify", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = 0
        assert _run_cutover_verify(args_source) == 0


def test_cli_runner_exception_handling(tmp_path: Path) -> None:
    """Test _run_cutover_verify returns 1 on unexpected runtime error."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        bundle_dir=str(bundle_dir),
        workspace="kanban",
        project="KANBA",
        qa_root="./docs/qa",
        pre_cutover_exempt_keys="KANBA-1, KANBA-2",
        json_out=None,
    )

    with patch(
        "kanban.cli.verify_cutover._execute_verify", side_effect=RuntimeError("Connection refused")
    ):
        code = _run_cutover_verify(args)
        assert code == 1

    # Non-existent bundle directory
    args_bad_bundle = argparse.Namespace(
        bundle_dir=str(tmp_path / "nonexistent_bundle"),
        workspace="kanban",
        project="KANBA",
        qa_root="./docs/qa",
        pre_cutover_exempt_keys="",
        json_out=None,
    )
    assert _run_cutover_verify(args_bad_bundle) == 2

    # Console report without detail but with error code
    from kanban.cli.verify_cutover import _print_console_report
    from kanban.importer.cutover_verifier import CheckResult, CutoverAuditReport

    rep = CutoverAuditReport(
        overall_passed=False,
        workspace_slug="kanban",
        project_identifier="KANBA",
        checks=[CheckResult(name="chk", passed=False, error_code="ERR_CODE", detail=None)],
        summary={"passed_checks": 0, "total_checks": 1},
    )
    _print_console_report(rep)
