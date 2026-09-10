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


# My Approvals (Phase B/2, 2026-09-10; Correction — Full RBAC, 2026-09-10): Admin เห็นเมนูนี้
# เสมอ ส่วนคนอื่นต้องถูก Admin เปิด can_view_approvals ให้จากหน้า "จัดการ User" ก่อน — ตัด
# is_fa ออกจากเงื่อนไขนี้แล้ว (ผู้ใช้ยืนยัน: FA หมายถึงแค่สิทธิ์ทำ FA Acknowledge เท่านั้น
# ไม่ได้แปลว่ามีสิทธิ์เข้าเมนู My Approvals ด้วยอัตโนมัติ — Admin ที่ต้องการให้ FA คนหนึ่ง
# ใช้ My Approvals ได้จริง ต้องติ๊กทั้ง FA และ "Approve" แยกกัน) ดู Docstring app/models/user.py
def require_can_view_approvals(user: User = Depends(get_current_user)) -> User:
    if not (user.is_admin or user.can_view_approvals):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์เข้าถึงเมนู 'การอนุมัติของฉัน'")
    return user


# Full RBAC (Correction 2026-09-10): เมนู "รายการ PR"/"สร้าง PR ใหม่" — Admin, can_view_pr,
# หรือ can_view_all_pr (เห็น PR ทั้งหมด) เท่านั้นที่เข้าเมนูนี้ได้ — ขอบเขตเห็น PR ของใครบ้าง
# (แค่ของตัวเอง หรือทั้งหมด) enforce แยกอีกชั้นที่ app/api/routes/purchasing_requisitions.py
def require_can_view_pr(user: User = Depends(get_current_user)) -> User:
    if not (user.is_admin or user.can_view_pr or user.can_view_all_pr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์เข้าถึงเมนู PR")
    return user


# Full RBAC (Correction 2026-09-10): เมนู "Approval Request" — Admin, can_view_ar, หรือ
# can_view_all_ar (เห็น AR ทั้งหมด) เท่านั้นที่เข้าเมนูนี้ได้ — ขอบเขตเห็น AR ของใครบ้าง
# enforce แยกอีกชั้นที่ app/api/routes/approval_requests.py (ผู้มีบทบาทอนุมัติ/FA ยังเห็น
# AR ที่รอตนเองอนุมัติผ่านเมนู My Approvals ได้เสมอ ไม่เกี่ยวกับ Dependency ตัวนี้)
def require_can_view_ar(user: User = Depends(get_current_user)) -> User:
    if not (user.is_admin or user.can_view_ar or user.can_view_all_ar):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์เข้าถึงเมนู Approval Request")
    return user


# Full RBAC (Correction 3 — แยก Log PR/Log AR, 2026-09-10): เดิมเมนู "Log" รวมเดียว แยกเป็น
# 2 เมนูอิสระกัน ตาม Matrix ที่ผู้ใช้ Confirm — Log PR ไม่มี FA (PR ไม่มี Workflow อนุมัติ/
# FA เกี่ยวข้องเลย) ส่วน Log AR มี FA เพราะเป็นผู้ทำ FA Acknowledge ในขั้นตอนอนุมัติงบของ AR
def require_can_view_log_pr(user: User = Depends(get_current_user)) -> User:
    if not (user.is_admin or user.can_view_all_pr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์เข้าถึงเมนู Log PR")
    return user


def require_can_view_log_ar(user: User = Depends(get_current_user)) -> User:
    if not (user.is_admin or user.is_fa or user.can_view_all_ar):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์เข้าถึงเมนู Log AR")
    return user
