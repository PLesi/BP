from sqlmodel import Field, SQLModel, create_engine
from sqlalchemy import func, Column, TIMESTAMP
from datetime import datetime, timezone
from typing import Optional

class User(SQLmodel, table = True):
    __tablename__ = "users" 
    id: int | None = Field(default = None, primary_key = True)
    name: str
    password: str
    is_admin: bool

class Device(SQLModel, table = True):
    __tablename__ = "devices"
    id: int | None = Field(default = None, primary_key = True)
    name: str
    port: int

class Config(SQLModel, table = True):
    __tablename__ = "congfigs"
    id: int | None = Field(default = None, primary_key = True)
    name: str
    device_id: int = Field(foreign_key="device.id")

class Input(SQLModel, table = True):
    __tablename__ = "inputs"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    type: str
    config_id: int = Field(foreign_key="config.id")

class Output(SQLModel, table = True):
    __tablename__ = "outputs"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    type: str
    config_id: int = Field(foreign_key="config.id")

class Experiment(SQLModel, table = True):
    __tablename__ = "experiments"
    id: int | None = Field(default = None, primary_key = True)
    created_at: datetime | None = Field( default= None,
        sa_column=Column(TIMESTAMP(timezone=True), server_default=func.now()))
    name: str
    duration: int
    sample_time: int
    outh_path: str
    device_id: int = Field(foreign_key="device.id")
    user_id: int = Field(foreign_key="user.id")


