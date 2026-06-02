from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Output, OutputCreate, OutputPublic, Config
from ..db import get_session
from ..services.services import verify_admin_api_key

router = APIRouter(prefix="/outputs", tags=["outputs"], dependencies=[Depends(verify_admin_api_key)])

def check_if_output_exists(output: Output | None):
    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Output not found"
        )

@router.get("", response_model=list[OutputPublic])
async def get_outputs(session: AsyncSession = Depends(get_session)):
    stmt = select(Output)
    result = await session.execute(stmt)
    return result.scalars().all()

@router.get("/{id}", response_model=OutputPublic)
async def get_output(id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Output).where(Output.id == id)
    result = await session.execute(stmt)
    output = result.scalar_one_or_none()
    
    check_if_output_exists(output)
    return output

@router.post("", response_model=OutputPublic)
async def create_output(
    output: OutputCreate,
    session: AsyncSession = Depends(get_session)
):
    config_stmt = select(Config).where(Config.id == output.config_id)
    config_result = await session.execute(config_stmt)
    config = config_result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    db_output = Output(
        config_id=output.config_id,
        type=output.type,
        name=output.name
    )
    
    session.add(db_output)
    await session.commit()
    await session.refresh(db_output)
    return db_output

@router.patch("/{id}", response_model=OutputPublic)
async def update_output(
    id: int,
    output_update: OutputCreate,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Output).where(Output.id == id)
    result = await session.execute(stmt)
    db_output = result.scalar_one_or_none()
    
    check_if_output_exists(db_output)
    
    if output_update.config_id != db_output.config_id:
        config_stmt = select(Config).where(Config.id == output_update.config_id)
        config_result = await session.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Config not found"
            )
        
        db_output.config_id = output_update.config_id
    
    db_output.type = output_update.type
    db_output.name = output_update.name
    
    session.add(db_output)
    await session.commit()
    await session.refresh(db_output)
    return db_output

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_output(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Output).where(Output.id == id)
    result = await session.execute(stmt)
    db_output = result.scalar_one_or_none()
    
    check_if_output_exists(db_output)
    
    await session.delete(db_output)
    await session.commit()
    return None