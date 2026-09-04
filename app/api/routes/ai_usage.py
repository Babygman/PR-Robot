"""หน้า "ค่าใช้จ่าย AI" — ดูยอดการใช้ Gemini API แยกรายรายการ/รายวัน/รายเดือน
(Feedback จริงจากผู้ใช้ 2026-09-04 หลัง Upgrade Gemini API ออกจาก Free Tier — อยาก
ติดตามค่าใช้จ่ายที่เกิดขึ้นจริง)

ตัวเลขในนี้เป็น "ประมาณการ" จากจำนวน Token ที่ Gemini ตอบกลับมาจริง x Rate ที่บันทึกไว้
ณ ตอน Transaction เกิดขึ้น ไม่ใช่ยอด Bill จริงจาก Google Cloud Billing โดยตรง — ดูยอด
Bill จริงและตั้ง Monthly Spend Cap ได้ที่ Google AI Studio

จัดกลุ่มรายวัน/รายเดือนด้วย Python ล้วนๆ (ไม่ใช้ func.date_trunc ของ PostgreSQL) เพราะ
Test Suite รันบน SQLite ซึ่งไม่รองรับ Syntax เดียวกัน — ปริมาณ Log ของระบบภายในบริษัท
เดียวไม่มากพอที่จะมีปัญหาประสิทธิภาพจากการ Group ฝั่ง Python
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AiUsageLog, User
from app.schemas.ai_usage import AiUsageLogRead, AiUsagePeriodSummary, AiUsageSummaryResponse
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/ai-usage", tags=["ai-usage"])

_DAILY_WINDOW_DAYS = 30
_MONTHLY_WINDOW_MONTHS = 12


def _to_read(log: AiUsageLog, names: dict[int, str]) -> AiUsageLogRead:
    item = AiUsageLogRead.model_validate(log)
    return item.model_copy(
        update={"uploaded_by_name": names.get(log.uploaded_by_id) if log.uploaded_by_id else None}
    )


@router.get("", response_model=list[AiUsageLogRead])
def list_ai_usage(
    date_from: date | None = Query(default=None, description="กรองตั้งแต่วันที่ (รวม)"),
    date_to: date | None = Query(default=None, description="กรองถึงวันที่ (รวม)"),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[AiUsageLogRead]:
    query = db.query(AiUsageLog)
    if date_from is not None:
        start = datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        query = query.filter(AiUsageLog.created_at >= start)
    if date_to is not None:
        exclusive_end = datetime.combine(
            date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
        )
        query = query.filter(AiUsageLog.created_at < exclusive_end)

    logs = query.order_by(AiUsageLog.id.desc()).limit(limit).all()
    names = resolve_user_names(db, {log.uploaded_by_id for log in logs})
    return [_to_read(log, names) for log in logs]


def _summarize(period: str, logs: list[AiUsageLog]) -> AiUsagePeriodSummary:
    return AiUsagePeriodSummary(
        period=period,
        transaction_count=len(logs),
        success_count=sum(1 for log in logs if log.success),
        failure_count=sum(1 for log in logs if not log.success),
        total_prompt_tokens=sum(log.prompt_token_count for log in logs),
        total_output_tokens=sum(log.output_token_count for log in logs),
        total_cost_usd=sum((log.cost_usd for log in logs), Decimal("0")),
        total_cost_thb=sum((log.cost_thb for log in logs), Decimal("0")),
    )


@router.get("/summary", response_model=AiUsageSummaryResponse)
def summarize_ai_usage(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> AiUsageSummaryResponse:
    now = datetime.now(timezone.utc)
    today = now.date()
    window_start = today - timedelta(days=max(_DAILY_WINDOW_DAYS, 31 * _MONTHLY_WINDOW_MONTHS))
    window_start_dt = datetime.combine(window_start, datetime.min.time(), tzinfo=timezone.utc)

    logs = (
        db.query(AiUsageLog)
        .filter(AiUsageLog.created_at >= window_start_dt)
        .order_by(AiUsageLog.created_at.asc())
        .all()
    )

    by_day: OrderedDict[str, list[AiUsageLog]] = OrderedDict()
    by_month: OrderedDict[str, list[AiUsageLog]] = OrderedDict()
    for log in logs:
        day_key = log.created_at.strftime("%Y-%m-%d")
        month_key = log.created_at.strftime("%Y-%m")
        by_day.setdefault(day_key, []).append(log)
        by_month.setdefault(month_key, []).append(log)

    today_key = today.strftime("%Y-%m-%d")
    month_key = today.strftime("%Y-%m")

    daily_cutoff = today - timedelta(days=_DAILY_WINDOW_DAYS)
    daily_summaries = [
        _summarize(day_key, day_logs)
        for day_key, day_logs in by_day.items()
        if date.fromisoformat(day_key) >= daily_cutoff
    ]
    daily_summaries.reverse()  # ล่าสุดขึ้นก่อน

    monthly_summaries = [_summarize(m_key, m_logs) for m_key, m_logs in by_month.items()]
    monthly_summaries.reverse()
    monthly_summaries = monthly_summaries[:_MONTHLY_WINDOW_MONTHS]

    return AiUsageSummaryResponse(
        today=_summarize(today_key, by_day.get(today_key, [])),
        this_month=_summarize(month_key, by_month.get(month_key, [])),
        daily=daily_summaries,
        monthly=monthly_summaries,
    )
