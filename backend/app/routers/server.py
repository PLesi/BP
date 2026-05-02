from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
import os

from ..db import get_session
from ..models import ServerDevicesPublic, ServerStatusPublic, ServerSyncPublic, ServerExperimentPublic, ExperimentReq
from ..services.device_services import get_devices_with_details, check_device_online
from ..services.services import validate_experiment

router = APIRouter(prefix="/api/server", tags=["server"])

def verify_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    expectedKey = os.getenv("API_KEY")
    if not expectedKey:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key is not found"
        )
    if x_api_key != expectedKey:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )

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

@router.post("/experiments/queue",response_model=ServerExperimentPublic)
async def queue_experiment(experiment: ExperimentReq, _: None = Depends(verify_api_key)
                           ):
    if experiment.command != "start":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid command"
        )    
    # TODO: ADD parameter validations in device_services, queue.
    validate_experiment(se)


 
