"""Upload เอกสารต้นทาง (ใบเสนอราคา/ใบยืมสินค้า/ใบส่งสินค้า/ใบรับของ) + เรียก AI
สกัดข้อมูล (Phase 4)

Scope Revision (Phase 9, 2026-09-03): ไม่บังคับเลือกประเภทเอกสารตอน Upload แล้ว —
AI เดาประเภทเองจากเนื้อหา (detected_doc_type) แล้วเก็บเป็นค่าเริ่มต้นให้ ผู้ใช้แก้ไข
ทีหลังผ่าน /review ได้ถ้า AI เดาผิด — รองรับ Upload หลายไฟล์พร้อมกัน (ฝั่งหน้าเว็บ
เรียก Endpoint นี้วนซ้ำทีละไฟล์ แล้วรวมผลเป็นตารางเดียวตอนสร้าง PR)

Flow:
1. POST /documents/upload -> บันทึกไฟล์ + เรียก Gemini สกัดข้อมูลทันที (Sync) รวมถึง
   เดาประเภทเอกสาร -> คืนผลลัพธ์ ถ้า Gemini เรียกไม่สำเร็จ (Network/Quota/Key ผิด)
   จะไม่ทำให้ Request ล้มเหลว — บันทึกไฟล์ไว้และเก็บ extraction_error ไว้ ผู้ใช้ Key
   ข้อมูลเองได้ผ่าน /review
2. GET /documents/{id} -> ดูข้อมูลเอกสาร + ผลสกัดจาก AI
3. GET /documents -> ประวัติเอกสารที่เคยอัปโหลดทั้งหมด
4. PATCH /documents/{id}/review -> บันทึกข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว (รวมถึงแก้
   doc_type ถ้า AI เดาผิด) แยกจาก ai_extraction_raw_json เพื่อรักษาผลดิบจาก AI ไว้เป็น
   Audit Trail เสมอ
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AiUsageLog, AuditLog, SourceDocType, SourceDocument, User
from app.schemas.source_document import (
    ExtractionResult,
    SourceDocumentRead,
    SourceDocumentReviewUpdate,
)
from app.services.ai_pricing import calculate_cost_usd
from app.services.gemini_extraction import (
    GeminiExtractionError,
    GeminiExtractionService,
    TokenUsage,
)

router = APIRouter(prefix="/documents", tags=["documents"])

# Word/Excel/CSV/TXT (Feedback จริงจากผู้ใช้ 2026-09-04) — ตรวจสอบทั้ง Content-Type และ
# นามสกุลไฟล์คู่กัน เพราะ Browser/OS บางตัวส่ง Content-Type ของ .csv/.docx มาไม่ตรงกัน
# เสมอไป (เช่น .csv บาง Client ส่งเป็น "application/vnd.ms-excel") — ผ่านแค่ทางใดทางหนึ่ง
# ก็พอ กันปฏิเสธไฟล์ที่ถูกต้องผิดพลาด
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "text/csv",
    "application/vnd.ms-excel",  # บาง Browser/Windows ส่ง .csv มาเป็น Content-Type นี้
    "text/plain",  # .txt
}
_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx", ".xlsx", ".csv", ".txt",
}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


def get_extraction_service() -> GeminiExtractionService:
    return GeminiExtractionService()


def _log_ai_usage(
    db: Session,
    *,
    document_id: int | None,
    file_name: str,
    model: str,
    usage: TokenUsage | None,
    success: bool,
    error_message: str | None,
    uploaded_by_id: int,
) -> None:
    """บันทึกค่าใช้จ่าย AI โดยประมาณของ 1 Transaction สำหรับหน้า "ค่าใช้จ่าย AI"
    (2026-09-04) — เรียกทั้งกรณีสำเร็จและไม่สำเร็จ (usage เป็น None ได้ถ้า Fail ก่อนได้
    Response กลับมาจาก Gemini เลย เช่น Retry หมด/อ่านไฟล์เสีย — จะบันทึก Token/ค่าใช้
    จ่ายเป็น 0 แต่ยังเห็นว่ามี Transaction เกิดขึ้นและ Fail ด้วยเหตุผลอะไร)"""
    prompt_tokens = usage.prompt_tokens if usage else 0
    output_tokens = usage.output_tokens if usage else 0
    total_tokens = usage.total_tokens if usage else 0
    cost_usd = calculate_cost_usd(model, prompt_tokens, output_tokens) if usage else Decimal("0")
    rate = Decimal(str(settings.gemini_usd_to_thb_rate))
    cost_thb = (cost_usd * rate).quantize(Decimal("0.0001"))
    db.add(
        AiUsageLog(
            document_id=document_id,
            file_name=file_name[:512],
            model=model,
            success=success,
            error_message=error_message,
            prompt_token_count=prompt_tokens,
            output_token_count=output_tokens,
            total_token_count=total_tokens,
            cost_usd=cost_usd,
            cost_thb=cost_thb,
            usd_to_thb_rate=rate,
            uploaded_by_id=uploaded_by_id,
        )
    )


@router.post("/upload", response_model=SourceDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: SourceDocType | None = Form(default=None, description="ไม่ระบุก็ได้ — ให้ AI เดาเอง"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    extraction_service: GeminiExtractionService = Depends(get_extraction_service),
) -> SourceDocument:
    file_suffix = Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_CONTENT_TYPES and file_suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"รองรับเฉพาะไฟล์ PDF/PNG/JPEG/WEBP/DOCX/XLSX/CSV/TXT (ได้รับ {file.content_type})",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ไฟล์ใหญ่เกิน 15 MB")
    if len(content) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไฟล์ว่างเปล่า")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)

    document = SourceDocument(
        file_path=str(stored_path),
        doc_type=doc_type,
        uploaded_by_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    db.add(
        AuditLog(
            action="document.uploaded",
            actor_id=current_user.id,
            detail={"document_id": document.id, "doc_type": doc_type.value if doc_type else None},
        )
    )
    db.commit()

    try:
        result: ExtractionResult = extraction_service.extract(str(stored_path))
    except GeminiExtractionError as exc:
        document.extraction_error = str(exc)
        # บันทึกค่าใช้จ่าย AI แม้ Fail (2026-09-04) — usage อาจมีค่าอยู่ถ้า Gemini ตอบ
        # กลับมาแล้วแต่ Parse ไม่ผ่าน (ยังถูก Bill Token ไปแล้ว) หรือเป็น None ถ้า Fail
        # ก่อนได้ Response เลย (เช่น Retry หมด/อ่านไฟล์เสีย)
        _log_ai_usage(
            db,
            document_id=document.id,
            file_name=file.filename or stored_name,
            model=extraction_service.model,
            usage=extraction_service.last_usage,
            success=False,
            error_message=str(exc),
            uploaded_by_id=current_user.id,
        )
        db.commit()
        db.refresh(document)
        return document

    document.ai_extraction_raw_json = result.model_dump(mode="json")
    document.ai_confidence = (
        Decimal(str(result.ai_confidence)) if result.ai_confidence is not None else None
    )
    # ถ้าไม่ได้ระบุ doc_type มาตอน Upload ใช้ค่าที่ AI เดาแทน (ยังแก้ทีหลังผ่าน
    # /review ได้เสมอถ้าเดาผิด) — Scope Revision Phase 9, 2026-09-03
    if document.doc_type is None and result.detected_doc_type is not None:
        document.doc_type = result.detected_doc_type
    _log_ai_usage(
        db,
        document_id=document.id,
        file_name=file.filename or stored_name,
        model=extraction_service.model,
        usage=extraction_service.last_usage,
        success=True,
        error_message=None,
        uploaded_by_id=current_user.id,
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[SourceDocumentRead])
def list_documents(
    unlinked_only: bool = Query(
        default=False,
        description=(
            "true = คืนเฉพาะเอกสารที่ยังไม่ถูกใช้สร้าง PR ไหนเลย (pr_id เป็น Null) — "
            "ใช้ตอนแสดงรายการให้เลือกที่หน้าสร้าง PR ใหม่ เพื่อไม่ให้เอกสารที่ถูกใช้ไป"
            "แล้วโผล่ให้เลือกซ้ำ (Feedback จริงจากผู้ใช้ 2026-09-03)"
        ),
    ),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[SourceDocument]:
    query = db.query(SourceDocument)
    if unlinked_only:
        query = query.filter(SourceDocument.pr_id.is_(None))
    return query.order_by(SourceDocument.id.desc()).all()


@router.get("/{document_id}", response_model=SourceDocumentRead)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> SourceDocument:
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเอกสาร")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """ลบเอกสารต้นทางที่อัปโหลดผิด/ไม่ต้องการแล้ว (Feedback จริงจากผู้ใช้ 2026-09-03 —
    รายการเอกสารที่หน้าสร้าง PR สะสมยาวขึ้นเรื่อยๆ ไม่มีทางลบทิ้งได้)

    ลบไม่ได้ถ้าเอกสารถูกใช้สร้าง PR ไปแล้ว (pr_id ไม่ใช่ Null) — กัน Audit Trail ของ PR
    นั้นขาดหาย ต้องลบ/แก้ไข PR นั้นก่อนถ้าต้องการลบเอกสารจริงๆ
    """
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเอกสาร")
    if document.pr_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "ลบไม่ได้ — เอกสารนี้ถูกใช้สร้าง PR ไปแล้ว"
        )

    file_path = Path(document.file_path)
    db.delete(document)
    db.add(
        AuditLog(
            action="document.deleted",
            actor_id=current_user.id,
            detail={"document_id": document_id, "file_path": document.file_path},
        )
    )
    db.commit()

    # ลบไฟล์จริงบน Disk แบบ Best-Effort — ถ้าไฟล์หายไปแล้ว/ลบไม่ได้ ไม่ทำให้ Request
    # ทั้งหมดล้มเหลว (แถวใน Database ลบสำเร็จแล้วซึ่งสำคัญกว่า)
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{document_id}/review", response_model=SourceDocumentRead)
def review_document(
    document_id: int,
    body: SourceDocumentReviewUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceDocument:
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเอกสาร")

    document.reviewed_data = body.reviewed_data.model_dump(mode="json")
    document.reviewed_by_id = current_user.id
    document.reviewed_at = datetime.now(timezone.utc)
    if body.doc_type is not None:
        document.doc_type = body.doc_type
    db.commit()
    db.refresh(document)

    db.add(
        AuditLog(
            action="document.reviewed",
            actor_id=current_user.id,
            detail={"document_id": document.id},
        )
    )
    db.commit()

    return document
