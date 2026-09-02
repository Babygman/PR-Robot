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
    QUOTATION = "quotation"
    RECEIVING_NOTE = "receiving_note"
    OTHER = "other"


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="SET NULL")
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    doc_type: Mapped[SourceDocType] = mapped_column(
        # values_callable: เหตุผลเดียวกับ PRStatus ใน purchasing_requisition.py —
        # บังคับเก็บ .value ("quotation") ไม่ใช่ .name ("QUOTATION") ให้ตรงกับ Native
        # Enum Type ที่ Alembic Migration สร้างไว้จริงบน PostgreSQL
        SAEnum(
            SourceDocType,
            name="source_doc_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
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
