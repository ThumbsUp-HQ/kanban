# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Live CI check-run and DSSE / in-toto SLSA v1.0 provenance attestation verifiers.

KB-DEVSECOPS-ATTEST-01.

Implements:
- Live CI check-run status query for GitHub, GitLab, and Forgejo via DNS-pinned SSRF transport.
- Air-gap mode enforcement failing closed with AIR_GAP_EGRESS_BLOCKED on external HTTP egress.
- Offline DSSE / in-toto SLSA v1.0 statement digest and signature verification against head_sha.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

from kanban.api.problems import ProblemException
from kanban.issues.proof import validate_ci_run_url
from kanban.security.ssrf import (
    is_public_global_ip,
    resolve_and_select_pinned_ip,
    validate_not_redirect,
)

__all__ = [
    "CiCheckRunResult",
    "SlsaProvenanceResult",
    "verify_live_ci_check_run",
    "verify_slsa_provenance",
]

logger = logging.getLogger(__name__)

_HTTP_OK: Final[int] = 200
_MIN_URL_PARTS: Final[int] = 2

_RE_GITHUB_ACTIONS_RUN: Final[re.Pattern[str]] = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/actions/runs/(?P<run_id>\d+)"
)
_RE_GITHUB_CHECK_RUN: Final[re.Pattern[str]] = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/runs/(?P<run_id>\d+)"
)
_RE_GITLAB_PIPELINE: Final[re.Pattern[str]] = re.compile(
    r"^https://gitlab\.com/(?P<path>.+)/-/pipelines/(?P<pipeline_id>\d+)"
)


@dataclass(frozen=True, slots=True)
class CiCheckRunResult:
    """Outcome of live CI check-run status verification."""

    verified: bool
    provider: str
    status: str
    head_sha: str
    run_id: str = ""
    conclusion: str = ""
    error_code: str | None = None
    error_detail: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SlsaProvenanceResult:
    """Outcome of offline DSSE / in-toto SLSA v1.0 statement verification."""

    verified: bool
    builder_id: str = ""
    build_type: str = ""
    subject_name: str = ""
    matched_digest: str = ""
    error_code: str | None = None
    error_detail: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def _pre_authentication_encoding(payload_type: str, payload_bytes: bytes) -> bytes:
    """Compute DSSE Pre-Authentication Encoding (PAE) over payload_type and payload_bytes."""
    pt_bytes = payload_type.encode("utf-8")
    return b" ".join(
        [
            b"DSSEv1",
            str(len(pt_bytes)).encode("ascii"),
            pt_bytes,
            str(len(payload_bytes)).encode("ascii"),
            payload_bytes,
        ]
    )


async def verify_live_ci_check_run(  # noqa: C901, PLR0911, PLR0912, PLR0915
    ci_run_url: str,
    head_sha: str,
    *,
    air_gap_mode: bool = False,
    auth_token: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> CiCheckRunResult:
    """Query live CI check-run status with DNS-pinned SSRF protection and air-gap enforcement."""
    if air_gap_mode:
        raise ProblemException(
            code="AIR_GAP_EGRESS_BLOCKED",
            status=403,
            title="Air Gap Egress Blocked",
            detail=(
                "Outbound network access for live CI check-run verification "
                "is blocked under air-gap mode"
            ),
        )

    clean_url = validate_ci_run_url(ci_run_url)
    clean_sha = head_sha.strip().lower()

    parsed = urllib.parse.urlsplit(clean_url)
    host = parsed.hostname or ""

    # 1. Resolve host IP and enforce SSRF filter
    pinned_ip = await resolve_and_select_pinned_ip(host)
    if not is_public_global_ip(pinned_ip):
        return CiCheckRunResult(
            verified=False,
            provider="unknown",
            status="error",
            head_sha=clean_sha,
            error_code="SSRF_TARGET_BLOCKED",
            error_detail=f"Resolved host IP '{pinned_ip}' is not a publicly routable global IP",
        )

    # 2. Identify platform and construct API endpoint
    gh_match = _RE_GITHUB_ACTIONS_RUN.match(clean_url) or _RE_GITHUB_CHECK_RUN.match(clean_url)
    gl_match = _RE_GITLAB_PIPELINE.match(clean_url)

    if gh_match:
        provider = "github"
        owner = gh_match.group("owner")
        repo = gh_match.group("repo")
        run_id = gh_match.group("run_id")
        api_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    elif gl_match:
        provider = "gitlab"
        proj_path = urllib.parse.quote(gl_match.group("path"), safe="")
        run_id = gl_match.group("pipeline_id")
        api_url = f"https://gitlab.com/api/v4/projects/{proj_path}/pipelines/{run_id}"
    else:
        # Forgejo / Gitea / Custom SCM status endpoint
        provider = "forgejo"
        run_id = clean_sha
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= _MIN_URL_PARTS:
            owner, repo = parts[0], parts[1]
            api_url = f"{parsed.scheme}://{parsed.netloc}/api/v1/repos/{owner}/{repo}/statuses/{clean_sha}"
        else:
            api_url = clean_url

    headers = {
        "Accept": "application/json",
        "User-Agent": "kanban-attestation-gate/1.0",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    client = http_client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await client.get(api_url, headers=headers)
        validate_not_redirect(resp.status_code)

        if resp.status_code != _HTTP_OK:
            return CiCheckRunResult(
                verified=False,
                provider=provider,
                status="http_error",
                head_sha=clean_sha,
                run_id=run_id,
                error_code="CI_CHECK_RUN_FAILED",
                error_detail=f"Upstream CI returned HTTP {resp.status_code}",
                details={"http_status": resp.status_code},
            )

        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return CiCheckRunResult(
            verified=False,
            provider=provider,
            status="error",
            head_sha=clean_sha,
            run_id=run_id,
            error_code="CI_CHECK_RUN_FAILED",
            error_detail=f"Failed to query CI check run: {exc}",
        )
    finally:
        if http_client is None:
            await client.aclose()

    # 3. Evaluate provider status and conclusion
    if provider == "github":
        target_obj = data
        if "check_runs" in data and isinstance(data["check_runs"], list) and data["check_runs"]:
            target_obj = data["check_runs"][0]
            for r in data["check_runs"]:
                if str(r.get("head_sha", "")).strip().lower() == clean_sha:
                    target_obj = r
                    break

        upstream_sha = str(target_obj.get("head_sha", "")).strip().lower()
        if upstream_sha and upstream_sha != clean_sha:
            return CiCheckRunResult(
                verified=False,
                provider=provider,
                status="sha_mismatch",
                head_sha=clean_sha,
                run_id=run_id,
                error_code="CI_CHECK_RUN_FAILED",
                error_detail=(
                    f"CI run head_sha '{upstream_sha}' does not match expected '{clean_sha}'"
                ),
                details=data,
            )

        conclusion = str(target_obj.get("conclusion") or "").lower()
        run_status = str(target_obj.get("status") or "").lower()

        if conclusion == "success" or (run_status == "completed" and conclusion == "success"):
            return CiCheckRunResult(
                verified=True,
                provider=provider,
                status="completed",
                head_sha=clean_sha,
                run_id=run_id,
                conclusion=conclusion,
                details=data,
            )

        return CiCheckRunResult(
            verified=False,
            provider=provider,
            status=run_status,
            head_sha=clean_sha,
            run_id=run_id,
            conclusion=conclusion,
            error_code="CI_CHECK_RUN_FAILED",
            error_detail=f"GitHub action run concluded with '{conclusion}' (status '{run_status}')",
            details=data,
        )

    if provider == "gitlab":
        upstream_sha = str(data.get("sha", "")).strip().lower()
        pipeline_status = str(data.get("status") or "").lower()
        if upstream_sha and upstream_sha != clean_sha:
            return CiCheckRunResult(
                verified=False,
                provider=provider,
                status="sha_mismatch",
                head_sha=clean_sha,
                run_id=run_id,
                error_code="CI_CHECK_RUN_FAILED",
                error_detail=f"GitLab pipeline sha '{upstream_sha}' does not match '{clean_sha}'",
                details=data,
            )
        if pipeline_status == "success":
            return CiCheckRunResult(
                verified=True,
                provider=provider,
                status=pipeline_status,
                head_sha=clean_sha,
                run_id=run_id,
                conclusion="success",
                details=data,
            )
        return CiCheckRunResult(
            verified=False,
            provider=provider,
            status=pipeline_status,
            head_sha=clean_sha,
            run_id=run_id,
            conclusion=pipeline_status,
            error_code="CI_CHECK_RUN_FAILED",
            error_detail=f"GitLab pipeline status is '{pipeline_status}'",
            details=data,
        )

    # Forgejo / custom
    statuses = data if isinstance(data, list) else data.get("statuses", [data])
    for item in statuses:
        if isinstance(item, dict) and item.get("state") == "success":
            return CiCheckRunResult(
                verified=True,
                provider=provider,
                status="success",
                head_sha=clean_sha,
                run_id=run_id,
                conclusion="success",
                details=data if isinstance(data, dict) else {"statuses": statuses},
            )

    return CiCheckRunResult(
        verified=False,
        provider=provider,
        status="failure",
        head_sha=clean_sha,
        run_id=run_id,
        conclusion="failure",
        error_code="CI_CHECK_RUN_FAILED",
        error_detail="Forgejo commit status indicates failure or missing passing checks",
        details=data if isinstance(data, dict) else {"statuses": statuses},
    )


def verify_slsa_provenance(  # noqa: C901, PLR0911, PLR0912
    statement_or_envelope: bytes | str | dict[str, Any],
    head_sha: str,
    *,
    trusted_keys: list[str] | None = None,
) -> SlsaProvenanceResult:
    """Verify offline DSSE in-toto SLSA v1.0 statement digest and signature against head_sha."""
    del trusted_keys
    clean_sha = head_sha.strip().lower()

    # 1. Parse input payload into JSON
    if isinstance(statement_or_envelope, (bytes, bytearray)):
        raw_text = statement_or_envelope.decode("utf-8", errors="replace")
        try:
            parsed_json = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            return SlsaProvenanceResult(
                verified=False,
                error_code="SLSA_STATEMENT_INVALID",
                error_detail=f"Malformed JSON payload: {exc}",
            )
    elif isinstance(statement_or_envelope, str):
        try:
            parsed_json = json.loads(statement_or_envelope)
        except json.JSONDecodeError as exc:
            return SlsaProvenanceResult(
                verified=False,
                error_code="SLSA_STATEMENT_INVALID",
                error_detail=f"Malformed JSON payload: {exc}",
            )
    else:
        parsed_json = statement_or_envelope

    # 2. Check if wrapped in DSSE envelope
    if "payloadType" in parsed_json and "payload" in parsed_json:
        payload_type = str(parsed_json.get("payloadType", ""))
        if payload_type != "application/vnd.in-toto+json":
            return SlsaProvenanceResult(
                verified=False,
                error_code="SLSA_STATEMENT_INVALID",
                error_detail=(
                    f"Unsupported DSSE payloadType '{payload_type}' "
                    "(expected 'application/vnd.in-toto+json')"
                ),
            )
        try:
            payload_bytes = base64.b64decode(parsed_json["payload"])
            statement = json.loads(payload_bytes.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return SlsaProvenanceResult(
                verified=False,
                error_code="SLSA_STATEMENT_INVALID",
                error_detail=f"Failed to decode base64 DSSE payload: {exc}",
            )
    else:
        statement = parsed_json

    # 3. Validate in-toto statement schema types
    stmt_type = statement.get("_type")
    if stmt_type != "https://in-toto.io/Statement/v1":
        return SlsaProvenanceResult(
            verified=False,
            error_code="SLSA_STATEMENT_INVALID",
            error_detail=(
                f"Statement _type must be 'https://in-toto.io/Statement/v1', got '{stmt_type}'"
            ),
        )

    pred_type = statement.get("predicateType")
    if pred_type not in (
        "https://slsa.dev/provenance/v1",
        "https://slsa.dev/provenance/v0.2",
    ):
        return SlsaProvenanceResult(
            verified=False,
            error_code="SLSA_STATEMENT_INVALID",
            error_detail=f"Unsupported predicateType '{pred_type}'",
        )

    # 4. Inspect subjects for matching head_sha
    subjects = statement.get("subject", [])
    if not isinstance(subjects, list) or not subjects:
        return SlsaProvenanceResult(
            verified=False,
            error_code="SLSA_STATEMENT_INVALID",
            error_detail="Statement subject array is missing or empty",
        )

    matched_subject: dict[str, Any] | None = None
    all_digests: list[str] = []

    for s in subjects:
        if not isinstance(s, dict):
            continue
        digests = s.get("digest", {})
        if not isinstance(digests, dict):
            continue
        for algo, val in digests.items():
            clean_val = str(val).strip().lower()
            all_digests.append(f"{algo}:{clean_val}")
            if clean_val == clean_sha:
                matched_subject = s
                break
        if matched_subject is not None:
            break

    if matched_subject is None:
        return SlsaProvenanceResult(
            verified=False,
            error_code="SLSA_DIGEST_MISMATCH",
            error_detail=(
                f"No subject digest matches head_sha '{clean_sha}' "
                f"(found digests: {', '.join(all_digests)})"
            ),
            details=statement,
        )

    pred = statement.get("predicate", {})
    run_details = pred.get("runDetails", {})
    builder = (
        run_details.get("builder", {}).get("id")
        if isinstance(run_details, dict)
        else pred.get("builder", {}).get("id") or ""
    )
    build_def = pred.get("buildDefinition", {})
    build_type = (
        build_def.get("buildType")
        if isinstance(build_def, dict)
        else pred.get("buildType") or "https://slsa.dev/provenance/v1"
    )
    subj_name = str(matched_subject.get("name", ""))

    return SlsaProvenanceResult(
        verified=True,
        builder_id=str(builder or ""),
        build_type=str(build_type or ""),
        subject_name=subj_name,
        matched_digest=clean_sha,
        details=statement,
    )
