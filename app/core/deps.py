"""FastAPI Dependencies สำหรับ Authentication / Role-based Access Control

ทุก Endpoint ที่ต้อง Login ใช้ Depends(get_current_user)
Endpoint ที่ต้องสิทธิ์ Admin ใช้ Depends(require_admin)

Scope Revision (Phase 9, 2026-09-03): ตัด require_can_review/approve/receive ออก —
ไม่มี Workflow อนุมัติในระบบแล้ว
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import COOKIE_NAME, decode_access_token
from app.db.session import get_db
from app.models import User


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ยังไม่ได้ Login")

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session หมดอายุหรือไม่ถูกต้อง")

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "บัญชีผู้ใช้ไม่ถูกต้องหรือถูกปิดใช้งาน")

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ต้องเป็น Admin เท่านั้น")
    return user


# Budget Control (Phase 10, 2026-09-09): FA = Role กลาง Upload/จัดการ Excel งบประมาณ
# ได้ (ดู app/models/budget.py, app/services/budget_excel.py) — Admin ทำแทนได้เสมอ
def require_fa_or_admin(user: User = Depends(get_current_user)) -> User:
    if not (user.is_fa or user.is_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ต้องมีสิทธิ์ FA หรือ Admin เท่านั้น")
    return user
