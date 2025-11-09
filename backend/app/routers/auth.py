import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..models import User, UserCreate, UserPublic
from ..db import get_session

    
router = APIRouter()
ph = PasswordHasher()


@router.post("/register", response_model=UserPublic)
async def register(user: UserCreate, session: AsyncSession = Depends(get_session)):
    email_re = '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.search(email_re, user.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )

    hashed_pasword = ph.hash(user.password)
    db_user = User(email=user.email, password=hashed_pasword)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user

@router.post("/login")
async def login(user: UserCreate, session: AsyncSession = Depends(get_session)):
    stmt = select(User).where(User.email == user.email)
    result = await session.execute(stmt)
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    try:
        ph.verify(db_user.password, user.password)
    except VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    return {"message": "Login successful","user_id":db_user.id}