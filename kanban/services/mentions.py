# Copyright 2026 Kanban Platform Contributors
# Apache-2.0 License. See LICENSE for details.
"""Mention extraction and access-checked mention resolution service (S7.2 8k, S3.4)."""

from __future__ import annotations

import re
import uuid  # noqa: TC003  # Runtime import required for Pydantic / type annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models.principals import Principal, User
from database.models.spine import ObjectRecord
from kanban.api.deps import PrincipalContext
from kanban.api.problems import ProblemException
from kanban.security.permissions import Capability, evaluate_capabilities

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "MAX_DISTINCT_MENTIONS",
    "ResolvedMention",
    "extract_mentions",
    "resolve_mentions",
]

MAX_DISTINCT_MENTIONS: Final[int] = 50

_MENTION_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w@])@([a-z0-9][a-z0-9_.-]{0,38})", re.IGNORECASE
)
_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")
_INLINE_CODE_RE: Final[re.Pattern[str]] = re.compile(r"(`+[\s\S]*?`+)")
_MD_LINK_URL_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_URL_RE: Final[re.Pattern[str]] = re.compile(r"https?://[^\s)\]]+")


@dataclass(frozen=True, slots=True)
class ResolvedMention:
    """Resolved mention entry with access capability verification."""

    handle: str
    principal_id: uuid.UUID
    has_access: bool


def extract_mentions(markdown: str) -> list[str]:
    """Extract distinct mention handles outside code fences, inline spans, and link URLs.

    Enforces maximum of 50 distinct handles per comment, raising 422 TOO_MANY_MENTIONS
    if the threshold is exceeded.
    """
    # 1. Strip fenced code blocks (``` and ~~~)
    text = _FENCE_RE.sub(" ", markdown)
    # 2. Strip inline code spans (`...`)
    text = _INLINE_CODE_RE.sub(" ", text)
    # 3. Strip markdown link URLs [text](url) -> keep [text], drop url
    text = _MD_LINK_URL_RE.sub(r"[\1]", text)
    # 4. Strip raw and autolink URLs
    text = _URL_RE.sub(" ", text)

    seen: set[str] = set()
    distinct_handles: list[str] = []

    for match in _MENTION_RE.finditer(text):
        handle = match.group(1).rstrip(".-").lower()
        if not handle:
            continue
        if handle not in seen:
            seen.add(handle)
            distinct_handles.append(handle)

    if len(distinct_handles) > MAX_DISTINCT_MENTIONS:
        raise ProblemException(
            code="TOO_MANY_MENTIONS",
            status=422,
            title="Too Many Mentions",
            detail=f"A comment may not mention more than {MAX_DISTINCT_MENTIONS} distinct handles.",
        )

    return distinct_handles


def _build_candidate_map(
    rows: Sequence[tuple[Principal, User, str | None]],
) -> dict[str, tuple[uuid.UUID, str]]:
    candidates_by_handle: dict[str, tuple[uuid.UUID, str]] = {}
    for p, u, ckey in rows:
        canonical_handle = (
            ckey.lstrip("@").lower() if ckey else p.display_name.lower().replace(" ", "")
        )
        p_id = p.id
        if ckey:
            candidates_by_handle[ckey.lstrip("@").lower()] = (p_id, canonical_handle)
        display_clean = p.display_name.lower().replace(" ", "")
        candidates_by_handle.setdefault(display_clean, (p_id, canonical_handle))
        if u.email:
            email_prefix = u.email.split("@")[0].lower()
            candidates_by_handle.setdefault(email_prefix, (p_id, canonical_handle))
    return candidates_by_handle


async def resolve_mentions(
    session: AsyncSession,
    caller: PrincipalContext,
    issue_id: uuid.UUID,
    handles: Sequence[str],
    acknowledge_mentions: Sequence[uuid.UUID] = (),
) -> tuple[list[ResolvedMention], list[ResolvedMention], list[uuid.UUID]]:
    """Resolve handles within caller's workspace visibility boundary and enforce access gate.

    - Handles outside workspace boundary or nonexistent are ignored (zero enumeration signal).
    - In-boundary principals lacking VIEW on the issue trigger 409 MENTION_ACCESS_WARNING
      unless acknowledged in acknowledge_mentions.
    - Mentions never modify resource_acl_entries.

    Returns:
        (authorized_mentions, unnotified_mentions, newly_acknowledged_principal_ids)

    """
    if not handles:
        return [], [], []

    # Query all active user principals in caller's workspace
    stmt = (
        select(Principal, User, ObjectRecord.canonical_key)
        .join(User, Principal.id == User.id)
        .outerjoin(ObjectRecord, ObjectRecord.id == Principal.id)
        .where(
            Principal.workspace_id == caller.workspace_id,
            Principal.status == "ACTIVE",
        )
    )
    rows = (await session.execute(stmt)).all()
    candidates_by_handle = _build_candidate_map(rows)  # type: ignore[arg-type]

    ack_set: set[uuid.UUID] = set(acknowledge_mentions)
    unauthorized_list: list[dict[str, str]] = []
    authorized_mentions: list[ResolvedMention] = []
    unnotified_mentions: list[ResolvedMention] = []
    newly_acknowledged_pids: list[uuid.UUID] = []

    seen_resolved_pids: set[uuid.UUID] = set()

    for raw_handle in handles:
        lookup_key = raw_handle.lstrip("@").lower()
        match = candidates_by_handle.get(lookup_key)
        if match is None:
            # Handle not found in caller's workspace boundary: leave as plain text
            continue

        p_id, canonical_handle = match
        if p_id in seen_resolved_pids:
            continue
        seen_resolved_pids.add(p_id)

        # Check VIEW capability on target issue
        user_ctx = PrincipalContext(
            principal_id=p_id,
            workspace_id=caller.workspace_id,
            token_scopes=("session",),
            aal_level=1,
        )
        caps = await evaluate_capabilities(session, user_ctx, issue_id)
        has_view = Capability.VIEW in caps

        if has_view:
            authorized_mentions.append(
                ResolvedMention(handle=canonical_handle, principal_id=p_id, has_access=True)
            )
        elif p_id in ack_set:
            unnotified_mentions.append(
                ResolvedMention(handle=canonical_handle, principal_id=p_id, has_access=False)
            )
            newly_acknowledged_pids.append(p_id)
        else:
            unauthorized_list.append({"handle": canonical_handle, "principal_id": str(p_id)})

    if unauthorized_list:
        raise ProblemException(
            type_uri="https://kanban/problems/mention-access-warning",
            code="MENTION_ACCESS_WARNING",
            status=409,
            title="Mentioned users cannot see this issue",
            detail="Resubmit with acknowledge_mentions to post without granting access.",
            unauthorized_mentions=unauthorized_list,
        )

    return authorized_mentions, unnotified_mentions, newly_acknowledged_pids
