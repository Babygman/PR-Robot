"""Term of Payment — Master Data (AR Redesign, 2026-09-11)

Admin จัดการรายการ Term of Payment เอง (เช่น "Credit 30 Days", "Cash", "50% Advance")
ผ่านหน้า Admin CRUD (Pattern เดียวกับหน้า "Approval Levels" — budget_levels.html) —
ฟอร์ม AR เปลี่ยนช่อง "Term of Payment" จากกรอกข้อความอิสระเป็น Dropdown เลือกจากตาราง
นี้แทน (ผู้ใช้ยืนยันแล้วว่าไม่ต้องให้ AI Extract ช่องนี้)

ไม่ผูก Foreign Key กับ approval_requests.term_of_payment โดยเจตนา — Field นั้นยังเก็บ
เป็น Text ธรรมดาเหมือนเดิม (แค่ค่าที่เลือก ณ ขณะบันทึก ไม่ต้องคงความสัมพันธ์ถาวรกับ
รายการ Master เพราะถ้า Admin ลบ/แก้ชื่อรายการทีหลัง AR เก่าที่เคยบันทึกไว้ไม่ควรเปลี่ยนค่าตาม)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TermOfPaymentOption(Base):
    __tablename__ = "term_of_payment_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
