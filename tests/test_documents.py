"""Test Upload + AI Extraction (Phase 4)

ไม่ยิง Network จริงไปหา Gemini — Override get_extraction_service ด้วย Fake Service แทน
เพื่อให้ Test รันซ้ำได้แน่นอน ไม่ขึ้นกับ Quota/Network/Google API จริง
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.documents import get_extraction_service
from app.main import app
from app.models import PRStatus, PurchasingRequisition, SourceDocType, SourceDocument, User
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
    # .txt กลายเป็นชนิดที่รองรับแล้ว (2026-09-04 — เพิ่ม Word/Excel/CSV/TXT) จึงเปลี่ยน
    # มาใช้ .zip แทนเพื่อทดสอบชนิดไฟล์ที่ยังไม่รองรับจริงๆ
    _login(client)
    res = client.post(
        "/documents/upload",
        files={"file": ("q.zip", io.BytesIO(b"PK\x03\x04fake"), "application/zip")},
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


def test_upload_accepts_word_excel_csv_txt(client: TestClient, plain_user: User):
    """รองรับ Word/Excel/CSV/TXT เพิ่มจากเดิม (Feedback จริงจากผู้ใช้ 2026-09-04) —
    ตรวจแค่ระดับ Endpoint ว่า Content-Type/นามสกุลผ่านแล้วเรียก Extraction Service
    ต่อสำเร็จ (Logic แตกข้อความจริงทดสอบแยกใน tests/test_gemini_extraction.py)"""
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionServiceSuccess()
    try:
        _login(client)
        cases = [
            (
                "q.docx",
                b"fake docx bytes",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            (
                "q.xlsx",
                b"fake xlsx bytes",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
            ("q.csv", b"Product,Qty\nA4,10\n", "text/csv"),
            ("q.txt", b"hello quotation", "text/plain"),
        ]
        for filename, content, content_type in cases:
            res = client.post(
                "/documents/upload",
                files={"file": (filename, io.BytesIO(content), content_type)},
                data={"doc_type": "quotation"},
            )
            assert res.status_code == 201, f"{filename} ควร Upload ผ่าน แต่ได้ {res.text}"
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


def test_list_documents_unlinked_only_excludes_docs_used_in_a_pr(
    client: TestClient, plain_user: User, db_session: Session
):
    """Feedback จริงจากผู้ใช้ 2026-09-03: หน้าสร้าง PR ใหม่ไม่ควรให้เลือกเอกสารที่ถูก
    ใช้สร้าง PR ไปแล้วซ้ำอีก — รายการยาวขึ้นเรื่อยๆ ไม่มีประโยชน์"""
    used_doc = SourceDocument(
        file_path="storage/uploads/used.pdf",
        doc_type=SourceDocType.QUOTATION,
        uploaded_by_id=plain_user.id,
    )
    unused_doc = SourceDocument(
        file_path="storage/uploads/unused.pdf",
        doc_type=SourceDocType.QUOTATION,
        uploaded_by_id=plain_user.id,
    )
    db_session.add_all([used_doc, unused_doc])
    db_session.commit()

    pr = PurchasingRequisition(
        pr_no=1,
        section="A",
        division="B",
        doc_date=date(2026, 9, 3),
        status=PRStatus.DRAFT,
        requested_by_id=plain_user.id,
    )
    db_session.add(pr)
    db_session.flush()
    used_doc.pr_id = pr.id
    db_session.commit()

    _login(client)
    res = client.get("/documents", params={"unlinked_only": True})
    assert res.status_code == 200
    ids = {d["id"] for d in res.json()}
    assert unused_doc.id in ids
    assert used_doc.id not in ids

    # ไม่ใส่ unlinked_only ต้องเห็นครบทั้งคู่เหมือนเดิม (ไม่กระทบ Endpoint เดิม)
    res_all = client.get("/documents")
    ids_all = {d["id"] for d in res_all.json()}
    assert {used_doc.id, unused_doc.id} <= ids_all


def test_delete_document_success_removes_row_and_file(
    client: TestClient, plain_user: User, db_session: Session, tmp_path
):
    file_path = tmp_path / "to_delete.pdf"
    file_path.write_bytes(b"%PDF-1.4 dummy")
    doc = SourceDocument(
        file_path=str(file_path), doc_type=SourceDocType.QUOTATION, uploaded_by_id=plain_user.id
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    _login(client)
    res = client.delete(f"/documents/{doc.id}")
    assert res.status_code == 204
    assert db_session.get(SourceDocument, doc.id) is None
    assert not Path(file_path).exists()


def test_delete_document_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.delete("/documents/9999")
    assert res.status_code == 404


def test_delete_document_rejected_if_linked_to_pr(
    client: TestClient, plain_user: User, db_session: Session
):
    doc = SourceDocument(
        file_path="storage/uploads/linked.pdf",
        doc_type=SourceDocType.QUOTATION,
        uploaded_by_id=plain_user.id,
    )
    db_session.add(doc)
    db_session.commit()

    pr = PurchasingRequisition(
        pr_no=1,
        section="A",
        division="B",
        doc_date=date(2026, 9, 3),
        status=PRStatus.DRAFT,
        requested_by_id=plain_user.id,
    )
    db_session.add(pr)
    db_session.flush()
    doc.pr_id = pr.id
    db_session.commit()

    _login(client)
    res = client.delete(f"/documents/{doc.id}")
    assert res.status_code == 409
    assert db_session.get(SourceDocument, doc.id) is not None


def test_delete_document_requires_login(client: TestClient):
    res = client.delete("/documents/1")
    assert res.status_code == 401
