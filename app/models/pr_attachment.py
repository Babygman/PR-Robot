"""เอกสารแนบของ Purchasing Requisition (PR Attachments, Phase 11, 2026-09-15)

Business Decision 2026-09-15: PR เปลี่ยนมาใช้ Workflow อนุมัติ Digital แบบเดียวกับ AR
— ต้องมี Attachment แนบเอกสารประกอบได้เหมือน AR ด้วย (Structure/Pattern เดียวกับ
app/models/ar_attachment.py ทุกประการ แค่แยกตารางเป็นของ PR เอง)

ไม่ใช้ SourceDocument (app/models/source_document.py) ร่วมกันโดยเจตนา — เหตุผลเดียวกับ
ที่ AR แยกออกมาตอน Phase A: Model นั้นผูกกับ Gemini AI Extraction แน่นเกินไป (มี Field
ai_extraction_raw_json/reviewed_data ที่ไม่เกี่ยวกับการแนบเอกสารประกอบการอนุมัติเลย)

ไม่ Mount เป็น Static File — ต้องดาวน์โหลดผ่าน Endpoint ที่ Login แล้วเท่านั้น (Pattern
เดียวกับ app/api/routes/ar_attachments.py — Endpoint ของ PR เป็น Phase 3 ของรอบนี้)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PRAttachment(Base):
    __tablename__ = "pr_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)  # ชื่อไฟล์เดิมจากผู้ใช้
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # Path จริงบน Disk
    content_type: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # หน่วย Byte
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    pr = relationship("PurchasingRequisition", back_populates="attachments")
