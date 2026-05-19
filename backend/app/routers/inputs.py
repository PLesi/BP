from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from ..models import Input, InputCreate, InputPublic, Config, InputLimit
from ..db import get_session
from ..services.services import RESERVED_KEYWORDS

router = APIRouter(prefix="/inputs", tags=["inputs"])

def check_if_input_exists(input: Input | None):
    """Helper function to check if input exists"""
    if not input:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Input not found"
        )

@router.get("/{id}", response_model=InputPublic)
async def get_input(id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Input).where(Input.id == id).options(
        selectinload(Input.input_limit)
    )
    result = await session.execute(stmt)
    input = result.scalar_one_or_none()
    
    check_if_input_exists(input)
    return input

@router.post("", response_model=InputPublic)
async def create_input(
    input: InputCreate,
    session: AsyncSession = Depends(get_session)
):
    # Check if input name is a reserved keyword
    if input.name.lower() in RESERVED_KEYWORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input name '{input.name}' is a reserved keyword and cannot be used"
        )
    
    # Check if config exists
    config_stmt = select(Config).where(Config.id == input.config_id)
    config_result = await session.execute(config_stmt)
    config = config_result.scalar_one_or_none()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Config not found"
        )
    
    # Create input_limit if provided
    input_limit_id = None
    if input.input_limit:
        db_input_limit = InputLimit(
            min=input.input_limit.min,
            max=input.input_limit.max
        )
        session.add(db_input_limit)
        await session.flush()
        input_limit_id = db_input_limit.id
    
    # Create input
    db_input = Input(
        config_id=input.config_id,
        type=input.type,
        name=input.name,
        input_limit_id=input_limit_id
    )
    
    session.add(db_input)
    await session.commit()

    stmt = select(Input).where(Input.id == db_input.id).options(
        selectinload(Input.input_limit)
    )
    result = await session.execute(stmt)
    created_input = result.scalar_one()
    return created_input

@router.patch("/{id}", response_model=InputPublic)
async def update_input(
    id: int,
    input_update: InputCreate,
    session: AsyncSession = Depends(get_session)
):
    # Check if input name is a reserved keyword
    if input_update.name.lower() in RESERVED_KEYWORDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input name '{input_update.name}' is a reserved keyword and cannot be used"
        )
    
    stmt = select(Input).where(Input.id == id)
    result = await session.execute(stmt)
    db_input = result.scalar_one_or_none()
    
    check_if_input_exists(db_input)
    
    if input_update.config_id != db_input.config_id:
        config_stmt = select(Config).where(Config.id == input_update.config_id)
        config_result = await session.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Config not found"
            )
        
        db_input.config_id = input_update.config_id
    
    if input_update.input_limit:
        db_input_limit = InputLimit(
            min=input_update.input_limit.min,
            max=input_update.input_limit.max
        )
        session.add(db_input_limit)
        await session.flush()
        db_input.input_limit_id = db_input_limit.id
    else:
        db_input.input_limit_id = None
    
    db_input.type = input_update.type
    db_input.name = input_update.name
    
    session.add(db_input)
    await session.commit()

    stmt = select(Input).where(Input.id == db_input.id).options(
        selectinload(Input.input_limit)
    )
    result = await session.execute(stmt)
    updated_input = result.scalar_one()
    return updated_input

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_input(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Input).where(Input.id == id)
    result = await session.execute(stmt)
    db_input = result.scalar_one_or_none()
    
    check_if_input_exists(db_input)
    
    await session.delete(db_input)
    await session.commit()
    return None