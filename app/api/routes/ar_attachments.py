"""เอกสารแนบของ Approval Request (AR Attachments, Phase A — Correction 2026-09-10)

ดู app/models/ar_attachment.py สำหรับที่มาของ Design (แยกจาก SourceDocument ของ PR
โดยเจตนา) — Pattern การเก็บไฟล์เดียวกับ app/api/routes/documents.py: upload_document
(uuid4().hex + นามสกุลเดิม เก็บใน settings.upload_dir, ตรวจ Content-Type + นามสกุลคู่
กัน) แต่จำกัดชนิดไฟล์แคบกว่า — Feedback จริงจากผู้ใช้ระบุไว้ชัดเจนแค่ 3 อย่าง: "pdf,
excel, picture" เท่านั้น (ไม่ใช่ Word/CSV/TXT เหมือนของ PR)

Flow:
1. POST /ars/{ar_id}/attachments -> Upload เอกสารแนบ 1 ไฟล์ (เรียกวนซ้ำฝั่งหน้าเว็บถ้า
   เลือกหลายไฟล์พร้อมกัน) — อนุญาตทั้งตอนสร้าง/แก้ไข AR (ยัง Draft) และ "แทรกเอกสาร
   เพิ่มเติมระหว่าง Approval" (ผู้อนุมัติ Level ปัจจุบัน/FA ที่กำลังรอตัดสินใจอยู่) ดู
   Permission เต็มที่ budget_workflow.can_upload_attachment
2. GET /ars/{ar_id}/attachments -> รายการเอกสารแนบทั้งหมดของ AR ใบนี้
3. GET /ars/{ar_id}/attachments/{attachment_id}/download -> ดาวน์โหลดไฟล์จริง (ต้อง
   Login เท่านั้น — ไม่ Mount เป็น Static ดู app/main.py)
4. DELETE /ars/{ar_id}/attachments/{attachment_id} -> ลบ (เฉพาะคนที่อัปโหลดเอง หรือ
   เจ้าของ AR หรือ Admin เท่านั้น — กันผู้อนุมัติคนอื่นในกลุ่มเดียวกันลบเอกสารของคนอื่น)
"""

from __future__ import annotations

import uuid
from pathlib import Path

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import ApprovalRequest, ARAttachment, AuditLog, User
from app.schemas.ar_attachment import (
    ARAttachmentRead,
    ARAttachmentXlsxPreview,
    ARAttachmentXlsxSheetPreview,
)
from app.services import budget_workflow
from app.services.user_lookup import resolve_user_names

# Comment 4 (2026-09-10 — xlsx-preview): จำกัดขนาดตารางที่ส่งกลับให้ Preview กันไฟล์ใหญ่
# เกินไปทำหน้าเว็บค้าง — พอสำหรับดูเนื้อหาคร่าวๆ ถ้าต้องการดูฉบับเต็มยังกดดาวน์โหลดได้
# _XLSX_PREVIEW_MAX_SHEETS (แก้ไขเพิ่ม): จำกัดจำนวน Sheet ที่ส่งกลับด้วย กันไฟล์ที่มี Sheet
# เยอะผิดปกติ
_XLSX_PREVIEW_MAX_ROWS = 300
_XLSX_PREVIEW_MAX_COLS = 40
_XLSX_PREVIEW_MAX_SHEETS = 20

router = APIRouter(prefix="/ars/{ar_id}/attachments", tags=["ar-attachments"])

# เฉพาะ 3 ชนิดที่ผู้ใช้ระบุจริง: PDF / Excel / รูปภาพ (แคบกว่า documents.py ของ PR
# โดยเจตนา — ดู Docstring บนสุดของไฟล์นี้)
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls (และบาง Browser ส่ง .csv มาเป็น Content-Type นี้)
}
_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".xlsx", ".xls"}
_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB — เท่ากับ documents.py


def _get_ar_or_404(db: Session, ar_id: int) -> ApprovalRequest:
    ar = db.get(ApprovalRequest, ar_id)
    if ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Approval Request")
    return ar


def _get_attachment_or_404(db: Session, ar_id: int, attachment_id: int) -> ARAttachment:
    attachment = db.get(ARAttachment, attachment_id)
    if attachment is None or attachment.ar_id != ar_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบเอกสารแนบนี้")
    return attachment


def _to_read(db: Session, attachment: ARAttachment) -> ARAttachmentRead:
    names = resolve_user_names(db, {attachment.uploaded_by_id})
    data = ARAttachmentRead.model_validate(attachment, from_attributes=True)
    return data.model_copy(update={"uploaded_by_name": names.get(attachment.uploaded_by_id)})


@router.post("", response_model=ARAttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_ar_attachment(
    ar_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARAttachmentRead:
    ar = _get_ar_or_404(db, ar_id)
    if not budget_workflow.can_upload_attachment(db, ar, current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "คุณไม่มีสิทธิ์แนบเอกสารให้ Approval Request นี้ในสถานะปัจจุบัน",
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

    attachment = ARAttachment(
        ar_id=ar.id,
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
            ar_id=ar.id,
            action="ar.attachment_uploaded",
            actor_id=current_user.id,
            detail={"attachment_id": attachment.id, "file_name": attachment.file_name},
        )
    )
    db.commit()
    db.refresh(attachment)
    return _to_read(db, attachment)


@router.get("", response_model=list[ARAttachmentRead])
def list_ar_attachments(
    ar_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[ARAttachmentRead]:
    _get_ar_or_404(db, ar_id)
    attachments = (
        db.query(ARAttachment)
        .filter(ARAttachment.ar_id == ar_id)
        .order_by(ARAttachment.uploaded_at)
        .all()
    )
    return [_to_read(db, a) for a in attachments]


@router.get("/{attachment_id}/download")
def download_ar_attachment(
    ar_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> FileResponse:
    _get_ar_or_404(db, ar_id)
    attachment = _get_attachment_or_404(db, ar_id, attachment_id)
    file_path = Path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไฟล์เอกสารแนบนี้หายไปจาก Server แล้ว")
    # Correction 2026-09-10 (Comment 4 — My Approvals Preview): เดิมส่ง
    # Content-Disposition: attachment (Default ของ FileResponse) เสมอ ทำให้เบราว์เซอร์
    # บังคับ Download ทุกครั้งแม้จะเปิดใน <iframe>/<img> เพื่อ Preview ในหน้าก็ตาม (โดย
    # เฉพาะ PDF ที่ผู้ใช้แจ้งปัญหา) เปลี่ยนเป็น inline ให้เบราว์เซอร์แสดงในหน้าได้แทน — ตัว
    # Viewer ในตัวเบราว์เซอร์เอง (Chrome/Firefox) มี Page Navigation/Zoom ของ PDF ให้อยู่
    # แล้วในตัว ไม่ต้องเพิ่ม Library ใหม่
    return FileResponse(
        path=str(file_path),
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.file_name,
        content_disposition_type="inline",
    )


@router.get("/{attachment_id}/xlsx-preview", response_model=ARAttachmentXlsxPreview)
def preview_ar_attachment_xlsx(
    ar_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> ARAttachmentXlsxPreview:
    """Comment 4 (2026-09-10): Preview เนื้อหาไฟล์ Excel (.xlsx เท่านั้น — .xls รูปแบบเก่า
    openpyxl อ่านไม่ได้ จะโดน 422 กลับไป ฝั่งหน้าเว็บ Fallback เป็นลิงก์ดาวน์โหลดแทน) อ่าน
    ทุก Sheet (จำกัดที่ _XLSX_PREVIEW_MAX_SHEETS) จำกัดจำนวนแถว/คอลัมน์ต่อ Sheet กันไฟล์
    ใหญ่เกินไป — แก้ไขเพิ่ม 2026-09-10: เดิมอ่านแค่ Sheet แรก ผู้ใช้แจ้งว่าไฟล์จริงมีหลาย
    Tab ต้องเห็นครบทุก Tab"""
    _get_ar_or_404(db, ar_id)
    attachment = _get_attachment_or_404(db, ar_id, attachment_id)
    file_path = Path(attachment.stored_path)
    if not file_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไฟล์เอกสารแนบนี้หายไปจาก Server แล้ว")

    try:
        workbook = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ไม่สามารถอ่านไฟล์นี้เพื่อ Preview ได้ (รองรับเฉพาะ .xlsx — ไฟล์ .xls แบบเก่ายังใช้ไม่ได้)",
        ) from exc

    try:
        sheets: list[ARAttachmentXlsxSheetPreview] = []
        for sheet in workbook.worksheets[:_XLSX_PREVIEW_MAX_SHEETS]:
            rows: list[list[str | float | int | None]] = []
            truncated = False
            for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                if row_index >= _XLSX_PREVIEW_MAX_ROWS:
                    truncated = True
                    break
                row_values = list(row[:_XLSX_PREVIEW_MAX_COLS])
                if len(row) > _XLSX_PREVIEW_MAX_COLS:
                    truncated = True
                cleaned_row = [
                    None if v is None else (v if isinstance(v, str | int | float) else str(v))
                    for v in row_values
                ]
                rows.append(cleaned_row)
            sheets.append(
                ARAttachmentXlsxSheetPreview(sheet_name=sheet.title, rows=rows, truncated=truncated)
            )
    finally:
        workbook.close()

    return ARAttachmentXlsxPreview(sheets=sheets)


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ar_attachment(
    ar_id: int,
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    ar = _get_ar_or_404(db, ar_id)
    attachment = _get_attachment_or_404(db, ar_id, attachment_id)

    is_uploader = attachment.uploaded_by_id == current_user.id
    is_owner = ar.requested_by_id == current_user.id
    if not (is_uploader or is_owner or current_user.is_admin):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "ลบได้เฉพาะคนที่อัปโหลดเอง เจ้าของ Approval Request หรือ Admin เท่านั้น",
        )

    file_path = Path(attachment.stored_path)
    db.delete(attachment)
    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.attachment_deleted",
            actor_id=current_user.id,
            detail={"attachment_id": attachment_id, "file_name": attachment.file_name},
        )
    )
    db.commit()

    # ลบไฟล์จริงบน Disk แบบ Best-Effort — เหมือน documents.py: delete_document
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
