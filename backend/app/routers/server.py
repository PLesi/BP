from fastapi import APIRouter, Depends, HTTPException, status, Header, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
import logging
import os
import uuid
import json
import asyncio
from datetime import datetime, UTC, timedelta
from pydantic import ValidationError

_log = logging.getLogger(__name__)

from ..db import get_session
from ..models import (
    ServerDevicesPublic,
    ServerStatusPublic,
    ServerSyncPublic,
    ServerExperimentPublic,
    ExperimentReq,
    ExperimentChangeReq,
    FinishedExperiment,
    UnfinishedExperiment,
    ExperimentNotFoundResponse,
)
from ..services.device_services import get_devices_with_details, check_device_online
from ..services.services import validate_experiment, verify_api_key
from ..redis_client import redis_client
from ..tasks import device_worker

router = APIRouter(prefix="/api/server", tags=["server"])
ws_router = APIRouter(tags=["server"])


def verify_ws_api_key(websocket: WebSocket):
    expected_key = os.getenv("API_KEY")
    if not expected_key:
        return False
    provided = websocket.headers.get("x-api-key")
    return provided == expected_key


def _clear_stale_lock(device_id: int) -> bool:
    lock_key = f"device_lock:{device_id}"
    raw = redis_client.get(lock_key)
    if not raw:
        return False

    try:
        lock_data = json.loads(raw)
    except json.JSONDecodeError:
        # Old-format lock from before metadata was added.
        redis_client.delete(lock_key)
        return True

    if not isinstance(lock_data, dict):
        redis_client.delete(lock_key)
        return True

    acquired_at = lock_data.get("acquired_at")
    if not acquired_at:
        redis_client.delete(lock_key)
        return True

    try:
        acquired_dt = datetime.fromisoformat(acquired_at)
    except ValueError:
        redis_client.delete(lock_key)
        return True

    age_seconds = (datetime.now(UTC) - acquired_dt).total_seconds()
    if age_seconds > 6 * 60 * 60:
        redis_client.delete(lock_key)
        return True

    return False


async def enqueue_server_experiment(
    experiment: ExperimentReq,
    session: AsyncSession,
) -> str:
    device = await validate_experiment(
        session,
        device_name=experiment.device_name,
        input_arguments=experiment.input_arguments,
        simulation_time=experiment.simulation_time,
        sample_rate=experiment.sample_rate,
    )

    if not device.config.software or device.config.software.name != experiment.software_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Software '{experiment.software_name}' not found on device '{experiment.device_name}'"
        )

    if redis_client.exists(f"device_lock:{device.id}"):
        if not _clear_stale_lock(device.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Device is currently busy with another experiment"
            )

    job_id = str(uuid.uuid4())
    queue_item = {
        "task_id": job_id,
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

    redis_client.set(
        f"experiment:{job_id}",
        json.dumps(
            {
                "device_name": experiment.device_name,
                "software_name": experiment.software_name,
                "run": None,
                "started_at": datetime.now(UTC).isoformat(),
                "finished_at": None,
                "finish_reason": "n/a",
            }
        ),
    )

    redis_client.lpush(f"device_queue:{device.id}", json.dumps(queue_item))
    device_worker.send(device.id)
    return job_id


async def stream_job_updates(websocket: WebSocket, job_id: str):
    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"ws:{job_id}")
    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True)
            if message and message.get("type") == "message":
                payload = json.loads(message["data"])
                await websocket.send_json({"job_id": job_id, **payload})
                if payload.get("status") in ("completed", "stopped", "failed"):
                    break
            await asyncio.sleep(0.05)
    finally:
        pubsub.unsubscribe(f"ws:{job_id}")
        pubsub.close()

@router.get("/status",response_model=ServerStatusPublic)
async def get_server_status( _ : None = Depends(verify_api_key)):
    return{ "status": "ok" }

@router.get("/devices", response_model=ServerDevicesPublic)
async def get_server_devices(
    _: None = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session)
):
    db_devices = await get_devices_with_details(session)
    devices_payload = []

    for device in db_devices:
        if not device.config or not device.config.port:
            continue

        if not device.slx_model:
            _log.info(
                "[get_server_devices] device=%r online=%s usable=%s reason=%r",
                device.name, False, False, "Missing slx_model",
            )
            continue

        slx_model = device.slx_model

        res = check_device_online(port=device.config.port, slx_model=slx_model)
        _log.info(
            "[get_server_devices] device=%r online=%s usable=%s reason=%r",
            device.name, res.get("online"), res.get("usable"), res.get("reason"),
        )

        # check_device_online returns dict, not object
        if not (res.get("online") and res.get("usable")):
            continue

        software_name = "unknown"
        if device.config.software and device.config.software.name:
            software_name = device.config.software.name

        devices_payload.append(
            {
                "name": device.name,
                "maintenance_start": str(device.maintenance_start) if device.maintenance_start else None,
                "maintenance_end": str(device.maintenance_end) if device.maintenance_end else None,
                "device_type": {"name": device.device_type} if device.device_type else None,
                "software": [{"name": software_name}],
            }
        )

    return {"devices": devices_payload}

@router.get("/sync", response_model=ServerSyncPublic)
async def get_server_sync(
    _: None = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session)
):
    db_devices = await get_devices_with_details(session)
    devices_payload = []

    for device in db_devices:
        software_name = "unknown"
        if device.config and device.config.software and device.config.software.name:
            software_name = device.config.software.name

        devices_payload.append(
            {
                "name": device.name,
                "maintenance_start": str(device.maintenance_start) if device.maintenance_start else None,
                "maintenance_end": str(device.maintenance_end) if device.maintenance_end else None,
                "device_type": {"name": device.device_type} if device.device_type else None,
                "software": [{"name": software_name}],
            }
        )

    # TODO: wire real readiness state here when availability source is implemented.
    return {
        "status": "ok",
        "devices": devices_payload,
    } 

@router.post("/experiments/queue", response_model=ServerExperimentPublic)
async def queue_experiment(
    experiment: ExperimentReq,
    _: None = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
):
    job_id = await enqueue_server_experiment(experiment, session)
    return {"job_id": job_id}


@router.get(
    "/experiments/{job_id}",
    response_model=FinishedExperiment | UnfinishedExperiment,
    responses={404: {"model": ExperimentNotFoundResponse}},
)
async def get_experiment(
    job_id: str,
    _: None = Depends(verify_api_key),
):
    raw = redis_client.get(f"experiment:{job_id}")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment with job_id not found",
        )

    return json.loads(raw)


@ws_router.websocket("/ws/server/experiments")
async def ws_server_experiments(
    websocket: WebSocket,
    session: AsyncSession = Depends(get_session),
):
    if not verify_ws_api_key(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    await websocket.send_json({"status": "ready", "message": "WebSocket connected"})

    active_job: list[str | None] = [None]
    disconnect_event = asyncio.Event()

    async def handle_client_messages():
        try:
            while not disconnect_event.is_set():
                message = await websocket.receive_json()
                command = message.get("command")

                if command == "start":
                    if active_job[0]:
                        await websocket.send_json({"error": "An experiment is already running"})
                        continue
                    try:
                        req = ExperimentReq.model_validate(message)
                    except ValidationError as exc:
                        await websocket.send_json({"error": "Invalid request", "detail": exc.errors()})
                        continue
                    try:
                        job_id = await enqueue_server_experiment(req, session)
                    except HTTPException as exc:
                        await websocket.send_json({"error": exc.detail, "status_code": exc.status_code})
                        continue
                    active_job[0] = job_id
                    await websocket.send_json({"job_id": job_id, "status": "queued"})

                elif command == "change":
                    if not active_job[0]:
                        await websocket.send_json({"error": "No active experiment to change"})
                        continue
                    try:
                        req = ExperimentChangeReq.model_validate(message)
                        redis_client.lpush(
                            f"input_changes:{active_job[0]}",
                            json.dumps({"input_args": {k: v.model_dump() for k, v in req.input_arguments.items()}}),
                        )
                        await websocket.send_json({"status": "change_accepted"})
                    except Exception as exc:
                        await websocket.send_json({"error": f"Invalid change request: {exc}"})

                elif command == "stop":
                    if not active_job[0]:
                        await websocket.send_json({"error": "No active experiment to stop"})
                        continue
                    redis_client.lpush(f"stop_signal:{active_job[0]}", "1")
                    await websocket.send_json({"status": "stop_accepted"})

                else:
                    await websocket.send_json({"error": f"Unsupported command: {command!r}"})
        except WebSocketDisconnect:
            disconnect_event.set()

    async def stream_experiment_updates():
        try:
            while not disconnect_event.is_set():
                job_id = active_job[0]
                if not job_id:
                    await asyncio.sleep(0.05)
                    continue
                pubsub = redis_client.pubsub()
                pubsub.subscribe(f"ws:{job_id}")
                try:
                    while not disconnect_event.is_set():
                        msg = pubsub.get_message(ignore_subscribe_messages=True)
                        if msg and msg.get("type") == "message":
                            payload = json.loads(msg["data"])
                            await websocket.send_json({"job_id": job_id, **payload})
                            if payload.get("status") in ("completed", "stopped", "failed"):
                                final_raw = redis_client.get(f"experiment:{job_id}")
                                if final_raw:
                                    await websocket.send_json({
                                        "job_id": job_id,
                                        "status": "final",
                                        "result": json.loads(final_raw),
                                    })
                                active_job[0] = None
                                break
                        await asyncio.sleep(0.05)
                finally:
                    pubsub.unsubscribe(f"ws:{job_id}")
                    pubsub.close()
        except Exception:
            disconnect_event.set()

    client_task = asyncio.create_task(handle_client_messages())
    stream_task = asyncio.create_task(stream_experiment_updates())
    try:
        done, pending = await asyncio.wait(
            [client_task, stream_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
