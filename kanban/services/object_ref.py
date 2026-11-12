"""Object reference resolution service for canonical keys, project keys, and UUIDs.

Traceability: Spec S7.2 8m, S3.4.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from database.models import ObjectKind, ObjectRecord

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_OBJECT_REF_LENGTH: Final[int] = 64
_UUID_RE: Final[re.Pattern[str]] = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ISSUE_KEY_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,17}$")
_PROJECT_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")


async def resolve_object_ref(
    session: AsyncSession,
    ref: str,
    expected_type: ObjectKind | None = None,
) -> ObjectRecord | None:
    """Resolve an object reference (UUID, issue key, or project key) through RLS.

    Accepts:
        - UUID string (e.g. 018f3a21-9876-7123-8abc-def012345678)
        - Issue canonical key (e.g. KAN-142)
        - Project identifier (e.g. KAN)
        - General canonical key matching objects.canonical_key

    Constraints:
        - Ref length must be between 1 and 64 characters; returns None otherwise.
        - Soft-deleted objects (deleted_at IS NOT NULL) return None.
        - Unreadable objects (filtered by PostgreSQL RLS) return None.
    """
    clean_ref = ref.strip()
    if not clean_ref or len(clean_ref) > MAX_OBJECT_REF_LENGTH:
        return None

    stmt = select(ObjectRecord).where(ObjectRecord.deleted_at.is_(None))

    if _UUID_RE.fullmatch(clean_ref):
        stmt = stmt.where(ObjectRecord.id == uuid.UUID(clean_ref))
    elif _ISSUE_KEY_RE.fullmatch(clean_ref):
        if expected_type is not None and expected_type != ObjectKind.ISSUE:
            return None
        stmt = stmt.where(
            ObjectRecord.canonical_key == clean_ref,
            ObjectRecord.object_type == ObjectKind.ISSUE,
        )
    elif _PROJECT_IDENTIFIER_RE.fullmatch(clean_ref):
        if expected_type is not None and expected_type != ObjectKind.PROJECT:
            return None
        stmt = stmt.where(
            ObjectRecord.canonical_key == clean_ref,
            ObjectRecord.object_type == ObjectKind.PROJECT,
        )
    else:
        stmt = stmt.where(ObjectRecord.canonical_key == clean_ref)

    if expected_type is not None:
        stmt = stmt.where(ObjectRecord.object_type == expected_type)

    return (await session.execute(stmt)).scalars().first()
