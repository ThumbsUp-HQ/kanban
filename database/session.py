"""RLS session binding, context management, and fail-closed security guards."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction

from database.rls.context import (
    RLSContext,
    RLSContextError,
    RLSRoleViolationError,
    UnboundRLSSessionError,
    bind_rls_context,
)

__all__ = [
    "RLSAsyncSession",
    "RLSContext",
    "RLSContextError",
    "RLSRoleViolationError",
    "RLSSessionFactory",
    "RLSSyncSession",
    "UnboundRLSSessionError",
    "bind_rls_context",
    "create_rls_engine",
]


class RLSSyncSession(Session):
    """Internal synchronous Session subclass with RLS event enforcement."""


class RLSAsyncSession(AsyncSession):
    """Asynchronous session subclass enforcing RLS context binding."""

    sync_session_class = RLSSyncSession


def _do_orm_execute(orm_execute_state: ORMExecuteState) -> None:
    session = orm_execute_state.session
    if session.info.get("rls_managed_session", False):
        session.info["rls_bound"] = True
        return
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
        sess.info["rls_managed_session"] = True

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
            sess.info.pop("rls_managed_session", None)
            sess.info.pop("rls_bound", None)
            sess.info.pop("rls_context", None)
            await sess.close()
