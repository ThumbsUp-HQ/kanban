"""Unit tests for Phase 1 issues table, sequence allocation, and tsvector."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class IssueContext:
    """Project and user context for issue creation."""

    workspace_id: uuid.UUID
    project_id: uuid.UUID
    identifier: str
    user_id: uuid.UUID
    state_id: uuid.UUID
    priority_id: uuid.UUID


@dataclass
class IssueParams:
    """Attributes and options for issue creation."""

    summary: str = "Sample Issue"
    description_markdown: str = ""
    start_date: date | None = None
    due_date: date | None = None
    board_rank: str = "0|hzzzzz:"
    issue_id: uuid.UUID | None = None


async def _create_workspace(
    session: AsyncSession,
    slug: str | None = None,
    name: str = "Test Workspace",
) -> uuid.UUID:
    """Create a test workspace and return its UUID."""
    ws_slug = slug or f"ws-{uuid.uuid4().hex[:12]}"
    row = await session.execute(
        text("INSERT INTO workspaces (slug, name) VALUES (:slug, :name) RETURNING id"),
        {"slug": ws_slug, "name": name},
    )
    val = row.scalar_one()
    assert isinstance(val, uuid.UUID)
    return val


async def _create_user(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    email: str,
    display_name: str = "Test User",
) -> uuid.UUID:
    """Create a user in principals, objects, and users tables."""
    u_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO principals (id, principal_type, workspace_id, display_name) "
            "VALUES (:id, 'USER', :ws_id, :name)"
        ),
        {"id": u_id, "ws_id": workspace_id, "name": display_name},
    )
    await session.execute(
        text(
            "SELECT register_object("
            "  'user'::object_kind, :ws_id, NULL::uuid, :ckey, :title, :creator, :id"
            ")"
        ),
        {
            "ws_id": workspace_id,
            "ckey": f"usr-{u_id.hex[:8]}",
            "title": display_name,
            "creator": u_id,
            "id": u_id,
        },
    )
    await session.execute(
        text("INSERT INTO users (id, workspace_id, email) VALUES (:id, :ws_id, :email)"),
        {"id": u_id, "ws_id": workspace_id, "email": email},
    )
    return u_id


async def _create_project(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    creator_id: uuid.UUID,
    identifier: str = "KAN",
    name: str = "Kanban Project",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create a project and return (project_id, default_state_id, default_priority_id)."""
    p_id = uuid.uuid4()
    await session.execute(
        text(
            "SELECT register_object("
            "  'project'::object_kind, :ws, NULL::uuid, :ident, :name, :creator, :id"
            ")"
        ),
        {"ws": workspace_id, "ident": identifier, "name": name, "creator": creator_id, "id": p_id},
    )
    await session.execute(
        text(
            "INSERT INTO projects (id, workspace_id, identifier, name) "
            "VALUES (:id, :ws, :ident, :name)"
        ),
        {"id": p_id, "ws": workspace_id, "ident": identifier, "name": name},
    )

    state_row = await session.execute(
        text("SELECT id FROM workflow_states WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    state_id = state_row.scalar_one()
    assert isinstance(state_id, uuid.UUID)

    prio_row = await session.execute(
        text("SELECT id FROM project_priorities WHERE project_id = :p AND is_default = true"),
        {"p": p_id},
    )
    prio_id = prio_row.scalar_one()
    assert isinstance(prio_id, uuid.UUID)

    return p_id, state_id, prio_id


async def _create_issue(
    session: AsyncSession,
    ctx: IssueContext,
    params: IssueParams | None = None,
) -> tuple[uuid.UUID, int]:
    """Execute full application flow to create an issue."""
    p = params or IssueParams()
    seq_row = await session.execute(
        text("SELECT allocate_issue_sequence(:p)"),
        {"p": ctx.project_id},
    )
    seq = seq_row.scalar_one()
    assert isinstance(seq, int)

    i_id = p.issue_id or uuid.uuid4()
    canonical_key = f"{ctx.identifier}-{seq}"

    await session.execute(
        text(
            "SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, :summary, :user, :id)"
        ),
        {
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "ckey": canonical_key,
            "summary": p.summary,
            "user": ctx.user_id,
            "id": i_id,
        },
    )

    await session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  description_markdown, state_id, priority_id, "
            "  created_by_id, original_created_by_id, start_date, due_date, board_rank"
            ") VALUES ("
            "  :id, :ws, :p, :seq, :summary, "
            "  :desc, :state, :prio, "
            "  :user, :user, :sdate, :ddate, :rank"
            ")"
        ),
        {
            "id": i_id,
            "ws": ctx.workspace_id,
            "p": ctx.project_id,
            "seq": seq,
            "summary": p.summary,
            "desc": p.description_markdown,
            "state": ctx.state_id,
            "prio": ctx.priority_id,
            "user": ctx.user_id,
            "sdate": p.start_date,
            "ddate": p.due_date,
            "rank": p.board_rank,
        },
    )

    return i_id, seq


async def test_01_positive_full_flow_and_sha256(db_session: AsyncSession) -> None:
    """Verify full app flow creates KAN-1 and description_sha256 matches sha256 digest."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "KAN")
    ctx = IssueContext(ws, p, "KAN", u, state_id, prio_id)

    desc = "This is a detailed markdown description of KAN-1."
    i_id, seq = await _create_issue(
        db_session,
        ctx,
        IssueParams(summary="First Issue", description_markdown=desc),
    )
    assert seq == 1

    res = await db_session.execute(
        text("SELECT sequence_id, description_sha256 FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    row = res.one()
    assert row.sequence_id == 1

    expected_hash = hashlib.sha256(desc.encode("utf-8")).digest()
    assert bytes(row.description_sha256) == expected_hash

    # Updating description changes the hash
    new_desc = "Updated description text with different content."
    await db_session.execute(
        text("UPDATE issues SET description_markdown = :desc WHERE id = :id"),
        {"desc": new_desc, "id": i_id},
    )
    new_res = await db_session.execute(
        text("SELECT description_sha256 FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    new_hash = hashlib.sha256(new_desc.encode("utf-8")).digest()
    assert bytes(new_res.scalar_one()) == new_hash
    assert new_hash != expected_hash


async def test_02_positive_markdown_tsvector(db_session: AsyncSession) -> None:
    """Verify build_markdown_tsvector strips fences, urls, and keeps code and link text."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "tsvector-author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "TSV")
    ctx = IssueContext(ws, p, "TSV", u, state_id, prio_id)

    desc = "see [docs](https://evil.example/path)\n```python\nfoo_bar()\n```"
    i_id, _ = await _create_issue(
        db_session,
        ctx,
        IssueParams(summary="Searchable Markdown", description_markdown=desc),
    )

    # 1. 'docs' is indexed from link text
    r_docs = await db_session.execute(
        text("SELECT search_tsv @@ to_tsquery('english', 'docs') FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_docs.scalar_one() is True

    # 2. 'evil' is stripped from url
    r_evil = await db_session.execute(
        text("SELECT search_tsv @@ to_tsquery('english', 'evil') FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_evil.scalar_one() is False

    # 3. 'python' info string stripped
    r_py = await db_session.execute(
        text("SELECT search_tsv @@ to_tsquery('english', 'python') FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_py.scalar_one() is False

    # 4. 'foo_bar' code content is indexed and searchable
    r_foo = await db_session.execute(
        text("SELECT search_tsv @@ to_tsquery('english', 'foo_bar') FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_foo.scalar_one() is True


async def test_03_negative_checks(db_session: AsyncSession) -> None:
    """Verify summary length, date order, and description size constraints raise 23514."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "checks-author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "CHK")
    ctx = IssueContext(ws, p, "CHK", u, state_id, prio_id)

    # 1. Summary with whitespace only raises 23514
    with pytest.raises((IntegrityError, DBAPIError)) as exc_sum_empty:
        async with db_session.begin_nested():
            await _create_issue(db_session, ctx, IssueParams(summary="   "))
    err_empty = str(exc_sum_empty.value).lower()
    assert "23514" in str(exc_sum_empty.value) or "check constraint" in err_empty

    # 2. Summary with 501 chars raises 23514
    with pytest.raises((IntegrityError, DBAPIError)) as exc_sum_long:
        async with db_session.begin_nested():
            await _create_issue(db_session, ctx, IssueParams(summary="s" * 501))
    err_long = str(exc_sum_long.value).lower()
    assert "23514" in str(exc_sum_long.value) or "check constraint" in err_long

    # 3. due_date < start_date raises 23514
    with pytest.raises((IntegrityError, DBAPIError)) as exc_date:
        async with db_session.begin_nested():
            await _create_issue(
                db_session,
                ctx,
                IssueParams(start_date=date(2026, 11, 12), due_date=date(2026, 11, 11)),
            )
    err_date = str(exc_date.value).lower()
    assert "23514" in str(exc_date.value) or "check constraint" in err_date

    # 4. Description of 1048577 bytes raises 23514
    desc_oversized = "a" * 1048577
    with pytest.raises((IntegrityError, DBAPIError)) as exc_desc:
        async with db_session.begin_nested():
            await _create_issue(
                db_session,
                ctx,
                IssueParams(description_markdown=desc_oversized),
            )
    assert "23514" in str(exc_desc.value) or "check constraint" in str(exc_desc.value).lower()

    # 5. Description of 1048576 bytes is accepted
    desc_max = "b" * 1048576
    i_id_max, _ = await _create_issue(
        db_session,
        ctx,
        IssueParams(description_markdown=desc_max),
    )
    assert isinstance(i_id_max, uuid.UUID)


async def test_04_negative_security_and_trigger_guards(db_session: AsyncSession) -> None:
    """Verify generated columns, state project mismatch, unallocated sequence, and ancestry."""
    ws = await _create_workspace(db_session)
    ws2 = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "guard-author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "GRD")
    _p2, state2_id, _ = await _create_project(db_session, ws, u, "OTHER")

    # 1. Inserting generated column description_sha256 explicitly raises 428C9
    i_gen_id = uuid.uuid4()
    with pytest.raises((ProgrammingError, DBAPIError)) as exc_gen:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, "
                    "  state_id, priority_id, created_by_id, original_created_by_id, "
                    "  board_rank, description_sha256"
                    ") VALUES ("
                    "  :id, :ws, :p, 999, 'Gen Test', :state, :prio, :u, :u, '0|:', "
                    "  decode('1234', 'hex')"
                    ")"
                ),
                {"id": i_gen_id, "ws": ws, "p": p, "state": state_id, "prio": prio_id, "u": u},
            )
    orig_gen = getattr(exc_gen.value, "orig", None)
    code_gen = getattr(orig_gen, "sqlstate", None) or getattr(exc_gen.value, "code", None)
    err_gen = str(exc_gen.value).lower()
    assert code_gen == "428C9" or "428c9" in err_gen or "generated" in err_gen

    # 2. State from another project raises ISSUE_STATE_PROJECT_MISMATCH
    ctx_bad_state = IssueContext(ws, p, "GRD", u, state2_id, prio_id)
    with pytest.raises((IntegrityError, DBAPIError)) as exc_state:
        async with db_session.begin_nested():
            await _create_issue(db_session, ctx_bad_state, IssueParams(summary="Cross State"))
    assert "ISSUE_STATE_PROJECT_MISMATCH" in str(exc_state.value)

    # 3. Sequence larger than counter raises ISSUE_SEQUENCE_NOT_ALLOCATED
    i_unalloc = uuid.uuid4()
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws, :p, 'GRD-999', 'Unallocated', :u, :id"
            ")"
        ),
        {"ws": ws, "p": p, "u": u, "id": i_unalloc},
    )
    with pytest.raises((IntegrityError, DBAPIError)) as exc_seq:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, "
                    "  state_id, priority_id, created_by_id, original_created_by_id, board_rank"
                    ") VALUES ("
                    "  :id, :ws, :p, 999, 'Unallocated', :state, :prio, :u, :u, '0|:'"
                    ")"
                ),
                {"id": i_unalloc, "ws": ws, "p": p, "state": state_id, "prio": prio_id, "u": u},
            )
    assert "ISSUE_SEQUENCE_NOT_ALLOCATED" in str(exc_seq.value)

    # 4. Workspace mismatch between issue and project raises ISSUE_WORKSPACE_MISMATCH
    i_ws_mismatch = uuid.uuid4()
    seq_row = await db_session.execute(text("SELECT allocate_issue_sequence(:p)"), {"p": p})
    seq_val = seq_row.scalar_one()
    await db_session.execute(
        text(
            "SELECT register_object(  'issue'::object_kind, :ws, :p, :ckey, 'WS Mismatch', :u, :id)"
        ),
        {"ws": ws, "p": p, "ckey": f"GRD-{seq_val}", "u": u, "id": i_ws_mismatch},
    )
    with pytest.raises((IntegrityError, DBAPIError)) as exc_ws:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO issues ("
                    "  id, workspace_id, project_id, sequence_id, summary, "
                    "  state_id, priority_id, created_by_id, original_created_by_id, board_rank"
                    ") VALUES ("
                    "  :id, :ws2, :p, :seq, 'WS Mismatch', :state, :prio, :u, :u, '0|:'"
                    ")"
                ),
                {
                    "id": i_ws_mismatch,
                    "ws2": ws2,
                    "p": p,
                    "seq": seq_val,
                    "state": state_id,
                    "prio": prio_id,
                    "u": u,
                },
            )
    assert "ISSUE_WORKSPACE_MISMATCH" in str(exc_ws.value)

    # 5. Client-supplied ancestry_path is overwritten on INSERT
    i_anc = uuid.uuid4()
    seq_anc = await db_session.scalar(text("SELECT allocate_issue_sequence(:p)"), {"p": p})
    await db_session.execute(
        text(
            "SELECT register_object("
            "  'issue'::object_kind, :ws, :p, :ckey, 'Ancestry Test', :u, :id"
            ")"
        ),
        {"ws": ws, "p": p, "ckey": f"GRD-{seq_anc}", "u": u, "id": i_anc},
    )
    await db_session.execute(
        text(
            "INSERT INTO issues ("
            "  id, workspace_id, project_id, sequence_id, summary, "
            "  state_id, priority_id, created_by_id, original_created_by_id, "
            "  board_rank, ancestry_path"
            ") VALUES ("
            "  :id, :ws, :p, :seq, 'Ancestry Test', :state, :prio, :u, :u, '0|:', "
            "  'untrusted.client.path'::ltree"
            ")"
        ),
        {
            "id": i_anc,
            "ws": ws,
            "p": p,
            "seq": seq_anc,
            "state": state_id,
            "prio": prio_id,
            "u": u,
        },
    )
    anc_row = await db_session.execute(
        text("SELECT ancestry_path::text FROM issues WHERE id = :id"),
        {"id": i_anc},
    )
    stored_path = anc_row.scalar_one()
    expected_path = i_anc.hex
    assert stored_path == expected_path
    assert stored_path != "untrusted.client.path"


async def test_05_negative_immutability_and_missing_project(db_session: AsyncSession) -> None:
    """Verify sequence_id and project_id immutability and allocate on missing project."""
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "immut-author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "IMM")
    ctx = IssueContext(ws, p, "IMM", u, state_id, prio_id)

    i_id, _ = await _create_issue(db_session, ctx)

    # 1. UPDATE sequence_id raises ISSUE_KEY_IMMUTABLE
    with pytest.raises((IntegrityError, DBAPIError)) as exc_seq:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET sequence_id = sequence_id + 1 WHERE id = :id"),
                {"id": i_id},
            )
    assert "ISSUE_KEY_IMMUTABLE" in str(exc_seq.value)

    # 2. UPDATE project_id raises ISSUE_KEY_IMMUTABLE
    other_p_id = uuid.uuid4()
    with pytest.raises((IntegrityError, DBAPIError)) as exc_proj:
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE issues SET project_id = :p WHERE id = :id"),
                {"p": other_p_id, "id": i_id},
            )
    assert "ISSUE_KEY_IMMUTABLE" in str(exc_proj.value)

    # 3. allocate_issue_sequence on non-existent project raises PROJECT_NOT_FOUND
    with pytest.raises((IntegrityError, DBAPIError)) as exc_alloc:
        async with db_session.begin_nested():
            await db_session.execute(
                text("SELECT allocate_issue_sequence(:p)"),
                {"p": uuid.uuid4()},
            )
    assert "PROJECT_NOT_FOUND" in str(exc_alloc.value)


async def test_07_boundary_and_volatility(db_session: AsyncSession) -> None:
    """Verify IMMUTABLE volatility of build_markdown_tsvector and empty description handling."""
    # 1. Verify build_markdown_tsvector is IMMUTABLE ('i') in pg_proc
    res = await db_session.execute(
        text("SELECT provolatile::text FROM pg_proc WHERE proname = 'build_markdown_tsvector'")
    )
    assert res.scalar_one() == "i"

    # 2. Empty description yields valid tsvector (not null, matches summary)
    ws = await _create_workspace(db_session)
    u = await _create_user(db_session, ws, "empty-author@example.com")
    p, state_id, prio_id = await _create_project(db_session, ws, u, "MT")
    ctx = IssueContext(ws, p, "MT", u, state_id, prio_id)

    i_id, _ = await _create_issue(
        db_session,
        ctx,
        IssueParams(summary="Unique Keyword In Summary", description_markdown=""),
    )

    r_empty = await db_session.execute(
        text("SELECT search_tsv IS NOT NULL FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_empty.scalar_one() is True

    r_kw = await db_session.execute(
        text("SELECT search_tsv @@ to_tsquery('english', 'Keyword') FROM issues WHERE id = :id"),
        {"id": i_id},
    )
    assert r_kw.scalar_one() is True
