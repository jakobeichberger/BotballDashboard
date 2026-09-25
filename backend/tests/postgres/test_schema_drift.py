"""The schema the migrations build on PostgreSQL is the schema the models declare.

The SQLite suite creates its tables from the models, production runs the
migrations; when the two drift apart, SQLite tests pass against a schema no
production database has (a missing unique index, a check constraint the
models don't know). This is `alembic check` as a test, plus the two things
autogenerate does not compare: partial-index predicates and check constraints.
CI runs it after `alembic upgrade head`.
"""

import importlib
import os
import pkgutil
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, text
from sqlalchemy.ext.asyncio import create_async_engine

import modules
from core.config import get_settings
from core.database import Base

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
    reason="requires explicit PostgreSQL/Redis integration environment",
)

BACKEND = Path(__file__).resolve().parents[2]


def _model_modules() -> list[str]:
    """Every models module under modules/ (models.py, *_models.py)."""
    return sorted(
        info.name
        for info in pkgutil.walk_packages(modules.__path__, "modules.")
        if info.name.rsplit(".", 1)[-1].endswith("models")
    )


def _load_models() -> None:
    import core.audit  # noqa: F401  (AuditLog lives outside modules/)

    for name in _model_modules():
        importlib.import_module(name)


async def _run_sync(function):
    # An engine of its own: pooled connections are bound to one test's event loop.
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(function)
    finally:
        await engine.dispose()


def test_alembic_env_imports_every_models_module():
    """Autogenerate (and `alembic check`) only sees models env.py imports."""
    env = (BACKEND / "alembic" / "env.py").read_text()
    missing = [name for name in _model_modules() if f"import {name}" not in env]
    assert not missing, f"alembic/env.py does not import {missing}"


@pytest.mark.asyncio
async def test_models_match_the_migrated_schema():
    _load_models()

    def compare(connection):
        # The options alembic/env.py configures, so this is `alembic check`.
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        return compare_metadata(context, Base.metadata)

    diffs = await _run_sync(compare)
    assert not diffs, "models and migrations differ:\n" + "\n".join(map(repr, diffs))


@pytest.mark.asyncio
async def test_partial_indexes_match():
    """Autogenerate compares index columns and expressions, not WHERE clauses."""
    _load_models()
    declared = {
        (table.name, index.name)
        for table in Base.metadata.tables.values()
        for index in table.indexes
        if index.dialect_options["postgresql"]["where"] is not None
    }

    def migrated(connection):
        rows = connection.execute(
            text(
                "SELECT tablename, indexname FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexdef LIKE '% WHERE %'"
            )
        )
        return {(row.tablename, row.indexname) for row in rows}

    assert await _run_sync(migrated) == declared


@pytest.mark.asyncio
async def test_check_constraints_match():
    """Autogenerate does not compare check constraints at all."""
    _load_models()
    declared = {
        (table.name, constraint.name)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    def migrated(connection):
        rows = connection.execute(
            text(
                "SELECT t.relname AS table_name, c.conname FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE c.contype = 'c' AND n.nspname = current_schema()"
            )
        )
        return {(row.table_name, row.conname) for row in rows}

    assert await _run_sync(migrated) == declared
