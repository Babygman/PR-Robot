"""Test หน้า "ค่าใช้จ่าย AI" (2026-09-04, Feedback จริงจากผู้ใช้ หลัง Upgrade Gemini API
ออกจาก Free Tier) — ครอบคลุม (1) Upload บันทึก Log ค่าใช้จ่ายถูกต้องทั้งกรณีสำเร็จ/ไม่
สำเร็จ (2) Endpoint /ai-usage และ /ai-usage/summary ต้อง Login ก่อน (3) กรองตามวันที่
และสรุปยอดรายวัน/รายเดือนถูกต้อง
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.documents import get_extraction_service
from app.main import app
from app.models import AiUsageLog, SourceDocType, User
from app.schemas.source_document import ExtractedItem, ExtractionResult
from app.services.gemini_extraction import GeminiExtractionError, TokenUsage

_FAKE_PDF_BYTES = b"%PDF-1.4 fake content for testing\n"


class _FakeExtractionServiceSuccess:
    model = "gemini-3.6-flash"
    last_usage = TokenUsage(prompt_tokens=15_000, output_tokens=400, total_tokens=15_400)

    def extract(self, file_path: str) -> ExtractionResult:
        return ExtractionResult(
            detected_doc_type=SourceDocType.QUOTATION,
            vendor_name="บริษัท ทดสอบ จำกัด",
            items=[ExtractedItem(description="กระดาษ A4", quantity="10", unit="รีม")],
            ai_confidence=0.9,
        )


class _FakeExtractionServiceFailure:
    model = "gemini-3.6-flash"
    last_usage = None

    def extract(self, file_path: str) -> ExtractionResult:
        raise GeminiExtractionError("จำลอง Error: เรียก Gemini API ไม่สำเร็จ")


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


def test_list_ai_usage_requires_login(client: TestClient):
    res = client.get("/ai-usage")
    assert res.status_code == 401


def test_summary_requires_login(client: TestClient):
    res = client.get("/ai-usage/summary")
    assert res.status_code == 401


def test_upload_success_logs_ai_usage_transaction(client: TestClient, plain_user: User):
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceSuccess()
    try:
        _login(client)
        res = client.post(
            "/documents/upload",
            files={"file": ("quote.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
        )
        assert res.status_code == 201

        list_res = client.get("/ai-usage")
        assert list_res.status_code == 200
        rows = list_res.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["file_name"] == "quote.pdf"
        assert row["model"] == "gemini-3.6-flash"
        assert row["success"] is True
        assert row["error_message"] is None
        assert row["prompt_token_count"] == 15_000
        assert row["output_token_count"] == 400
        assert row["total_token_count"] == 15_400
        # cost_usd = (15000*0.75 + 400*3.75) / 1_000_000 = 0.012750
        assert Decimal(row["cost_usd"]) == Decimal("0.01275")
        assert row["uploaded_by_name"] == "Plain User"
    finally:
        del app.dependency_overrides[get_extraction_service]


def test_upload_failure_logs_ai_usage_transaction_as_unsuccessful(
    client: TestClient, plain_user: User
):
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceFailure()
    try:
        _login(client)
        res = client.post(
            "/documents/upload",
            files={"file": ("bad.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
        )
        assert res.status_code == 201  # Upload ยังสำเร็จแม้ AI อ่านไม่สำเร็จ (Design เดิม)

        rows = client.get("/ai-usage").json()
        assert len(rows) == 1
        row = rows[0]
        assert row["success"] is False
        assert "จำลอง Error" in row["error_message"]
        assert row["prompt_token_count"] == 0
        assert Decimal(row["cost_usd"]) == Decimal("0")
    finally:
        del app.dependency_overrides[get_extraction_service]


def test_ai_usage_date_filter(client: TestClient, plain_user: User, db_session: Session):
    _login(client)
    today = datetime.now(timezone.utc)
    old = today - timedelta(days=10)
    db_session.add_all(
        [
            AiUsageLog(
                file_name="today.pdf",
                model="gemini-3.6-flash",
                success=True,
                prompt_token_count=100,
                output_token_count=10,
                total_token_count=110,
                cost_usd=Decimal("0.001"),
                cost_thb=Decimal("0.033"),
                usd_to_thb_rate=Decimal("33"),
                uploaded_by_id=plain_user.id,
                created_at=today,
            ),
            AiUsageLog(
                file_name="old.pdf",
                model="gemini-3.6-flash",
                success=True,
                prompt_token_count=200,
                output_token_count=20,
                total_token_count=220,
                cost_usd=Decimal("0.002"),
                cost_thb=Decimal("0.066"),
                usd_to_thb_rate=Decimal("33"),
                uploaded_by_id=plain_user.id,
                created_at=old,
            ),
        ]
    )
    db_session.commit()

    all_rows = client.get("/ai-usage").json()
    assert len(all_rows) == 2

    filtered = client.get(
        "/ai-usage", params={"date_from": today.date().isoformat()}
    ).json()
    assert len(filtered) == 1
    assert filtered[0]["file_name"] == "today.pdf"


def test_ai_usage_summary_groups_today_and_this_month(
    client: TestClient, plain_user: User, db_session: Session
):
    _login(client)
    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=15)
    db_session.add_all(
        [
            AiUsageLog(
                file_name="a.pdf",
                model="gemini-3.6-flash",
                success=True,
                prompt_token_count=1000,
                output_token_count=100,
                total_token_count=1100,
                cost_usd=Decimal("0.01"),
                cost_thb=Decimal("0.33"),
                usd_to_thb_rate=Decimal("33"),
                uploaded_by_id=plain_user.id,
                created_at=now,
            ),
            AiUsageLog(
                file_name="b.pdf",
                model="gemini-3.6-flash",
                success=False,
                error_message="จำลอง Error",
                prompt_token_count=0,
                output_token_count=0,
                total_token_count=0,
                cost_usd=Decimal("0"),
                cost_thb=Decimal("0"),
                usd_to_thb_rate=Decimal("33"),
                uploaded_by_id=plain_user.id,
                created_at=now,
            ),
            AiUsageLog(
                file_name="c.pdf",
                model="gemini-3.6-flash",
                success=True,
                prompt_token_count=500,
                output_token_count=50,
                total_token_count=550,
                cost_usd=Decimal("0.005"),
                cost_thb=Decimal("0.165"),
                usd_to_thb_rate=Decimal("33"),
                uploaded_by_id=plain_user.id,
                created_at=last_month,
            ),
        ]
    )
    db_session.commit()

    summary = client.get("/ai-usage/summary").json()

    assert summary["today"]["transaction_count"] == 2
    assert summary["today"]["success_count"] == 1
    assert summary["today"]["failure_count"] == 1
    assert Decimal(summary["today"]["total_cost_thb"]) == Decimal("0.33")

    # this_month รวมเฉพาะ Transaction เดือนปัจจุบัน (a.pdf, b.pdf) ไม่รวม c.pdf เดือนก่อน
    assert summary["this_month"]["transaction_count"] == 2

    monthly_periods = [row["period"] for row in summary["monthly"]]
    assert now.strftime("%Y-%m") in monthly_periods
    if last_month.strftime("%Y-%m") != now.strftime("%Y-%m"):
        assert last_month.strftime("%Y-%m") in monthly_periods
