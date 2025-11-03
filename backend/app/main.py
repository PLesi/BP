from fastapi import FastAPI
from backend.app.db import init_db

app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_db()