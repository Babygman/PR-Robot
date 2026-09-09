"""Level Management — Admin เท่านั้น (Phase 10, 2026-09-09, Business Decision v4.1)

กำหนดว่าแผนกไหนมีกี่ Level อนุมัติ Budget อะไรบ้าง ใครเป็นผู้อนุมัติแต่ละ Level —
ยืดหยุ่นต่อแผนก (ไม่ Fix จำนวน Level เท่ากันทุกแผนก) ผู้อนุมัติผูกกับบุคคลเจาะจง (ไม่
ผูก Position) ดู app/services/budget_workflow.py สำหรับ Logic การใช้ข้อมูลนี้จริง
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models import BudgetApprovalLevel, User
from app.schemas.budget import (
    BudgetApprovalLevelCreate,
    BudgetApprovalLevelRead,
    BudgetApprovalLevelUpdate,
)
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/budget-approval-levels", tags=["budget-levels"])


def _to_read(db: Session, level: BudgetApprovalLevel) -> BudgetApprovalLevelRead:
    names = resolve_user_names(db, {level.approver_user_id})
    data = BudgetApprovalLevelRead.model_validate(level, from_attributes=True)
    return data.model_copy(update={"approver_name": names.get(level.approver_user_id)})


@router.get("", response_model=list[BudgetApprovalLevelRead])
def list_levels(
    department: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[BudgetApprovalLevelRead]:
    query = db.query(BudgetApprovalLevel)
    if department is not None:
        query = query.filter(BudgetApprovalLevel.department == department)
    levels = query.order_by(BudgetApprovalLevel.department, BudgetApprovalLevel.level_no).all()
    return [_to_read(db, lv) for lv in levels]


@router.get("/departments", response_model=list[str])
def list_departments_with_levels(
    db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[str]:
    rows = (
        db.query(BudgetApprovalLevel.department)
        .distinct()
        .order_by(BudgetApprovalLevel.department)
        .all()
    )
    return [r[0] for r in rows]


@router.post("", response_model=BudgetApprovalLevelRead, status_code=status.HTTP_201_CREATED)
def create_level(
    body: BudgetApprovalLevelCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> BudgetApprovalLevelRead:
    approver = db.get(User, body.approver_user_id)
    if approver is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่พบผู้อนุมัติ (approver_user_id) นี้")

    existing = (
        db.query(BudgetApprovalLevel)
        .filter(
            BudgetApprovalLevel.department == body.department,
            BudgetApprovalLevel.level_no == body.level_no,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"แผนก {body.department} มี Level {body.level_no} อยู่แล้ว"
        )

    level = BudgetApprovalLevel(
        department=body.department,
        level_no=body.level_no,
        level_name=body.level_name,
        approver_user_id=body.approver_user_id,
    )
    db.add(level)
    db.commit()
    db.refresh(level)
    return _to_read(db, level)


@router.patch("/{level_id}", response_model=BudgetApprovalLevelRead)
def update_level(
    level_id: int,
    body: BudgetApprovalLevelUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> BudgetApprovalLevelRead:
    level = db.get(BudgetApprovalLevel, level_id)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Level นี้")

    updates = body.model_dump(exclude_unset=True)
    if "approver_user_id" in updates and updates["approver_user_id"] is not None:
        approver = db.get(User, updates["approver_user_id"])
        if approver is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่พบผู้อนุมัติ (approver_user_id) นี้")

    if (
        "level_no" in updates
        and updates["level_no"] is not None
        and updates["level_no"] != level.level_no
    ):
        clash = (
            db.query(BudgetApprovalLevel)
            .filter(
                BudgetApprovalLevel.department == level.department,
                BudgetApprovalLevel.level_no == updates["level_no"],
                BudgetApprovalLevel.id != level.id,
            )
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"แผนก {level.department} มี Level {updates['level_no']} อยู่แล้ว",
            )

    for key, value in updates.items():
        setattr(level, key, value)

    db.commit()
    db.refresh(level)
    return _to_read(db, level)


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_level(
    level_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> None:
    """Soft-delete เท่านั้น (is_active=False) — กันประวัติ Audit เก่า
    (ARBudgetApproval.level_name_snapshot) อ้างอิง Level ที่ถูกลบไปแล้วพัง"""
    level = db.get(BudgetApprovalLevel, level_id)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Level นี้")
    level.is_active = False
    db.commit()
