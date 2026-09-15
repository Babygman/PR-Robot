"""เอกสารแนบของ PR (PR Attachments, Phase 11, 2026-09-15)

Pattern เดียวกับ app/api/routes/ar_attachments.py ทุกประการ (ชนิดไฟล์ที่อนุญาตเหมือน
กัน — PDF/Excel/รูปภาพ) แต่แยกตาราง (PRAttachment) และ Permission ผูกกับ
pr_budget_workflow.can_upload_attachment แทน — ไม่มี xlsx-preview Endpoint (Scope
รอบนี้ยังไม่ต้องมี ตัดออกจาก Phase นี้ก่อน เพิ่มทีหลังได้ถ้าต้องการ)

Flow: เหมือน ar_attachments.py — Upload/List/Download/Delete
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AuditLog, PRAttachment, PurchasingRequisition, User
from app.schemas.pr_attachment import PRAttachmentRead
from app.services import pr_budget_workflow
from app.services.user_lookup import resolve_user_names

_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls (และบาง Browser ส่ง .csv มาเป็น Content-Type นี้)
}
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".xlsx", ".xls"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB — เท่ากับ ar_attachments.py/documents.py

router = APIRouter(prefix="/prs/{pr_id}/attachments", tags=["pr-attachments"])


def _get_pr_or_404(db: Session, pr_id: int) -> PurchasingRequisition:
    pr = db.get(PurchasingRequisition, pr_id)
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ PR")
    return pr


def _get_attachment_or_404(db: Session, pr_id: int, attachment_id: int) -> PRAttachment:
    attachment = db.get(PRAttachment, attachment_id)
    if attachment is None or attachment.pr_id != pr_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเอกสารแนบนี้")
    return attachment


def _to_read(db: Session, attachment: PRAttachment) -> PRAttachmentRead:
    names = resolve_user_names(db, {attachment.uploaded_by_id})
    data = PRAttachmentRead.model_validate(attachment, from_attributes=True)
    return data.model_copy(update={"uploaded_by_name": names.get(attachment.uploaded_by_id)})


@router.post("", response_model=PRAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_pr_attachment(
    pr_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRAttachmentRead:
    pr = _get_pr_or_404(db, pr_id)
    if not pr_budget_workflow.can_upload_attachment(db, pr, current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "คุณไม่มีสิทธิ์แนบเอกสารให้ PR นี้ในสถานะปัจจุบัน"
        )

    file_suffix = Path(file.filename or "").suffix.lower()
    if file.content_type not in _ALLOWED_CONTENT_TYPES and file_suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "รองรับเฉพาะไฟล์ PDF/Excel (.xlsx, .xls)/รูปภาพ (PNG, JPEG, WEBP) "
            f"(ได้รับ {file.content_type})",
        )

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ไฟล์ใหญ่เกิน 15 MB")
    if len(content) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไฟล์ว่างเปล่า")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{file_suffix}"
    stored_path = upload_dir / stored_name
    stored_path.write_bytes(content)

    attachment = PRAttachment(
        pr_id=pr.id,
        file_name=(file.filename or stored_name)[:512],
        stored_path=str(stored_path),
        content_type=file.content_type,
        file_size=len(content),
        uploaded_by_id=current_user.id,
    )
    db.add(attachment)
    db.flush()

    db.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.attachment_uploaded",
            actor_id=current_user.id,
            detail={"attachment_id": attachment.id, "file_name": attachment.file_name},
        )
    )
    db.commit()
    db.refresh(attachment)
    return _to_read(db, attachment)


@router.get("", response_model=list[PRAttachmentRead])
def list_pr_attachments(
    pr_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[PRAttachmentRead]:
    _get_pr_or_404(db, pr_id)
    attachments = (
        db.query(PRAttachment)
        .filter(PRAttachment.pr_id == pr_id)
        .order_by(PRAttachment.uploaded_at)
        .all()
    )
    return [_to_read(db, a) for a in attachments]


@router.get("/{attachment_id}/download")
def download_pr_attachment(
    pr_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> FileResponse:
    _get_pr_or_404(db, pr_id)
    attachment = _get_attachment_or_404(db, pr_id, attachment_id)
    file_path = Path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไฟล์เอกสารแนบนี้หายไปจาก Server แล้ว")
    return FileResponse(
        path=str(file_path),
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.file_name,
        content_disposition_type="inline",
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pr_attachment(
    pr_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    pr = _get_pr_or_404(db, pr_id)
    attachment = _get_attachment_or_404(db, pr_id, attachment_id)

    is_uploader = attachment.uploaded_by_id == current_user.id
    is_owner = pr.requested_by_id == current_user.id
    if not (is_uploader or is_owner or current_user.is_admin):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "ลบได้เฉพาะคนที่อัปโหลดเอง เจ้าของ PR หรือ Admin เท่านั้น"
        )

    file_path = Path(attachment.stored_path)
    db.delete(attachment)
    db.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.attachment_deleted",
            actor_id=current_user.id,
            detail={"attachment_id": attachment_id, "file_name": attachment.file_name},
        )
    )
    db.commit()

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
