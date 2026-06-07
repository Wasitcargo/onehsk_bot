import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings


async def reset_database_schema() -> None:
    if os.getenv("RESET_DATABASE_ON_DEPLOY") != "1":
        raise SystemExit("RESET_DATABASE_ON_DEPLOY=1 is required to reset the database schema.")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            if connection.dialect.name != "postgresql":
                raise SystemExit("Database schema reset is only supported for PostgreSQL.")
            await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
            await connection.execute(text("GRANT ALL ON SCHEMA public TO public"))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_database_schema())
