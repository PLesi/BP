from fastapi import FastAPI
from contextlib import asynccontextmanager
from .db import init_db
from .routers import devices, configs, software, inputs, outputs

async def lifespan(app: FastAPI):
    await init_db()
    yield
    print("end")

app = FastAPI(lifespan=lifespan)

# Register all routers
app.include_router(devices.router)
app.include_router(configs.router)
app.include_router(software.router)
app.include_router(inputs.router)
app.include_router(outputs.router)