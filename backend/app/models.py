from sqlmodel import Field, SQLModel, Relationship
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, Literal
from datetime import time

# Database models

class Software(SQLModel, table=True):
    __tablename__ = "software"
    id: int | None = Field(default=None, primary_key=True)
    name: str

class Device(SQLModel, table=True):
    __tablename__ = "devices"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    slx_model: str | None = None
    device_type: str | None = None
    maintenance_start: time | None = None
    maintenance_end: time | None = None

    # Relationships - 1:1 (jeden config na zariadenie)
    config: Optional["Config"] = Relationship(back_populates="device")

class Config(SQLModel, table=True):
    __tablename__ = "configs"
    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id", unique=True)  # unique=True = 1:1
    software_id: int | None = Field(default=None, foreign_key="software.id")
    time_limit_id: int | None = Field(default=None, foreign_key="time_limits.id")
    output_path: str | None = None
    port: str
    
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
    device_id: int
    port: str
    software: SoftwarePublic | None = None
    inputs: list[InputPublic]
    outputs: list[OutputPublic]
    time_limit: TimeLimitPublic | None = None
    output_path: str | None = None

class DeviceDetailPublic(BaseModel):
    id: int
    name: str
    slx_model: str | None = None
    device_type: str | None = None
    maintenance_start: time | None = None
    maintenance_end: time | None = None
    config: ConfigPublic | None = None  # ← Zmenené z list na Optional
    
    class Config:
        from_attributes = True

class DevicePublic(BaseModel):
    id: int
    name: str
    slx_model: str | None = None
    device_type: str | None = None
    maintenance_start: time | None = None
    maintenance_end: time | None = None

    class Config:
        from_attributes = True

#Response pre server

class ServerStatusPublic(BaseModel):
    status: str

class ServerDeviceSoftwarePublic(BaseModel):
    name: str


class ServerDevicePublic(BaseModel):
    name: str
    maintenance_start: str
    maintenance_end: str
    device_type: str | None = None
    software: list[ServerDeviceSoftwarePublic]


class ServerDevicesPublic(BaseModel):
    devices: list[ServerDevicePublic]


class ServerSyncDeviceTypePublic(BaseModel):
    name: str


class ServerSyncDevicePublic(BaseModel):
    name: str
    maintenance_start: str
    maintenance_end: str
    device_type: ServerSyncDeviceTypePublic
    software: list[ServerDeviceSoftwarePublic]


class ServerSyncPublic(BaseModel):
    status: Literal["ok", "unavailable"]
    devices: list[ServerSyncDevicePublic]

class ServerExperimentPublic(BaseModel):
    job_id: str


class WebRTCGrantRefreshReq(BaseModel):
    grant_token: str

    @field_validator("grant_token")
    @classmethod
    def validate_grant_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("grant_token must not be empty")
        return token


class WebRTCGrantRevokeReq(BaseModel):
    grant_token: str

    @field_validator("grant_token")
    @classmethod
    def validate_grant_token(cls, value: str) -> str:
        token = value.strip()
        if not token:
            raise ValueError("grant_token must not be empty")
        return token


class WebRTCGrantPublic(BaseModel):
    device_name: str
    grant_token: str
    expires_at: str


class WebRTCOfferReq(BaseModel):
    sdp: str
    type: str


class WebRTCOfferPublic(BaseModel):
    sdp: str
    type: str


class WebRTCRevokePublic(BaseModel):
    status: Literal["revoked"]

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
    slx_model: str
    device_type: str | None = None
    maintenance_start: time | None = None
    maintenance_end: time | None = None

    @field_validator("slx_model")
    @classmethod
    def validate_slx_model(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("slx_model must not be empty")
        return cleaned

class ConfigCreate(BaseModel):
    device_id: int
    port: str
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


# ── Experiment request / response models ────────────────────────────────────

class ExperimentSetpointStep(BaseModel):
    duration: float
    value: float


class ExperimentSetpointChanges(BaseModel):
    start_value: float
    steps: list[ExperimentSetpointStep]


class ExperimentInputArgument(BaseModel):
    value: int | float | bool | str
    type: Literal["number", "string", "boolean"]
    unit: str                       # required per spec
    order: int


class ExperimentReq(BaseModel):
    command: Literal["start"]       # any other value → 400
    setpoint_changes: ExperimentSetpointChanges | None = None   # optional per spec
    input_arguments: dict[str, ExperimentInputArgument]
    output_arguments: list[str]
    simulation_time: float
    sample_rate: float
    software_name: str
    device_name: str


# WebSocket-only commands (change / stop)

class ExperimentChangeReq(BaseModel):
    command: Literal["change"]
    input_arguments: dict[str, ExperimentInputArgument]

class ExperimentStopReq(BaseModel):
    command: Literal["stop"]


# ── Experiment response / log models ────────────────────────────────────────

class ExperimentInputHistoryEntry(BaseModel):
    command: str
    input_args: dict[str, ExperimentInputArgument]
    applied_at: float


class ExperimentOutputHistoryEntry(BaseModel):
    time: float
    model_config = ConfigDict(extra="allow")


class ExperimentRunLog(BaseModel):
    input_history: list[ExperimentInputHistoryEntry]
    output_history: list[ExperimentOutputHistoryEntry]
    setpoint_changes: ExperimentSetpointChanges | None = None


class FinishedExperiment(BaseModel):
    device_name: str
    software_name: str
    run: ExperimentRunLog | None
    started_at: str
    finished_at: str | None
    finish_reason: str


class UnfinishedExperiment(BaseModel):
    device_name: str
    software_name: str
    run: None = None
    started_at: str
    finished_at: None = None
    finish_reason: Literal["n/a"] = "n/a"


class ExperimentLog(FinishedExperiment):
    pass


class ExperimentNotFoundResponse(BaseModel):
    detail: str









