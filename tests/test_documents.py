"""Test Upload + AI Extraction (Phase 4)

ไม่ยิง Network จริงไปหา Gemini — Override get_extraction_service ด้วย Fake Service แทน
เพื่อให้ Test รันซ้ำได้แน่นอน ไม่ขึ้นกับ Quota/Network/Google API จริง
"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.api.routes.documents import get_extraction_service
from app.main import app
from app.models import SourceDocType, User
from app.schemas.source_document import ExtractedItem, ExtractionResult
from app.services.gemini_extraction import GeminiExtractionError

_FAKE_PDF_BYTES = b"%PDF-1.4 fake content for testing\n"


class _FakeExtractionServiceSuccess:
    def extract(self, file_path: str) -> ExtractionResult:
        return ExtractionResult(
            detected_doc_type=SourceDocType.QUOTATION,
            vendor_name="บริษัท ทดสอบ จำกัด",
            document_no="QT-2026-001",
            items=[
                ExtractedItem(
                    product_name="SILICONE PAPER",
                    description="BS-W 1000MM.XL300M.",
                    color="Blonde",
                    quantity="2",
                    unit="Roll",
                    amount="1500",
                )
            ],
            ai_confidence=0.92,
        )


class _FakeExtractionServiceFailure:
    def extract(self, file_path: str) -> ExtractionResult:
        raise GeminiExtractionError("จำลอง Error: เรียก Gemini API ไม่สำเร็จ")


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


def test_upload_requires_login(client: TestClient):
    res = client.post(
        "/documents/upload",
        files={"file": ("q.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
        data={"doc_type": "quotation"},
    )
    assert res.status_code == 401


def test_upload_rejects_unsupported_content_type(client: TestClient, plain_user: User):
    _login(client)
    res = client.post(
        "/documents/upload",
        files={"file": ("q.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"doc_type": "quotation"},
    )
    assert res.status_code == 415


def test_upload_success_stores_extraction(client: TestClient, plain_user: User, tmp_path):
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceSuccess()
    try:
        _login(client)
        res = client.post(
            "/documents/upload",
            files={"file": ("q.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
            data={"doc_type": "quotation"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["doc_type"] == "quotation"
        assert body["extraction_error"] is None
        assert body["ai_extraction_raw_json"]["vendor_name"] == "บริษัท ทดสอบ จำกัด"
        assert body["ai_extraction_raw_json"]["items"][0]["product_name"] == "SILICONE PAPER"
        assert body["ai_extraction_raw_json"]["items"][0]["color"] == "Blonde"
        assert float(body["ai_confidence"]) == 0.92
    finally:
        del app.dependency_overrides[get_extraction_service]


def test_upload_without_doc_type_uses_ai_detected_type(
    client: TestClient, plain_user: User, tmp_path
):
    """Scope Revision (Phase 9): ไม่ระบุ doc_type ตอน Upload ได้ — ใช้ค่าที่ AI เดาแทน"""
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceSuccess()
    try:
        _login(client)
        res = client.post(
            "/documents/upload",
            files={"file": ("q.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["doc_type"] == "quotation"
    finally:
        del app.dependency_overrides[get_extraction_service]


def test_upload_extraction_failure_is_recorded_not_fatal(client: TestClient, plain_user: User):
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceFailure()
    try:
        _login(client)
        res = client.post(
            "/documents/upload",
            files={"file": ("r.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
            data={"doc_type": "receiving_note"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["ai_extraction_raw_json"] is None
        assert "จำลอง Error" in body["extraction_error"]
    finally:
        del app.dependency_overrides[get_extraction_service]


def test_get_document_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.get("/documents/9999")
    assert res.status_code == 404


def test_list_documents_requires_login(client: TestClient):
    res = client.get("/documents")
    assert res.status_code == 401


def test_review_document_saves_corrected_data(client: TestClient, plain_user: User):
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceSuccess()
    try:
        _login(client)
        upload_res = client.post(
            "/documents/upload",
            files={"file": ("q.pdf", io.BytesIO(_FAKE_PDF_BYTES), "application/pdf")},
            data={"doc_type": "quotation"},
        )
        doc_id = upload_res.json()["id"]

        review_res = client.patch(
            f"/documents/{doc_id}/review",
            json={
                "reviewed_data": {
                    "vendor_name": "บริษัท ทดสอบ จำกัด (แก้ไขแล้ว)",
                    "document_no": "QT-2026-001",
                    "items": [
                        {"description": "กระดาษ A4 80 แกรม", "quantity": "12", "unit": "รีม"}
                    ],
                }
            },
        )
        assert review_res.status_code == 200
        body = review_res.json()
        assert body["reviewed_data"]["vendor_name"] == "บริษัท ทดสอบ จำกัด (แก้ไขแล้ว)"
        assert body["reviewed_by_id"] is not None
        assert body["reviewed_at"] is not None
        # ai_extraction_raw_json (ผลดิบจาก AI) ต้องไม่ถูกเขียนทับ
        assert body["ai_extraction_raw_json"]["vendor_name"] == "บริษัท ทดสอบ จำกัด"
    finally:
        del app.dependency_overrides[get_extraction_service]
