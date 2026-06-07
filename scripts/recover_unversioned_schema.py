import asyncio

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db.base import Base
from app.db.session import _ensure_bootstrap_columns, _ensure_bootstrap_indexes
from app.db import models  # noqa: F401 - import models so Base.metadata is populated


def _head_revision() -> str:
    config = Config("alembic.ini")
    return ScriptDirectory.from_config(config).get_current_head()


async def _has_table(connection, table_name: str) -> bool:
    return await connection.run_sync(
        lambda sync_conn, table_name=table_name: inspect(sync_conn).has_table(table_name)
    )


async def _has_revision(connection) -> bool:
    if not await _has_table(connection, "alembic_version"):
        return False
    result = await connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
    return result.scalar_one_or_none() is not None


async def recover_unversioned_schema() -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            if await _has_revision(connection):
                print("Alembic revision already exists; recovery skipped.")
                return

            if not await _has_table(connection, "users"):
                print("No existing users table; fresh database will migrate from base.")
                return

            print("Existing unversioned users table detected.")
            print("Creating any missing tables and patching legacy columns before stamping Alembic.")

            await connection.run_sync(Base.metadata.create_all)
            await _ensure_bootstrap_columns(connection)
            await _ensure_bootstrap_indexes(connection)

            head = _head_revision()
            await connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS alembic_version (
                        version_num VARCHAR(255) NOT NULL,
                        CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
                    )
                    """
                )
            )
            await connection.execute(
                text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)")
            )
            await connection.execute(text("DELETE FROM alembic_version"))
            await connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:version_num)"),
                {"version_num": head},
            )
            print(f"Legacy schema stamped at Alembic head: {head}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(recover_unversioned_schema())
