# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
# ruff: noqa: E501, PLR0913, PLR0917, ARG001, ANN401, PLC0415, PYI034, PYI036, ARG002, TRY003, EM101, C901, PLR0915, ASYNC221, S106, D413, TC003
"""Unit and integration tests for commit signature, live CI, and SLSA attestation workflow gates (KB-DEVSECOPS-ATTEST-01, KAN-76)."""

from __future__ import annotations

import base64
import json
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from sqlalchemy import select

from database.models.projects import WorkflowState
from database.models.repo_binding import CommitAttestation, ProjectRepoBinding
from database.models.workflow import (
    WorkflowTransitionExecution,
    WorkflowTransitionHook,
)
from kanban.api.problems import ProblemException
from kanban.issues.proof import validate_ci_run_url_live
from kanban.workflows.attestation_gate import (
    verify_live_ci_check_run,
    verify_slsa_provenance,
)
from kanban.workflows.manifest import compute_hook_manifest_sha256

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser
    from kanban.tests.contract import ContractRecorder

pytestmark = pytest.mark.committed_db


def make_slsa_v1_envelope(head_sha: str) -> dict[str, Any]:
    """Generate a DSSE envelope with in-toto SLSA v1.0 predicate matching head_sha."""
    clean_sha = head_sha.strip().lower()
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [
            {
                "name": "git+https://github.com/example/kanban",
                "digest": {
                    "sha1": clean_sha if len(clean_sha) == 40 else "a" * 40,
                    "sha256": clean_sha if len(clean_sha) == 64 else "b" * 64,
                },
            }
        ],
        "predicate": {
            "buildDefinition": {
                "buildType": "https://actions.github.com/buildtypes/runner/v1",
                "internalParameters": {},
            },
            "runDetails": {
                "builder": {
                    "id": "https://github.com/actions/runner",
                },
            },
        },
    }
    raw_bytes = json.dumps(statement).encode("utf-8")
    return {
        "payloadType": "application/vnd.in-toto+json",
        "payload": base64.b64encode(raw_bytes).decode("ascii"),
        "signatures": [
            {
                "keyid": "test-key-id",
                "sig": base64.b64encode(b"dummy_sigstore_bytes").decode("ascii"),
            }
        ],
    }


def create_git_repo_with_ssh_commit(
    tmp_path: Path,
) -> tuple[Path, str, str, str, str]:
    """Generate bare git repo with unsigned and SSH signed commits.

    Returns:
        (bare_mirror_path, signed_sha, unsigned_sha, allowed_signers_str, untrusted_signers_str)
    """
    work = tmp_path / "work"
    work.mkdir()

    # Generate primary test key
    key_path = tmp_path / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path), "-C", "sec@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    pub_key = (tmp_path / "id_ed25519.pub").read_text(encoding="utf-8").strip()

    # Generate rogue/untrusted key
    rogue_path = tmp_path / "id_rogue"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(rogue_path), "-C", "rogue@example.com"],
        check=True,
        capture_output=True,
        text=True,
    )
    rogue_pub = (tmp_path / "id_rogue.pub").read_text(encoding="utf-8").strip()

    allowed_signers_str = f"sec@example.com {pub_key}\n"
    untrusted_signers_str = f"rogue@example.com {rogue_pub}\n"

    allowed_file = tmp_path / "allowed_signers"
    allowed_file.write_text(allowed_signers_str, encoding="utf-8")

    def run_git(*args: str) -> str:
        res = subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
        )
        return res.stdout.strip()

    run_git("init")
    run_git("config", "user.name", "Security Lead")
    run_git("config", "user.email", "sec@example.com")
    run_git("config", "commit.gpgsign", "false")

    # 1. Unsigned commit
    (work / "README.md").write_text("# Project\nInitial commit.\n", encoding="utf-8")
    run_git("add", "README.md")
    run_git("commit", "-m", "Initial unsigned commit")
    unsigned_sha = run_git("rev-parse", "HEAD")

    # 2. Signed commit
    run_git("config", "gpg.format", "ssh")
    run_git("config", "user.signingkey", str(key_path))
    run_git("config", "gpg.ssh.allowedSignersFile", str(allowed_file))
    run_git("config", "commit.gpgsign", "true")

    (work / "secure_file.py").write_text("print('Verified secure code')\n", encoding="utf-8")
    run_git("add", "secure_file.py")
    run_git("commit", "-m", "Verified SSH signed commit")
    signed_sha = run_git("rev-parse", "HEAD")

    # Clone bare mirror
    bare_path = tmp_path / "repo.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare_path)],
        check=True,
        capture_output=True,
    )

    return bare_path, signed_sha, unsigned_sha, allowed_signers_str, untrusted_signers_str


async def create_deterministic_hook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    to_state_id: uuid.UUID,
    name: str,
    hook_kind: str,
    sort_rank: str = "10",
) -> WorkflowTransitionHook:
    """Create a validated deterministic WorkflowTransitionHook."""
    hook_id = uuid.uuid4()
    manifest_sha = compute_hook_manifest_sha256(
        hook_kind=hook_kind,
        wasm_module_sha256=None,
        agent_definition_id=None,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        from_state_id=None,
        to_state_id=to_state_id,
    )
    hook = WorkflowTransitionHook(
        id=hook_id,
        workspace_id=workspace_id,
        project_id=project_id,
        from_state_id=None,
        to_state_id=to_state_id,
        sort_rank=str(sort_rank),
        name=name,
        hook_kind=hook_kind,
        is_enabled=True,
        wasm_module_sha256=None,
        agent_definition_id=None,
        allowed_mutable_fields=[],
        failure_policy="fail_closed",
        manifest_sha256=manifest_sha,
    )
    session.add(hook)
    await session.commit()
    return hook


async def _get_states(session: AsyncSession, project_id: uuid.UUID) -> dict[str, uuid.UUID]:
    """Fetch workflow state IDs by name."""
    await session.rollback()
    stmt = select(WorkflowState.name, WorkflowState.id).where(
        WorkflowState.project_id == project_id
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0]): r[1] for r in rows}


# ---------------------------------------------------------------------------
# Test Case 1: Positive Flow
# ---------------------------------------------------------------------------


async def test_case_1_positive_signed_commit_passing_ci_valid_slsa(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive: Verified SSH commit + passing CI check-run + matching SLSA v1 bundle succeeds to Done."""
    admin = await make_user("attest_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("ATTP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    # 1. Setup Bare Git Mirror
    mirrors_base = tmp_path / "mirrors"
    mirrors_base.mkdir()
    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", str(mirrors_base))

    bare_repo, signed_sha, _, allowed_signers, _ = create_git_repo_with_ssh_commit(tmp_path)

    # 2. Add ProjectRepoBinding in DB
    binding_id = uuid.uuid4()
    binding_mirror_dir = mirrors_base / str(api_env.workspace_id) / f"{binding_id}.git"
    binding_mirror_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", str(bare_repo), str(binding_mirror_dir)], check=True)

    binding = ProjectRepoBinding(
        id=binding_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        slug="attestation-repo",
        remote_url="https://github.com/example/kanban.git",
        default_ref="main",
        access_mode="bare_git_tools",
        ssh_allowed_signers=allowed_signers,
        gpg_trusted_armored_keys=None,
        sigstore_trusted_identities_json=[],
        last_fetched_commit=signed_sha,
        created_by=admin.id,
    )
    api_env.seed.add(binding)
    await api_env.seed.commit()

    # 3. Create 3 deterministic workflow transition hooks for transition to Done
    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="commit-sig-gate",
        hook_kind="commit_signature",
        sort_rank="10",
    )
    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="ci-check-gate",
        hook_kind="ci_check_run",
        sort_rank="20",
    )
    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="slsa-provenance-gate",
        hook_kind="slsa_provenance",
        sort_rank="30",
    )

    # 4. Create Issue
    resp = await client.post(
        "/api/v1/projects/ATTP/issues",
        json={"summary": "Attested Issue", "description_markdown": "Requires signed commit & CI"},
    )
    assert resp.status_code == 201, resp.text
    issue_key = resp.json()["key"]

    # 5. Mock GitHub Check Runs API response for live CI check
    ci_url = "https://github.com/example/kanban/actions/runs/987654321"
    mock_gh_data = {
        "total_count": 1,
        "check_runs": [
            {
                "id": 112233,
                "name": "Build & Test",
                "head_sha": signed_sha,
                "status": "completed",
                "conclusion": "success",
                "html_url": ci_url,
            }
        ],
    }

    class MockAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> MockAsyncClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=mock_gh_data, request=request)

    async def mock_resolve_ip(host: str, **kwargs: Any) -> str:
        return "140.82.121.4"

    monkeypatch.setattr(
        "kanban.workflows.attestation_gate.resolve_and_select_pinned_ip",
        mock_resolve_ip,
    )
    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    # 6. Execute Transition with complete verification_proof packet
    slsa_bundle = make_slsa_v1_envelope(signed_sha)
    verification_proof = {
        "head_sha": signed_sha,
        "ci_run_url": ci_url,
        "slsa_provenance": slsa_bundle,
    }

    t_resp = await client.post(
        f"/api/v1/issues/{issue_key}/transitions",
        json={"to_state": "Done", "verification_proof": verification_proof},
    )
    contract_recorder.record("transition_positive_attested_gates_200", t_resp.request, t_resp)
    assert t_resp.status_code == 200, t_resp.text
    body = t_resp.json()
    assert body["status"] == "approved"
    assert body["state"] == "Done"

    # 7. Forensic DB Verification: commit_attestations persisted
    await api_env.seed.rollback()
    att_stmt = select(CommitAttestation).where(
        CommitAttestation.repo_binding_id == binding_id,
        CommitAttestation.commit_sha == signed_sha,
    )
    att_row = (await api_env.seed.execute(att_stmt)).scalar_one_or_none()
    assert att_row is not None
    assert att_row.verified is True
    assert att_row.sig_scheme == "ssh"
    assert "sec@example.com" in (att_row.signer_identity or "")

    # 8. Forensic DB Verification: execution verdict contains attestation records
    exec_stmt = select(WorkflowTransitionExecution).where(
        WorkflowTransitionExecution.to_state_id == done_id
    )
    exec_row = (await api_env.seed.execute(exec_stmt)).scalars().first()
    assert exec_row is not None
    assert exec_row.status == "approved"
    verdict = exec_row.verdict_json or {}
    assert "commit_attestation" in verdict
    assert verdict["commit_attestation"]["verified"] is True
    assert "ci_check_run" in verdict
    assert verdict["ci_check_run"]["verified"] is True
    assert "slsa_provenance" in verdict
    assert verdict["slsa_provenance"]["verified"] is True


# ---------------------------------------------------------------------------
# Test Case 2: Negative / Security Flows (Fail Closed 409)
# ---------------------------------------------------------------------------


async def test_case_2_negative_security_failures(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
    as_principal: Callable[..., httpx.AsyncClient],
    contract_recorder: ContractRecorder,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative: Unsigned commits, untrusted keys, red CI, or tampered SLSA fail closed with 409."""
    admin = await make_user("neg_admin", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("NEGP", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    client = as_principal(admin)

    states = await _get_states(api_env.seed, proj_id)
    done_id = states["Done"]

    mirrors_base = tmp_path / "mirrors_neg"
    mirrors_base.mkdir()
    monkeypatch.setenv("KANBAN_REPO_MIRROR_DIR", str(mirrors_base))

    bare_repo, signed_sha, unsigned_sha, allowed_signers, untrusted_signers = (
        create_git_repo_with_ssh_commit(tmp_path)
    )

    binding_id = uuid.uuid4()
    binding_mirror_dir = mirrors_base / str(api_env.workspace_id) / f"{binding_id}.git"
    binding_mirror_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", str(bare_repo), str(binding_mirror_dir)], check=True)

    binding = ProjectRepoBinding(
        id=binding_id,
        workspace_id=api_env.workspace_id,
        project_id=proj_id,
        slug="neg-repo",
        remote_url="https://github.com/example/kanban.git",
        default_ref="main",
        access_mode="bare_git_tools",
        ssh_allowed_signers=allowed_signers,
        gpg_trusted_armored_keys=None,
        sigstore_trusted_identities_json=[],
        last_fetched_commit=signed_sha,
        created_by=admin.id,
    )
    api_env.seed.add(binding)
    await api_env.seed.commit()

    # Subcase A: Unsigned commit rejected by commit_signature gate
    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="gate-commit-sig",
        hook_kind="commit_signature",
    )

    resp_a = await client.post(
        "/api/v1/projects/NEGP/issues",
        json={"summary": "Issue Unsigned", "description_markdown": "Test"},
    )
    key_a = resp_a.json()["key"]

    t_resp_a = await client.post(
        f"/api/v1/issues/{key_a}/transitions",
        json={"to_state": "Done", "verification_proof": {"head_sha": unsigned_sha}},
    )
    contract_recorder.record("transition_negative_unsigned_commit_409", t_resp_a.request, t_resp_a)
    assert t_resp_a.status_code == 409, t_resp_a.text
    assert t_resp_a.json()["code"] == "PROVENANCE_ATTESTATION_FAILED"
    assert t_resp_a.json()["error_code"] == "SIGNATURE_NOT_FOUND"

    # Subcase B: Untrusted signer rejected by commit_signature gate
    binding.ssh_allowed_signers = untrusted_signers
    api_env.seed.add(binding)
    await api_env.seed.commit()

    resp_b = await client.post(
        "/api/v1/projects/NEGP/issues",
        json={"summary": "Issue Untrusted", "description_markdown": "Test"},
    )
    key_b = resp_b.json()["key"]

    t_resp_b = await client.post(
        f"/api/v1/issues/{key_b}/transitions",
        json={"to_state": "Done", "verification_proof": {"head_sha": signed_sha}},
    )
    assert t_resp_b.status_code == 409, t_resp_b.text
    assert t_resp_b.json()["code"] == "PROVENANCE_ATTESTATION_FAILED"
    assert t_resp_b.json()["error_code"] == "UNTRUSTED_SIGNER"

    # Restore trusted signers for CI and SLSA checks
    binding.ssh_allowed_signers = allowed_signers
    api_env.seed.add(binding)
    await api_env.seed.commit()

    # Subcase C: Failed CI run rejected by ci_check_run gate
    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="gate-ci-check",
        hook_kind="ci_check_run",
    )

    mock_failed_gh = {
        "total_count": 1,
        "check_runs": [
            {
                "id": 998877,
                "name": "Integration Tests",
                "head_sha": signed_sha,
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/example/kanban/actions/runs/111",
            }
        ],
    }

    class MockFailedClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> MockFailedClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=mock_failed_gh, request=request)

    async def mock_failed_resolve_ip(host: str, **kwargs: Any) -> str:
        return "140.82.121.4"

    monkeypatch.setattr(
        "kanban.workflows.attestation_gate.resolve_and_select_pinned_ip",
        mock_failed_resolve_ip,
    )
    monkeypatch.setattr("httpx.AsyncClient", MockFailedClient)

    resp_c = await client.post(
        "/api/v1/projects/NEGP/issues",
        json={"summary": "Issue Failed CI", "description_markdown": "Test"},
    )
    key_c = resp_c.json()["key"]

    t_resp_c = await client.post(
        f"/api/v1/issues/{key_c}/transitions",
        json={
            "to_state": "Done",
            "verification_proof": {
                "head_sha": signed_sha,
                "ci_run_url": "https://github.com/example/kanban/actions/runs/111",
            },
        },
    )
    contract_recorder.record("transition_negative_failed_ci_409", t_resp_c.request, t_resp_c)
    assert t_resp_c.status_code == 409, t_resp_c.text
    assert t_resp_c.json()["code"] == "PROVENANCE_ATTESTATION_FAILED"
    assert t_resp_c.json()["error_code"] == "CI_CHECK_RUN_FAILED"

    # Subcase D: Tampered SLSA bundle digest rejected by slsa_provenance gate
    mock_passing_gh = {
        "id": 111,
        "head_sha": signed_sha,
        "status": "completed",
        "conclusion": "success",
    }

    class MockPassingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> MockPassingClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request("GET", url)
            return httpx.Response(200, json=mock_passing_gh, request=request)

    monkeypatch.setattr("httpx.AsyncClient", MockPassingClient)

    await create_deterministic_hook(
        api_env.seed,
        api_env.workspace_id,
        proj_id,
        to_state_id=done_id,
        name="gate-slsa",
        hook_kind="slsa_provenance",
    )

    tampered_slsa = make_slsa_v1_envelope("1111222233334444555566667777888899990000")

    resp_d = await client.post(
        "/api/v1/projects/NEGP/issues",
        json={"summary": "Issue Tampered SLSA", "description_markdown": "Test"},
    )
    key_d = resp_d.json()["key"]

    t_resp_d = await client.post(
        f"/api/v1/issues/{key_d}/transitions",
        json={
            "to_state": "Done",
            "verification_proof": {
                "head_sha": signed_sha,
                "ci_run_url": "https://github.com/example/kanban/actions/runs/111",
                "slsa_provenance": tampered_slsa,
            },
        },
    )
    contract_recorder.record("transition_negative_tampered_slsa_409", t_resp_d.request, t_resp_d)
    assert t_resp_d.status_code == 409, t_resp_d.text
    assert t_resp_d.json()["code"] == "PROVENANCE_ATTESTATION_FAILED"
    assert t_resp_d.json()["error_code"] == "SLSA_DIGEST_MISMATCH"


# ---------------------------------------------------------------------------
# Test Case 3: Boundary (Air-Gap Mode & Zero-Shell Invariants)
# ---------------------------------------------------------------------------


async def test_case_3_boundary_air_gap_mode_and_offline_verification(
    tmp_path: Path,
) -> None:
    """Boundary: air_gap_mode=True blocks live CI egress with AIR_GAP_EGRESS_BLOCKED while local gates verify offline."""
    # 1. verify_live_ci_check_run blocked under air_gap_mode with 403 AIR_GAP_EGRESS_BLOCKED
    with pytest.raises(ProblemException) as exc_ci:
        await verify_live_ci_check_run(
            "https://github.com/example/kanban/actions/runs/123",
            "a" * 40,
            air_gap_mode=True,
        )
    assert exc_ci.value.code == "AIR_GAP_EGRESS_BLOCKED"
    assert exc_ci.value.status == 403

    # 2. validate_ci_run_url_live raises under air_gap_mode
    with pytest.raises(ProblemException) as exc_live:
        await validate_ci_run_url_live(
            "https://github.com/example/kanban/actions/runs/123",
            "a" * 40,
            air_gap_mode=True,
        )
    assert exc_live.value.code == "AIR_GAP_EGRESS_BLOCKED"
    assert exc_live.value.status == 403

    # 3. Local SLSA provenance verifies completely offline without network sockets
    valid_sha = "e" * 40
    bundle = make_slsa_v1_envelope(valid_sha)
    res_slsa = verify_slsa_provenance(bundle, valid_sha)
    assert res_slsa.verified is True
    assert res_slsa.matched_digest == valid_sha
    assert res_slsa.build_type == "https://actions.github.com/buildtypes/runner/v1"


# ---------------------------------------------------------------------------
# Direct Gate & Attestation Unit Tests (Coverage & Branch Exhaustion)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gitlab_pipeline_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitLab pipeline status verification handles success, sha mismatch, and failure."""
    head_sha = "c" * 40
    gl_url = "https://gitlab.com/group/project/-/pipelines/456789"

    async def mock_ip(host: str, **kw: Any) -> str:
        return "172.65.251.78"

    monkeypatch.setattr("kanban.workflows.attestation_gate.resolve_and_select_pinned_ip", mock_ip)

    # 1. Success
    class MockGitLabSuccess:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockGitLabSuccess:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json={"id": 456789, "sha": head_sha, "status": "success"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockGitLabSuccess)
    res_ok = await verify_live_ci_check_run(gl_url, head_sha, auth_token="glpat-token")
    assert res_ok.verified is True
    assert res_ok.provider == "gitlab"

    # 2. SHA mismatch
    class MockGitLabMismatch:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockGitLabMismatch:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json={"id": 456789, "sha": "d" * 40, "status": "success"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockGitLabMismatch)
    res_mismatch = await verify_live_ci_check_run(gl_url, head_sha)
    assert res_mismatch.verified is False
    assert "does not match" in str(res_mismatch.error_detail)

    # 3. Failed pipeline
    class MockGitLabFail:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockGitLabFail:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json={"id": 456789, "sha": head_sha, "status": "failed"},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockGitLabFail)
    res_fail = await verify_live_ci_check_run(gl_url, head_sha)
    assert res_fail.verified is False


@pytest.mark.asyncio
async def test_forgejo_commit_status_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forgejo / custom commit status verification evaluates passing and failing states."""
    head_sha = "f" * 40
    fj_url = f"https://code.example.com/org/repo/commit/{head_sha}"

    async def mock_ip(host: str, **kw: Any) -> str:
        return "93.184.216.34"

    monkeypatch.setattr("kanban.workflows.attestation_gate.resolve_and_select_pinned_ip", mock_ip)

    # 1. Success
    class MockForgejoSuccess:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockForgejoSuccess:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json=[{"state": "success", "context": "ci/test"}],
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockForgejoSuccess)
    res_ok = await verify_live_ci_check_run(fj_url, head_sha)
    assert res_ok.verified is True
    assert res_ok.provider == "forgejo"

    # 2. Failure
    class MockForgejoFail:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockForgejoFail:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json=[{"state": "failure", "context": "ci/lint"}],
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockForgejoFail)
    res_fail = await verify_live_ci_check_run(fj_url, head_sha)
    assert res_fail.verified is False


@pytest.mark.asyncio
async def test_ci_check_run_ssrf_and_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-public IP or upstream HTTP errors fail closed."""
    head_sha = "0" * 40
    ci_url = "https://github.com/example/kanban/actions/runs/123"

    # 1. Non-public IP (SSRF blocked)
    async def mock_private_ip(host: str, **kw: Any) -> str:
        return "192.168.1.50"

    monkeypatch.setattr(
        "kanban.workflows.attestation_gate.resolve_and_select_pinned_ip", mock_private_ip
    )
    res_ssrf = await verify_live_ci_check_run(ci_url, head_sha)
    assert res_ssrf.verified is False
    assert res_ssrf.error_code == "SSRF_TARGET_BLOCKED"

    # 2. Upstream HTTP 500 error
    async def mock_public_ip(host: str, **kw: Any) -> str:
        return "140.82.121.4"

    monkeypatch.setattr(
        "kanban.workflows.attestation_gate.resolve_and_select_pinned_ip", mock_public_ip
    )

    class MockHttpErrorClient:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockHttpErrorClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(500, request=httpx.Request("GET", url))

    monkeypatch.setattr("httpx.AsyncClient", MockHttpErrorClient)
    res_http = await verify_live_ci_check_run(ci_url, head_sha)
    assert res_http.verified is False
    assert res_http.error_code == "CI_CHECK_RUN_FAILED"
    assert "HTTP 500" in str(res_http.error_detail)


def test_slsa_provenance_schema_boundary_cases() -> None:
    """SLSA provenance parser rejects malformed JSON, invalid DSSE types, and wrong schema types."""
    from kanban.workflows.attestation_gate import _pre_authentication_encoding

    # 1. Pre-authentication encoding test
    pae = _pre_authentication_encoding("application/json", b'{"key": "val"}')
    assert pae.startswith(b"DSSEv1 ")
    assert b"application/json" in pae

    # 2. Malformed JSON string
    res_malformed = verify_slsa_provenance("not json", "a" * 40)
    assert res_malformed.verified is False
    assert res_malformed.error_code == "SLSA_STATEMENT_INVALID"

    # 3. Bad DSSE payloadType
    bad_dsse = {"payloadType": "text/plain", "payload": "dGVzdA=="}
    res_pt = verify_slsa_provenance(bad_dsse, "a" * 40)
    assert res_pt.verified is False
    assert "Unsupported DSSE payloadType" in str(res_pt.error_detail)

    # 4. Bad base64 payload
    corrupted_b64 = {"payloadType": "application/vnd.in-toto+json", "payload": "not_base_64!!!"}
    res_b64 = verify_slsa_provenance(corrupted_b64, "a" * 40)
    assert res_b64.verified is False

    # 5. Wrong _type
    wrong_type = {
        "_type": "https://example.com/invalid",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [{"name": "pkg", "digest": {"sha1": "a" * 40}}],
    }
    res_type = verify_slsa_provenance(wrong_type, "a" * 40)
    assert res_type.verified is False
    assert "Statement _type must be" in str(res_type.error_detail)

    # 6. Unsupported predicateType
    wrong_pred = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://custom.dev/unknown",
        "subject": [{"name": "pkg", "digest": {"sha1": "a" * 40}}],
    }
    res_pred = verify_slsa_provenance(wrong_pred, "a" * 40)
    assert res_pred.verified is False
    assert "Unsupported predicateType" in str(res_pred.error_detail)

    # 7. Empty subject
    empty_subj = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [],
    }
    res_subj = verify_slsa_provenance(empty_subj, "a" * 40)
    assert res_subj.verified is False
    assert "subject array is missing or empty" in str(res_subj.error_detail)

    # 8. Malformed bytes payload
    res_bad_bytes = verify_slsa_provenance(b"\x00\xff invalid", "a" * 40)
    assert res_bad_bytes.verified is False
    assert res_bad_bytes.error_code == "SLSA_STATEMENT_INVALID"

    # 9. Valid bytes payload (JSON bytes DSSE envelope)
    valid_sha = "d" * 40
    valid_env = make_slsa_v1_envelope(valid_sha)
    env_bytes = json.dumps(valid_env).encode("utf-8")
    res_bytes_ok = verify_slsa_provenance(env_bytes, valid_sha)
    assert res_bytes_ok.verified is True
    assert res_bytes_ok.matched_digest == valid_sha


@pytest.mark.asyncio
async def test_ci_check_run_additional_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI check run handles sha mismatch on GitHub and general request exceptions."""
    head_sha = "1" * 40
    ci_url = "https://github.com/example/kanban/actions/runs/555"

    async def mock_ip(host: str, **kw: Any) -> str:
        return "140.82.121.4"

    monkeypatch.setattr("kanban.workflows.attestation_gate.resolve_and_select_pinned_ip", mock_ip)

    # 1. GitHub SHA mismatch
    class MockGhMismatch:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockGhMismatch:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "id": 555,
                    "head_sha": "2" * 40,
                    "status": "completed",
                    "conclusion": "success",
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr("httpx.AsyncClient", MockGhMismatch)
    res_mismatch = await verify_live_ci_check_run(ci_url, head_sha)
    assert res_mismatch.verified is False
    assert "does not match" in str(res_mismatch.error_detail)

    # 2. General exception during request
    class MockGhException:
        def __init__(self, *args: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> MockGhException:
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def aclose(self) -> None:
            pass

        async def get(self, url: str, **kw: Any) -> httpx.Response:
            raise httpx.ConnectError("Network unreachable")

    monkeypatch.setattr("httpx.AsyncClient", MockGhException)
    res_exc = await verify_live_ci_check_run(ci_url, head_sha)
    assert res_exc.verified is False
    assert res_exc.error_code == "CI_CHECK_RUN_FAILED"
    assert "Network unreachable" in str(res_exc.error_detail)
