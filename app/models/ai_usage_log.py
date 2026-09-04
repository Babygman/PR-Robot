"""Log การเรียก Gemini API แต่ละครั้ง สำหรับหน้า "ค่าใช้จ่าย AI" (2026-09-04, Feedback
จริงจากผู้ใช้ — อยากเห็นค่าใช้จ่าย AI แยกรายรายการ/รายวัน/รายเดือน หลัง Upgrade ออกจาก
Free Tier ของ Gemini API)

ค่าใช้จ่ายที่บันทึก (cost_usd/cost_thb) เป็น "ประมาณการ" คำนวณจากจำนวน Token ที่ Gemini
ตอบกลับมาจริง x Rate ที่ตั้งไว้ ณ ตอนนั้น (Snapshot — ไม่คำนวณซ้ำทีหลังแม้ Rate ในตาราง
Pricing หรืออัตราแลกเปลี่ยนจะเปลี่ยนไป) ไม่ใช่ยอด Bill จริงจาก Google Cloud Billing
โดยตรง เก็บ usd_to_thb_rate ที่ใช้ ณ ตอนนั้นไว้ด้วยเพื่อความโปร่งใสว่าคำนวณด้วย Rate ไหน

document_id เป็น Nullable + ON DELETE SET NULL เพราะเอกสารต้นทางลบทิ้งได้ (ดู
DELETE /documents/{id}) แต่ประวัติค่าใช้จ่ายต้องอยู่ต่อ — เก็บ file_name Snapshot ไว้
แยกต่างหากด้วยเหตุผลเดียวกัน
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    prompt_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=0)
    cost_thb: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=0)
    usd_to_thb_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)

    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
