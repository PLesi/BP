from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Config, ConfigCreate, ConfigPublic, Device, TimeLimit, Software, Input
from ..db import get_session


router = APIRouter(prefix="/configs", tags=["configs"])

@router.get("/{id}", response_model=ConfigPublic)
async def get_config(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = (
        select(Config)
        .where(Config.id == id)
        .options(  
            selectinload(Config.software),
            selectinload(Config.inputs).selectinload(Input.input_limit),
            selectinload(Config.outputs),
            selectinload(Config.time_limit)
        )
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    return config


@router.post("", response_model=ConfigPublic)
async def create_config(
    config: ConfigCreate,
    session: AsyncSession = Depends(get_session)
):
    # Does device exist?
    device_stmt = select(Device).where(Device.id == config.device_id)
    device_result = await session.execute(device_stmt)
    device = device_result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    # Does software exist?    
    if config.software_id:
        software_stmt = select(Software).where(Software.id == config.software_id)
        software_result = await session.execute(software_stmt)
        software = software_result.scalar_one_or_none()
        
        if not software:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Software not found"
            )

    # Create time limits  
    time_limit_id = None
    if config.time_limit:
        db_time_limit = TimeLimit(
            period=config.time_limit.period,
            frequency=config.time_limit.frequency
        )
        session.add(db_time_limit)
        await session.flush()
        time_limit_id = db_time_limit.id

    # Create config
    db_config = Config(
        device_id=config.device_id,
        software_id=config.software_id,  
        time_limit_id=time_limit_id,
        output_path=config.output_path
    )

    session.add(db_config)
    await session.commit()
    
    # Reload with relationships
    stmt = select(Config).where(Config.id == db_config.id).options(
        selectinload(Config.software),
        selectinload(Config.time_limit),
        selectinload(Config.inputs).selectinload(Input.input_limit),
        selectinload(Config.outputs)
    )
    result = await session.execute(stmt)
    db_config = result.scalar_one()

    return db_config


@router.patch("/{id}", response_model=ConfigPublic)
async def update_config(
    id: int,
    config_update: ConfigCreate, 
    session: AsyncSession = Depends(get_session)
):
    # Check if config, device and sw exist
    stmt = select(Config).where(Config.id == id)
    result = await session.execute(stmt)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    if config_update.device_id != db_config.device_id:
        device_stmt = select(Device).where(Device.id == config_update.device_id)
        device_result = await session.execute(device_stmt)
        device = device_result.scalar_one_or_none()
        
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )
        
        db_config.device_id = config_update.device_id
    
    if config_update.software_id:
        software_stmt = select(Software).where(Software.id == config_update.software_id)
        software_result = await session.execute(software_stmt)
        software = software_result.scalar_one_or_none()
        
        if not software:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Software not found"
            )
        
        db_config.software_id = config_update.software_id
    else:
        db_config.software_id = None
    
    # Change the time limits
    if config_update.time_limit:
        db_time_limit = TimeLimit(
            period=config_update.time_limit.period,
            frequency=config_update.time_limit.frequency
        )
        session.add(db_time_limit)
        await session.flush()
        db_config.time_limit_id = db_time_limit.id
    else:
        db_config.time_limit_id = None
    
    # Update output_path
    db_config.output_path = config_update.output_path
    
    session.add(db_config)
    await session.commit()
    await session.refresh(db_config)
    
    return db_config


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_config(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Config).where(Config.id == id)
    result = await session.execute(stmt)
    db_config = result.scalar_one_or_none()
    
    if not db_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    await session.delete(db_config)
    await session.commit()
    
    return None