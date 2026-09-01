"""Audit Log — บันทึกทุก Action สำคัญที่เกิดกับแต่ละ PR"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    detail: Mapped[dict | None] = mapped_column(JSON)
