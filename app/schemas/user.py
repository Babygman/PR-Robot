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
    division: str | None = None
    position: str | None = None
    is_admin: bool = False
    is_fa: bool = False
    can_view_approvals: bool = False
    can_view_pr: bool = False
    can_view_ar: bool = False
    can_view_all_pr: bool = False
    can_view_all_ar: bool = False


class UserUpdate(BaseModel):
    """แก้ไข User ที่มีอยู่แล้ว — ทุก Field เป็น Optional (ส่งมาเฉพาะที่จะเปลี่ยน)

    เพิ่ม `email` (2026-09-10, ตามคำขอ Admin) เพื่อแก้ Email ที่กรอกไว้ชั่วคราวตอน Import
    User จำนวนมากจาก Excel/ตารางแผนผังจริงให้เป็น Email จริงทีหลังได้จากหน้าเว็บ ไม่ต้อง
    ลบ User แล้วสร้างใหม่ — Route ตรวจ Unique กันชนกับ User คนอื่นให้ (ดู
    app/api/routes/users.py) — ไม่มี password ในนี้โดยเจตนา (เปลี่ยนรหัสผ่านเป็นคนละ
    Flow แยกออกไปเป็น UserPasswordReset/PATCH /users/{id}/password ด้านล่าง — User
    Management Redesign, 2026-09-11)

    เพิ่ม `can_view_approvals`/`can_view_pr`/`can_view_ar`/`can_view_all_pr`/`can_view_all_ar`
    (Full RBAC, 2026-09-10 — ตัด `approver_only` ออกแล้ว, แยก `can_view_all` เดิมเป็น 2 Field
    ตาม PR/AR) — ดู Docstring app/models/user.py สำหรับความหมายแต่ละ Field
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    department: str | None = None
    division: str | None = None
    position: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None
    is_fa: bool | None = None
    can_view_approvals: bool | None = None
    can_view_pr: bool | None = None
    can_view_ar: bool | None = None
    can_view_all_pr: bool | None = None
    can_view_all_ar: bool | None = None


class UserPasswordReset(BaseModel):
    """PATCH /users/{id}/password (Admin เท่านั้น) — Reset รหัสผ่านของ User คนอื่น
    (User Management Redesign, 2026-09-11) แยก Endpoint ออกจาก UserUpdate โดยเจตนา
    (ดู Comment เดิมใน UserUpdate ด้านบน) กันโครงสร้าง PATCH หลักปนกับข้อมูลอ่อนไหว"""

    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    name: str
    email: EmailStr
    department: str | None
    division: str | None
    position: str | None
    is_active: bool
    is_admin: bool
    is_fa: bool
    can_view_approvals: bool
    can_view_pr: bool
    can_view_ar: bool
    can_view_all_pr: bool
    can_view_all_ar: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserExcelUploadRowError(BaseModel):
    row_no: int
    message: str


class UserExcelUploadResult(BaseModel):
    """ผลลัพธ์ Import Excel แบบ Partial-success (User Management Redesign, 2026-09-11)
    — Pattern เดียวกับ BudgetUploadResult (app/schemas/budget.py) แต่ไม่มี Batch Log
    Table แยกต่างหาก (ไม่ได้ร้องขอ) คืนผลสรุปตรงๆ ในการเรียกครั้งเดียว"""

    total_rows: int
    success_rows: int
    error_rows: int
    errors: list[UserExcelUploadRowError]
