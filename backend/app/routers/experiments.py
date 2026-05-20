from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json
import asyncio

from ..models import ExperimentReq
from ..db import get_session
from ..websocket_manager import ws_manager
from ..services.services import validate_experiment
from ..redis_client import redis_client
from ..tasks import device_worker


router = APIRouter(prefix="/experiments", tags=["experiments"])

@router.post("/run")
async def run_experiment(
    experiment: ExperimentReq,
    session: AsyncSession = Depends(get_session)
):
    device = await validate_experiment(
        session,
        device_name=experiment.device_name,
        input_arguments=experiment.input_arguments,
        simulation_time=experiment.simulation_time,
        sample_rate=experiment.sample_rate,
    )

    task_id = str(uuid.uuid4())

    queue_item = {
        "task_id": task_id,
        "device_id": device.id,
        "device_name": experiment.device_name,
        "software_name": experiment.software_name,
        "port": device.config.port,
        "output_path": device.config.output_path or "out.txt",
        "slx_model": device.slx_model,
        "input_arguments": {k: v.model_dump() for k, v in experiment.input_arguments.items()},
        "output_arguments": experiment.output_arguments,
        "simulation_time": experiment.simulation_time,
        "sample_rate": experiment.sample_rate,
        "setpoint_changes": experiment.setpoint_changes.model_dump() if experiment.setpoint_changes else None,
    }
    redis_client.lpush(f"device_queue:{device.id}", json.dumps(queue_item))
    device_worker.send(device.id)

    return {"task_id": task_id}


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect(websocket, task_id)
    
    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"ws:{task_id}")
    
    async def listen_redis():
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message and message['type'] == 'message':
                data = json.loads(message['data'])
                await websocket.send_json(data)
                
                if data.get('status') == 'completed':
                    break
            
            await asyncio.sleep(0.01)
    
    try:
        await listen_redis()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, task_id)
        pubsub.unsubscribe(f"ws:{task_id}")
        pubsub.close()

