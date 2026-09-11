from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    """PATCH /auth/password — User เปลี่ยนรหัสผ่านของตัวเอง (Popup ที่ Sidebar,
    2026-09-11) ต้องกรอกรหัสผ่านเดิมยืนยันก่อนเสมอ (คนละ Flow จาก Admin Reset ให้
    User คนอื่นที่ app/schemas/user.py: UserPasswordReset ซึ่งไม่ต้องรู้รหัสเดิม)"""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
