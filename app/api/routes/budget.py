"""Budget Master + Excel Upload (Phase 10, 2026-09-09, Business Decision v4.1)

Upload สงวนสิทธิ์ให้ `is_fa` หรือ `is_admin` เท่านั้น (Design §4/§1) — ดู
app/services/budget_excel.py สำหรับ Parser/Validator/Upsert Logic เต็ม
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_fa_or_admin
from app.db.session import get_db
from app.models import ARBudgetType, BudgetMaster, BudgetUploadBatch, User
from app.schemas.budget import (
    BudgetMasterRead,
    BudgetUploadBatchRead,
    BudgetUploadResult,
    BudgetUploadRowResult,
)
from app.services.budget_excel import parse_and_upsert
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


@router.get("", response_model=list[BudgetMasterRead])
def list_budget_master(
    department: str | None = Query(default=None),
    budget_type: ARBudgetType | None = Query(default=None),
    account_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
    # เปิดให้ User ทั่วไป Login แล้วดูได้ (ไม่ใช่แค่ FA/Admin) — หน้าสร้าง AR ต้องใช้
    # Endpoint นี้ Filter Budget Code ตาม Department ของผู้สร้างเอง (Design §6)
    _current_user: User = Depends(get_current_user),
) -> list[BudgetMasterRead]:
    query = db.query(BudgetMaster)
    if department is not None:
        query = query.filter(BudgetMaster.department == department)
    if budget_type is not None:
        query = query.filter(BudgetMaster.budget_type == budget_type)
    if account_code is not None:
        query = query.filter(BudgetMaster.account_code == account_code)
    rows = query.order_by(
        BudgetMaster.department, BudgetMaster.account_code, BudgetMaster.period_start.desc()
    ).all()
    result = []
    for row in rows:
        item = BudgetMasterRead.model_validate(row, from_attributes=True)
        result.append(item.model_copy(update={"balance": row.budgeted_amount - row.used_amount}))
    return result
