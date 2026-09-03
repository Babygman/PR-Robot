"""Pydantic Schemas สำหรับ User (Request/Response) — แยกจาก SQLAlchemy Model เสมอ
ห้าม Return password_hash ออกไปทาง API เด็ดขาด
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department: str | None = None
    is_admin: bool = False


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    department: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}
