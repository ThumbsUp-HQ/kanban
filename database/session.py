"""RLS session binding, context management, and fail-closed security guards."""

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction

_SCOPE_REGEX = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,63}$")


class RLSContextError(RuntimeError):
    """Base exception for RLS context and session binding violations."""


class UnboundRLSSessionError(RLSContextError):
    """Raised when an ORM query is attempted on a session lacking RLS context binding."""


class RLSRoleViolationError(RLSContextError):
    """Raised when the connected database role has SUPERUSER or BYPASSRLS privileges."""


@dataclass(frozen=True, slots=True)
class RLSContext:
    """Immutable security context bound to PostgreSQL session variables via SET LOCAL."""

    principal_id: uuid.UUID
    workspace_id: uuid.UUID
    token_scopes: tuple[str, ...] = ()
    aal_level: Literal[1, 2] = 1
    user_access_hash: bytes | str | None = None
    agent_principal_id: uuid.UUID | None = None
    ephemeral_project_id: uuid.UUID | None = None
    read_only: bool = False

    def __post_init__(self) -> None:
        """Validate aal_level and token scope formatting constraints."""
        if self.aal_level not in (1, 2):
            msg = f"Invalid aal_level: {self.aal_level} (must be 1 or 2)"
            raise ValueError(msg)

        raw_scopes: object = self.token_scopes
        if not isinstance(raw_scopes, tuple):
            if not hasattr(raw_scopes, "__iter__"):
                msg = f"Token scopes must be an iterable (got {type(raw_scopes).__name__})"
                raise TypeError(msg)
            converted: tuple[object, ...] = tuple(raw_scopes)
            object.__setattr__(self, "token_scopes", converted)
            raw_scopes = converted

        for scope in raw_scopes:
            if not isinstance(scope, str):
                msg = f"Token scope must be a string (got {type(scope).__name__})"
                raise TypeError(msg)
            if "," in scope or any(c.isspace() for c in scope) or not _SCOPE_REGEX.match(scope):
                msg = f"Invalid token scope: {scope!r}"
                raise ValueError(msg)


async def bind_rls_context(session: AsyncSession, ctx: RLSContext) -> None:
    """Bind RLS session context variables using SET LOCAL within an active transaction."""
    if not session.in_transaction():
        msg = "bind_rls_context requires an active transaction"
        raise RLSContextError(msg)

    session.info["_binding_in_progress"] = True
    try:
        user_hash_val = ""
        if ctx.user_access_hash is not None:
            if isinstance(ctx.user_access_hash, bytes):
                user_hash_val = ctx.user_access_hash.hex()
            else:
                user_hash_val = str(ctx.user_access_hash)

        stmt = text(
            "SELECT set_config('app.principal_id', :principal_id, true), "
            "set_config('app.workspace_id', :workspace_id, true), "
            "set_config('app.token_scopes', :token_scopes, true), "
            "set_config('app.aal_level', :aal_level, true), "
            "set_config('app.user_access_hash', :user_access_hash, true), "
            "set_config('app.agent_principal_id', :agent_principal_id, true), "
            "set_config('app.ephemeral_project_id', :ephemeral_project_id, true)"
        )
        params = {
            "principal_id": str(ctx.principal_id),
            "workspace_id": str(ctx.workspace_id),
            "token_scopes": ",".join(ctx.token_scopes),
            "aal_level": str(ctx.aal_level),
            "user_access_hash": user_hash_val,
            "agent_principal_id": (
                str(ctx.agent_principal_id) if ctx.agent_principal_id is not None else ""
            ),
            "ephemeral_project_id": (
                str(ctx.ephemeral_project_id) if ctx.ephemeral_project_id is not None else ""
            ),
        }
        await session.execute(stmt, params)
        if ctx.read_only:
            await session.execute(text("SET LOCAL TRANSACTION READ ONLY"))
        session.info["rls_bound"] = True
        session.info["rls_context"] = ctx
    finally:
        session.info.pop("_binding_in_progress", None)


class RLSSyncSession(Session):
    """Internal synchronous Session subclass with RLS event enforcement."""


class RLSAsyncSession(AsyncSession):
    """Asynchronous session subclass enforcing RLS context binding."""

    sync_session_class = RLSSyncSession


def _do_orm_execute(orm_execute_state: ORMExecuteState) -> None:
    session = orm_execute_state.session
    if not session.info.get("rls_bound", False) and not session.info.get(
        "_binding_in_progress", False
    ):
        msg = (
            "Executing query on unbound RLS session is forbidden. "
            "Bind RLS context with bind_rls_context(session, ctx) inside an active transaction."
        )
        raise UnboundRLSSessionError(msg)


def _after_transaction_end(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop("rls_bound", None)
        session.info.pop("rls_context", None)


event.listen(RLSSyncSession, "do_orm_execute", _do_orm_execute)
event.listen(RLSSyncSession, "after_transaction_end", _after_transaction_end)


def create_rls_engine(
    dsn: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 10,
    **kwargs: Any,  # noqa: ANN401
) -> AsyncEngine:
    """Create an AsyncEngine configured for RLS connection management."""
    return create_async_engine(
        dsn,
        pool_size=pool_size,
        max_overflow=max_overflow,
        **kwargs,
    )


class RLSSessionFactory:
    """Factory producing RLS-bound AsyncSessions with fail-closed security guards."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Initialize session factory with an AsyncEngine."""
        self._engine = engine
        self._sessionmaker: async_sessionmaker[RLSAsyncSession] = async_sessionmaker(
            engine,
            class_=RLSAsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """The underlying database engine."""
        return self._engine

    @property
    def sessionmaker(self) -> async_sessionmaker[RLSAsyncSession]:
        """The async sessionmaker bound to RLSAsyncSession."""
        return self._sessionmaker

    @classmethod
    def create_rls_engine(
        cls,
        dsn: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 10,
        **kwargs: Any,  # noqa: ANN401
    ) -> AsyncEngine:
        """Create an AsyncEngine via classmethod."""
        return create_rls_engine(dsn, pool_size=pool_size, max_overflow=max_overflow, **kwargs)

    async def verify_non_bypass_role(self) -> None:
        """Verify the database connection role does not have SUPERUSER or BYPASSRLS."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
            row = result.first()
            if row is not None:
                rolsuper, rolbypassrls = bool(row[0]), bool(row[1])
                if rolsuper or rolbypassrls:
                    msg = (
                        f"Database role has bypass privileges (rolsuper={rolsuper}, "
                        f"rolbypassrls={rolbypassrls}). Production queries must run under "
                        "a non-bypass role such as kanban_app."
                    )
                    raise RLSRoleViolationError(msg)

    @asynccontextmanager
    async def session(self, ctx: RLSContext) -> AsyncIterator[RLSAsyncSession]:
        """Async context manager yielding an RLS-bound session inside a transaction."""
        sess = self._sessionmaker()

        def _rebind_on_begin(sync_sess: Session, _trans: SessionTransaction, _conn: object) -> None:
            sync_sess.info["rls_bound"] = True
            sync_sess.info["rls_context"] = ctx

        event.listen(sess.sync_session, "after_begin", _rebind_on_begin)
        try:
            await sess.begin()
            await bind_rls_context(sess, ctx)
            try:
                yield sess
            except BaseException:
                if sess.in_transaction():
                    await sess.rollback()
                raise
            else:
                if sess.in_transaction():
                    await sess.commit()
        finally:
            event.remove(sess.sync_session, "after_begin", _rebind_on_begin)
            sess.info.pop("rls_bound", None)
            sess.info.pop("rls_context", None)
            await sess.close()
