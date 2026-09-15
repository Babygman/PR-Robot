"""Level Management ของ PR — Admin เท่านั้น (Phase 11, 2026-09-15)

Pattern เดียวกับ app/api/routes/budget_levels.py (Level Management ของ AR) ทุกประการ
แต่แยกตาราง (PRApprovalLevel) และแยก Endpoint Prefix ("/pr-approval-levels" แทน
"/budget-approval-levels") เต็มรูปแบบ — เมนูหน้าเว็บจะแยก "Approval Level-PR" ออกจาก
"Approval Level-AR" (ดู Docstring เต็มที่ app/models/pr_budget.py)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models import PRApprovalLevel, User
from app.schemas.pr_budget import PRApprovalLevelCreate, PRApprovalLevelRead, PRApprovalLevelUpdate
from app.services.system_log import get_client_ip, log_event, stringify_changes
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/pr-approval-levels", tags=["pr-approval-levels"])


def _to_read(db: Session, level: PRApprovalLevel) -> PRApprovalLevelRead:
    names = resolve_user_names(db, {level.approver_user_id})
    data = PRApprovalLevelRead.model_validate(level, from_attributes=True)
    return data.model_copy(update={"approver_name": names.get(level.approver_user_id)})


def _active_group(
    db: Session, department: str, level_no: int, exclude_id: int | None = None
) -> list[PRApprovalLevel]:
    query = db.query(PRApprovalLevel).filter(
        PRApprovalLevel.department == department,
        PRApprovalLevel.level_no == level_no,
        PRApprovalLevel.is_active.is_(True),
    )
    if exclude_id is not None:
        query = query.filter(PRApprovalLevel.id != exclude_id)
    return query.all()


def _validate_level_slot(
    db: Session,
    *,
    department: str,
    level_no: int,
    level_name: str,
    approver_user_id: int,
    exclude_id: int | None = None,
) -> None:
    group = _active_group(db, department, level_no, exclude_id=exclude_id)
    if any(lv.approver_user_id == approver_user_id for lv in group):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"ผู้อนุมัติคนนี้อยู่ใน Level {level_no} ของแผนกนี้อยู่แล้ว"
        )
    if group and group[0].level_name != level_name:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f'Level {level_no} ของแผนกนี้ตั้งชื่อไว้แล้วว่า "{group[0].level_name}" '
            "— ทุกคนใน Level เดียวกันต้องใช้ชื่อเดียวกัน (แก้ชื่อผ่านแถวใดก็ได้ในกลุ่ม ระบบจะ Sync ให้ทั้งกลุ่ม)",
        )


@router.get("", response_model=list[PRApprovalLevelRead])
def list_levels(
    department: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[PRApprovalLevelRead]:
    query = db.query(PRApprovalLevel)
    if department is not None:
        query = query.filter(PRApprovalLevel.department == department)
    levels = query.order_by(PRApprovalLevel.department, PRApprovalLevel.level_no).all()
    return [_to_read(db, lv) for lv in levels]


@router.get("/departments", response_model=list[str])
def list_departments_with_levels(
    db: Session = Depends(get_db), _admin: User = Depends(require_admin)
) -> list[str]:
    """Pattern เดียวกับ list_departments_with_levels ของ AR — รวมแผนกที่มี Level PR
    ตั้งไว้แล้ว + แผนกของ User ทุกคนในระบบ"""
    level_depts = {r[0] for r in db.query(PRApprovalLevel.department).distinct().all()}
    user_depts = {
        r[0]
        for r in db.query(User.department)
        .filter(User.department.isnot(None), User.department != "")
        .distinct()
        .all()
    }
    return sorted(level_depts | user_depts)


@router.post("", response_model=PRApprovalLevelRead, status_code=status.HTTP_201_CREATED)
def create_level(
    body: PRApprovalLevelCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> PRApprovalLevelRead:
    approver = db.get(User, body.approver_user_id)
    if approver is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่พบผู้อนุมัติ (approver_user_id) นี้")

    _validate_level_slot(
        db,
        department=body.department,
        level_no=body.level_no,
        level_name=body.level_name,
        approver_user_id=body.approver_user_id,
    )

    dormant = (
        db.query(PRApprovalLevel)
        .filter(
            PRApprovalLevel.department == body.department,
            PRApprovalLevel.level_no == body.level_no,
            PRApprovalLevel.approver_user_id == body.approver_user_id,
            PRApprovalLevel.is_active.is_(False),
        )
        .first()
    )
    if dormant is not None:
        dormant.level_name = body.level_name
        dormant.is_active = True
        log_event(
            db,
            actor_id=admin.id,
            action="pr_level.reactivated",
            entity_type="pr_level",
            entity_id=dormant.id,
            detail={"department": dormant.department, "level_no": dormant.level_no},
            ip_address=get_client_ip(request),
        )
        db.commit()
        db.refresh(dormant)
        return _to_read(db, dormant)

    level = PRApprovalLevel(
        department=body.department,
        level_no=body.level_no,
        level_name=body.level_name,
        approver_user_id=body.approver_user_id,
    )
    db.add(level)
    try:
        db.flush()
        log_event(
            db,
            actor_id=admin.id,
            action="pr_level.created",
            entity_type="pr_level",
            entity_id=level.id,
            detail={"department": level.department, "level_no": level.level_no},
            ip_address=get_client_ip(request),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "ข้อมูลนี้ซ้ำกับที่มีอยู่แล้วในระบบ (แผนก+Level+ผู้อนุมัติ)"
        ) from None
    db.refresh(level)
    return _to_read(db, level)


@router.patch("/{level_id}", response_model=PRApprovalLevelRead)
def update_level(
    level_id: int,
    body: PRApprovalLevelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> PRApprovalLevelRead:
    level = db.get(PRApprovalLevel, level_id)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Level นี้")

    updates = body.model_dump(exclude_unset=True)
    if "approver_user_id" in updates and updates["approver_user_id"] is not None:
        approver = db.get(User, updates["approver_user_id"])
        if approver is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่พบผู้อนุมัติ (approver_user_id) นี้")

    moving_slot = (
        "level_no" in updates
        and updates["level_no"] is not None
        and updates["level_no"] != level.level_no
    ) or (
        "approver_user_id" in updates
        and updates["approver_user_id"] is not None
        and updates["approver_user_id"] != level.approver_user_id
    )
    final_level_no = updates.get("level_no", level.level_no)
    final_approver_user_id = updates.get("approver_user_id", level.approver_user_id)
    final_level_name = updates.get("level_name", level.level_name)

    if moving_slot:
        _validate_level_slot(
            db,
            department=level.department,
            level_no=final_level_no,
            level_name=final_level_name,
            approver_user_id=final_approver_user_id,
            exclude_id=level.id,
        )

    renaming_group_only = (
        "level_name" in updates
        and updates["level_name"] is not None
        and updates["level_name"] != level.level_name
        and not moving_slot
    )

    before = {key: getattr(level, key) for key in updates}
    for key, value in updates.items():
        setattr(level, key, value)

    if renaming_group_only:
        for sib in _active_group(db, level.department, level.level_no, exclude_id=level.id):
            sib.level_name = level.level_name

    log_event(
        db,
        actor_id=admin.id,
        action="pr_level.updated",
        entity_type="pr_level",
        entity_id=level.id,
        detail={
            "department": level.department,
            "level_no": level.level_no,
            "changes": stringify_changes(before, updates),
        },
        ip_address=get_client_ip(request),
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "ข้อมูลนี้ซ้ำกับที่มีอยู่แล้วในระบบ (แผนก+Level+ผู้อนุมัติ)"
        ) from None
    db.refresh(level)
    return _to_read(db, level)


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_level(
    level_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    """Soft-delete เท่านั้น (is_active=False) — กันประวัติ Audit เก่า
    (PRBudgetApproval.level_name_snapshot) อ้างอิง Level ที่ถูกลบไปแล้วพัง"""
    level = db.get(PRApprovalLevel, level_id)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Level นี้")
    level.is_active = False
    log_event(
        db,
        actor_id=admin.id,
        action="pr_level.deleted",
        entity_type="pr_level",
        entity_id=level.id,
        detail={"department": level.department, "level_no": level.level_no},
        ip_address=get_client_ip(request),
    )
    db.commit()
