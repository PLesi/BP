from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .db import init_db
from .routers import devices, configs, software, inputs, outputs, experiments, server

async def lifespan(app: FastAPI):
    await init_db()
    yield
    print("end")

app = FastAPI(lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # V produkcii použite konkrétne domény
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(devices.router)
app.include_router(configs.router)
app.include_router(software.router)
app.include_router(inputs.router)
app.include_router(outputs.router)
app.include_router(experiments.router)
app.include_router(server.router)