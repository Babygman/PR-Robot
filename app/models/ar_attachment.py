"""เอกสารแนบของ Approval Request (AR Attachments, Phase A — Correction 2026-09-10)

Feedback จริงจากผู้ใช้: "ในการสร้าง Approval Request ต้องมีเอกสารแนบให้ upload ด้วย
เอกสารมีทั้ง pdf,excel,picture" + "มีการแนบ แทรกเอกสารเพิ่มเติมได้ ในระหว่างการ
approval" — จึงรองรับทั้ง Upload ตอนสร้าง/แก้ไข AR (ยัง Draft) และ Upload เพิ่มระหว่าง
รอ Level/FA อนุมัติอยู่ (ดู Permission ที่ app/services/budget_workflow.py:
can_upload_attachment)

ไม่ใช้ SourceDocument (app/models/source_document.py) ร่วมกันโดยเจตนา — Model นั้นผูก
กับ Gemini AI Extraction ของ PR แน่นเกินไป (มี Field เยอะที่ไม่เกี่ยวกับ AR เลย เช่น
ai_extraction_raw_json/reviewed_data) จึงแยก Table ใหม่ที่เรียบง่ายกว่าสำหรับ AR
โดยเฉพาะ — ใช้ Pattern การเก็บไฟล์เดียวกัน (uuid4().hex + นามสกุลเดิม เก็บใน
settings.upload_dir) ดู app/api/routes/documents.py: upload_document

ไม่ Mount เป็น Static File (ดู app/main.py — Mount แค่ /static สำหรับ Asset ของแอปเอง)
— ต้องดาวน์โหลดผ่าน Endpoint ที่ต้อง Login เท่านั้น (ดู app/api/routes/ar_attachments.py)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ARAttachment(Base):
    __tablename__ = "ar_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    ar_id: Mapped[int] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)  # ชื่อไฟล์เดิมจากผู้ใช้
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)  # Path จริงบน Disk
    content_type: Mapped[str | None] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # หน่วย Byte
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ar = relationship("ApprovalRequest", back_populates="attachments")
