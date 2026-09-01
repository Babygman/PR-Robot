"""User model — ผู้ใช้ระบบทุกคน Login แล้วเป็น "Requester" ได้เสมอ (ไม่ต้องมี Flag)
ส่วน can_review / can_approve / can_receive คือสิทธิ์เสริมเฉพาะที่ Admin กำหนดให้
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    can_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_approve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_receive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
