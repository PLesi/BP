from sqlmodel import Field, SQLModel, create_engine
from sqlalchemy import func, Column, TIMESTAMP
from datetime import datetime, timezone
from typing import Optional

# DB representation
class User(SQLmodel, table = True):
    __tablename__ = "users" 
    id: int | None = Field(default = None, primary_key = True)
    name: str
    password: str
    is_admin: bool

# What api recieve
class UserCreate(SQLModel):
    name: str
    password: str

# What api return
class UserPublic(SQLModel):
    id: int
    name: str

class UserRead(SQLModel):
    id: int
    name: str
    is_admin: bool

class Device(SQLModel, table = True):
    __tablename__ = "devices"
    id: int | None = Field(default = None, primary_key = True)
    name: str
    port: int

class DeviceCreate(SQLModel):
    name: str
    port: str

class DevicePublic(SQLModel):
    id: int
    name: str
    port: int

class Config(SQLModel, table = True):
    __tablename__ = "congfigs"
    id: int | None = Field(default = None, primary_key = True)
    name: str
    device_id: int = Field(foreign_key="device.id")

class ConfigCreate(SQLModel):
    name: str
    device_id: int

class ConfigPublic(SQLModel):
    id: int
    name: str
    device_id: int

class Input(SQLModel, table = True):
    __tablename__ = "inputs"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    type: str
    config_id: int = Field(foreign_key="config.id")

class InputCreate(SQLModel):
    name: str
    type: str
    config_id: int

class InputPublic(SQLModel):
    id: int
    name: str
    type: str
    config_id: int

class Output(SQLModel, table = True):
    __tablename__ = "outputs"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    type: str
    config_id: int = Field(foreign_key="config.id")

class OutputCreate(SQLModel):
    name: str
    type: str
    config_id: int

class OutputPublic(SQLModel):
    id: int
    name: str
    type: str
    config_id: int

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

class ExperimentCreate(SQLModel):
    name: str
    duration: int
    sample_time: int
    outh_path: str
    device_id: int
    user_id: int

class ExperimentPublic(SQLModel):
    id: int
    created_at: datetime
    name: str
    duration: int
    sample_time: int
    outh_path: str
    device_id: int
    user_id: int









