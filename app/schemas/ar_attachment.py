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
