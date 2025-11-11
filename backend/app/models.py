from sqlmodel import Field, SQLModel, create_engine
from sqlalchemy import func, Column, TIMESTAMP
from pydantic import field_validator, BaseModel
from datetime import datetime, timezone
from typing import Optional


# DB representation
class User(SQLModel, table = True):
    __tablename__ = "users" 
    id: int | None = Field(default = None, primary_key = True)
    email: str
    password: str
    is_admin: bool = Field(default=False)

# What api recieve
class UserCreate(SQLModel):
    email: str
    password: str

class UserRegister(SQLModel):
    email: str
    password: str
    password_confirm: str

    @field_validator('password_confirm')
    def password_match(cls, value, info):
        if 'password' in info.data and value != info.data['password']:
            raise ValueError("Passwords do not match")
        return value

# What api return
class UserPublic(SQLModel):
    id: int
    email: str

class UserRead(SQLModel):
    id: int
    email: str
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
    __tablename__ = "configs"
    id: int | None = Field(default = None, primary_key = True)
    name: str
    device_id: int = Field(foreign_key="devices.id")

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
    config_id: int = Field(foreign_key="configs.id")

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
    config_id: int = Field(foreign_key="configs.id")

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
    device_id: int = Field(foreign_key="devices.id")
    user_id: int = Field(foreign_key="users.id")

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






