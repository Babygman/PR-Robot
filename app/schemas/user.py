"""Pydantic Schemas สำหรับ User (Request/Response) — แยกจาก SQLAlchemy Model เสมอ
ห้าม Return password_hash ออกไปทาง API เด็ดขาด

Budget Control (Phase 10, 2026-09-09): เพิ่ม `position` (ตำแหน่งงาน แสดงผลอย่างเดียว)
และ `is_fa` (Role กลาง Upload Excel งบ + FA Acknowledge ทุกแผนก — ดู app/models/budget.py)
เพิ่ม UserUpdate สำหรับหน้าจัดการ User (`PATCH /users/{id}`, Admin เท่านั้น)
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    department: str | None = None
    position: str | None = None
    is_admin: bool = False
    is_fa: bool = False


class UserUpdate(BaseModel):
    """แก้ไข User ที่มีอยู่แล้ว — ทุก Field เป็น Optional (ส่งมาเฉพาะที่จะเปลี่ยน) ไม่มี
    password/email ในนี้โดยเจตนา (เปลี่ยนอีเมล/รหัสผ่านเป็นคนละ Flow ยังไม่ทำ Phase นี้)
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    department: str | None = None
    position: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    is_fa: bool | None = None


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    department: str | None
    position: str | None
    is_active: bool
    is_admin: bool
    is_fa: bool
    created_at: datetime

    model_config = {"from_attributes": True}
