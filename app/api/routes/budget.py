"""Budget Master + Excel Upload (Phase 10, 2026-09-09, Business Decision v4.1)

Upload สงวนสิทธิ์ให้ `is_fa` หรือ `is_admin` เท่านั้น (Design §4/§1) — ดู
app/services/budget_excel.py สำหรับ Parser/Validator/Upsert Logic เต็ม
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_fa_or_admin
from app.db.session import get_db
from app.models import ARBudgetType, BudgetMaster, BudgetUploadBatch, User
from app.schemas.budget import (
    BudgetMasterCreate,
    BudgetMasterRead,
    BudgetMasterUpdate,
    BudgetUploadBatchRead,
    BudgetUploadResult,
    BudgetUploadRowResult,
)
from app.services.budget_excel import build_export_workbook, parse_and_upsert
from app.services.system_log import log_event
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/budget", tags=["budget"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB — ไฟล์ Excel งบประมาณไม่ควรใหญ่กว่านี้


@router.post("/upload", response_model=BudgetUploadResult, status_code=status.HTTP_201_CREATED)
async def upload_budget_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_fa_or_admin),
) -> BudgetUploadResult:
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ไฟล์ใหญ่เกิน 5MB")
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไฟล์ว่างเปล่า")

    batch, outcomes = parse_and_upsert(
        db,
        filename=file.filename or "budget.xlsx",
        file_bytes=content,
        uploaded_by_id=current_user.id,
    )
    log_event(
        db,
        actor_id=current_user.id,
        action="budget.bulk_uploaded",
        entity_type="budget",
        entity_id=batch.id,
        detail={
            "filename": batch.filename,
            "total_rows": batch.total_rows,
            "success_rows": batch.success_rows,
            "error_rows": batch.error_rows,
        },
    )
    db.commit()
    db.refresh(batch)

    return BudgetUploadResult(
        batch_id=batch.id,
        filename=batch.filename,
        total_rows=batch.total_rows,
        success_rows=batch.success_rows,
        error_rows=batch.error_rows,
        rows=[
            BudgetUploadRowResult(
                row_no=o.row_no,
                ok=o.ok,
                message=o.message,
                department=o.department,
                account_code=o.account_code,
            )
            for o in outcomes
        ],
    )


@router.get("/upload-history", response_model=list[BudgetUploadBatchRead])
def list_upload_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(require_fa_or_admin),
) -> list[BudgetUploadBatchRead]:
    batches = (
        db.query(BudgetUploadBatch)
        .order_by(BudgetUploadBatch.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    names = resolve_user_names(db, {b.uploaded_by_id for b in batches})
    return [
        BudgetUploadBatchRead.model_validate(b, from_attributes=True).model_copy(
            update={"uploaded_by_name": names.get(b.uploaded_by_id) if b.uploaded_by_id else None}
        )
        for b in batches
    ]


@router.get("/export")
def export_budget_master(
    db: Session = Depends(get_db),
    _user: User = Depends(require_fa_or_admin),
) -> Response:
    """Export ยอดงบทั้งหมดในระบบเป็น Excel (Correction 2026-09-11) — เอาทุกแถวเสมอ
    ไม่สนตัวกรองค้นหาที่หน้าจอ (Business Decision — ผู้ใช้เลือกไว้ตอนออกแบบ) คอลัมน์
    ตรงกับ Format Upload เดิม (เอากลับไป Re-upload ได้ทันที) ดู
    app/services/budget_excel.build_export_workbook สำหรับรายละเอียดคอลัมน์"""
    rows = (
        db.query(BudgetMaster)
        .order_by(BudgetMaster.department, BudgetMaster.budget_no)
        .all()
    )
    content = build_export_workbook(rows)
    filename = f"budget_export_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=BudgetMasterRead, status_code=status.HTTP_201_CREATED)
def create_budget_master(
    body: BudgetMasterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_fa_or_admin),
) -> BudgetMasterRead:
    """เพิ่มรายการ Budget เองทีละแถว (Correction 2026-09-11) — ดู Docstring
    BudgetMasterCreate สำหรับที่มา — budget_no ซ้ำ = ปฏิเสธด้วย 409 (ไม่ Upsert ทับ
    เหมือน Excel Upload เพราะไม่มีขั้นตอน Confirm ก่อนเหมือน Batch Upload)"""
    if body.period_start > body.period_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period_start ต้องไม่เกิน period_end")

    existing = db.query(BudgetMaster).filter(BudgetMaster.budget_no == body.budget_no).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f'Budget No. "{body.budget_no}" มีอยู่แล้วในระบบ'
        )

    row = BudgetMaster(
        budget_no=body.budget_no,
        department=body.department,
        budget_type=body.budget_type,
        account_code=body.account_code,
        period_start=body.period_start,
        period_end=body.period_end,
        budget_name=body.budget_name,
        budgeted_amount=body.budgeted_amount,
        used_amount=Decimal("0"),
    )
    db.add(row)
    db.flush()
    log_event(
        db,
        actor_id=current_user.id,
        action="budget.created",
        entity_type="budget",
        entity_id=row.id,
        detail={"budget_no": row.budget_no, "department": row.department},
    )
    db.commit()
    db.refresh(row)
    item = BudgetMasterRead.model_validate(row, from_attributes=True)
    return item.model_copy(update={"balance": row.budgeted_amount - row.used_amount})


@router.get("", response_model=list[BudgetMasterRead])
def list_budget_master(
    department: str | None = Query(default=None),
    budget_type: ARBudgetType | None = Query(default=None),
    account_code: str | None = Query(default=None),
    budget_no: str | None = Query(default=None),
    db: Session = Depends(get_db),
    # เปิดให้ User ทั่วไป Login แล้วดูได้ (ไม่ใช่แค่ FA/Admin) — หน้าสร้าง AR ต้องใช้
    # Endpoint นี้ Filter Budget No. ตาม Department ของผู้สร้างเอง (Design §6)
    _current_user: User = Depends(get_current_user),
) -> list[BudgetMasterRead]:
    query = db.query(BudgetMaster)
    if department is not None:
        query = query.filter(BudgetMaster.department == department)
    if budget_type is not None:
        query = query.filter(BudgetMaster.budget_type == budget_type)
    if account_code is not None:
        query = query.filter(BudgetMaster.account_code == account_code)
    if budget_no is not None:
        query = query.filter(BudgetMaster.budget_no == budget_no)
    rows = query.order_by(
        BudgetMaster.department, BudgetMaster.budget_no, BudgetMaster.period_start.desc()
    ).all()
    result = []
    for row in rows:
        item = BudgetMasterRead.model_validate(row, from_attributes=True)
        result.append(item.model_copy(update={"balance": row.budgeted_amount - row.used_amount}))
    return result


@router.patch("/{budget_id}", response_model=BudgetMasterRead)
def update_budget_master(
    budget_id: int,
    body: BudgetMasterUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_fa_or_admin),
) -> BudgetMasterRead:
    """แก้ไขรายการ Budget ที่มีอยู่แล้ว (Correction 2026-09-11) — ดู Docstring
    BudgetMasterUpdate: budget_no/used_amount แก้ทางนี้ไม่ได้โดยเจตนา"""
    row = db.get(BudgetMaster, budget_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบรายการ Budget นี้")

    updates = body.model_dump(exclude_unset=True)
    new_period_start = updates.get("period_start", row.period_start)
    new_period_end = updates.get("period_end", row.period_end)
    if new_period_start > new_period_end:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period_start ต้องไม่เกิน period_end")

    for key, value in updates.items():
        setattr(row, key, value)

    log_event(
        db,
        actor_id=current_user.id,
        action="budget.updated",
        entity_type="budget",
        entity_id=row.id,
        detail={"fields": sorted(updates.keys())} if updates else None,
    )
    db.commit()
    db.refresh(row)
    item = BudgetMasterRead.model_validate(row, from_attributes=True)
    return item.model_copy(update={"balance": row.budgeted_amount - row.used_amount})
