from sqlmodel import Field, SQLModel, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from os import getenv
from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from .models import User, UserCreate, UserPublic

load_dotenv()

file_name = "lab"
database_url = f"{getenv("DATABASE_URL")}{file_name}" 


engine: AsyncEngine = create_async_engine(database_url, echo=True, future=True)
async_session = sessionmaker( engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        print("working")
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

