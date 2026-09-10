"""Schema สำหรับเอกสารแนบของ AR (Phase A, 2026-09-10) — ดู
app/models/ar_attachment.py สำหรับที่มา/เหตุผลของ Design"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ARAttachmentRead(BaseModel):
    id: int
    ar_id: int
    file_name: str
    content_type: str | None
    file_size: int
    uploaded_by_id: int
    uploaded_by_name: str | None = None  # เติมใน Route (ไม่ใช่คอลัมน์จริง)
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# Comment 4 (2026-09-10, My Approvals — Lightbox): ผู้ใช้แจ้งว่าอยากให้ไฟล์ Excel (.xlsx)
# มี Preview ในตัว Lightbox ด้วยเหมือน PDF/รูปภาพ (ไม่ใช่แค่ลิงก์ดาวน์โหลด) — เบราว์เซอร์
# Preview .xlsx ตรงๆ ไม่ได้ (ไม่มี Native Viewer เหมือน PDF) จึงอ่านค่าด้วย openpyxl ฝั่ง
# Server แล้วส่งเป็นตาราง Rows/Cols กลับมาให้ฝั่งหน้าเว็บ Render เป็น <table> เอง (Vanilla
# JS ตามหลักการของโปรเจกต์นี้ ไม่ใช้ Library แปลง Excel ฝั่ง Browser)
class ARAttachmentXlsxPreview(BaseModel):
    sheet_name: str
    rows: list[list[str | float | int | None]]
    truncated: bool
