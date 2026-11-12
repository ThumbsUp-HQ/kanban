# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Unit tests for mention extraction and mention access resolution (S7.2 8k, S3.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.permissions import Capability
from kanban.services.mentions import extract_mentions, resolve_mentions
from kanban.tests.security.helpers import (
    add_acl_entry,
    create_project,
    create_registered_object,
    create_user,
    create_workspace,
    rebuild_era,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def test_extract_mentions_parser_and_boundary_rules() -> None:
    """Test Case 4 parser rules: code fences, inline code, URLs, emails, and 51 handles."""
    # 1. Negative extractions inside fenced code, inline code, URLs, and emails
    md = """
    # Updates

    Here is a mention @alice and another @bob.

    ```python
    # Code fence should not extract @fence_user
    x = "@fence_user"
    ```

    ~~~
    @tilde_fence_user
    ~~~

    Here is inline code `@inline_user` and double backtick ``@double_inline``.

    Check out https://github.com/@url_user/repo and [link text](https://example.com/@link_dest_user).
    Also an autolink <https://test.com/@autolink_user>.
    And my email is contact@domain_user.com or test.user@company.org.

    And here is a link with a mention in its label: [@link_label_user](https://example.com).
    """

    handles = extract_mentions(md)
    assert "alice" in handles
    assert "bob" in handles
    assert "link_label_user" in handles

    # Verify excluded handles
    assert "fence_user" not in handles
    assert "tilde_fence_user" not in handles
    assert "inline_user" not in handles
    assert "double_inline" not in handles
    assert "url_user" not in handles
    assert "link_dest_user" not in handles
    assert "autolink_user" not in handles
    assert "domain_user" not in handles
    assert "company" not in handles

    # 2. Deduplication preserving distinct count
    dup_md = "@charlie @charlie @charlie"
    assert extract_mentions(dup_md) == ["charlie"]

    # 3. 50 distinct handles succeeds
    fifty_handles = " ".join(f"@user{i}" for i in range(50))
    extracted_50 = extract_mentions(fifty_handles)
    assert len(extracted_50) == 50

    # 4. 51 distinct handles raises 422 TOO_MANY_MENTIONS
    fifty_one_handles = " ".join(f"@user{i}" for i in range(51))
    with pytest.raises(ProblemException) as exc_info:
        extract_mentions(fifty_one_handles)
    assert exc_info.value.code == "TOO_MANY_MENTIONS"
    assert exc_info.value.status == 422

    # 5. Empty handles stripped by punctuation
    assert extract_mentions("Empty @. and @- handle") == []


@pytest.mark.asyncio
async def test_resolve_mentions_access_boundaries_and_enumeration(db_session: AsyncSession) -> None:
    """Test resolution: access warning 409, acknowledgement bypass, and zero enumeration."""
    ws1_id = await create_workspace(db_session, name="Workspace 1")
    ws2_id = await create_workspace(db_session, name="Workspace 2")

    # Users in Workspace 1
    adam_id = await create_user(db_session, ws1_id, handle="@adam", display_name="Adam Outler")
    maya_id = await create_user(db_session, ws1_id, handle="@maya", display_name="Maya Lin")

    # User in Workspace 2 (outside boundary)
    _ = await create_user(db_session, ws2_id, handle="@other", display_name="Other User")

    # Project and Issue in Workspace 1
    proj_id = await create_project(
        db_session, ws1_id, identifier="KAN", name="Kanban Core", created_by_id=adam_id
    )
    issue_id = await create_registered_object(
        db_session,
        ws1_id,
        kind="issue",
        key="KAN-1",
        title="Issue 1",
        project_id=proj_id,
        created_by_id=adam_id,
    )

    # Grant VIEW capability to Adam on the issue
    await add_acl_entry(
        db_session, ws1_id, issue_id, adam_id, effect="ALLOW", capability_mask=Capability.VIEW
    )
    await rebuild_era(db_session, ws1_id)

    caller_ctx = PrincipalContext(
        principal_id=adam_id,
        workspace_id=ws1_id,
        token_scopes=("session",),
        aal_level=1,
    )

    # 1. Mention Adam (has access) -> authorized (deduplicating duplicate handles)
    auth, unnotified, newly_acked = await resolve_mentions(
        db_session, caller_ctx, issue_id, ["adam", "adamoutler"]
    )
    assert len(auth) == 1
    assert auth[0].handle == "adam"
    assert auth[0].principal_id == adam_id
    assert auth[0].has_access is True
    assert len(unnotified) == 0
    assert len(newly_acked) == 0

    # 2. Mention Maya (in workspace, but lacks VIEW) -> raises 409 MENTION_ACCESS_WARNING
    with pytest.raises(ProblemException) as exc_info:
        await resolve_mentions(db_session, caller_ctx, issue_id, ["maya"])
    exc = exc_info.value
    assert exc.code == "MENTION_ACCESS_WARNING"
    assert exc.status == 409
    assert exc.unauthorized_mentions is not None
    assert (
        len(
            exc.unnotified_mentions
            if hasattr(exc, "unnotified_mentions")
            else exc.unauthorized_mentions
        )
        == 1
    )
    unauth = exc.unauthorized_mentions[0]
    assert unauth["handle"] == "maya"
    assert unauth["principal_id"] == str(maya_id)

    # 3. Mention Maya with acknowledgement -> returns in unnotified_mentions
    auth, unnotified, newly_acked = await resolve_mentions(
        db_session, caller_ctx, issue_id, ["maya"], acknowledge_mentions=[maya_id]
    )
    assert len(auth) == 0
    assert len(unnotified) == 1
    assert unnotified[0].handle == "maya"
    assert unnotified[0].principal_id == maya_id
    assert unnotified[0].has_access is False
    assert newly_acked == [maya_id]

    # 4. Anti-enumeration: external and nonexistent users yield empty (zero signal)
    auth_ext, unnot_ext, newly_ext = await resolve_mentions(
        db_session, caller_ctx, issue_id, ["other", "nonexistent_ghost"]
    )
    assert len(auth_ext) == 0
    assert len(unnot_ext) == 0
    assert len(newly_ext) == 0
