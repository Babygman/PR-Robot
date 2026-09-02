"""Schema สำหรับ Upload + AI Extraction (Phase 4)"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.source_document import SourceDocType


class ExtractedItem(BaseModel):
    description: str
    quantity: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class ExtractionResult(BaseModel):
    """โครงสร้างข้อมูลที่ให้ Gemini สกัดออกมาจากเอกสารต้นทาง (ใบเสนอราคา/ใบรับของ)

    ใช้เป็นทั้ง Response Schema ที่ส่งให้ Gemini (Structured Output)
    และ Schema ของข้อมูลที่ผู้ใช้แก้ไขก่อนนำไปสร้าง PR จริงใน Phase 5
    """

    vendor_name: str | None = None
    document_no: str | None = None
    document_date: date | None = None
    items: list[ExtractedItem] = Field(default_factory=list)
    notes: str | None = None
    ai_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="ค่าประเมินความมั่นใจของ AI เอง (0-1) เป็นค่าประมาณ ไม่ใช่ค่า Calibrate จริง",
    )


class SourceDocumentRead(BaseModel):
    id: int
    pr_id: int | None
    file_path: str
    doc_type: SourceDocType
    uploaded_by_id: int
    uploaded_at: datetime
    ai_extraction_raw_json: dict | None
    ai_confidence: Decimal | None
    extraction_error: str | None
    reviewed_data: dict | None
    reviewed_by_id: int | None
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class SourceDocumentReviewUpdate(BaseModel):
    """ข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว ก่อนนำไปสร้าง PR จริง (Phase 5)"""

    reviewed_data: ExtractionResult
