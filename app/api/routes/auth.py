"""Auth Routes — Login ตั้ง Cookie แบบ HttpOnly, Logout ล้าง Cookie, /me คืนข้อมูลตัวเอง"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import COOKIE_NAME, create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

# Secure Cookie เฉพาะ Production เท่านั้น (ต้องรันหลัง HTTPS ผ่าน Nginx Proxy Manager
# เสมอ — ดู docs/00_KICKOFF_AND_DESIGN.md ข้อ 3.3) — UAT ตัดสินใจแล้ว (2026-09-02)
# ให้รันบน HTTP ธรรมดาไปก่อน (Let's Encrypt ใช้กับ .sct.local Internal Domain
# ไม่ได้ ต้องรอ Internal CA จาก IT) ถ้ายังคง Secure=True ไว้ Browser จะไม่ยอมเก็บ
# Cookie บน HTTP เลย ทำให้ Login สำเร็จจริงที่ Server แต่วน Loop กลับมาหน้า Login
# ตลอด (พบจริงตอน UAT Walkthrough ครั้งแรก 2026-09-02) — ต้องกลับมาเอา "uat" ออก
# จาก List นี้ทันทีที่ตั้ง HTTPS ให้ UAT ได้จริง
_SECURE_COOKIE = settings.app_env not in ("dev", "verify-sandbox", "test", "uat")


@router.post("/login", response_model=UserRead)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")

    token = create_access_token(user.id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_SECURE_COOKIE,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
