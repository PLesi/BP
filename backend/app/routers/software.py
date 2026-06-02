from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Software, SoftwareCreate, SoftwarePublic
from ..db import get_session
from ..services.services import verify_admin_api_key

router = APIRouter(prefix="/software", tags=["software"], dependencies=[Depends(verify_admin_api_key)])

@router.get("",response_model=list[SoftwarePublic])
async def get_software(session: AsyncSession = Depends(get_session)):
    stmt = select(Software)
    
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{id}", response_model=SoftwarePublic)
async def get_software_by_id(id: int, session: AsyncSession = Depends(get_session)):
    stmt = select(Software).where(Software.id == id)
    result = await session.execute(stmt)
    sw = result.scalar_one_or_none()

    if not sw:
        raise HTTPException(
            status_code= status.HTTP_404_NOT_FOUND,
            detail= "Software not found"
        )
    
    return sw


@router.post("",response_model=SoftwarePublic)
async def create_software(
    software: SoftwareCreate,
    session: AsyncSession = Depends(get_session)
):
    db_sw = Software(name=software.name)
    session.add(db_sw)
    await session.commit()
    await session.refresh(db_sw)
    
    return db_sw

@router.patch("/{id}",response_model=SoftwarePublic)
async def update_software(
    id: int,
    software: SoftwareCreate,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Software).where(Software.id == id)
    result = await session.execute(stmt)
    db_sw = result.scalar_one_or_none()

    check_if_sw_exist(db_sw)
    
    db_sw.name = software.name
    session.add(db_sw)
    await session.commit()
    await session.refresh(db_sw)

    return db_sw

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_software(
    id: int,
    session: AsyncSession = Depends(get_session)
):
    stmt = select(Software).where(Software.id == id)
    result = await session.execute(stmt)
    db_sw = result.scalar_one_or_none()

    check_if_sw_exist(db_sw)

    
    

def check_if_sw_exist(sw: Software):
    if not sw:
        raise HTTPException(
            status_code= status.HTTP_404_NOT_FOUND,
            detail="Software not found"
        )