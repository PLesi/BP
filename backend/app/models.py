from sqlmodel import Field, SQLModel, Relationship
from pydantic import BaseModel, field_validator
from typing import Optional

# Database models

class Software(SQLModel, table=True):
    __tablename__ = "software"
    id: int | None = Field(default=None, primary_key=True)
    name: str

class Device(SQLModel, table=True):
    __tablename__ = "devices"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    
    # Relationships - 1:1 (jeden config na zariadenie)
    config: Optional["Config"] = Relationship(back_populates="device")

class Config(SQLModel, table=True):
    __tablename__ = "configs"
    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id", unique=True)  # unique=True = 1:1
    software_id: int | None = Field(default=None, foreign_key="software.id")
    time_limit_id: int | None = Field(default=None, foreign_key="time_limits.id")
    output_path: str | None = None
    
    # Relationships
    device: "Device" = Relationship(back_populates="config")
    software: Optional["Software"] = Relationship()
    inputs: list["Input"] = Relationship(back_populates="config")
    outputs: list["Output"] = Relationship(back_populates="config")
    time_limit: Optional["TimeLimit"] = Relationship()

class Input(SQLModel, table=True):
    __tablename__ = "inputs"
    id: int | None = Field(default=None, primary_key=True)
    config_id: int = Field(foreign_key="configs.id")
    type: str
    name: str
    input_limit_id: int | None = Field(default=None, foreign_key="input_limits.id")
    
    # Relationships
    config: "Config" = Relationship(back_populates="inputs")
    input_limit: Optional["InputLimit"] = Relationship()

class Output(SQLModel, table=True):
    __tablename__ = "outputs"
    id: int | None = Field(default=None, primary_key=True)
    config_id: int = Field(foreign_key="configs.id")
    type: str
    name: str
    
    # Relationships
    config: "Config" = Relationship(back_populates="outputs")

class TimeLimit(SQLModel, table=True):
    __tablename__ = "time_limits"
    id: int | None = Field(default=None, primary_key=True)
    period: int
    frequency: int

class InputLimit(SQLModel, table=True):
    __tablename__ = "input_limits"
    id: int | None = Field(default=None, primary_key=True)
    min: float
    max: float

# Response models

class SoftwarePublic(BaseModel):
    id: int
    name: str

class InputLimitPublic(BaseModel):
    id: int
    min: float
    max: float

class InputPublic(BaseModel):
    id: int
    type: str
    name: str
    input_limit: InputLimitPublic | None = None

class OutputPublic(BaseModel):
    id: int
    type: str
    name: str

class TimeLimitPublic(BaseModel):
    id: int
    period: int
    frequency: int

class ConfigPublic(BaseModel):
    id: int
    software: SoftwarePublic | None = None
    inputs: list[InputPublic]
    outputs: list[OutputPublic]
    time_limit: TimeLimitPublic | None = None
    output_path: str | None = None

class DeviceDetailPublic(BaseModel):
    id: int
    name: str
    config: ConfigPublic | None = None  # ← Zmenené z list na Optional
    
    class Config:
        from_attributes = True

class DevicePublic(BaseModel):
    id: int
    name: str

# Create modely

class SoftwareCreate(BaseModel):
    name: str

class TimeLimitCreate(BaseModel):
    period: int
    frequency: int

class InputLimitCreate(BaseModel):
    min: float
    max: float

class DeviceCreate(BaseModel):
    name: str

class ConfigCreate(BaseModel):
    device_id: int
    software_id: int | None = None
    time_limit: TimeLimitCreate | None = None
    output_path: str | None = None

class InputCreate(BaseModel):
    config_id: int
    type: str
    name: str
    input_limit: InputLimitCreate | None = None

class OutputCreate(BaseModel):
    config_id: int
    type: str
    name: str