# backend/app/services.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import Header, HTTPException, status
import json
import os
import time
from datetime import datetime, timedelta


from ..models import Device, Config, Input, ExperimentInputArgument
from ..redis_client import redis_client


# Reserved keywords that cannot be used as input parameter names
RESERVED_KEYWORDS = {
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def',
    'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if',
    'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise',
    'return', 'try', 'while', 'with', 'yield',
    'case', 'catch', 'classdef', 'elseif', 'end', 'function', 'otherwise',
    'persistent', 'switch',
    'true', 'false', 'null', 'none', 'var', 'let', 'const', 'void', 'public',
    'private', 'protected', 'static', 'final', 'abstract', 'interface', 'enum',
}


def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server API key is not found")
    if x_api_key != expected_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


async def validate_experiment(
    session: AsyncSession,
    device_name: str,
    input_arguments: dict[str, ExperimentInputArgument],
    simulation_time: float,
    sample_rate: float,
) -> Device:
    stmt = (
        select(Device)
        .where(Device.name == device_name)
        .options(
            selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
            selectinload(Device.config).selectinload(Config.time_limit),
            selectinload(Device.config).selectinload(Config.software),
        )
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_name}' not found"
        )

    if not device.config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device has no configuration"
        )

    if device.maintenance_start and device.maintenance_end:
        now = datetime.now()
        exp_end = now + timedelta(seconds=simulation_time)
        maint_start_dt = now.replace(
            hour=device.maintenance_start.hour,
            minute=device.maintenance_start.minute,
            second=device.maintenance_start.second,
            microsecond=0,
        )
        maint_end_dt = now.replace(
            hour=device.maintenance_end.hour,
            minute=device.maintenance_end.minute,
            second=device.maintenance_end.second,
            microsecond=0,
        )
        # Handle overnight window (e.g. 23:00 – 01:00)
        if maint_end_dt <= maint_start_dt:
            maint_end_dt += timedelta(days=1)
        if now < maint_end_dt and maint_start_dt < exp_end:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Device '{device_name}' is in maintenance window "
                    f"({device.maintenance_start} – {device.maintenance_end}). "
                    "Experiment not allowed during this time."
                ),
            )

    if device.config.time_limit:
        if simulation_time > device.config.time_limit.period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"simulation_time {simulation_time}s exceeds maximum {device.config.time_limit.period}s"
            )
        if sample_rate > device.config.time_limit.frequency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"sample_rate {sample_rate} exceeds maximum {device.config.time_limit.frequency}"
            )

    required_inputs = {inp.name: inp for inp in device.config.inputs}

    # reject reserved keywords saved in DB config
    for input_name in required_inputs:
        if input_name.lower() in RESERVED_KEYWORDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Device configuration error: Input '{input_name}' is a reserved keyword. Please remove or rename this input."
            )

    for input_name in input_arguments:
        if input_name.lower() in RESERVED_KEYWORDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Input name '{input_name}' is a reserved keyword and cannot be used"
            )

    for input_name in required_inputs:
        if input_name not in input_arguments:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required input: {input_name}"
            )

    for input_name in input_arguments:
        if input_name not in required_inputs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown input: {input_name}"
            )

    for input_name, arg in input_arguments.items():
        input_def = required_inputs[input_name]
        value = arg.value
        req_type = arg.type  # "number" | "string" | "boolean" — validated by Pydantic

        if req_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be numeric, got {type(value).__name__}"
                )
        elif req_type == "boolean":
            if not isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be boolean, got {type(value).__name__}"
                )
        elif req_type == "string":
            if not isinstance(value, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be a string, got {type(value).__name__}"
                )

        if input_def.input_limit and isinstance(value, (int, float)):
            if value < input_def.input_limit.min:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' value {value} is below minimum {input_def.input_limit.min}"
                )
            if value > input_def.input_limit.max:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' value {value} exceeds maximum {input_def.input_limit.max}"
                )

    # Inject workspace from DB into each argument so start.py can route correctly
    for input_name, arg in input_arguments.items():
        arg.workspace = required_inputs[input_name].workspace

    return device

def get_task_device_id(task_id: str) -> int | None:
    for key in redis_client.scan_iter("device_queue:*"):
        tasks = redis_client.lrange(key, 0, -1)
        for task_json in tasks:
            try:
                task = json.loads(task_json)
                if task.get('task_id') == task_id:
                    return task.get('device_id')
            except json.JSONDecodeError:
                continue
    return None

def calculate_estimated_wait_time(device_id: int, task_id: str):
    queue_key = f"device_queue:{device_id}"
    queued_tasks = redis_client.lrange(queue_key, 0, -1)

    queue_position = 0

    for idx, task_json in enumerate(queued_tasks):
        try:
            task = json.loads(task_json)
            if task.get('task_id') == task_id:
                queue_position = idx + 1
                break
        except json.JSONDecodeError:
            pass

    return {
        "queue_position": queue_position,
    }
