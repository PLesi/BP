"""
Background tasks for experiments using Dramatiq
"""
import dramatiq
import asyncio
import json
import redis
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from sqlalchemy.orm import selectinload
import httpx

# Import dramatiq config first to set up broker
from .dramatiq_config import redis_broker
from .models import Device, Config, Input
from .db import DATABASE_URL


redis_client = redis.Redis(host='localhost',port=6379,decode_responses=True)

def acquire_device_lock(device_id: int, timeout: int = 3600) -> bool:
    lock_key = f"device_lock:{device_id}"
    return redis_client.set(lock_key, "locked", nx=True, ex=timeout)

def release_device_lock(device_id: int):
    lock_key = f"device_lock:{device_id}"
    redis_client.delete(lock_key)

# WebSocket notification helper
async def send_websocket_notification(task_id: str, message: dict):
    """Send notification to WebSocket clients via HTTP request to FastAPI"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "http://localhost:8000/experiments/ws-notify",
                json={"task_id": task_id, "message": message},
                timeout=5.0
            )
    except Exception as e:
        print(f"Failed to send WebSocket notification: {e}")

@dramatiq.actor(max_retries=3, time_limit=3600000)  # 1 hour timeout
def run_experiment_task(
    task_id: str,
    device_id: int, 
    input_values: dict, 
    period: int, 
    frequency: int, 
    retry_count=0
    ):
    MAX_QUEUE_RETRIES = 10

    if not acquire_device_lock(device_id):
        if retry_count <= MAX_QUEUE_RETRIES:
            # Device is busy - reschedule after 60 seconds
            asyncio.run(send_websocket_notification(task_id, {
                "status": "waiting",
                "message": f"Device busy for too long. Exceeded {MAX_QUEUE_RETRIES} retry attempts."
            }))
            return # give up
        run_experiment_task.send_with_options(
            args=(task_id, device_id, input_values, period, frequency),
            delay=60000
        )
        return
    try:    
        asyncio.run(_run_experiment_async(task_id, device_id, input_values, period, frequency))
    finally:
        release_device_lock(device_id)

async def _run_experiment_async(task_id: str, device_id: int, input_values: dict, period: int, frequency: int) -> dict:
    """Async implementation of experiment execution"""
    
    # Send initial status via WebSocket
    await send_websocket_notification(task_id, {
        "task_id": task_id,
        "status": "running",
        "device_id": device_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Create async engine for this task
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    try:
        async with async_session_maker() as session:
            # Load device with config
            stmt = (
                select(Device)
                .where(Device.id == device_id)
                .options(
                    selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
                    selectinload(Device.config).selectinload(Config.outputs),
                    selectinload(Device.config).selectinload(Config.software)
                )
            )
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()
            
            if not device or not device.config:
                error_result = {
                    "task_id": task_id,
                    "status": "error",
                    "error": "Device or config not found",
                    "timestamp": datetime.utcnow().isoformat()
                }
                await send_websocket_notification(task_id, error_result)
                return error_result
            
            # Prepare experiment data
            experiment_data = {
                "device_id": device_id,
                "device_name": device.name,
                "input_values": input_values,
                "period": period,
                "frequency": frequency,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Run the actual experiment
            try:
                output_values = await _execute_device_software(
                    device.config,
                    input_values,
                    period,
                    frequency,
                    task_id  # Pass task_id for progress updates
                )
                
                # Save results to output_path if configured
                if device.config.output_path:
                    await _save_experiment_results(
                        device.config.output_path,
                        experiment_data,
                        output_values
                    )
                
                success_result = {
                    "task_id": task_id,
                    "status": "completed",
                    "device_id": device_id,
                    "device_name": device.name,
                    "input_values": input_values,
                    "output_values": output_values,
                    "output_path": device.config.output_path,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Send success via WebSocket
                await send_websocket_notification(task_id, success_result)
                
                return success_result
                
            except Exception as e:
                error_result = {
                    "task_id": task_id,
                    "status": "error",
                    "error": f"Experiment execution failed: {str(e)}",
                    "device_id": device_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await send_websocket_notification(task_id, error_result)
                return error_result
            
    except Exception as e:
        error_result = {
            "task_id": task_id,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
        await send_websocket_notification(task_id, error_result)
        return error_result
    finally:
        await engine.dispose()


async def _save_experiment_results(output_path: str, experiment_data: dict, output_values: dict):
    """Save experiment results to file"""
    
    # Create output directory if it doesn't exist
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"experiment_{timestamp}.json"
    
    # Combine all data
    result_data = {
        **experiment_data,
        "output_values": output_values
    }
    
    # Save to file
    with open(filename, 'w') as f:
        json.dump(result_data, f, indent=2)
    
    print(f"Results saved to: {filename}")
