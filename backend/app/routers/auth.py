import re
from os import getenv
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from fastapi import APIRouter, Depends, HTTPException, status, Cookie, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from dotenv import load_dotenv

from ..models import User, UserCreate, UserPublic, UserRegister
from ..db import get_session

load_dotenv()

# TODO: Refresh token

SECRET_KEY = f"{getenv("SECRET_KEY")}"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours
    
router = APIRouter()
ph = PasswordHasher()

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)  # Fixed: minuntes → minutes, datetime.timezone.utc → timezone.utc
    to_encode = {"user_id": user_id, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY,algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token:str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
async def get_current_user(
    access_token: str | None = Cookie(None, include_in_schema=False),
    session: AsyncSession = Depends(get_session)
) -> User:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    token = access_token.replace("Bearer ", "")
    user_id = verify_token(token)
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

@router.post("/register", response_model=UserPublic)
async def register(user: UserRegister, session: AsyncSession = Depends(get_session)):
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
async def login(user: UserCreate,response: Response, session: AsyncSession = Depends(get_session)):
    stmt = select(User).where(User.email == user.email)
    result = await session.execute(stmt)
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    # Check if passwords match
    try:
        ph.verify(db_user.password, user.password)
    except VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create and give JWT to user
    access_token = create_access_token(db_user.id)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        secure=False, #TODO nastavit true v produkcii
        samesite="lax",
        max_age=3600
    )
    return {"message": "Login successful","user_id":db_user.id}

@router.post("/logout")
async def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(key="access_token")
    return {"message": "Logout successful"}
    
