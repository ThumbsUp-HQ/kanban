# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Integration and unit tests for KAN-20 Synaptic Object-Graph Semantic Search."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import asyncpg  # type: ignore[import-untyped]
import numpy as np
import pytest
from sqlalchemy import text

from kanban.api.deps import PrincipalContext
from kanban.api.v1.schemas.search import (
    IssueSearchRequest,
    KnowledgeSearchRequest,
)
from kanban.services.search import (
    search_issues,
    search_knowledge,
    search_unified,
)
from kanban.services.synaptic_rescorer import (
    MatryoshkaQuantizer,
    SynapticSeed,
    _compute_recency_decay,
    extract_heading_anchors,
    spread_synaptic_activation,
)
from kanban.tests.security.helpers import rebuild_era

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from kanban.tests.api.conftest import ApiEnv, SeededUser

pytestmark = pytest.mark.committed_db


async def _seed_issue(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    ident: str,
    seq: int,
    summary: str,
    desc: str,
    user_id: uuid.UUID,
    state_id: uuid.UUID,
    pri_id: uuid.UUID,
) -> uuid.UUID:
    """Register and insert an issue row."""
    iss_id = uuid.uuid4()
    await session.execute(
        text(
            "UPDATE projects SET issue_seq_counter = GREATEST(issue_seq_counter, :seq) "
            "WHERE id = :p"
        ),
        {"p": proj_id, "seq": seq},
    )
    await session.execute(
        text("SELECT register_object('issue'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": f"{ident}-{seq}",
            "title": summary,
            "cr": user_id,
            "id": iss_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO issues (id, object_type, workspace_id, project_id, sequence_id, summary, "
            "description_markdown, state_id, priority_id, created_by_id, original_created_by_id, "
            "board_rank, ancestry_path) "
            "VALUES (:id, 'issue', :ws, :proj, :seq, :summary, :desc, :st, :pri, :cr, :cr, "
            "'a0', 'top')"
        ),
        {
            "id": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "seq": seq,
            "summary": summary,
            "desc": desc,
            "st": state_id,
            "pri": pri_id,
            "cr": user_id,
        },
    )
    return iss_id


async def _seed_doc(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    proj_id: uuid.UUID,
    key: str,
    title: str,
    content: str,
    user_id: uuid.UUID,
) -> uuid.UUID:
    """Register and insert a doc row."""
    doc_id = uuid.uuid4()
    await session.execute(
        text("SELECT register_object('doc'::object_kind, :ws, :proj, :ckey, :title, :cr, :id)"),
        {
            "ws": ws_id,
            "proj": proj_id,
            "ckey": key,
            "title": title,
            "cr": user_id,
            "id": doc_id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO docs (id, object_type, workspace_id, project_id, title, "
            "body_markdown, hierarchy_path) "
            "VALUES (:id, 'doc', :ws, :proj, :title, :content, 'top')"
        ),
        {
            "id": doc_id,
            "ws": ws_id,
            "proj": proj_id,
            "title": title,
            "content": content,
        },
    )
    return doc_id


async def _link_objects(  # noqa: PLR0913, PLR0917
    session: AsyncSession,
    ws_id: uuid.UUID,
    src_id: uuid.UUID,
    src_type: str,
    target_id: uuid.UUID,
    target_type: str,
    link_type: str,
    user_id: uuid.UUID,
) -> None:
    """Create an active typed object link with proper source and target types."""
    await session.execute(
        text(
            "INSERT INTO object_links (id, workspace_id, source_id, source_type, "
            "target_id, target_type, link_type, link_state, source_key_snapshot, "
            "target_key_snapshot, created_by_id) "
            "VALUES (:id, :ws, :src, CAST(:st AS object_kind), :tgt, CAST(:tt AS object_kind), "
            "CAST(:lt AS link_kind), 'ACTIVE', '', '', :cr)"
        ),
        {
            "id": uuid.uuid4(),
            "ws": ws_id,
            "src": src_id,
            "st": src_type,
            "tgt": target_id,
            "tt": target_type,
            "lt": link_type,
            "cr": user_id,
        },
    )


async def test_hybrid_search_unindexed_graceful_degradation(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Graceful degradation: unindexed embeddings fall back cleanly to executed_mode='lexical'."""
    admin = await make_user("admin_degrade", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("DEG", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    ws_id = api_env.workspace_id

    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "DEG",
        1,
        "Lexical fallback verification issue zygote",
        "This contains rare token zygote for lexical matching.",
        admin.id,
        st_id,
        pri_id,
    )
    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    caller = PrincipalContext(principal_id=admin.id, workspace_id=ws_id)

    # Calling search_unified with mode="hybrid" when embeddings table has no rows
    res = await search_unified(api_env.seed, caller, query="zygote", mode="hybrid")

    assert res.total >= 1
    # Fallback cleanly degrades to lexical
    assert res.executed_mode == "lexical"
    assert res.items[0].match_reason == "Lexical match"


async def test_hybrid_search_with_embeddings_and_rrf(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Hybrid search fuses FTS, trigram, and vector HNSW candidates with match_reason provenance."""
    admin = await make_user("admin_hybrid", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("HYB", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    ws_id = api_env.workspace_id

    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    iss_id = await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "HYB",
        42,
        "Zero-Egress Synaptic Search Engine",
        "Architecture for local onnx embeddings and matryoshka head projection.",
        admin.id,
        st_id,
        pri_id,
    )

    # Insert deterministic test embedding vector into object_embeddings
    test_vec = [0.0] * 384
    test_vec[0] = 1.0  # Unit vector along dimension 0
    sha_bytes = hashlib.sha256(b"HYB-42").digest()
    await api_env.seed.execute(
        text(
            "INSERT INTO object_embeddings (object_id, object_type, chunk_index, "
            "workspace_id, project_id, content_sha256, model_id, embedding) "
            "VALUES (:oid, 'issue', 0, :ws, :proj, :sha, 'fixture-bge-small-en-v1.5', :emb)"
        ),
        {
            "oid": iss_id,
            "ws": ws_id,
            "proj": proj_id,
            "sha": sha_bytes,
            "emb": str(test_vec),
        },
    )
    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    caller = PrincipalContext(principal_id=admin.id, workspace_id=ws_id)

    res = await search_unified(api_env.seed, caller, query="HYB-42 synaptic search", mode="hybrid")

    assert res.total >= 1
    assert res.items[0].key == "HYB-42"
    assert res.items[0].match_reason in ("Semantic match", "Lexical match")
    assert res.executed_mode in ("hybrid", "lexical")


async def test_2hop_synaptic_activation_spreading(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """2-hop Synaptic Activation Spreading across VERIFIED_BY_DOC and BLOCKS."""
    admin = await make_user("admin_synaptic", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SYN", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    ws_id = api_env.workspace_id

    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    # Seed 3 objects: Seed Issue -> Doc (Hop 1) -> Target Issue (Hop 2)
    seed_issue_id = await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "SYN",
        10,
        "Origin Seed Issue",
        "The root issue providing the initial synaptic impulse.",
        admin.id,
        st_id,
        pri_id,
    )

    doc_id = await _seed_doc(
        api_env.seed,
        ws_id,
        proj_id,
        "docs/spec/synaptic-proof",
        "Synaptic Architecture Proof Doc",
        "Document explaining the verification graph.",
        admin.id,
    )

    target_issue_id = await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "SYN",
        11,
        "Downstream Blocked Issue",
        "Issue blocked by the verification doc.",
        admin.id,
        st_id,
        pri_id,
    )

    # Link: Seed Issue -> Target Issue via BLOCKS (weight 0.75)
    await _link_objects(
        api_env.seed, ws_id, seed_issue_id, "issue", target_issue_id, "issue", "BLOCKS", admin.id
    )

    # Link: Target Issue -> Doc via VERIFIED_BY_DOC (weight 0.85)
    await _link_objects(
        api_env.seed, ws_id, target_issue_id, "issue", doc_id, "doc", "VERIFIED_BY_DOC", admin.id
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    caller = PrincipalContext(principal_id=admin.id, workspace_id=ws_id)

    seeds = [
        SynapticSeed(
            object_id=seed_issue_id,
            object_type="issue",
            score=10.0,
            key="SYN-10",
            title="Origin Seed Issue",
            had_semantic_match=True,
            had_lexical_match=True,
        )
    ]

    spreading_results = await spread_synaptic_activation(
        session=api_env.seed,
        caller=caller,
        seeds=seeds,
        workspace_id=ws_id,
        max_hops=2,
    )

    # Verify seed entity is present at hop 0
    assert seed_issue_id in spreading_results
    assert spreading_results[seed_issue_id].hop_distance == 0

    # Verify 1-hop neighbor (Target Issue) was activated via BLOCKS
    assert target_issue_id in spreading_results
    tgt_activation = spreading_results[target_issue_id]
    assert tgt_activation.hop_distance == 1
    assert tgt_activation.via_link_type == "BLOCKS"
    assert "Linked via BLOCKS to SYN-10" in tgt_activation.match_reason
    assert tgt_activation.activation_score > 0.0

    # Verify 2-hop neighbor (Doc) was activated via VERIFIED_BY_DOC
    assert doc_id in spreading_results
    doc_activation = spreading_results[doc_id]
    assert doc_activation.hop_distance == 2
    assert doc_activation.via_link_type == "VERIFIED_BY_DOC"
    assert "Linked via VERIFIED_BY_DOC to" in doc_activation.match_reason
    assert doc_activation.activation_score > 0.0


async def test_synaptic_zero_oracle_leakage(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Zero Oracle Leakage Invariant: Unauthorized or explicit DENY neighbors contribute 0.0."""
    admin = await make_user("admin_oracle", workspace_role="WORKSPACE_ADMIN")
    restricted_user = await make_user("guest_user", workspace_role="WORKSPACE_MEMBER")

    proj_public = await make_project(
        "PUB",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN", restricted_user: "MEMBER"},
    )
    proj_secret = await make_project(
        "SEC",
        created_by=admin,
        roles={admin: "PROJECT_ADMIN"},  # restricted_user has NO access
    )
    ws_id = api_env.workspace_id

    st_pub = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_public}
        )
    ).scalar_one()
    pri_pub = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"),
            {"p": proj_public},
        )
    ).scalar_one()

    public_issue_id = await _seed_issue(
        api_env.seed,
        ws_id,
        proj_public,
        "PUB",
        1,
        "Public Publicly Visible Issue",
        "Everyone in workspace can view this public issue.",
        admin.id,
        st_pub,
        pri_pub,
    )

    secret_doc_id = await _seed_doc(
        api_env.seed,
        ws_id,
        proj_secret,
        "docs/secret/vault-creds",
        "Top Secret Master Encryption Keys",
        "Zero access allowed to unprivileged members.",
        admin.id,
    )

    # Link Public Issue -> Secret Doc via VERIFIED_BY_DOC
    await _link_objects(
        api_env.seed,
        ws_id,
        public_issue_id,
        "issue",
        secret_doc_id,
        "doc",
        "VERIFIED_BY_DOC",
        admin.id,
    )

    # Add explicit DENY ACL entry for restricted_user on secret_doc_id (Zero Oracle Leakage check)
    await api_env.seed.execute(
        text(
            "INSERT INTO resource_acl_entries "
            "(workspace_id, object_id, principal_id, effect, capability_mask) "
            "VALUES (:ws, :doc, :u, 'DENY', 255)"
        ),
        {"ws": ws_id, "doc": secret_doc_id, "u": restricted_user.id},
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    # Calling spread_synaptic_activation as restricted_user
    caller_restricted = PrincipalContext(principal_id=restricted_user.id, workspace_id=ws_id)

    seeds = [
        SynapticSeed(
            object_id=public_issue_id,
            object_type="issue",
            score=5.0,
            key="PUB-1",
            title="Public Visible Issue",
            had_semantic_match=True,
            had_lexical_match=True,
        )
    ]

    spreading_results = await spread_synaptic_activation(
        session=api_env.seed,
        caller=caller_restricted,
        seeds=seeds,
        workspace_id=ws_id,
        max_hops=2,
    )

    # Public issue is accessible to caller
    assert public_issue_id in spreading_results

    # Secret doc must NOT be in spreading results at all! (0.0 score, zero leakage)
    assert secret_doc_id not in spreading_results

    # And search_unified executed as restricted_user must never reveal secret doc
    res = await search_unified(api_env.seed, caller_restricted, query="PUB-1", mode="hybrid")
    returned_ids = [item.id for item in res.items]
    assert secret_doc_id not in returned_ids
    for it in res.items:
        if it.match_reason:
            assert "vault-creds" not in it.match_reason
            assert "Top Secret" not in it.match_reason


async def test_hybrid_search_issues_and_knowledge_endpoints(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Endpoints search_issues and search_knowledge preserve mode='hybrid'."""
    admin = await make_user("admin_sub_search", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("SUB", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    ws_id = api_env.workspace_id

    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "SUB",
        5,
        "Micro-Service Issue Title",
        "Body content for search_issues test.",
        admin.id,
        st_id,
        pri_id,
    )

    await _seed_doc(
        api_env.seed,
        ws_id,
        proj_id,
        "docs/sub/guide",
        "Micro-Service Architecture Guide",
        "Body content for search_knowledge test.",
        admin.id,
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    caller = PrincipalContext(principal_id=admin.id, workspace_id=ws_id)

    # search_issues with hybrid mode
    issue_req = IssueSearchRequest(query="SUB-5 Micro-Service", mode="hybrid")
    issue_resp = await search_issues(api_env.seed, caller, issue_req)
    assert issue_resp.total >= 1
    assert issue_resp.items[0].key == "SUB-5"
    assert issue_resp.items[0].match_reason is not None

    # search_knowledge with hybrid mode
    know_req = KnowledgeSearchRequest(query="Architecture Guide", mode="hybrid")
    know_resp = await search_knowledge(api_env.seed, caller, know_req)
    assert know_resp.total >= 1
    assert know_resp.items[0].title == "Micro-Service Architecture Guide"
    assert know_resp.items[0].match_reason is not None


async def test_synaptic_recency_decay(
    api_env: ApiEnv,
    make_user: Callable[..., Awaitable[SeededUser]],
    make_project: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Synaptic spreading exponentially attenuates activation from older neighbor objects."""
    admin = await make_user("admin_decay", workspace_role="WORKSPACE_ADMIN")
    proj_id = await make_project("DCY", created_by=admin, roles={admin: "PROJECT_ADMIN"})
    ws_id = api_env.workspace_id

    st_id = (
        await api_env.seed.execute(
            text("SELECT id FROM workflow_states WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()
    pri_id = (
        await api_env.seed.execute(
            text("SELECT id FROM project_priorities WHERE project_id = :p LIMIT 1"), {"p": proj_id}
        )
    ).scalar_one()

    seed_id = await _seed_issue(
        api_env.seed,
        ws_id,
        proj_id,
        "DCY",
        1,
        "Decay Seed Issue",
        "Seed description",
        admin.id,
        st_id,
        pri_id,
    )

    # Fresh doc (created now)
    fresh_doc_id = await _seed_doc(
        api_env.seed,
        ws_id,
        proj_id,
        "docs/dcy/fresh",
        "Fresh Documentation",
        "Recently created content",
        admin.id,
    )

    # Old doc (simulate created 60 days ago)
    old_doc_id = await _seed_doc(
        api_env.seed,
        ws_id,
        proj_id,
        "docs/dcy/old",
        "Old Documentation",
        "Content from sixty days ago",
        admin.id,
    )
    # 1. Verify mathematical 30-day half-life recency decay function directly
    now = dt.datetime.now(dt.UTC)
    decay_0d = _compute_recency_decay(now)
    decay_30d = _compute_recency_decay(now - dt.timedelta(days=30))
    decay_60d = _compute_recency_decay(now - dt.timedelta(days=60))
    assert math.isclose(decay_0d, 1.0, rel_tol=1e-3)
    assert math.isclose(decay_30d, 0.5, rel_tol=1e-3)
    assert math.isclose(decay_60d, 0.25, rel_tol=1e-3)

    # Link both with identical link type
    await _link_objects(
        api_env.seed, ws_id, seed_id, "issue", fresh_doc_id, "doc", "VERIFIED_BY_DOC", admin.id
    )
    await _link_objects(
        api_env.seed, ws_id, seed_id, "issue", old_doc_id, "doc", "VERIFIED_BY_DOC", admin.id
    )

    await rebuild_era(api_env.seed, ws_id)
    await api_env.seed.commit()

    caller = PrincipalContext(principal_id=admin.id, workspace_id=ws_id)
    seeds = [
        SynapticSeed(
            object_id=seed_id,
            object_type="issue",
            score=10.0,
            key="DCY-1",
            title="Decay Seed",
            had_semantic_match=True,
            had_lexical_match=True,
        )
    ]

    # Mock recency decay to simulate fresh doc receiving 1.0 and old doc receiving 0.25
    with patch(
        "kanban.services.synaptic_rescorer._compute_recency_decay",
        side_effect=[1.0, 0.25],
    ):
        res = await spread_synaptic_activation(
            session=api_env.seed,
            caller=caller,
            seeds=seeds,
            workspace_id=ws_id,
            max_hops=1,
        )

    assert fresh_doc_id in res
    assert old_doc_id in res
    # Fresh doc must have higher activation than 60-day old doc due to exponential half-life decay
    assert res[fresh_doc_id].activation_score > res[old_doc_id].activation_score


async def test_synaptic_rescorer_edge_cases(api_env: ApiEnv) -> None:
    """Cover edge cases in synaptic activation spreading and recency decay."""
    # None updated_at defaults to 0.5 decay
    assert _compute_recency_decay(None) == 0.5

    # Naive datetime without tzinfo
    naive_dt = dt.datetime(2026, 1, 1, 12, 0, 0)  # noqa: DTZ001
    decay_naive = _compute_recency_decay(naive_dt)
    assert 0.1 <= decay_naive <= 1.0

    # Empty seeds list returns empty dict
    dummy_caller = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=api_env.workspace_id)
    empty_res = await spread_synaptic_activation(
        session=api_env.seed,
        caller=dummy_caller,
        seeds=[],
        workspace_id=api_env.workspace_id,
        max_hops=2,
    )
    assert empty_res == {}

    # Seed with lexical match only
    u_id = uuid.uuid4()
    lex_seed = SynapticSeed(
        object_id=u_id,
        object_type="issue",
        score=5.0,
        key="LEX-1",
        title="Lexical Only",
        had_semantic_match=False,
        had_lexical_match=True,
    )
    lex_res = await spread_synaptic_activation(
        session=api_env.seed,
        caller=dummy_caller,
        seeds=[lex_seed],
        workspace_id=api_env.workspace_id,
        max_hops=0,
    )
    assert u_id in lex_res
    assert lex_res[u_id].match_reason == "Lexical match"


async def test_synaptic_statement_timeout_graceful_degradation(api_env: ApiEnv) -> None:
    """Verify statement_timeout or DB errors inside spreading degrade gracefully."""
    ws_id = api_env.workspace_id
    caller = PrincipalContext(principal_id=uuid.uuid4(), workspace_id=ws_id)
    u_id = uuid.uuid4()
    seed = SynapticSeed(
        object_id=u_id,
        object_type="issue",
        score=7.5,
        key="TO-1",
        title="Timeout Test",
        had_semantic_match=True,
        had_lexical_match=True,
    )

    orig_execute = api_env.seed.execute

    async def _failing_execute(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if args and "FROM object_links ol" in str(args[0]):
            msg = "canceling statement due to statement timeout"
            raise asyncpg.exceptions.QueryCanceledError(msg)
        return await orig_execute(*args, **kwargs)

    with patch.object(api_env.seed, "execute", side_effect=_failing_execute):
        res = await spread_synaptic_activation(
            session=api_env.seed,
            caller=caller,
            seeds=[seed],
            workspace_id=ws_id,
            max_hops=2,
        )

    assert u_id in res
    assert res[u_id].activation_score == 7.5


def test_synaptic_quantizer_and_maxsim_units() -> None:
    """Exercise MatryoshkaQuantizer and maxsim helpers in synaptic_rescorer."""
    vec = [0.1 * i for i in range(128)]
    head = MatryoshkaQuantizer.extract_head(vec, dim=64)
    assert len(head) == 64
    zero_head = MatryoshkaQuantizer.extract_head([0.0] * 64, dim=64)
    assert zero_head == [0.0] * 64

    sign = MatryoshkaQuantizer.binary_sign(vec, dim=64)
    assert len(sign) == 8
    short_sign = MatryoshkaQuantizer.binary_sign([0.5, -0.5], dim=16)
    assert len(short_sign) == 2

    q8, scale = MatryoshkaQuantizer.quantize(vec)
    assert len(q8) == 128
    assert scale > 0.0

    empty_q8, empty_scale = MatryoshkaQuantizer.quantize([])
    assert empty_q8 == b""
    assert empty_scale == 1.0

    deq = MatryoshkaQuantizer.dequantize(q8, scale)
    assert len(deq) == 128

    deq_np = MatryoshkaQuantizer.dequantize(np.array([1, 2, 3], dtype=np.int8), 1.0)
    assert len(deq_np) == 3

    dp = MatryoshkaQuantizer.dot_product(q8, scale, q8, scale)
    assert dp > 0.0
    assert MatryoshkaQuantizer.dot_product(b"", 1.0, q8, scale) == 0.0

    boost1 = MatryoshkaQuantizer.maxsim_boost("KEY-1", "Some title", identifier="KEY-1")
    assert boost1 >= 10.0
    boost_empty = MatryoshkaQuantizer.maxsim_boost("", "title")
    assert boost_empty == 0.0
    assert MatryoshkaQuantizer.maxsim_boost("x", "title") == 0.0
    assert MatryoshkaQuantizer.maxsim_boost("hello", "x", headings=["y"]) == 0.0
    boost_nomatch = MatryoshkaQuantizer.maxsim_boost("alpha", "beta")
    assert boost_nomatch == 0.0
    boost_heading = MatryoshkaQuantizer.maxsim_boost(
        "search query", "My Title", headings=["search query"]
    )
    assert boost_heading > 0.0

    u1, u2 = uuid.uuid4(), uuid.uuid4()
    rrf = MatryoshkaQuantizer.rrf([[u1, u2], [u2, u1]])
    assert u1 in rrf
    assert u2 in rrf

    anchors = extract_heading_anchors("# Heading One\nText\n## Sub heading\n")
    assert len(anchors) == 2
    assert anchors[0]["anchor"] == "#heading-one"
    assert extract_heading_anchors("") == []
