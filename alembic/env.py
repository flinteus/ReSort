from alembic import context

from app.core.config import settings
from app.db.database import Base, engine
from app.models.collection_point import CollectionPoint, CollectionPointMaterial  # noqa: F401
from app.models.progress import Achievement, SortingEvent, UserAchievement  # noqa: F401
from app.models.photo import Photo  # noqa: F401
from app.models.sorting import SortingGuidance  # noqa: F401
from app.models.user import User  # noqa: F401: register model metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
