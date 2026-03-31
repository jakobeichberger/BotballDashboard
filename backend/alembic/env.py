import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Import all models so Alembic can detect them
from core.database import Base
from core.audit import AuditLog  # noqa: F401
import modules.auth.models  # noqa: F401
import modules.seasons.models  # noqa: F401
import modules.teams.models  # noqa: F401
import modules.scoring.models  # noqa: F401
import modules.scoring.score_sheets.models  # noqa: F401
import modules.paper_review.models  # noqa: F401
import modules.printing.models  # noqa: F401
import modules.dashboard.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    import os
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_url())

    async with connectable.connect() as connection:
        await connection.run_sync(
            lambda conn: context.configure(
                connection=conn,
                target_metadata=target_metadata,
                compare_type=True,
            )
        )
        async with connection.begin():
            await connection.run_sync(lambda conn: context.run_migrations())

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
