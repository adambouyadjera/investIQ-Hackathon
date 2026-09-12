"""Auth endpoints: register, login, refresh, me.

Age and citizenship are self-attested checkboxes — not KYC.
The word 'verification' must not appear in this file or the UI.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str
    date_of_birth: date
    citizenship_attested: bool          # self-attestation — not KYC
    age_attested: bool = False          # "I confirm I am 18 or older"
    terms_attested: bool = False        # "I understand this is educational"
    monthly_income: Optional[float] = Field(default=None, gt=0)

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def must_be_18(cls, v: date) -> date:
        today = date.today()
        age = today.year - v.year - (
            (today.month, today.day) < (v.month, v.day)
        )
        if age < 18:
            raise ValueError("You must be at least 18 years old to register")
        return v

    @field_validator("citizenship_attested")
    @classmethod
    def must_attest_citizenship(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "This platform is available to US citizens and permanent residents only."
            )
        return v

    @field_validator("age_attested")
    @classmethod
    def must_attest_age(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must confirm you are 18 or older.")
        return v

    @field_validator("terms_attested")
    @classmethod
    def must_attest_terms(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "You must confirm you understand this is an educational simulator."
            )
        return v


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: str
    email: str
    username: str
    date_of_birth: date
    citizenship_attested: bool
    monthly_income: Optional[float]
    is_guest: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(User).where(
            (User.email == body.email) | (User.username == body.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already registered")

    user = User(
        email=body.email,
        username=body.username,
        hashed_password=hash_password(body.password),
        date_of_birth=body.date_of_birth,
        citizenship_attested=body.citizenship_attested,
        monthly_income=body.monthly_income,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/guest", response_model=TokenResponse, status_code=201)
async def guest_session(db: AsyncSession = Depends(get_db)):
    """Create a throwaway demo account. No credentials collected.

    A guest gets a real, isolated user row so every downstream route behaves
    identically — the only difference is the is_guest flag, which the UI uses
    to label the session as demo data. The password is a random value that is
    hashed and never shown to anyone, so the account cannot be logged back
    into. It exists for the life of the browser session.
    """
    suffix = secrets.token_hex(6)
    user = User(
        email=f"guest-{suffix}@demo.investiq.local",
        username=f"guest_{suffix}",
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        date_of_birth=date(1990, 1, 1),      # placeholder; guests attest nothing
        citizenship_attested=True,
        monthly_income=None,
        is_active=True,
        is_guest=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    user_id = decode_token(body.refresh_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        date_of_birth=current_user.date_of_birth,
        citizenship_attested=current_user.citizenship_attested,
        monthly_income=float(current_user.monthly_income)
        if current_user.monthly_income is not None
        else None,
        is_guest=bool(current_user.is_guest),
        created_at=current_user.created_at,
    )
