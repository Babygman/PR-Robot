"""Schema สำหรับหน้า "ค่าใช้จ่าย AI" (2026-09-04)"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AiUsageLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int | None
    file_name: str
    model: str
    success: bool
    error_message: str | None
    prompt_token_count: int
    output_token_count: int
    total_token_count: int
    cost_usd: Decimal
    cost_thb: Decimal
    uploaded_by_id: int | None
    uploaded_by_name: str | None = None
    created_at: datetime


class AiUsagePeriodSummary(BaseModel):
    """สรุปยอดรวมของ 1 ช่วงเวลา (1 วัน หรือ 1 เดือน) — period เป็น "YYYY-MM-DD"
    สำหรับรายวัน หรือ "YYYY-MM" สำหรับรายเดือน"""

    period: str
    transaction_count: int
    success_count: int
    failure_count: int
    total_prompt_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
    total_cost_thb: Decimal


class AiUsageSummaryResponse(BaseModel):
    today: AiUsagePeriodSummary
    this_month: AiUsagePeriodSummary
    daily: list[AiUsagePeriodSummary]
    monthly: list[AiUsagePeriodSummary]
