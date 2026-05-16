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

    # Validate software exists on the device
    if not device.config.software or device.config.software.name != experiment.software_name:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Software '{experiment.software_name}' not found on device '{experiment.device_name}'"
        )

    # Check device is not already locked (busy)
    if redis_client.exists(f"device_lock:{device.id}"):
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
                if payload.get("status") == "completed":
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
        # Device without config cannot be usable
        if not device.config or not device.config.port:
            continue

        # Build model name for Simulink check
        slx_model = device.name if device.name.endswith(".slx") else f"{device.name}.slx"

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
                "maintenance_start": "04:00:00",
                "maintenance_end": "04:05:00",
                "device_type": device.device_type,
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
                "maintenance_start": "04:00:00",
                "maintenance_end": "04:05:00",
                "device_type": {"name": device.device_type or ""},
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

    try:
        while True:
            message = await websocket.receive_json()
            command = message.get("command")

            if command != "start":
                await websocket.send_json({"error": "Unsupported command. Use command='start'."})
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

            await websocket.send_json({"job_id": job_id, "status": "queued"})
            await stream_job_updates(websocket, job_id)
            final_raw = redis_client.get(f"experiment:{job_id}")
            if final_raw:
                await websocket.send_json({"job_id": job_id, "status": "final", "result": json.loads(final_raw)})
    except WebSocketDisconnect:
        return
