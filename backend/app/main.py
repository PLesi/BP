from fastapi import FastAPI
from backend.app.db import init_db, add_user
from . import models
from models import User


app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await init_db()



