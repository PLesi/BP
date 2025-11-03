from sqlmodel import Field, SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from os import getenv
from dotenv import load_dotenv

load_dotenv()

file_name = "lab"
database_url = f"{getenv("DATABASE_URL")}{file_name}" 

engine: AsyncEngine = create_async_engine(database_url, echo=True, future=True)
async def init_db():
    async with engine.begin() as conn:
        print("working")
        from . import models
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session

