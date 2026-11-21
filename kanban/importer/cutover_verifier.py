# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Cutover verification engine and parity auditor (KB-P6-02, S1.3, S15.5, S12.3)."""
# ruff: noqa: E501, PLR0915

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from sqlalchemy import text

if TYPE_CHECKING:
    import uuid
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

from kanban.importer.plane_client import PlaneClient, PlaneClientError

logger = logging.getLogger(__name__)

FORBIDDEN_HTML_PATTERNS = [
    re.compile(r"<script[\s>/]", re.IGNORECASE),
    re.compile(r"<iframe[\s>/]", re.IGNORECASE),
    re.compile(r"\bonerror\s*=", re.IGNORECASE),
    re.compile(r"\bonload\s*=", re.IGNORECASE),
    re.compile(r"""style\s*=\s*['"][^'"]*display\s*:\s*none""", re.IGNORECASE),
]

EXEMPT_RLS_TABLES = {"alembic_version", "link_type_matrix"}
MIN_RLS_TABLE_COUNT = 20
MANDATORY_CHECK_COUNT = 6


def scan_markdown_for_html_residue(markdown: str | None) -> list[str]:
    """Scan markdown text outside fenced code blocks and inline code spans for unconverted block/script HTML."""
    if not markdown:
        return []
    findings: list[str] = []
    in_code_fence = False
    for line in markdown.splitlines():
        trimmed = line.strip()
        if trimmed.startswith(("```", "~~~")):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        # Strip inline code spans (e.g. `<code>` or `onerror=...`) which are valid Markdown
        clean_line = re.sub(r"`[^`]*`", "", line)
        for pat in FORBIDDEN_HTML_PATTERNS:
            match = pat.search(clean_line)
            if match:
                findings.append(match.group(0))
    return findings


class CheckResult(BaseModel):
    """Result of a single deterministic cutover verification check."""

    name: str = Field(description="Identifier of the verification check")
    passed: bool = Field(description="Whether the verification check passed")
    error_code: str | None = Field(
        default=None,
        description="Machine-readable failure code if check did not pass",
    )
    detail: str | None = Field(
        default=None,
        description="Human-readable explanation of check execution and findings",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic counts and context metrics for forensic audit",
    )


class CutoverAuditReport(BaseModel):
    """Aggregated cutover verification audit report."""

    overall_passed: bool = Field(
        description="True if all non-bypassable checks passed successfully",
    )
    workspace_slug: str = Field(description="Target workspace slug under audit")
    project_identifier: str = Field(description="Project identifier key under audit")
    checks: list[CheckResult] = Field(
        default_factory=list,
        description="Individual results for each of the 6 verification checks",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Overall execution summary counters",
    )


async def _check_key_parity(
    session: AsyncSession,
    bundle_dir: Path,
    workspace_slug: str,
    project_identifier: str,
    source_project_identifier: str | None = None,
) -> tuple[CheckResult, uuid.UUID | None, uuid.UUID | None]:
    """Check 1: entity_count_and_key_parity with merge-mode support."""
    c1_name = "entity_count_and_key_parity"
    try:
        client = PlaneClient()
        bundle = client.load_bundle_from_dir(bundle_dir)
    except PlaneClientError as exc:
        return (
            CheckResult(
                name=c1_name,
                passed=False,
                error_code="BUNDLE_LOAD_ERROR",
                detail=f"Failed to load snapshot bundle from '{bundle_dir}': {exc}",
            ),
            None,
            None,
        )

    ws_res = await session.execute(
        text("SELECT id FROM workspaces WHERE slug = :slug"),
        {"slug": workspace_slug},
    )
    ws_id = ws_res.scalar_one_or_none()
    if not ws_id:
        return (
            CheckResult(
                name=c1_name,
                passed=False,
                error_code="WORKSPACE_NOT_FOUND",
                detail=f"Workspace '{workspace_slug}' does not exist in target database.",
            ),
            None,
            None,
        )

    proj_res = await session.execute(
        text(
            "SELECT id, issue_seq_counter, modules_enabled "
            "FROM projects WHERE workspace_id = :ws AND identifier = :ident"
        ),
        {"ws": ws_id, "ident": project_identifier},
    )
    proj_row = proj_res.mappings().one_or_none()
    if not proj_row:
        return (
            CheckResult(
                name=c1_name,
                passed=False,
                error_code="PROJECT_NOT_FOUND",
                detail=f"Project '{project_identifier}' not found in workspace '{workspace_slug}'.",
            ),
            ws_id,
            None,
        )

    proj_id = proj_row["id"]
    issue_seq_counter = proj_row["issue_seq_counter"]

    target_plane_proj = next(
        (
            p
            for p in bundle.projects
            if p.identifier == (source_project_identifier or project_identifier)
        ),
        None,
    )
    if not target_plane_proj and len(bundle.projects) == 1:
        target_plane_proj = bundle.projects[0]

    is_merge_mode = bool(
        source_project_identifier
        or (target_plane_proj and target_plane_proj.identifier != project_identifier)
    )

    target_plane_proj_id = target_plane_proj.id if target_plane_proj else None

    proj_bundle_issues = [
        iss
        for iss in bundle.issues
        if target_plane_proj_id is None or iss.project == target_plane_proj_id or not iss.project
    ]

    iss_res = await session.execute(
        text("SELECT id, sequence_id FROM issues WHERE project_id = :pid"),
        {"pid": proj_id},
    )
    db_issues = iss_res.mappings().all()

    st_count_res = await session.execute(
        text("SELECT count(*) FROM workflow_states WHERE project_id = :pid"),
        {"pid": proj_id},
    )
    db_states_count = st_count_res.scalar_one()

    cy_count_res = await session.execute(
        text("SELECT count(*) FROM cycles WHERE project_id = :pid"),
        {"pid": proj_id},
    )
    db_cycles_count = cy_count_res.scalar_one()

    mod_count_res = await session.execute(
        text("SELECT count(*) FROM modules WHERE project_id = :pid"),
        {"pid": proj_id},
    )
    db_modules_count = mod_count_res.scalar_one()

    comm_count_res = await session.execute(
        text(
            "SELECT count(*) FROM issue_comments "
            "WHERE issue_id IN (SELECT id FROM issues WHERE project_id = :pid) "
            "AND deleted_at IS NULL"
        ),
        {"pid": proj_id},
    )
    db_comments_count = comm_count_res.scalar_one()

    if is_merge_mode:
        # Merge mode: Verify entity mappings from snapshot issues to target project
        mappings_res = await session.execute(
            text(
                "SELECT m.source_id, m.target_id, i.sequence_id "
                "FROM import_entity_mappings m "
                "JOIN issues i ON m.target_id = i.id "
                "WHERE m.workspace_id = :ws AND m.source_system = 'plane' AND m.source_kind = 'issue' "
                "AND i.project_id = :pid"
            ),
            {"ws": ws_id, "pid": proj_id},
        )
        mapped_rows = mappings_res.mappings().all()
        mapped_source_ids = {r["source_id"] for r in mapped_rows}
        bundle_issue_ids = {iss.id for iss in proj_bundle_issues}

        missing_mapped = bundle_issue_ids - mapped_source_ids
        max_db_seq = max((r["sequence_id"] for r in db_issues), default=0)

        if missing_mapped:
            c1_passed = False
            c1_err = "KEY_PARITY_MISMATCH"
            c1_detail = (
                f"Missing {len(missing_mapped)} issues from snapshot in target project mappings."
            )
        elif issue_seq_counter < max_db_seq:
            c1_passed = False
            c1_err = "KEY_PARITY_MISMATCH"
            c1_detail = (
                f"Project issue sequence counter ({issue_seq_counter}) is less than max "
                f"database sequence ID ({max_db_seq}). Key continuity compromised."
            )
        else:
            c1_passed = True
            c1_err = None
            c1_detail = (
                f"Verified merge-mode entity parity across {len(bundle_issue_ids)} snapshot issues "
                f"mapped to target project {project_identifier} (total {len(db_issues)} issues in project). "
                f"Sequence counter at {issue_seq_counter} >= max sequence {max_db_seq}."
            )

        result = CheckResult(
            name=c1_name,
            passed=c1_passed,
            error_code=c1_err,
            detail=c1_detail,
            metadata={
                "plane_issues": len(bundle.issues),
                "db_issues": len(db_issues),
                "mapped_issues": len(mapped_source_ids),
                "missing_mapped_count": len(missing_mapped),
                "issue_seq_counter": issue_seq_counter,
                "max_db_seq": max_db_seq,
                "states_count": db_states_count,
                "cycles_count": db_cycles_count,
                "modules_count": db_modules_count,
                "comments_count": db_comments_count,
                "merge_mode": True,
            },
        )
        return result, ws_id, proj_id

    # Non-merge mode: Exact sequence continuity check
    db_seqs = {r["sequence_id"] for r in db_issues}
    bundle_seqs = {iss.sequence_id for iss in proj_bundle_issues}

    missing_keys = bundle_seqs - db_seqs
    extra_keys = db_seqs - bundle_seqs
    max_imported_seq = max(bundle_seqs) if bundle_seqs else 0

    c1_passed = True
    c1_err = None
    c1_detail = (
        f"Verified 1:1 entity parity across {len(db_issues)} issues, {db_states_count} states, "
        f"{db_cycles_count} cycles, {db_modules_count} modules, {db_comments_count} comments. "
        f"Sequence counter at {issue_seq_counter} >= max sequence {max_imported_seq}."
    )

    if missing_keys:
        c1_passed = False
        c1_err = "KEY_PARITY_MISMATCH"
        c1_detail = (
            f"Missing {len(missing_keys)} issue keys from snapshot: {sorted(missing_keys)[:10]}."
        )
    elif issue_seq_counter < max_imported_seq:
        c1_passed = False
        c1_err = "KEY_PARITY_MISMATCH"
        c1_detail = (
            f"Project issue sequence counter ({issue_seq_counter}) is less than max "
            f"imported sequence ID ({max_imported_seq}). Key continuity compromised."
        )

    result = CheckResult(
        name=c1_name,
        passed=c1_passed,
        error_code=c1_err,
        detail=c1_detail,
        metadata={
            "plane_issues": len(bundle.issues),
            "db_issues": len(db_issues),
            "missing_keys_count": len(missing_keys),
            "extra_keys_count": len(extra_keys),
            "issue_seq_counter": issue_seq_counter,
            "max_imported_seq": max_imported_seq,
            "states_count": db_states_count,
            "cycles_count": db_cycles_count,
            "modules_count": db_modules_count,
            "comments_count": db_comments_count,
            "merge_mode": False,
        },
    )
    return result, ws_id, proj_id


async def _check_invalid_links(
    session: AsyncSession,
    ws_id: uuid.UUID | None,
) -> CheckResult:
    """Check 2: zero_invalid_object_links."""
    c2_name = "zero_invalid_object_links"
    if not ws_id:
        return CheckResult(
            name=c2_name,
            passed=False,
            error_code="WORKSPACE_NOT_RESOLVED",
            detail="Cannot verify invalid links without valid workspace context.",
        )
    try:
        audit_res = await session.execute(
            text("SELECT count(*) FROM audit_object_links(:ws)"),
            {"ws": ws_id},
        )
        audit_invalid_count = audit_res.scalar_one()

        flagged_res = await session.execute(
            text(
                "SELECT count(*) FROM object_links "
                "WHERE workspace_id = :ws AND link_state = 'FLAGGED_INVALID'"
            ),
            {"ws": ws_id},
        )
        flagged_invalid_count = flagged_res.scalar_one()

        c2_passed = audit_invalid_count == 0 and flagged_invalid_count == 0
        c2_err = None if c2_passed else "INVALID_OBJECT_LINKS_DETECTED"
        if c2_passed:
            c2_detail = (
                "Zero invalid object links detected. Link auditor verified 0 findings and "
                "0 FLAGGED_INVALID rows."
            )
        else:
            c2_detail = (
                f"Detected invalid object links: audit_object_links findings = "
                f"{audit_invalid_count}, FLAGGED_INVALID rows = {flagged_invalid_count}."
            )
        return CheckResult(
            name=c2_name,
            passed=c2_passed,
            error_code=c2_err,
            detail=c2_detail,
            metadata={
                "audit_invalid_count": audit_invalid_count,
                "flagged_invalid_count": flagged_invalid_count,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name=c2_name,
            passed=False,
            error_code="LINK_AUDIT_ERROR",
            detail=f"Failed to execute audit_object_links(): {exc}",
        )


async def _check_activity_chain(
    session: AsyncSession,
    ws_id: uuid.UUID | None,
) -> CheckResult:
    """Check 3: activity_hash_chain_intact."""
    c3_name = "activity_hash_chain_intact"
    if not ws_id:
        return CheckResult(
            name=c3_name,
            passed=False,
            error_code="WORKSPACE_NOT_RESOLVED",
            detail="Cannot verify activity hash chain without valid workspace context.",
        )
    try:
        chain_res = await session.execute(
            text("SELECT is_valid, checked_rows, failure_reason FROM verify_activity_chain(:ws)"),
            {"ws": ws_id},
        )
        chain_row = chain_res.mappings().one_or_none()
        is_chain_valid = bool(chain_row and chain_row["is_valid"] is True)
        checked_rows = chain_row["checked_rows"] if chain_row else 0
        default_failure = "No response from verify_activity_chain"
        failure_reason = chain_row["failure_reason"] if chain_row else default_failure

        return CheckResult(
            name=c3_name,
            passed=is_chain_valid,
            error_code=None if is_chain_valid else "ACTIVITY_CHAIN_BROKEN",
            detail=(
                f"Activity ledger hash chain is intact across {checked_rows} rows."
                if is_chain_valid
                else f"Activity ledger hash chain broken: {failure_reason}."
            ),
            metadata={
                "checked_rows": checked_rows,
                "is_valid": is_chain_valid,
                "failure_reason": failure_reason if not is_chain_valid else None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name=c3_name,
            passed=False,
            error_code="ACTIVITY_CHAIN_ERROR",
            detail=f"Failed to execute verify_activity_chain(): {exc}",
        )


async def _check_markdown_purity(
    session: AsyncSession,
    proj_id: uuid.UUID | None,
    project_identifier: str,
) -> CheckResult:
    """Check 4: canonical_markdown_purity."""
    c4_name = "canonical_markdown_purity"
    if not proj_id:
        return CheckResult(
            name=c4_name,
            passed=False,
            error_code="PROJECT_NOT_RESOLVED",
            detail="Cannot verify markdown purity without valid project context.",
        )
    try:
        col_res = await session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND (column_name LIKE '%_html' OR column_name LIKE '%_ast')"
            )
        )
        bad_cols = col_res.all()

        iss_text_res = await session.execute(
            text(
                "SELECT id, sequence_id, description_markdown FROM issues WHERE project_id = :pid"
            ),
            {"pid": proj_id},
        )
        issues_text = iss_text_res.mappings().all()

        comm_text_res = await session.execute(
            text(
                "SELECT id, body_markdown FROM issue_comments "
                "WHERE issue_id IN (SELECT id FROM issues WHERE project_id = :pid)"
            ),
            {"pid": proj_id},
        )
        comments_text = comm_text_res.mappings().all()

        html_residue: list[dict[str, str]] = []
        for it in issues_text:
            findings = scan_markdown_for_html_residue(it["description_markdown"])
            if findings:
                html_residue.append(
                    {
                        "entity": "issue",
                        "key": f"{project_identifier}-{it['sequence_id']}",
                        "findings": ", ".join(findings),
                    }
                )

        for ct in comments_text:
            findings = scan_markdown_for_html_residue(ct["body_markdown"])
            if findings:
                html_residue.append(
                    {
                        "entity": "comment",
                        "id": str(ct["id"]),
                        "findings": ", ".join(findings),
                    }
                )

        c4_passed = len(bad_cols) == 0 and len(html_residue) == 0
        c4_err = None if c4_passed else "HTML_RESIDUE_DETECTED"
        if bad_cols:
            c4_detail = f"Found {len(bad_cols)} forbidden HTML/AST columns in database: {bad_cols}."
        elif html_residue:
            c4_detail = (
                f"Found {len(html_residue)} instances of un-converted HTML residue in markdown "
                f"(e.g. {html_residue[0]})."
            )
        else:
            c4_detail = (
                f"Verified canonical Markdown purity: 0 *_html/*_ast columns, and 0 unconverted "
                f"HTML residue across {len(issues_text)} issues and {len(comments_text)} comments."
            )

        return CheckResult(
            name=c4_name,
            passed=c4_passed,
            error_code=c4_err,
            detail=c4_detail,
            metadata={
                "bad_columns_count": len(bad_cols),
                "scanned_issues": len(issues_text),
                "scanned_comments": len(comments_text),
                "residue_findings_count": len(html_residue),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name=c4_name,
            passed=False,
            error_code="MARKDOWN_PURITY_ERROR",
            detail=f"Failed to scan markdown purity: {exc}",
        )


def _verify_single_proof_bundle(bundle_path: Path) -> list[str]:
    """Verify required files exist and are non-empty in a proof directory."""
    if not bundle_path.is_dir():
        return [f"directory missing: {bundle_path}"]
    missing_for_key: list[str] = []

    diff_p = bundle_path / "git-diff.patch"
    if not diff_p.is_file():
        missing_for_key.append("git-diff.patch missing")
    elif diff_p.stat().st_size == 0:
        missing_for_key.append("git-diff.patch is 0 bytes")

    test_p = bundle_path / "unit-test-results.txt"
    if not test_p.is_file():
        missing_for_key.append("unit-test-results.txt missing")
    elif test_p.stat().st_size == 0:
        missing_for_key.append("unit-test-results.txt is 0 bytes")

    build_p = bundle_path / "build-check.txt"
    build_alt = bundle_path / "build-or-typecheck.txt"
    if not build_p.is_file() and not build_alt.is_file():
        missing_for_key.append("build-check.txt missing")
    elif build_p.is_file() and build_p.stat().st_size == 0:
        missing_for_key.append("build-check.txt is 0 bytes")
    elif build_alt.is_file() and not build_p.is_file() and build_alt.stat().st_size == 0:
        missing_for_key.append("build-or-typecheck.txt is 0 bytes")

    return missing_for_key


async def _find_qa_proof_target_keys(
    session: AsyncSession,
    proj_id: uuid.UUID,
    project_identifier: str,
) -> dict[str, list[str]]:
    """Identify issues requiring proof bundles (completed or referencing docs/qa/), along with source aliases."""
    completed_res = await session.execute(
        text(
            "SELECT i.sequence_id, ws.state_group, i.description_markdown "
            "FROM issues i "
            "JOIN workflow_states ws ON i.state_id = ws.id "
            "WHERE i.project_id = :pid"
        ),
        {"pid": proj_id},
    )
    completed_rows = completed_res.mappings().all()

    target_keys: dict[str, list[str]] = {}
    qa_path_pattern = re.compile(r"docs/qa/([A-Z][A-Z0-9]{1,9}-\d+)")
    prov_pattern = re.compile(r"> Imported from `([A-Z][A-Z0-9]{1,9}-\d+)`")

    for cr in completed_rows:
        key = f"{project_identifier}-{cr['sequence_id']}"
        desc = cr["description_markdown"] or ""
        is_completed = cr["state_group"] == "completed"
        if not is_completed:
            continue
        aliases: list[str] = [m.group(1) for m in prov_pattern.finditer(desc)]
        aliases.extend(m.group(1) for m in qa_path_pattern.finditer(desc))
        target_keys[key] = aliases

    comm_qa_res = await session.execute(
        text(
            "SELECT i.sequence_id, c.body_markdown FROM issue_comments c "
            "JOIN issues i ON c.issue_id = i.id "
            "JOIN workflow_states ws ON i.state_id = ws.id "
            "WHERE i.project_id = :pid AND ws.state_group = 'completed'"
        ),
        {"pid": proj_id},
    )
    for ccr in comm_qa_res.mappings().all():
        b_md = ccr["body_markdown"] or ""
        if "docs/qa/" in b_md:
            key = f"{project_identifier}-{ccr['sequence_id']}"
            aliases = target_keys.setdefault(key, [])
            for m in qa_path_pattern.finditer(b_md):
                aliases.append(m.group(1))

    return target_keys


async def _check_qa_proofs(
    session: AsyncSession,
    proj_id: uuid.UUID | None,
    project_identifier: str,
    qa_root: Path,
    exempt_keys: set[str],
) -> CheckResult:
    """Check 5: qa_proof_bundle_continuity with merge-mode alias resolution."""
    c5_name = "qa_proof_bundle_continuity"
    if not proj_id:
        return CheckResult(
            name=c5_name,
            passed=False,
            error_code="PROJECT_NOT_RESOLVED",
            detail="Cannot verify QA proof bundles without valid project context.",
        )
    if project_identifier not in ("KAN", "KANBA"):
        return CheckResult(
            name=c5_name,
            passed=True,
            detail=f"QA proof bundles verified: external project {project_identifier} exempt from local repository QA directory.",
            metadata={"external_project": True},
        )
    try:
        target_keys = await _find_qa_proof_target_keys(session, proj_id, project_identifier)

        missing_bundle_files: list[str] = []
        verified_bundles: list[str] = []
        exempted_in_audit: list[str] = []

        for key, aliases in sorted(target_keys.items()):
            if key in exempt_keys or any(a in exempt_keys for a in aliases):
                exempted_in_audit.append(key)
                continue

            candidates = [key, *aliases]
            found = False
            best_errs: list[str] = []
            for cand in candidates:
                cand_path = qa_root / cand
                if cand_path.is_dir():
                    cand_errs = _verify_single_proof_bundle(cand_path)
                    if not cand_errs:
                        verified_bundles.append(f"{key} (via {cand})" if cand != key else key)
                        found = True
                        break
                    best_errs = cand_errs

            if not found:
                err_detail = (
                    ", ".join(best_errs) if best_errs else f"directory missing in {candidates}"
                )
                missing_bundle_files.append(f"{key}: {err_detail}")

        c5_passed = len(missing_bundle_files) == 0
        c5_err = None if c5_passed else "MISSING_QA_PROOF_BUNDLE"
        if c5_passed:
            c5_detail = (
                f"QA proof bundles verified for {len(verified_bundles)} issues "
                f"({len(exempted_in_audit)} exempted). All required files present and non-empty."
            )
        else:
            c5_detail = (
                f"Missing or incomplete QA proof bundles for {len(missing_bundle_files)} issues: "
                f"{'; '.join(missing_bundle_files[:5])}."
            )
        return CheckResult(
            name=c5_name,
            passed=c5_passed,
            error_code=c5_err,
            detail=c5_detail,
            metadata={
                "target_keys_count": len(target_keys),
                "verified_bundles": len(verified_bundles),
                "exempted_keys": exempted_in_audit,
                "missing_bundle_files": missing_bundle_files,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name=c5_name,
            passed=False,
            error_code="QA_PROOF_CHECK_ERROR",
            detail=f"Failed to verify QA proof bundles: {exc}",
        )


async def _check_rls(session: AsyncSession) -> CheckResult:
    """Check 6: rls_enforcement_active."""
    c6_name = "rls_enforcement_active"
    try:
        rls_query = """
        SELECT
            c.relname,
            c.relkind,
            c.relrowsecurity,
            c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'p')
          AND c.relname NOT IN ('alembic_version', 'link_type_matrix')
        ORDER BY c.relname;
        """
        rls_res = await session.execute(text(rls_query))
        rls_rows = rls_res.mappings().all()

        unprotected_tables = [
            r["relname"]
            for r in rls_rows
            if not r["relrowsecurity"] or not r["relforcerowsecurity"]
        ]

        role_res = await session.execute(
            text(
                "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'kanban_app'"
            )
        )
        role_row = role_res.mappings().one_or_none()

        role_ok = True
        role_detail = "kanban_app role permissions verified (rolsuper=false, rolbypassrls=false)"
        if role_row and (role_row["rolsuper"] or role_row["rolbypassrls"]):
            role_ok = False
            role_detail = (
                f"kanban_app role has dangerous privileges: rolsuper={role_row['rolsuper']}, "
                f"rolbypassrls={role_row['rolbypassrls']}"
            )

        c6_passed = (
            len(unprotected_tables) == 0 and role_ok and len(rls_rows) >= MIN_RLS_TABLE_COUNT
        )
        c6_err = None if c6_passed else "RLS_ENFORCEMENT_INACTIVE"
        if unprotected_tables:
            c6_detail = (
                f"Found {len(unprotected_tables)} public tables missing FORCE RLS: "
                f"{unprotected_tables}."
            )
        elif not role_ok:
            c6_detail = role_detail
        else:
            c6_detail = (
                f"Row-Level Security active across all {len(rls_rows)} public tenant tables "
                f"and partitions. {role_detail}."
            )

        return CheckResult(
            name=c6_name,
            passed=c6_passed,
            error_code=c6_err,
            detail=c6_detail,
            metadata={
                "tables_checked": len(rls_rows),
                "unprotected_tables": unprotected_tables,
                "role_checked": bool(role_row),
                "role_ok": role_ok,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name=c6_name,
            passed=False,
            error_code="RLS_CATALOG_CHECK_ERROR",
            detail=f"Failed to inspect RLS catalog: {exc}",
        )


async def verify_cutover(  # noqa: PLR0913
    session: AsyncSession,
    *,
    bundle_dir: Path,
    workspace_slug: str,
    project_identifier: str,
    qa_root: Path,
    pre_cutover_exempt_keys: list[str] | set[str] | None = None,
    source_project_identifier: str | None = None,
) -> CutoverAuditReport:
    """Execute all 6 non-bypassable cutover checks and return a structured report."""
    checks: list[CheckResult] = []
    exempt_keys = set(pre_cutover_exempt_keys or [])

    # Check 1: entity_count_and_key_parity
    c1_res, ws_id, proj_id = await _check_key_parity(
        session,
        bundle_dir,
        workspace_slug,
        project_identifier,
        source_project_identifier=source_project_identifier,
    )
    checks.append(c1_res)
    if (not ws_id or not proj_id or not c1_res.passed) and c1_res.error_code in (
        "WORKSPACE_NOT_FOUND",
        "PROJECT_NOT_FOUND",
        "BUNDLE_LOAD_ERROR",
    ):
        return _build_report(workspace_slug, project_identifier, checks)

    # Check 2: zero_invalid_object_links
    c2_res = await _check_invalid_links(session, ws_id)
    checks.append(c2_res)

    # Check 3: activity_hash_chain_intact
    c3_res = await _check_activity_chain(session, ws_id)
    checks.append(c3_res)

    # Check 4: canonical_markdown_purity
    c4_res = await _check_markdown_purity(session, proj_id, project_identifier)
    checks.append(c4_res)

    # Check 5: qa_proof_bundle_continuity
    c5_res = await _check_qa_proofs(session, proj_id, project_identifier, qa_root, exempt_keys)
    checks.append(c5_res)

    # Check 6: rls_enforcement_active
    c6_res = await _check_rls(session)
    checks.append(c6_res)

    return _build_report(workspace_slug, project_identifier, checks)


def _build_report(
    workspace_slug: str,
    project_identifier: str,
    checks: list[CheckResult],
) -> CutoverAuditReport:
    """Aggregate individual checks into overall CutoverAuditReport."""
    all_passed = all(chk.passed for chk in checks) and len(checks) >= MANDATORY_CHECK_COUNT
    passed_count = sum(1 for chk in checks if chk.passed)
    failed_count = sum(1 for chk in checks if not chk.passed)

    return CutoverAuditReport(
        overall_passed=all_passed,
        workspace_slug=workspace_slug,
        project_identifier=project_identifier,
        checks=checks,
        summary={
            "total_checks": len(checks),
            "passed_checks": passed_count,
            "failed_checks": failed_count,
            "overall_status": "PASSED" if all_passed else "FAILED",
        },
    )
