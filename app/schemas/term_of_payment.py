"""Schema สำหรับ Term of Payment Master Data (AR Redesign, 2026-09-11) — ดู
app/models/term_of_payment.py สำหรับที่มา/เหตุผลของ Design"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TermOfPaymentOptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TermOfPaymentOptionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None


class TermOfPaymentOptionRead(BaseModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
