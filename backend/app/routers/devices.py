from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Device, DeviceCreate, DevicePublic, DeviceDetailPublic, Config, Input, Output, TimeLimit, InputLimit
from ..db import get_session
from ..services.device_services import get_devices_with_details


router = APIRouter(prefix="/devices", tags=["devices"])

@router.get("", response_model=list[DeviceDetailPublic])  
async def get_devices(session: AsyncSession = Depends(get_session)):
    return await get_devices_with_details(session)

@router.get("/{id}", response_model=DeviceDetailPublic)
async def get_device(id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Device).where(Device.id == id).options(
        selectinload(Device.config).selectinload(Config.software),
        selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
        selectinload(Device.config).selectinload(Config.outputs),
        selectinload(Device.config).selectinload(Config.time_limit)
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()  
    
    if not device:  
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    return device

@router.post("", response_model=DevicePublic)  
async def create_device(
    device: DeviceCreate,
    session: AsyncSession = Depends(get_session)
):
    clean_device_type = None
    if device.device_type:
        clean_device_type = device.device_type.strip() or None

    db_device = Device(
        name=device.name,
        device_type=clean_device_type,
        maintenance_start=device.maintenance_start,
        maintenance_end=device.maintenance_end,
    )
    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    return db_device

@router.patch("/{id}", response_model=DevicePublic)
async def update_device(
    id: int,
    device: DeviceCreate,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Device).where(Device.id == id)
    result = await session.execute(stmt)
    db_device = result.scalar_one_or_none()

    if not db_device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )
    
    db_device.name = device.name
    if "device_type" in device.model_fields_set:
        if device.device_type is None:
            db_device.device_type = None
        else:
            db_device.device_type = device.device_type.strip() or None
    db_device.maintenance_start = device.maintenance_start
    db_device.maintenance_end = device.maintenance_end

    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    return db_device

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = (
        select(Device)
        .where(Device.id == id)
        .options(
            selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
            selectinload(Device.config).selectinload(Config.outputs),
            selectinload(Device.config).selectinload(Config.time_limit),
        )
    )
    result = await session.execute(stmt)
    db_device = result.scalar_one_or_none()

    if not db_device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    if db_device.config:
        config = db_device.config

        # Delete inputs and their limits
        for inp in config.inputs:
            if inp.input_limit:
                await session.delete(inp.input_limit)
            await session.delete(inp)

        # Delete outputs
        for out in config.outputs:
            await session.delete(out)

        # Delete time limit
        if config.time_limit:
            await session.delete(config.time_limit)

        await session.delete(config)

    await session.delete(db_device)
    await session.commit()
    return None