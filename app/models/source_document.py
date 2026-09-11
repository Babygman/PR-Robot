"""เอกสารต้นทางที่อัปโหลด (ใบเสนอราคา / ใบรับของ) + ผล AI Extraction ดิบ"""
from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceDocType(str, enum.Enum):
    """Scope Revision (Phase 9, 2026-09-03): เพิ่ม BORROW_NOTE (ใบยืมสินค้า) และ
    DELIVERY_NOTE (ใบส่งสินค้า) ตาม Feedback จริงจาก Product Owner — AI เป็นคนเดา
    ประเภทเอกสารเองจากเนื้อหา (ไม่บังคับเลือกตอน Upload แล้ว) ผู้ใช้แก้ไขทีหลังได้"""

    QUOTATION = "quotation"
    RECEIVING_NOTE = "receiving_note"
    BORROW_NOTE = "borrow_note"
    DELIVERY_NOTE = "delivery_note"
    OTHER = "other"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="SET NULL")
    )
    # AI Extract for AR (2026-09-11) — คู่กับ pr_id ด้านบน (Pattern เดียวกับ audit_log
    # ที่มี pr_id/ar_id คู่กันอยู่แล้ว) แถวหนึ่งผูกได้แค่อย่างใดอย่างหนึ่งเท่านั้น — เอกสาร
    # ต้นทางของ AR คือใบเสนอราคาเหมือน PR เป๊ะ จึงใช้ Schema เดียวกันนี้ทั้งหมด ไม่แยกตาราง
    ar_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL")
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    doc_type: Mapped[SourceDocType | None] = mapped_column(
        # values_callable: เหตุผลเดียวกับ PRStatus ใน purchasing_requisition.py —
        # บังคับเก็บ .value ("quotation") ไม่ใช่ .name ("QUOTATION") ให้ตรงกับ Native
        # Enum Type ที่ Alembic Migration สร้างไว้จริงบน PostgreSQL
        # Nullable (Phase 9, 2026-09-03): ไม่บังคับเลือกตอน Upload แล้ว — AI เดาเอง
        # หลัง Extract เสร็จ (เก็บใน ai_extraction_raw_json.detected_doc_type ก่อน
        # แล้วค่อย Apply ทับที่นี่) ผู้ใช้แก้ไขทีหลังผ่าน /review ได้เสมอ
        SAEnum(
            SourceDocType,
            name="source_doc_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=True,
    )
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    ai_extraction_raw_json: Mapped[dict | None] = mapped_column(JSON)
    ai_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extraction_error: Mapped[str | None] = mapped_column(
        Text, comment="ข้อความ Error ถ้า Gemini สกัดข้อมูลไม่สำเร็จ (ai_extraction_raw_json จะเป็น null)"
    )

    # ข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว (Phase 4) — แยกจาก ai_extraction_raw_json
    # เพื่อรักษาผลดิบจาก AI ไว้เป็น Audit Trail เสมอ ไม่ถูกเขียนทับ
    reviewed_data: Mapped[dict | None] = mapped_column(JSON)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
