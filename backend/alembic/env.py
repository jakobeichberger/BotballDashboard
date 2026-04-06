from logging.config import fileConfig

from sqlalchemy import create_engine
from alembic import context

# Import all models so Alembic can detect them
from core.database import Base
from core.audit import AuditLog  # noqa: F401
import modules.auth.models  # noqa: F401
import modules.seasons.models  # noqa: F401
import modules.teams.models  # noqa: F401
import modules.scoring.models  # noqa: F401
import modules.scoring.score_sheets.models  # noqa: F401
import modules.scoring.competition_models  # noqa: F401
import modules.paper_review.models  # noqa: F401
import modules.printing.models  # noqa: F401
import modules.dashboard.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    import os
    url = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url", ""))
    # Convert async URL (asyncpg) to sync URL (psycopg2) for Alembic migrations.
    # Alembic runs synchronously; using asyncio.run() fails in restricted
    # environments (Proxmox LXC) where socket.socketpair(AF_UNIX) is blocked.
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url())
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
