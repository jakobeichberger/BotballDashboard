"""Check constraints of the migrated PostgreSQL schema accept what the models write.

The SQLite suite builds its tables from the models, so a check constraint that
only a migration creates is never exercised there. The paper-review E2E flow
found one: 0012 allowed 'assigned' while the model writes 'pending'.
"""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings
from modules.paper_review.models import ReviewerAssignment

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)


async def _accepts(table: str, constraint: str, column: str, value: str) -> bool:
    """Evaluate the named check constraint for one column value."""
    # An engine of its own: pooled connections are bound to one test's event loop.
    engine = create_async_engine(get_settings().database_url)
    async with engine.connect() as connection:
        definition = (
            await connection.execute(
                text(
                    "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = :table AND c.conname = :constraint"
                ),
                {"table": table, "constraint": constraint},
            )
        ).scalar_one()
        expression = definition.removeprefix("CHECK ")
        query = text(
            f"SELECT {expression} FROM (SELECT CAST(:value AS varchar) AS {column}) AS row"
        )
        accepted = bool((await connection.execute(query, {"value": value})).scalar_one())
    await engine.dispose()
    return accepted


@pytest.mark.asyncio
async def test_reviewer_assignment_status_accepts_the_model_vocabulary():
    default = ReviewerAssignment.__table__.c.status.default.arg
    for status in (default, "in_progress", "completed", "overdue"):
        assert await _accepts(
            "reviewer_assignments", "ck_reviewer_assignment_status", "status", status
        ), status
    assert not await _accepts(
        "reviewer_assignments", "ck_reviewer_assignment_status", "status", "bogus"
    )
