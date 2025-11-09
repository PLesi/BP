from fastapi import FastAPI
from contextlib import asynccontextmanager
from .db import init_db
from .routers import users, auth

async def lifespan(app: FastAPI):
    await init_db()
    yield
    print("end")

app = FastAPI(lifespan=lifespan)

app.include_router(users.router)
app.include_router(auth.router)

