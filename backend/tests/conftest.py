"""
Pytest configuration and shared fixtures for BotballDashboard backend tests.
Uses an in-memory SQLite database for fast, isolated unit tests.
Integration tests use a dedicated PostgreSQL test database.
"""
import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from core.auth import create_access_token
from main import app

# ── In-memory SQLite engine for unit/integration tests ───────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    echo=False,
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Create all tables fresh for each test, yield session, drop all after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.commit()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTP test client with overridden DB dependency."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession):
    """Create a superuser for testing protected routes."""
    from modules.auth.service import create_user, hash_password
    from modules.auth.models import User

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
    from modules.seasons.models import Season

    s = Season(name="Test Season 2026", year=2026, is_active=True)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def team(db: AsyncSession):
    """Create a test team."""
    from modules.teams.models import Team

    t = Team(name="Test Team Alpha", team_number="TTA-01", country="DE")
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t
