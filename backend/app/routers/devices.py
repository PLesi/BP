from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Device, DeviceCreate, DevicePublic, DeviceDetailPublic, Config, Input
from ..db import get_session


router = APIRouter(prefix="/devices", tags=["devices"])

@router.get("", response_model=list[DeviceDetailPublic])  
async def get_devices(session: AsyncSession = Depends(get_session)):
    # load everything NOW ( eager load )
    stmt = select(Device).options(
        selectinload(Device.config).selectinload(Config.software), 
        selectinload(Device.config).selectinload(Config.inputs).selectinload(Input.input_limit),
        selectinload(Device.config).selectinload(Config.outputs),
        selectinload(Device.config).selectinload(Config.time_limit)
    )
    results = await session.execute(stmt)
    return results.scalars().all() 

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
    db_device = Device(name=device.name)
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
    session.add(db_device)
    await session.commit()
    await session.refresh(db_device)
    return db_device

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    id: int,
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
    
    await session.delete(db_device)    
    await session.commit()
    return None