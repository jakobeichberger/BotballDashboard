from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from core.config import get_settings

settings = get_settings()

# The API engine: one pool per API process. Pre-ping and recycling replace
# connections that died while idle (database restart, firewall timeouts)
# instead of failing the request that happens to draw them.
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle_seconds,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Celery tasks run every job in a fresh event loop (asyncio.run). asyncpg
# connections are bound to the loop that opened them, so a pooled connection
# handed to the next task's loop fails ("attached to a different loop"). The
# worker engine therefore keeps no pool: each task opens its connections and
# closes them before its loop ends.
worker_engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    poolclass=NullPool,
)

WorkerSessionLocal = async_sessionmaker(
    worker_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    from core.audit import add_pending_audit_entry

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            # The audit row of a successful write request rides along in the
            # request's own transaction (see main.audit_successful_mutations).
            add_pending_audit_entry(session)
            await session.commit()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Session factory for code that must not hold a session for a whole request.

    WebSocket routes stream for minutes or hours; a ``Depends(get_db)`` session
    would keep its pool connection for that long. They open a short-lived
    session from this factory instead (tests override it like ``get_db``).
    """
    return AsyncSessionLocal
