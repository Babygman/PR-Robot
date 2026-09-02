"""Password Hashing + JWT — ตาม PROJECT_STANDARD.md ข้อ 8 ห้าม Hard-code Secret
SECRET_KEY มาจาก app.core.config.settings (อ่านจาก .env) เท่านั้น

หมายเหตุ: ใช้ bcrypt โดยตรง ไม่ผ่าน passlib — เพราะ passlib 1.7.4 (Release ล่าสุด
ปี 2020, ไม่มีการดูแลต่อแล้ว) เข้ากันไม่ได้กับ bcrypt เวอร์ชันปัจจุบัน (>=4.1 ขึ้นไป
ตัด Attribute __about__ ออก) ทำให้ Self-test ภายในของ passlib Crash ตอน Import
(พิสูจน์แล้วจริงตอน Verify — ดู Commit Message ประกอบ)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

COOKIE_NAME = "pr_robot_session"

_BCRYPT_MAX_BYTES = 72  # ข้อจำกัดของ bcrypt เอง ไม่ใช่ของเรา


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        # password_hash ไม่ใช่ Bcrypt Hash ที่ถูกต้อง (ข้อมูลเสีย/ผิดรูปแบบ)
        return False


def create_access_token(user_id: int, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> int | None:
    """คืนค่า user_id ถ้า Token ถูกต้องและยังไม่หมดอายุ ไม่งั้นคืน None (ไม่ Raise)"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except ValueError:
        return None
