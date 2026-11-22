# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""REST API router for inbound SCM webhooks (KB-DEVSECOPS-BUS-01)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from fastapi import APIRouter, Request, status
from sqlalchemy import text

from database.session import RLSContext, RLSSessionFactory
from kanban.api.problems import ProblemException
from kanban.api.timing import timing_floor
from kanban.security.envelope import KekProvider, SealedSecret, StaticKekProvider, open_bound

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/git", tags=["webhooks-scm"])

MAX_PAYLOAD_BYTES: Final[int] = 1_048_576  # 1 MiB limit
ENVELOPE_HEADER_SIZE: Final[int] = 2
KEY_RE: Final[re.Pattern[str]] = re.compile(r"\b([A-Z][A-Z0-9_]{1,15}-\d+)\b")


@dataclass(frozen=True)
class _WebhookProcessingContext:
    """Context holding tenant and binding identifiers for webhook execution."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    binding_id: uuid.UUID
    creator_id: uuid.UUID


def _get_kek(request: Request) -> KekProvider:
    """Retrieve KEK provider from app state or return fallback."""
    kek: KekProvider | None = getattr(request.app.state, "kek_provider", None)
    if kek is not None:
        return kek
    key_material = getattr(request.app.state, "key_material", None)
    if key_material is not None:
        fallback = StaticKekProvider(
            {key_material.master_kek_kid: key_material.master_kek},
            current=key_material.master_kek_kid,
        )
    else:
        fallback = StaticKekProvider({"kek-v1": b"k" * 32}, current="kek-v1")
    request.app.state.kek_provider = fallback
    return fallback


def _extract_delivery_id(provider: str, request: Request, raw_body: bytes) -> str:
    """Extract or derive unique delivery identifier from provider request headers."""
    headers = request.headers
    if provider == "github":
        delivery_id = headers.get("x-github-delivery")
    elif provider == "gitlab":
        delivery_id = headers.get("x-gitlab-event-uuid") or headers.get("x-gitlab-delivery")
    elif provider in ("forgejo", "gitea"):
        delivery_id = headers.get("x-forgejo-delivery") or headers.get("x-gitea-delivery")
    else:
        delivery_id = None

    if not delivery_id:
        delivery_id = headers.get("x-delivery-id")

    if not delivery_id:
        delivery_id = hashlib.sha256(raw_body).hexdigest()[:32]

    return delivery_id


def _extract_event_type(provider: str, request: Request) -> str:
    """Extract event type name from provider headers."""
    headers = request.headers
    if provider == "github":
        return headers.get("x-github-event", "unknown")
    if provider == "gitlab":
        return headers.get("x-gitlab-event", "unknown")
    if provider in ("forgejo", "gitea"):
        return headers.get("x-forgejo-event") or headers.get("x-gitea-event", "unknown")
    return "unknown"


def _verify_signature(
    provider: str,
    request: Request,
    raw_body: bytes,
    secret_bytes: bytes,
) -> None:
    """Verify cryptographic HMAC signature from Git forge provider."""
    headers = request.headers
    if provider == "github":
        header_sig = headers.get("x-hub-signature-256")
        if not header_sig:
            msg = "Missing X-Hub-Signature-256 header"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )
        computed = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(f"sha256={computed}", header_sig):
            msg = "X-Hub-Signature-256 verification failed"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )
    elif provider in ("forgejo", "gitea"):
        header_sig = headers.get("x-forgejo-signature") or headers.get("x-gitea-signature")
        if not header_sig:
            msg = "Missing X-Forgejo-Signature or X-Gitea-Signature header"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )
        computed = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
        clean_sig = header_sig.removeprefix("sha256=")
        if not hmac.compare_digest(computed, clean_sig):
            msg = "Forgejo signature verification failed"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )
    elif provider == "gitlab":
        header_token = headers.get("x-gitlab-token")
        if not header_token:
            msg = "Missing X-Gitlab-Token header"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )
        secret_str = secret_bytes.decode("utf-8", errors="replace").strip()
        if not hmac.compare_digest(secret_str, header_token.strip()):
            msg = "X-Gitlab-Token verification failed"
            raise ProblemException(
                code="INVALID_SIGNATURE",
                status=401,
                title="Invalid Signature",
                detail=msg,
            )


def _extract_repo_patterns(request: Request, payload: dict[str, Any]) -> list[str]:
    """Extract candidate repo URL patterns from query parameters and webhook payload."""
    repo_dict = payload.get("repository", {}) if isinstance(payload.get("repository"), dict) else {}
    patterns: list[str] = []
    repo_url_param = request.query_params.get("repo_url")
    if repo_url_param:
        patterns.append(repo_url_param)
    for field in ("clone_url", "html_url", "ssh_url", "full_name"):
        val = repo_dict.get(field)
        if val and isinstance(val, str):
            patterns.append(val)
    return patterns


async def _lookup_repo_binding(
    request: Request,
    payload: dict[str, Any],
    session_factory: RLSSessionFactory,
) -> dict[str, Any]:
    """Lookup repository binding row by binding_id or repository URL."""
    binding_id_str = request.query_params.get("binding_id")
    binding_row: dict[str, Any] | None = None

    anon_ctx = RLSContext(
        principal_id=uuid.UUID(int=0),
        workspace_id=uuid.UUID(int=0),
        token_scopes=("system",),
    )

    async with session_factory.session(anon_ctx) as lookup_session:
        if binding_id_str:
            try:
                b_uuid = uuid.UUID(binding_id_str)
                res = await lookup_session.execute(
                    text("SELECT * FROM get_repo_binding_for_webhook(:id)"),
                    {"id": b_uuid},
                )
                m_row = res.mappings().one_or_none()
                if m_row is not None:
                    binding_row = dict(m_row)
            except ValueError:
                pass

        if binding_row is None:
            patterns = _extract_repo_patterns(request, payload)
            for pattern in patterns:
                res = await lookup_session.execute(
                    text("SELECT * FROM find_repo_binding_by_url_for_webhook(:url)"),
                    {"url": pattern},
                )
                row = res.mappings().one_or_none()
                if row is not None:
                    binding_row = dict(row)
                    break

    if binding_row is None:
        msg = "No repository binding found for webhook"
        raise ProblemException(
            code="REPO_BINDING_NOT_FOUND",
            status=404,
            title="Repo Binding Not Found",
            detail=msg,
        )
    return dict(binding_row)


def _unseal_webhook_secret(binding_row: dict[str, Any], request: Request) -> bytes:
    """Unseal envelope-encrypted webhook secret for repository binding."""
    wrapped_secret = binding_row.get("wrapped_webhook_secret")
    secret_dek_kid = binding_row.get("webhook_secret_dek_kid")
    if wrapped_secret is None or secret_dek_kid is None:
        msg = "Repository binding does not have a webhook secret configured"
        raise ProblemException(
            code="WEBHOOK_SECRET_NOT_CONFIGURED",
            status=400,
            title="Webhook Secret Not Configured",
            detail=msg,
        )

    kek = _get_kek(request)
    binding_id = binding_row["id"]
    project_id = binding_row["project_id"]
    aad = f"kanban/repo-binding/v1|{binding_id}|{project_id}".encode()
    raw_s = bytes(wrapped_secret)
    if len(raw_s) > ENVELOPE_HEADER_SIZE:
        w_len = int.from_bytes(raw_s[:ENVELOPE_HEADER_SIZE], "big")
        w_dek = raw_s[ENVELOPE_HEADER_SIZE : ENVELOPE_HEADER_SIZE + w_len]
        s_blob = raw_s[ENVELOPE_HEADER_SIZE + w_len :]
        sealed = SealedSecret(
            encrypted_secret_blob=s_blob,
            wrapped_dek=w_dek,
            dek_kid=str(secret_dek_kid),
        )
        try:
            ba = open_bound(sealed, aad, kek)
            return bytes(ba)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to open webhook secret: %s", exc)
            return raw_s
    return raw_s


def _extract_pr_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract PR/MR artifacts from webhook payload."""
    pr_obj = payload.get("pull_request") or payload.get("merge_request")
    if not (pr_obj and isinstance(pr_obj, dict)):
        return []
    pr_title = pr_obj.get("title", "")
    pr_body = pr_obj.get("body") or pr_obj.get("description") or ""
    pr_head = pr_obj.get("head", {}) if isinstance(pr_obj.get("head"), dict) else {}
    pr_head_ref = pr_head.get("ref", "") or pr_obj.get("source_branch", "")
    keys = set(KEY_RE.findall(pr_title) + KEY_RE.findall(pr_body) + KEY_RE.findall(pr_head_ref))
    if not keys:
        return []
    ext_id = str(pr_obj.get("id") or pr_obj.get("number") or pr_obj.get("iid") or "")
    return [
        {
            "kind": "pull_request",
            "external_id": ext_id,
            "title": pr_title or f"PR #{ext_id}",
            "url": pr_obj.get("html_url") or pr_obj.get("url") or "",
            "state": pr_obj.get("state"),
            "head_sha": pr_head.get("sha") or pr_obj.get("sha"),
            "keys": keys,
            "link_kind": "IMPLEMENTED_IN_PR",
            "metadata": {"number": pr_obj.get("number") or pr_obj.get("iid")},
        }
    ]


def _extract_commit_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract commit artifacts from webhook payload."""
    commits = payload.get("commits", [])
    if not isinstance(commits, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for c in commits:
        if not isinstance(c, dict):
            continue
        msg = c.get("message", "")
        keys = set(KEY_RE.findall(msg))
        if keys:
            c_id = str(c.get("id") or c.get("sha") or "")
            first_line = msg.split("\n", 1)[0][:200]
            artifacts.append(
                {
                    "kind": "commit",
                    "external_id": c_id,
                    "title": first_line or f"Commit {c_id[:8]}",
                    "url": c.get("url") or "",
                    "state": "committed",
                    "head_sha": c_id,
                    "keys": keys,
                    "link_kind": "REFERENCED_BY_COMMIT",
                    "metadata": {"author": c.get("author")},
                }
            )
    return artifacts


def _extract_branch_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract branch ref artifacts from webhook payload."""
    ref = payload.get("ref", "")
    if not (ref and isinstance(ref, str) and ref.startswith("refs/heads/")):
        return []
    branch_name = ref.removeprefix("refs/heads/")
    branch_keys = set(KEY_RE.findall(branch_name))
    if not branch_keys:
        return []
    repo_dict = payload.get("repository", {}) if isinstance(payload.get("repository"), dict) else {}
    repo_url = repo_dict.get("html_url", "")
    return [
        {
            "kind": "branch",
            "external_id": branch_name,
            "title": branch_name,
            "url": f"{repo_url}/tree/{branch_name}" if repo_url else "",
            "state": "active",
            "head_sha": payload.get("after"),
            "keys": branch_keys,
            "link_kind": "TRACKED_ON_BRANCH",
            "metadata": {"ref": ref},
        }
    ]


def _extract_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract all relevant Git artifacts referencing issue keys."""
    artifacts: list[dict[str, Any]] = []
    artifacts.extend(_extract_pr_artifacts(payload))
    artifacts.extend(_extract_commit_artifacts(payload))
    artifacts.extend(_extract_branch_artifacts(payload))
    return artifacts


async def _upsert_scm_artifact(
    session: AsyncSession,
    ctx: _WebhookProcessingContext,
    art: dict[str, Any],
) -> uuid.UUID:
    """Upsert SCM artifact record and return its object_id."""
    art_res = await session.execute(
        text(
            "SELECT id, object_id FROM scm_artifacts "
            "WHERE repo_binding_id = :repo_id AND artifact_kind = :kind AND external_id = :ext_id"
        ),
        {
            "repo_id": ctx.binding_id,
            "kind": art["kind"],
            "ext_id": art["external_id"],
        },
    )
    art_row = art_res.mappings().one_or_none()
    meta_json = json.dumps(art["metadata"])

    if art_row is not None:
        art_id = uuid.UUID(str(art_row["id"]))
        art_obj_id = uuid.UUID(str(art_row["object_id"])) if art_row["object_id"] else art_id
        await session.execute(
            text(
                "UPDATE scm_artifacts SET "
                "  title = :title, url = :url, state = :state, "
                "  head_sha = :sha, metadata_json = CAST(:meta AS jsonb) "
                "WHERE id = :id"
            ),
            {
                "id": art_id,
                "title": art["title"],
                "url": art["url"],
                "state": art.get("state"),
                "sha": art.get("head_sha"),
                "meta": meta_json,
            },
        )
        return art_obj_id

    art_id = uuid.uuid4()
    art_ckey = f"scm:{ctx.binding_id}:{art['kind']}:{art['external_id']}"
    await session.execute(
        text(
            "SELECT register_object("
            "  CAST('scm_artifact' AS object_kind), :ws, :proj, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "ckey": art_ckey,
            "title": art["title"][:255],
            "creator": ctx.creator_id,
            "id": art_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO scm_artifacts ("
            "  id, object_id, workspace_id, project_id, repo_binding_id, "
            "  artifact_kind, external_id, title, url, state, head_sha, metadata_json"
            ") VALUES ("
            "  :id, :obj_id, :ws, :proj, :repo, :kind, :ext, :title, :url, :state, "
            "  :sha, CAST(:meta AS jsonb)"
            ")"
        ),
        {
            "id": art_id,
            "obj_id": art_id,
            "ws": ctx.workspace_id,
            "proj": ctx.project_id,
            "repo": ctx.binding_id,
            "kind": art["kind"],
            "ext": art["external_id"],
            "title": art["title"],
            "url": art["url"],
            "state": art.get("state"),
            "sha": art.get("head_sha"),
            "meta": meta_json,
        },
    )
    return art_id


async def _link_issue_to_artifact(
    session: AsyncSession,
    ctx: _WebhookProcessingContext,
    issue_info: tuple[uuid.UUID, str],
    art_obj_id: uuid.UUID,
    art: dict[str, Any],
) -> bool:
    """Create object_link between issue and artifact if not already exists."""
    issue_id, issue_key = issue_info
    link_kind = str(art["link_kind"])
    art_title = str(art["title"])[:255]

    link_exists = await session.scalar(
        text(
            "SELECT 1 FROM object_links "
            "WHERE source_id = :src AND target_id = :tgt AND link_type = CAST(:ltype AS link_kind)"
        ),
        {
            "src": issue_id,
            "tgt": art_obj_id,
            "ltype": link_kind,
        },
    )
    if link_exists:
        return False

    await session.execute(
        text(
            "INSERT INTO object_links ("
            "  id, workspace_id, source_id, source_type, target_id, target_type, "
            "  link_type, link_state, source_key_snapshot, target_key_snapshot, created_by_id"
            ") VALUES ("
            "  uuidv7(), :ws, :src, CAST('issue' AS object_kind), :tgt, "
            "  CAST('scm_artifact' AS object_kind), CAST(:ltype AS link_kind), "
            "  'ACTIVE', :s_key, :t_key, :creator"
            ")"
        ),
        {
            "ws": ctx.workspace_id,
            "src": issue_id,
            "tgt": art_obj_id,
            "ltype": link_kind,
            "s_key": issue_key,
            "t_key": art_title,
            "creator": ctx.creator_id,
        },
    )
    return True


async def _process_artifacts_and_links(
    session: AsyncSession,
    ctx: _WebhookProcessingContext,
    artifacts: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    """Process all extracted artifacts and link them to matching issues."""
    links_created = 0
    all_linked_keys: list[str] = []

    for art in artifacts:
        for k in art["keys"]:
            try:
                seq_num = int(k.split("-")[-1])
            except ValueError:
                continue

            issue_res = await session.execute(
                text(
                    "SELECT i.id, i.sequence_id, o.canonical_key "
                    "FROM issues i "
                    "JOIN objects o ON o.id = i.id "
                    "WHERE i.project_id = :proj_id AND i.sequence_id = :seq"
                ),
                {"proj_id": ctx.project_id, "seq": seq_num},
            )
            issue_row = issue_res.mappings().one_or_none()
            if issue_row is None:
                continue

            issue_id = uuid.UUID(str(issue_row["id"]))
            issue_key = str(issue_row["canonical_key"] or k)

            art_obj_id = await _upsert_scm_artifact(session, ctx, art)

            created = await _link_issue_to_artifact(
                session,
                ctx,
                (issue_id, issue_key),
                art_obj_id,
                art,
            )
            if created:
                links_created += 1
                all_linked_keys.append(issue_key)

    return links_created, all_linked_keys


def _validate_payload_size(request: Request, raw_body: bytes) -> None:
    """Validate request content-length and body size within MAX_PAYLOAD_BYTES."""
    cl_header = request.headers.get("content-length")
    if cl_header:
        try:
            if int(cl_header) > MAX_PAYLOAD_BYTES:
                msg = f"Payload exceeds limit of {MAX_PAYLOAD_BYTES} bytes"
                raise ProblemException(
                    code="PAYLOAD_TOO_LARGE",
                    status=413,
                    title="Payload Too Large",
                    detail=msg,
                )
        except ValueError:
            pass

    if len(raw_body) > MAX_PAYLOAD_BYTES:
        msg = f"Payload exceeds limit of {MAX_PAYLOAD_BYTES} bytes"
        raise ProblemException(
            code="PAYLOAD_TOO_LARGE",
            status=413,
            title="Payload Too Large",
            detail=msg,
        )


@router.post(
    "/{provider}",
    status_code=status.HTTP_200_OK,
    summary="Receive inbound Git forge webhook",
)
async def receive_scm_webhook(
    provider: str,
    request: Request,
) -> dict[str, Any]:
    """Process inbound webhook from GitHub, GitLab, or Forgejo."""
    async with timing_floor(floor_ms=25.0):
        provider_norm = provider.lower()
        if provider_norm not in ("github", "gitlab", "forgejo", "gitea"):
            msg = f"Unsupported SCM webhook provider: {provider}"
            raise ProblemException(
                code="UNSUPPORTED_PROVIDER",
                status=400,
                title="Unsupported Provider",
                detail=msg,
            )
        canonical_provider = "forgejo" if provider_norm == "gitea" else provider_norm

        raw_body = await request.body()
        _validate_payload_size(request, raw_body)

        delivery_id = _extract_delivery_id(canonical_provider, request, raw_body)
        event_type = _extract_event_type(canonical_provider, request)

        try:
            payload: dict[str, Any] = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception as exc:
            msg = "Failed to parse request JSON payload"
            raise ProblemException(
                code="INVALID_JSON",
                status=400,
                title="Invalid JSON",
                detail=msg,
            ) from exc

        session_factory: RLSSessionFactory | None = getattr(
            request.app.state, "session_factory", None
        )
        if session_factory is None:
            err_msg = "RLSSessionFactory not configured on app.state"
            raise RuntimeError(err_msg)

        # 1. Lookup binding & unseal secret
        binding_row = await _lookup_repo_binding(request, payload, session_factory)
        binding_id = uuid.UUID(str(binding_row["id"]))
        workspace_id = uuid.UUID(str(binding_row["workspace_id"]))
        project_id = uuid.UUID(str(binding_row["project_id"]))
        creator_id = uuid.UUID(str(binding_row["created_by"]))

        secret_bytes = _unseal_webhook_secret(binding_row, request)
        _verify_signature(canonical_provider, request, raw_body, secret_bytes)

        # 2. Replay deduplication
        proc_ctx = RLSContext(
            principal_id=creator_id,
            workspace_id=workspace_id,
            token_scopes=("system", "webhook"),
        )
        async with session_factory.session(proc_ctx) as dedup_session:
            res_dedup = await dedup_session.execute(
                text(
                    "SELECT 1 FROM scm_webhook_deliveries "
                    "WHERE repo_binding_id = :repo_id AND delivery_id = :del_id"
                ),
                {"repo_id": binding_id, "del_id": delivery_id},
            )
            if res_dedup.scalar_one_or_none() is not None:
                return {
                    "status": "duplicate_ignored",
                    "delivery_id": delivery_id,
                    "message": "Delivery already processed",
                }

        # 3. Extract artifacts & apply DB changes
        artifacts = _extract_artifacts(payload)
        sha256_hash = hashlib.sha256(raw_body).hexdigest()

        async with session_factory.session(proc_ctx) as proc_session:
            await proc_session.execute(
                text(
                    "INSERT INTO scm_webhook_deliveries ("
                    "  id, workspace_id, repo_binding_id, provider, "
                    "  delivery_id, event_type, payload_sha256"
                    ") VALUES (:id, :ws, :repo, :prov, :del_id, :event, :sha)"
                ),
                {
                    "id": uuid.uuid4(),
                    "ws": workspace_id,
                    "repo": binding_id,
                    "prov": canonical_provider,
                    "del_id": delivery_id,
                    "event": event_type,
                    "sha": sha256_hash,
                },
            )

            proc_ctx_obj = _WebhookProcessingContext(
                workspace_id=workspace_id,
                project_id=project_id,
                binding_id=binding_id,
                creator_id=creator_id,
            )
            links_count, linked_keys = await _process_artifacts_and_links(
                proc_session,
                proc_ctx_obj,
                artifacts,
            )

        return {
            "status": "ok",
            "provider": canonical_provider,
            "delivery_id": delivery_id,
            "links_created": links_count,
            "issues_linked": linked_keys,
        }
