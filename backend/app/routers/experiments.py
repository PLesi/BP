from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json
import asyncio

from ..models import ExperimentReq, ExperimentChangeReq
from ..db import get_session
from ..websocket_manager import ws_manager
from ..services.services import validate_experiment, get_task_device_id, calculate_estimated_wait_time
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

    if not redis_client.exists(f"experiment:{task_id}"):
        device_id = get_task_device_id(task_id)
        if device_id is not None:
            info = calculate_estimated_wait_time(device_id, task_id)
            await websocket.send_json({"status": "queued", **info})

    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"ws:{task_id}")
    done_event = asyncio.Event()

    async def listen_redis():
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message and message['type'] == 'message':
                data = json.loads(message['data'])
                await websocket.send_json(data)

                if data.get('status') in ('completed', 'failed', 'stopped'):
                    done_event.set()
                    break

            await asyncio.sleep(0.01)

    async def listen_client():
        """Accept change/stop commands from the WS client."""
        try:
            while not done_event.is_set():
                msg = await websocket.receive_json()
                command = msg.get("command")
                if command == "change":
                    try:
                        req = ExperimentChangeReq.model_validate(msg)
                        change_payload = json.dumps({
                            "input_args": {k: v.model_dump() for k, v in req.input_arguments.items()}
                        })
                        redis_client.lpush(f"input_changes:{task_id}", change_payload)
                        await websocket.send_json({"status": "change_accepted"})
                    except Exception as exc:
                        await websocket.send_json({"error": f"Invalid change request: {exc}"})
                elif command == "stop":
                    redis_client.lpush(f"stop_signal:{task_id}", "1")
                    await websocket.send_json({"status": "stop_accepted"})
                else:
                    await websocket.send_json({"error": f"Unsupported command: {command!r}"})
        except WebSocketDisconnect:
            done_event.set()

    try:
        redis_task = asyncio.create_task(listen_redis())
        client_task = asyncio.create_task(listen_client())
        done, pending = await asyncio.wait(
            [redis_task, client_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(websocket, task_id)
        pubsub.unsubscribe(f"ws:{task_id}")
        pubsub.close()

