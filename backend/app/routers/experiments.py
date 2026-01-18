from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import uuid

from ..models import Device, Config, Input, ExperimentRun
from ..db import get_session
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/experiments", tags=["experiments"])


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


@router.post("/run")
async def run_experiment(
    experiment: ExperimentRun,
    session: AsyncSession = Depends(get_session)
):
    """Spustí experiment v Dramatiq queue"""
    
    # Import task here to avoid circular imports
    from ..tasks import run_experiment_task
    
    # Validuj všetko
    device = await validate_experiment(
        session,
        experiment.device_id,
        experiment.input_values,
        experiment.period,
        experiment.frequency
    )
    
    # Generate unique task_id
    task_id = str(uuid.uuid4())
    
    # Pošli do Dramatiq queue
    run_experiment_task.send_with_options(
        task_id,
        experiment.device_id,
        experiment.input_values,
        experiment.period,
        experiment.frequency
    )
    
    return {
        "task_id": task_id,
        "status": "queued",
        "device_id": device.id,
        "device_name": device.name,
        "input_values": experiment.input_values,
        "period": experiment.period,
        "frequency": experiment.frequency
    }


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for receiving experiment results"""
    await ws_manager.connect(websocket, task_id)
    try:
        while True:
            # Keep connection alive and wait for messages
            data = await websocket.receive_text()
            # Client can send heartbeat or other messages if needed
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id)


class WebSocketNotification(BaseModel):
    task_id: str
    message: dict


@router.post("/ws-notify")
async def notify_websocket_clients(notification: WebSocketNotification):
    """Internal endpoint for Dramatiq workers to send results via WebSocket"""
    await ws_manager.send_to_task_subscribers(
        notification.task_id,
        notification.message
    )
    return {"status": "sent"}


@router.get("/status/{task_id}")
async def get_experiment_status(task_id: str):
    """
    Polling endpoint (fallback if WebSocket not available)
    Note: Without storing results, this will only show if task is in queue
    """
    return {
        "task_id": task_id,
        "status": "unknown",
        "message": "Use WebSocket connection for real-time updates"
    }
    
    