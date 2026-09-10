"""User Management — Admin เท่านั้นที่สร้าง/ดู/แก้ไขรายชื่อ User ได้ (Phase 3, ขยาย
Phase 10 2026-09-09 เพิ่ม PATCH สำหรับหน้า /app/users — Budget Control ต้องมีหน้า
จัดการ User จริงเพื่อกำหนด Department/Position/is_fa ให้แต่ละคน — ขยายอีกครั้ง
2026-09-10 ให้ PATCH แก้ email ได้ด้วย เพื่อรองรับ Import User จำนวนมากจากตาราง
Approve Flow/User Register จริงของบริษัทที่ยังไม่มี Email จริงครบทุกคน — สร้างด้วย
Email ชั่วคราวก่อน แล้วให้ Admin แก้เป็น Email จริงทีหลังจากหน้านี้ได้)
ยังไม่มีหน้าเว็บ Self-service สมัครสมาชิก — ตั้งใจให้ Admin เป็นคนเพิ่ม User เข้าระบบเท่านั้น
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    existing = db.query(User).filter(User.email == body.email).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้มีผู้ใช้ในระบบแล้ว")

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        department=body.department,
        position=body.position,
        is_admin=body.is_admin,
        is_fa=body.is_fa,
        can_view_approvals=body.can_view_approvals,
        approver_only=body.approver_only,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ User นี้")

    updates = body.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] is not None and updates["email"] != user.email:
        clash = db.query(User).filter(User.email == updates["email"], User.id != user.id).first()
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้มีผู้ใช้ในระบบแล้ว")

    # exclude_unset=True: อัปเดตเฉพาะ Field ที่ Client ส่งมาจริงๆ (รวมถึงกรณีส่ง null
    # มาตั้งใจล้างค่า เช่น เคลียร์ department ของผู้อนุมัติ Cross-department) — Field ที่
    # ไม่ได้ส่งมาเลยจะไม่ถูกแตะต้อง
    for key, value in updates.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user
