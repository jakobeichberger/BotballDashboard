from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
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


def get_url() -> URL:
    """Build connection URL from individual components (never embed password in string).

    Uses psycopg2 (sync) driver so Alembic does not need asyncio.  Python's
    _UnixSelectorEventLoop calls socket.socketpair(AF_UNIX) on init, which is
    blocked by the seccomp/AppArmor profile in Proxmox LXC containers.
    """
    import os
    return URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ.get("POSTGRES_USER", "botball"),
        password=os.environ.get("POSTGRES_PASSWORD", "botball"),
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        database=os.environ.get("POSTGRES_DB", "botball"),
    )


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
