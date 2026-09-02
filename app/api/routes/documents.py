"""Upload เอกสารต้นทาง (ใบเสนอราคา/ใบรับของ) + เรียก AI สกัดข้อมูล (Phase 4)

Flow:
1. POST /documents/upload -> บันทึกไฟล์ + เรียก Gemini สกัดข้อมูลทันที (Sync) -> คืนผลลัพธ์
   ถ้า Gemini เรียกไม่สำเร็จ (Network/Quota/Key ผิด) จะไม่ทำให้ Request ล้มเหลว —
   บันทึกไฟล์ไว้และเก็บ extraction_error ไว้ ผู้ใช้ Key ข้อมูลเองได้ผ่าน /review
2. GET /documents/{id} -> ดูข้อมูลเอกสาร + ผลสกัดจาก AI
3. GET /documents -> ประวัติเอกสารที่เคยอัปโหลดทั้งหมด
4. PATCH /documents/{id}/review -> บันทึกข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว
   (แยกจาก ai_extraction_raw_json เพื่อรักษาผลดิบจาก AI ไว้เป็น Audit Trail เสมอ)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, SourceDocType, SourceDocument, User
from app.schemas.source_document import (
    ExtractionResult,
    SourceDocumentRead,
    SourceDocumentReviewUpdate,
)
from app.services.gemini_extraction import GeminiExtractionError, GeminiExtractionService

router = APIRouter(prefix="/documents", tags=["documents"])

_ALLOWED_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB


def get_extraction_service() -> GeminiExtractionService:
    return GeminiExtractionService()


@router.post("/upload", response_model=SourceDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: SourceDocType = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    extraction_service: GeminiExtractionService = Depends(get_extraction_service),
) -> SourceDocument:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"รองรับเฉพาะไฟล์ PDF/PNG/JPEG/WEBP (ได้รับ {file.content_type})",
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
            detail={"document_id": document.id, "doc_type": doc_type.value},
        )
    )
    db.commit()

    try:
        result: ExtractionResult = extraction_service.extract(str(stored_path))
    except GeminiExtractionError as exc:
        document.extraction_error = str(exc)
        db.commit()
        db.refresh(document)
        return document

    document.ai_extraction_raw_json = result.model_dump(mode="json")
    document.ai_confidence = (
        Decimal(str(result.ai_confidence)) if result.ai_confidence is not None else None
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[SourceDocumentRead])
def list_documents(
    db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[SourceDocument]:
    return db.query(SourceDocument).order_by(SourceDocument.id.desc()).all()


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
