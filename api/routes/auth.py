"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Admin, User
from database.session import get_db
from utils.security import generate_token, verify_password

router = APIRouter()


class LoginRequest(BaseModel):
    """Login request model."""

    telegram_id: int
    password: str


class TokenResponse(BaseModel):
    """Token response model."""

    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Login endpoint."""
    # Get user
    user = await db.get(User, credentials.telegram_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if user is admin
    res = await db.execute(select(Admin).where(Admin.user_id == user.id, Admin.is_active.is_(True)))
    admin = res.scalars().first()
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if not user.password_hash or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Generate token
    token = generate_token({"sub": str(user.id), "admin_level": admin.level.value})
    return TokenResponse(access_token=token)
