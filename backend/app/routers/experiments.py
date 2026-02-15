from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json
import asyncio

from ..models import ExperimentRun
from ..db import get_session
from ..websocket_manager import ws_manager
from ..services import validate_experiment
from ..redis_client import redis_client
from ..tasks import device_worker


router = APIRouter(prefix="/experiments", tags=["experiments"])

@router.post("/run")
async def run_experiment(
    experiment: ExperimentRun,
    session: AsyncSession = Depends(get_session)
):    

    device = await validate_experiment(
        session,
        experiment.device_id,
        experiment.input_values,
        experiment.period,
        experiment.frequency
    )
    
    # Generate unique task_id
    task_id = str(uuid.uuid4())
    
    queue_item = {
        "task_id": task_id,
        "device_id": experiment.device_id,
        "input_values": experiment.input_values,
        "period": experiment.period,
        "frequency": experiment.frequency
    }
    redis_client.lpush(f"device_queue:{experiment.device_id}", json.dumps(queue_item))
    device_worker.send(experiment.device_id)
    
    return queue_item


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect(websocket, task_id)
    
    # Subscribe to Redis channel for this task
    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"ws:{task_id}")
    
    async def listen_redis():
        """Listen for messages from worker via Redis in non-blocking way"""
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message and message['type'] == 'message':
                data = json.loads(message['data'])
                await websocket.send_json(data)
                
                # Check if experiment is completed
                if data.get('status') == 'completed':
                    break
            
            await asyncio.sleep(0.01)  # Small delay to not block event loop
    
    try:
        # Listen to Redis messages
        await listen_redis()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, task_id)
        pubsub.unsubscribe(f"ws:{task_id}")
        pubsub.close()

