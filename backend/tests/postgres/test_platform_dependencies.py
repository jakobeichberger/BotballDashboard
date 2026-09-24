"""Integration smoke tests executed against real PostgreSQL and Redis in CI."""

import os

import pytest
from redis.asyncio import Redis
from sqlalchemy import text

from core.config import get_settings
from core.database import engine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)


@pytest.mark.asyncio
async def test_postgresql_and_migration_head_are_available():
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        version = result.scalar_one()
        assert version == _migration_head()


def _migration_head() -> str:
    """The single head of the migration chain, so new migrations need no test edit."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = Path(__file__).resolve().parents[2]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, f"migration chain has several heads: {heads}"
    return heads[0]


@pytest.mark.asyncio
async def test_redis_roundtrip():
    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        await redis.set("botball:ci:smoke", "ok", ex=10)
        assert await redis.get("botball:ci:smoke") == "ok"
    finally:
        await redis.aclose()
