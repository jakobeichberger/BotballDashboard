"""
Pytest configuration and shared fixtures for BotballDashboard backend tests.

The suite runs against one in-memory SQLite database. The schema is created
once per test process; every test runs inside an outer transaction that is
rolled back afterwards, and the session joins it through SAVEPOINTs, so code
under test may commit (and roll back) freely without leaking rows into the
next test. PostgreSQL-specific checks live in tests/postgres.
"""

import logging
import os
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("UPLOAD_DIR", "/tmp/botball-dashboard-tests/uploads")
# No Redis in the unit/integration suite: keep logged-out tokens in-process.
os.environ.setdefault("TOKEN_DENYLIST_BACKEND", "memory")
# Tests change data behind the API's back; cache tests switch it on explicitly.
os.environ.setdefault("CACHE_BACKEND", "none")
# Hashing dominated the suite's runtime at the production work factor (12).
os.environ.setdefault("BCRYPT_ROUNDS", "4")
# Debug logs of every request and query only slow the suite down.
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from core.auth import create_access_token
from core.database import Base, get_db
from main import app

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# ── In-memory SQLite engine for unit/integration tests ───────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)


# The sqlite3 driver manages transactions itself and breaks SAVEPOINTs; let
# SQLAlchemy emit BEGIN instead (SQLAlchemy docs, "Serializable isolation /
# Savepoints / Transactional DDL" for aiosqlite).
@event.listens_for(test_engine.sync_engine, "connect")
def _sqlite_driver_autocommit(dbapi_connection, _record):
    dbapi_connection.isolation_level = None


@event.listens_for(test_engine.sync_engine, "begin")
def _sqlite_explicit_begin(connection):
    connection.exec_driver_sql("BEGIN")


_schema_created = False


async def _ensure_schema() -> None:
    global _schema_created
    if not _schema_created:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _schema_created = True


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """A session whose work is rolled back after the test, commits included."""
    await _ensure_schema()
    async with test_engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            autoflush=False,
            # session.commit()/rollback() release/roll back a SAVEPOINT; the
            # outer transaction stays open until the test is over.
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if outer.is_active:
                await outer.rollback()


class _EngineInTestTransaction:
    """Stands in for ``core.database.engine`` inside one test's transaction.

    Code that opens its own connection (``engine.begin()`` / ``engine.connect()``,
    e.g. the audit fallback or the readiness probe) would otherwise ask the one
    in-memory connection for a second transaction. Here it gets the test's
    connection inside a SAVEPOINT instead, so its writes are visible to the test
    and rolled back with everything else.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        connection = await self._session.connection()
        async with connection.begin_nested():
            yield connection

    connect = begin


@pytest_asyncio.fixture
async def engine_in_test_transaction(db: AsyncSession) -> _EngineInTestTransaction:
    return _EngineInTestTransaction(db)


@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with overridden DB dependency."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.state.testing = True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    app.state.testing = False


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession):
    """Create a superuser for testing protected routes."""
    from modules.auth.models import User
    from modules.auth.service import hash_password

    user = User(
        email="admin@test.com",
        display_name="Test Admin",
        hashed_password=hash_password("testpassword"),
        is_active=True,
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user) -> str:
    """Access token for the admin user."""
    return create_access_token(admin_user.id)


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    """Authorization headers for HTTP requests."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def season(db: AsyncSession):
    """Create a test season."""
    from modules.events.models import Event
    from modules.seasons.models import Season

    s = Season(name="Test Season 2026", year=2026, is_active=True)
    db.add(s)
    await db.flush()
    db.add(
        Event(
            season_id=s.id,
            name="Test Event",
            slug=f"test-event-{s.id}",
            status="published",
            public_scoreboard=True,
            public_schedule=True,
        )
    )
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def event(db: AsyncSession, season):
    """Return the default event belonging to the test season."""
    from sqlalchemy import select

    from modules.events.models import Event

    return (await db.execute(select(Event).where(Event.season_id == season.id))).scalar_one()


@pytest_asyncio.fixture
async def team(db: AsyncSession):
    """Create a test team."""
    from modules.teams.models import Team

    t = Team(name="Test Team Alpha", team_number="TTA-01", country="DE")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t
