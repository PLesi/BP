from os import getenv
from dotenv import load_dotenv

from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from collections.abc import AsyncGenerator


load_dotenv()

database_url = f"{getenv('DATABASE_URL')}" 
DATABASE_URL = database_url  


engine: AsyncEngine = create_async_engine(database_url, echo=True, future=True)
async_session = sessionmaker( engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        print("working")
        await conn.run_sync(SQLModel.metadata.create_all)
        # Lightweight migration for existing DBs: ensure plain string device_type exists.
        await conn.execute(text("""
            ALTER TABLE devices
            ADD COLUMN IF NOT EXISTS device_type VARCHAR
        """))

        has_device_type_id_result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'devices' AND column_name = 'device_type_id'
            )
        """))
        has_device_type_id = bool(has_device_type_id_result.scalar())

        has_device_types_table_result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'device_types'
            )
        """))
        has_device_types_table = bool(has_device_types_table_result.scalar())

        if has_device_type_id and has_device_types_table:
            await conn.execute(text("""
                UPDATE devices d
                SET device_type = dt.name
                FROM device_types dt
                WHERE d.device_type_id = dt.id
                  AND d.device_type IS NULL
            """))

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

