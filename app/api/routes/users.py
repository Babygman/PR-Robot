"""User Management — Admin เท่านั้นที่สร้าง/ดูรายชื่อ User ได้ (Phase 3)
ยังไม่มีหน้าเว็บ Self-service สมัครสมาชิก — ตั้งใจให้ Admin เป็นคนเพิ่ม User เข้าระบบเท่านั้น
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreate, UserRead

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
        can_review=body.can_review,
        can_approve=body.can_approve,
        can_receive=body.can_receive,
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)) -> list[User]:
    return db.query(User).order_by(User.id).all()
