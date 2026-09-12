"""Level Management — Admin เท่านั้น (Phase 10, 2026-09-09, Business Decision v4.1
+ Correction 2026-09-09 Multi-approver per Level)

กำหนดว่าแผนกไหนมีกี่ Level อนุมัติ Budget อะไรบ้าง ใครเป็นผู้อนุมัติแต่ละ Level —
ยืดหยุ่นต่อแผนก (ไม่ Fix จำนวน Level เท่ากันทุกแผนก) ผู้อนุมัติผูกกับบุคคลเจาะจง (ไม่
ผูก Position) ดู app/services/budget_workflow.py สำหรับ Logic การใช้ข้อมูลนี้จริง

Correction (ตัวอย่าง Approve Flow จริงที่ผู้ใช้ส่งมา 2026-09-09 ยืนยันว่า Level เดียวกัน
มีผู้อนุมัติได้มากกว่า 1 คน เช่น Level "President or Director" มี 3 คนพร้อมกัน): 1 แถว
ในตาราง BudgetApprovalLevel ตอนนี้คือ "1 คนใน 1 Level" ไม่ใช่ "1 Level" อีกต่อไป —
department+level_no มีได้หลายแถว (หลายคน) แต่ทุกแถวในกลุ่มเดียวกันต้องมี level_name
ตรงกันเป๊ะเสมอ (บังคับ Sync ที่นี่ ไม่ปล่อยให้ Client ส่งชื่อไม่ตรงกันมาสร้างความสับสน
ใน Audit Trail) — ดู Docstring เต็มที่ app/models/budget.py
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models import BudgetApprovalLevel, User
from app.schemas.budget import (
    BudgetApprovalLevelCreate,
    BudgetApprovalLevelRead,
    BudgetApprovalLevelUpdate,
)
from app.services.system_log import get_client_ip, log_event, stringify_changes
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/budget-approval-levels", tags=["budget-levels"])


def _to_read(db: Session, level: BudgetApprovalLevel) -> BudgetApprovalLevelRead:
    names = resolve_user_names(db, {level.approver_user_id})
    data = BudgetApprovalLevelRead.model_validate(level, from_attributes=True)
    return data.model_copy(update={"approver_name": names.get(level.approver_user_id)})


def _active_group(
    db: Session, department: str, level_no: int, exclude_id: int | None = None
) -> list[BudgetApprovalLevel]:
    """ทุกแถว Active ของ department+level_no นี้ (ไม่รวมแถวตัวเองตอน Update) — ใช้เช็ค
    ผู้อนุมัติซ้ำ + บังคับ level_name ต้องตรงกันทั้งกลุ่ม"""
    query = db.query(BudgetApprovalLevel).filter(
        BudgetApprovalLevel.department == department,
        BudgetApprovalLevel.level_no == level_no,
        BudgetApprovalLevel.is_active.is_(True),
    )
    if exclude_id is not None:
        query = query.filter(BudgetApprovalLevel.id != exclude_id)
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
    """เช็คก่อน Insert/Update แถวใหม่เข้ากลุ่ม department+level_no: (1) คนนี้ต้องไม่ได้
    อยู่ในกลุ่มนี้อยู่แล้ว (2) ถ้ากลุ่มนี้มีคนอื่นอยู่แล้ว level_name ที่ส่งมาต้องตรงกับ
    กลุ่มเป๊ะ (กัน Level เดียวกันมีชื่อไม่ตรงกันในแต่ละแถว ทำให้ Audit Trail สับสน)"""
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
    """คืนชื่อแผนกทั้งหมดให้เลือกในหน้านี้ — ไม่มีตาราง "แผนก" แยกต่างหากในระบบ
    (department เป็น Free-text ทั้งใน User/BudgetApprovalLevel/BudgetMaster) จึงรวมจาก
    2 แหล่ง: (1) แผนกที่มี Level ตั้งไว้แล้ว (2) แผนกของ User ทุกคนในระบบ (มาจาก User
    Register จริงของบริษัท — ครอบคลุมแผนกที่ยังไม่เคยตั้ง Level เลยด้วย) เพื่อให้ Admin
    เห็นแผนกทั้งหมดพร้อมกันโดยไม่ต้องพิมพ์เดา (ขอตามคำขอ 2026-09-10)"""
    level_depts = {r[0] for r in db.query(BudgetApprovalLevel.department).distinct().all()}
    user_depts = {
        r[0]
        for r in db.query(User.department)
        .filter(User.department.isnot(None), User.department != "")
        .distinct()
        .all()
    }
    return sorted(level_depts | user_depts)


@router.post("", response_model=BudgetApprovalLevelRead, status_code=status.HTTP_201_CREATED)
def create_level(
    body: BudgetApprovalLevelCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> BudgetApprovalLevelRead:
    """เพิ่มผู้อนุมัติ 1 คนเข้า Level นี้ — ถ้า department+level_no มีคนอยู่แล้ว จะเพิ่ม
    เป็นคนที่ 2, 3, ... เข้ากลุ่มเดียวกันได้เลย (Multi-approver, OR — ดู Docstring บนสุด
    ของไฟล์นี้) ไม่ Error เหมือนเดิมอีกต่อไป ยกเว้นคนซ้ำหรือชื่อ Level ไม่ตรงกับกลุ่ม"""
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

    # เคยมีแถวนี้มาก่อนแต่ถูกปิดใช้งานไว้ (is_active=False) — Reactivate แทน Insert ใหม่
    # เพราะ Unique Constraint (department, level_no, approver_user_id) ผูกกับค่าจริงใน
    # DB เสมอไม่สนใจ is_active ถ้า Insert ซ้ำจะชน Constraint ทันที
    dormant = (
        db.query(BudgetApprovalLevel)
        .filter(
            BudgetApprovalLevel.department == body.department,
            BudgetApprovalLevel.level_no == body.level_no,
            BudgetApprovalLevel.approver_user_id == body.approver_user_id,
            BudgetApprovalLevel.is_active.is_(False),
        )
        .first()
    )
    if dormant is not None:
        dormant.level_name = body.level_name
        dormant.is_active = True
        log_event(
            db,
            actor_id=admin.id,
            action="budget_level.reactivated",
            entity_type="budget_level",
            entity_id=dormant.id,
            detail={"department": dormant.department, "level_no": dormant.level_no},
            ip_address=get_client_ip(request),
        )
        db.commit()
        db.refresh(dormant)
        return _to_read(db, dormant)

    level = BudgetApprovalLevel(
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
            action="budget_level.created",
            entity_type="budget_level",
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


@router.patch("/{level_id}", response_model=BudgetApprovalLevelRead)
def update_level(
    level_id: int,
    body: BudgetApprovalLevelUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> BudgetApprovalLevelRead:
    """แก้ 1 แถว (1 คน) — ถ้าเปลี่ยนแค่ level_name เฉยๆ (ไม่ย้าย Level/ไม่เปลี่ยนคน) จะ
    Sync ชื่อใหม่ให้ทุกคนในกลุ่ม department+level_no เดียวกันอัตโนมัติ (กันชื่อไม่ตรง
    กันในกลุ่ม) แต่ถ้าย้าย Level (level_no) หรือเปลี่ยนตัวคน (approver_user_id) จะเช็ค
    กับกลุ่มปลายทางแทน (ห้ามซ้ำคน + ชื่อต้องตรงกับกลุ่มปลายทาง)"""
    level = db.get(BudgetApprovalLevel, level_id)
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
        action="budget_level.updated",
        entity_type="budget_level",
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
    (ARBudgetApproval.level_name_snapshot) อ้างอิง Level ที่ถูกลบไปแล้วพัง"""
    level = db.get(BudgetApprovalLevel, level_id)
    if level is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Level นี้")
    level.is_active = False
    log_event(
        db,
        actor_id=admin.id,
        action="budget_level.deleted",
        entity_type="budget_level",
        entity_id=level.id,
        detail={"department": level.department, "level_no": level.level_no},
        ip_address=get_client_ip(request),
    )
    db.commit()
