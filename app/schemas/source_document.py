"""Schema สำหรับ Upload + AI Extraction (Phase 4)"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.source_document import SourceDocType


class ExtractedItem(BaseModel):
    """Scope Revision (Phase 9, 2026-09-03): แยก product_name/description/color
    ออกจากกันชัดเจน ตรงกับคอลัมน์จริงในใบเสนอราคาส่วนใหญ่ (PRODUCT NAME / PRODUCT
    DESCRIPTION / COLOR แยกคอลัมน์) — ฝั่งหน้าเว็บจะรวมเป็น Description บรรทัดเดียว
    ตอนสร้าง PR ตาม Format ที่ผู้ใช้เขียนมือจริง (ดูตัวอย่างจริงใน
    docs/00_KICKOFF_AND_DESIGN.md)"""

    product_name: str | None = None
    description: str | None = None
    color: str | None = None
    quantity: str | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class ExtractionResult(BaseModel):
    """โครงสร้างข้อมูลที่ให้ Gemini สกัดออกมาจากเอกสารต้นทาง (ใบเสนอราคา/ใบยืมสินค้า/
    ใบส่งสินค้า/ใบรับของ)

    ใช้เป็นทั้ง Response Schema ที่ส่งให้ Gemini (Structured Output)
    และ Schema ของข้อมูลที่ผู้ใช้แก้ไขก่อนนำไปสร้าง PR จริงใน Phase 5

    detected_doc_type (Phase 9, 2026-09-03): AI เดาประเภทเอกสารเองจากเนื้อหา ไม่บังคับ
    ให้ผู้ใช้เลือกตอน Upload แล้ว — ผู้ใช้แก้ไขทีหลังผ่าน /review ได้เสมอถ้า AI เดาผิด
    """

    detected_doc_type: SourceDocType | None = None
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
    doc_type: SourceDocType | None
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
    """ข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว ก่อนนำไปสร้าง PR จริง (Phase 5)

    doc_type (Phase 9, 2026-09-03): ให้แก้ประเภทเอกสารที่ AI เดามาผิดได้ในขั้นตอน
    เดียวกันนี้ ไม่ต้องมี Endpoint แยก — ไม่ส่งมาก็ได้ถ้าไม่ต้องการแก้
    """

    reviewed_data: ExtractionResult
    doc_type: SourceDocType | None = None
