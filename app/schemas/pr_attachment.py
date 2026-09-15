"""Schema สำหรับเอกสารแนบของ PR (Phase 11, 2026-09-15) — Pattern เดียวกับ
app/schemas/ar_attachment.py ทุกประการ"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PRAttachmentRead(BaseModel):
    id: int
    pr_id: int
    file_name: str
    content_type: str | None
    file_size: int
    uploaded_by_id: int
    uploaded_by_name: str | None = None  # เติมใน Route (ไม่ใช่คอลัมน์จริง)
    uploaded_at: datetime

    model_config = {"from_attributes": True}
