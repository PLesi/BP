# backend/app/services.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
import json
import time

from .models import Device, Config, Input
from .redis_client import redis_client


async def validate_experiment(
    session: AsyncSession, 
    device_id: int, 
    input_values: dict[str, int | float | bool],
    period: int,
    frequency: int
) -> Device:
    """
    Validuje kompletný experiment:
    - Device existuje
    - Config existuje
    - Všetky required inputy sú prítomné
    - Typy inputov sa zhodujú
    - Input hodnoty sú v limitoch
    - Period a frequency sú v time_limit
    """
    
    # 1. Načítaj device s config a všetkými vzťahmi
    stmt = (
        select(Device)
        .where(Device.id == device_id)
        .options(
            selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
            selectinload(Device.config).selectinload(Config.time_limit)
        )
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    if not device.config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device has no configuration"
        )
    
    # 2. Validuj time_limit (period a frequency)
    if device.config.time_limit:
        if period > device.config.time_limit.period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Period {period}s exceeds maximum {device.config.time_limit.period}s"
            )
        
        if frequency > device.config.time_limit.frequency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Frequency {frequency}s exceeds maximum {device.config.time_limit.frequency}s"
            )
    
    # 3. Vytvor dict inputov podľa názvu pre rýchle vyhľadávanie
    required_inputs = {inp.name: inp for inp in device.config.inputs}
    
    # 4. Skontroluj, že všetky required inputy sú prítomné
    for input_name in required_inputs.keys():
        if input_name not in input_values:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required input: {input_name}"
            )
    
    # 5. Skontroluj, že user neposlal neznáme inputy
    for input_name in input_values.keys():
        if input_name not in required_inputs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown input: {input_name}"
            )
    
    # 6. Validuj typy a limity pre každý input
    for input_name, value in input_values.items():
        input_def = required_inputs[input_name]
        
        # Validuj typ
        if input_def.type == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be int, got {type(value).__name__}"
                )
        
        elif input_def.type == "float":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be float, got {type(value).__name__}"
                )
        
        elif input_def.type == "bool":
            if not isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Input '{input_name}' must be bool, got {type(value).__name__}"
                )
        
        # Validuj limity (ak existujú a hodnota je číselná)
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
    
    return device

def get_task_device_id(task_id: str) -> int | None:
    """
    Find device_id for a given task_id by scanning device queues.

    Args:
        task_id: The unique task identifier

    Returns:
        device_id if found, None othervise
    """
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
    """
    Calculate estimated wait time and queue position for a task.

    Returns:
        dict with:
            - queue_position
            - estimated_wait_time 
    """
    queue_key = f"device_queue:{device_id}"
    lock_key = f"device_lock:{device_id}"

    is_locked = redis_client.exists(lock_key)
    queued_tasks = redis_client.lrange(queue_key, 0, -1)

    queue_position = 0
    total_wait_time = 0
    found = False

    # If device is currently locked, add time for the running task
    if is_locked:
        total_wait_time += 60

    for idx, task_json in enumerate(queued_tasks):
        try: 
            task = json.loads(task_json)
            if task.get('task_id') == task_id:
                queue_position = idx + 1
                found = True
                break
            total_wait_time += task.get('period', 60)
        except json.JSONDecodeError:
            total_wait_time += 60

    return {
        "queue_position": queue_position,
        "estimated_wait_time": total_wait_time
    }