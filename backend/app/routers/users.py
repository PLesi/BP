from fastapi import Depends, APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import User, UserPublic, UserCreate
from ..db import get_session

router = APIRouter(prefix="/users", tags=["users"])

@router.post("", response_model=UserPublic)
async def create_user(user: UserCreate, session: AsyncSession = Depends(get_session)):
    db_user = User(email=user.email, password=user.password, is_admin=False)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user    

