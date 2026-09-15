"""PR Budget Approval — Workflow Engine (Phase 11 Phase 2, 2026-09-15)

Pattern เดียวกับ app/services/budget_workflow.py (AR) เกือบทุกประการ แต่ต่าง 3 จุด
ตามที่ยืนยันกับผู้ใช้แล้ว (2026-09-15):
1. ไม่มี FA Acknowledge — Level สุดท้ายอนุมัติผ่าน = หักงบจริงทันที (รวมอยู่ใน
   approve_level เลย ไม่มีฟังก์ชัน fa_acknowledge แยกต่างหาก)
2. ไม่มีขั้น Received แยก — จบ Workflow ที่ Level สุดท้าย
3. PR ที่ไม่มี budget_control เลย (ไม่ติ๊ก "Has Budget Control") — กด "ส่งขออนุมัติ"
   แล้ว Finalize ทันที ไม่มี Workflow อนุมัติเลย (ต่างจาก AR ที่ budget_no เป็น Field
   บังคับเสมอ) — ดู start_or_finalize_pr ที่ Route Layer จะเรียกแทน start_budget_workflow
   ตรงๆ เพื่อเช็คเงื่อนไขนี้ก่อน

กติกาที่ต้องคุมให้แน่นในไฟล์นี้ (เหมือน budget_workflow.py ของ AR ทุกประการ):
1. หัก/คืนยอด `budget_master.used_amount` ด้วย Atomic `UPDATE ... RETURNING` เท่านั้น
   — ห้าม Read-modify-write ใน Python (Budget Pool ใช้ร่วมกับ AR จริงผ่าน budget_master
   แถวเดียวกัน — Race Condition ระหว่าง PR/AR อนุมัติพร้อมกันต้องกันด้วย Pattern นี้)
2. Revise เมื่อไหร่ก็ได้ (กลไกเดิม) ต้องคืนยอด (ถ้าเคย Approved แล้ว) + Reset
   budget_approval_status ของ PR ใหม่กลับเป็น not_submitted เสมอ
3. is_admin Override ได้ทุก Level — Audit ต้อง Mark acted_as_override=True
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    BudgetApprovalAction,
    BudgetMaster,
    PRApprovalLevel,
    PRBudgetApproval,
    PRBudgetApprovalStatus,
    PRBudgetControl,
    PRStatus,
    PurchasingRequisition,
    User,
)


# ───────────────────────── Lookup ─────────────────────────
def get_department_levels(db: Session, department: str) -> list[PRApprovalLevel]:
    """Level ที่ Active ของแผนกนี้ เรียงจาก Level แรกสุด (level_no น้อยสุด) ก่อน"""
    return list(
        db.execute(
            select(PRApprovalLevel)
            .where(
                PRApprovalLevel.department == department,
                PRApprovalLevel.is_active.is_(True),
            )
            .order_by(PRApprovalLevel.level_no)
        )
        .scalars()
        .all()
    )


def resolve_current_level_name(db: Session, bc: PRBudgetControl) -> str | None:
    """แปลง bc.current_approval_level (แค่ตัวเลข) เป็นชื่อ Level จริงๆ — Pattern เดียวกับ
    resolve_current_level_name ของ AR แต่ไม่มีเคส FA Acknowledge (ไม่มีใน PR)"""
    if bc.current_approval_level is not None and bc.budget_department:
        levels = get_department_levels(db, bc.budget_department)
        match = next((lv for lv in levels if lv.level_no == bc.current_approval_level), None)
        return match.level_name if match else None
    return None


def resolve_budget_master(
    db: Session,
    *,
    budget_no: str,
    department: str,
    application_date: date,
) -> BudgetMaster | None:
    """หา budget_master ที่ budget_no ตรง — ไม่เช็ค budget_type แบบ AR เพราะ PR ไม่มี
    แนวคิด Expenses/Assets (budget_no เป็น Key จริงที่ไม่ซ้ำกัน Global อยู่แล้ว การเช็ค
    department+ช่วงเวลาประกอบเป็นแค่กันผู้สร้าง PR พิมพ์ Budget No. ผิดของแผนก/หมดอายุ)"""
    if not budget_no:
        return None
    return (
        db.execute(
            select(BudgetMaster).where(
                BudgetMaster.budget_no == budget_no,
                BudgetMaster.department == department,
                BudgetMaster.period_start <= application_date,
                BudgetMaster.period_end >= application_date,
            )
        )
        .scalars()
        .first()
    )


# ───────────────────────── Start Workflow (ตอน Submit) ─────────────────────────
def start_budget_workflow(
    db: Session,
    bc: PRBudgetControl,
    requester: User,
    application_date: date,
    *,
    force: bool = False,
) -> None:
    """เรียกตอนกด "ส่งขออนุมัติ" — Resolve Department Snapshot + Budget Master ที่
    อ้างอิง + ตั้งสถานะเริ่มต้นของ Workflow อนุมัติ ไม่ Commit เอง (ให้ Caller Commit
    พร้อมกับการเปลี่ยน pr.status ใน Transaction เดียว) — Caller ต้องเช็คก่อนแล้วว่า
    bc.budget_no มีค่าจริง (ถ้าไม่มี budget_no เลยไม่ต้องเรียกฟังก์ชันนี้ — Finalize
    ตรงๆ แทน ดู Docstring บนสุดของไฟล์นี้ ข้อ 3)

    แผนกไม่มี Level อนุมัติเลย (0 แถว): ต่างจาก AR ตรงที่ PR ไม่มี FA Acknowledge ให้
    คั่นเป็นขั้นยืนยันสุดท้าย จึงต้องหักงบจริง "ทันทีในนี้เลย" (เรียก _deduct_budget) —
    ยังคงเช็คเกินงบ + ต้องการ force=true เหมือน Level สุดท้ายปกติทุกประการ กัน Submit
    เกินงบแบบไม่มีใครยืนยันเลยสักคน (Caller ต้องรับ force มาจาก Client ส่งต่อมาที่นี่)"""
    bc.budget_department = requester.department
    bc.budget_master_id = None
    bc.budget_deducted_amount = None
    bc.budget_overridden = False

    if requester.department and bc.budget_no:
        master = resolve_budget_master(
            db,
            budget_no=bc.budget_no,
            department=requester.department,
            application_date=application_date,
        )
        bc.budget_master_id = master.id if master else None
        bc.account_code = master.account_code if master else None

    levels = get_department_levels(db, requester.department) if requester.department else []
    if levels:
        bc.budget_approval_status = PRBudgetApprovalStatus.PENDING
        bc.current_approval_level = levels[0].level_no
    else:
        # แผนกนี้ยังไม่ได้ Setup Level เลย (0 แถว) — ไม่มี Level ให้รอ หักงบจริงทันที
        # (ดู Docstring ด้านบน) แล้วถือว่าอนุมัติผ่าน
        bc.current_approval_level = None
        _deduct_budget(db, bc, force=force)
        bc.budget_approval_status = PRBudgetApprovalStatus.APPROVED


def _deduct_budget(db: Session, bc: PRBudgetControl, *, force: bool) -> bool:
    """หักยอดงบจริงจาก budget_master.used_amount (Atomic) — เรียกตอน Level สุดท้าย
    อนุมัติผ่าน (ไม่มี FA Acknowledge คั่นแบบ AR) คืนค่า overridden (True ถ้าเกินงบแต่ถูก
    Force อนุมัติ) — ถ้าไม่มี budget_master_id (Resolve ไม่เจอตอน Submit) ข้ามการหักยอด
    ไปเฉย ๆ (ถือว่าอนุมัติผ่านแต่ไม่มีอะไรให้หัก เหมือน AR กรณีเดียวกัน)"""
    amount = bc.this_application or Decimal("0")
    overridden = False
    if bc.budget_master_id is not None:
        master = db.get(BudgetMaster, bc.budget_master_id)
        if master is not None:
            balance = master.budgeted_amount - master.used_amount
            if amount > balance and not force:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "message": "ยอดเงินเกินงบประมาณคงเหลือ — ส่ง force=true เพื่อยืนยันอนุมัติทั้งที่เกินงบ",
                        "budgeted_amount": str(master.budgeted_amount),
                        "used_amount": str(master.used_amount),
                        "balance": str(balance),
                        "requested_amount": str(amount),
                        "shortfall": str(amount - balance),
                    },
                )
            overridden = amount > balance and force
            stmt = (
                update(BudgetMaster)
                .where(BudgetMaster.id == master.id)
                .values(used_amount=BudgetMaster.used_amount + amount)
                .returning(BudgetMaster.used_amount)
            )
            db.execute(stmt).scalar_one()
    bc.budget_deducted_amount = amount
    bc.budget_overridden = overridden
    return overridden


# ───────────────────────── Permission Helper ─────────────────────────
def _current_level_group(db: Session, bc: PRBudgetControl) -> list[PRApprovalLevel]:
    """คืนทุกแถว (ทุกคน) ของ Level ปัจจุบันที่ยัง Active — Level เดียวกันมีได้หลายคน
    (OR — ใครก็ได้ในกลุ่มอนุมัติ/ปฏิเสธก่อน ถือว่า Level นั้นจบ)"""
    if bc.current_approval_level is None or not bc.budget_department:
        raise HTTPException(status.HTTP_409_CONFLICT, "PR นี้ไม่ได้อยู่ระหว่างรอ Level อนุมัติ")
    group = list(
        db.execute(
            select(PRApprovalLevel).where(
                PRApprovalLevel.department == bc.budget_department,
                PRApprovalLevel.level_no == bc.current_approval_level,
                PRApprovalLevel.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if not group:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"ไม่พบ Level {bc.current_approval_level} ที่ยัง Active ของแผนก {bc.budget_department} "
            "(อาจถูกลบ/ปิดใช้งานไปแล้ว — กรุณาติดต่อ Admin)",
        )
    return group


@dataclass
class _ActorCheck:
    is_override: bool


def _check_level_actor(group: list[PRApprovalLevel], actor: User) -> _ActorCheck:
    """เช็คว่า actor เป็นหนึ่งในกลุ่มผู้มีสิทธิ์อนุมัติ Level นี้หรือไม่ (OR — เป็นคน
    ไหนในกลุ่มก็ได้)"""
    approver_ids = {lv.approver_user_id for lv in group}
    if actor.id in approver_ids:
        return _ActorCheck(is_override=False)
    if actor.is_admin:
        return _ActorCheck(is_override=True)
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, f'คุณไม่ใช่ผู้อนุมัติ Level "{group[0].level_name}" ของแผนกนี้'
    )


# ───────────────────────── Level (Approve/Reject) ─────────────────────────
def approve_level(
    db: Session,
    pr: PurchasingRequisition,
    actor: User,
    *,
    comment: str | None = None,
    force: bool = False,
) -> PurchasingRequisition:
    """การอนุมัติ Level ครั้งแรกของ PR ใบนี้ (ไม่ว่าจะเป็น Level เลขอะไร) คือจุดที่ทำให้
    PR เปลี่ยนจาก Draft -> Finalized (ล็อกแก้ไขไม่ได้อีก) — Pattern เดียวกับ AR
    (Correction 2026-09-10) — ต่างจาก AR ตรงที่ Level สุดท้ายอนุมัติผ่าน = หักงบจริง
    ทันทีในนี้เลย (ไม่มี FA Acknowledge คั่น — ดู _deduct_budget)"""
    bc = pr.budget_control
    if bc is None or bc.budget_approval_status != PRBudgetApprovalStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "PR นี้ไม่ได้อยู่ในสถานะรอ Level อนุมัติ")

    group = _current_level_group(db, bc)
    check = _check_level_actor(group, actor)
    level = group[0]  # ทุกแถวในกลุ่มเดียวกันมี level_no/level_name ตรงกันเสมอ (บังคับ Sync ที่ Route Layer)

    if pr.status == PRStatus.DRAFT:
        pr.status = PRStatus.FINALIZED

    db.add(
        PRBudgetApproval(
            pr_id=pr.id,
            level_no=level.level_no,
            level_name_snapshot=level.level_name,
            action=BudgetApprovalAction.APPROVED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=comment or None,
        )
    )

    remaining_levels = get_department_levels(db, bc.budget_department)
    next_level_nos = sorted(
        {lv.level_no for lv in remaining_levels if lv.level_no > level.level_no}
    )
    if next_level_nos:
        bc.current_approval_level = next_level_nos[0]
    else:
        # Level สุดท้ายแล้ว — หักงบจริงทันที + APPROVED (ไม่มี FA Acknowledge คั่น)
        bc.current_approval_level = None
        _deduct_budget(db, bc, force=force)
        bc.budget_approval_status = PRBudgetApprovalStatus.APPROVED
    return pr


def reject_level(
    db: Session, pr: PurchasingRequisition, actor: User, reason: str
) -> PurchasingRequisition:
    bc = pr.budget_control
    if bc is None or bc.budget_approval_status != PRBudgetApprovalStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "PR นี้ไม่ได้อยู่ในสถานะรอ Level อนุมัติ")

    group = _current_level_group(db, bc)
    check = _check_level_actor(group, actor)
    level = group[0]

    db.add(
        PRBudgetApproval(
            pr_id=pr.id,
            level_no=level.level_no,
            level_name_snapshot=level.level_name,
            action=BudgetApprovalAction.REJECTED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=reason,
        )
    )
    bc.budget_approval_status = PRBudgetApprovalStatus.REJECTED
    bc.current_approval_level = None
    return pr


# ───────────────────────── Revise: คืนยอด + Reset ─────────────────────────
def refund_on_revise(db: Session, original: PurchasingRequisition) -> None:
    """เรียกตอน Revise PR ที่ Finalized แล้ว — คืนยอดงบทันทีถ้า PR ต้นฉบับเคย Approved
    แล้ว (หักยอดไปแล้วจริง) ไม่ทำอะไรถ้ายังไม่เคย Approved"""
    bc = original.budget_control
    if (
        bc is not None
        and bc.budget_approval_status == PRBudgetApprovalStatus.APPROVED
        and bc.budget_master_id is not None
        and bc.budget_deducted_amount is not None
    ):
        stmt = (
            update(BudgetMaster)
            .where(BudgetMaster.id == bc.budget_master_id)
            .values(used_amount=BudgetMaster.used_amount - bc.budget_deducted_amount)
            .returning(BudgetMaster.used_amount)
        )
        db.execute(stmt).scalar_one()


def reset_for_new_draft(bc: PRBudgetControl) -> None:
    """ตั้งค่า Field Workflow อนุมัติทั้งหมดของ PRBudgetControl ใหม่ให้เป็นค่าเริ่มต้น
    เสมอ — ใช้ทั้งตอน Revise และตอนแก้ไข PR ระหว่างรอ Level อนุมัติ (ยกเลิกคำขออนุมัติ
    ที่ค้างอยู่อัตโนมัติ — Pattern เดียวกับ AR) — ไม่แตะ budget_no/account_code/
    this_application (เป็น Input ของผู้ใช้ ไม่ใช่ State ของ Workflow)"""
    bc.budget_department = None
    bc.budget_master_id = None
    bc.budget_approval_status = PRBudgetApprovalStatus.NOT_SUBMITTED
    bc.current_approval_level = None
    bc.budget_deducted_amount = None
    bc.budget_overridden = False


# ───────────────────────── Progress (PR Detail UI + PDF Auto-fill) ─────────────────────────
def build_approval_progress(db: Session, pr: PurchasingRequisition) -> list[dict]:
    """สร้างรายการ Step ของ Stepper (Level 1..N) รวมผลจริงจาก pr_budget_approvals เข้า
    ด้วยกัน — Pattern เดียวกับ build_approval_progress ของ AR แต่ไม่มี Step FA
    Acknowledge ต่อท้าย (ไม่มีใน PR)"""
    from app.services.user_lookup import resolve_user_names  # กัน Circular Import

    bc = pr.budget_control
    levels = get_department_levels(db, bc.budget_department) if bc and bc.budget_department else []
    approvals = {a.level_no: a for a in sorted(pr.budget_approvals, key=lambda a: a.acted_at)}

    user_ids = {lv.approver_user_id for lv in levels}
    user_ids |= {a.acted_by_id for a in pr.budget_approvals}
    names = resolve_user_names(db, user_ids)

    groups: dict[int, list[PRApprovalLevel]] = {}
    for lv in levels:
        groups.setdefault(lv.level_no, []).append(lv)

    steps: list[dict] = []
    for level_no in sorted(groups):
        group = groups[level_no]
        rec = approvals.get(level_no)
        approver_ids = [lv.approver_user_id for lv in group]
        step = {
            "level_no": level_no,
            "level_name": group[0].level_name,
            "approver_user_ids": approver_ids,
            "approver_names": ", ".join(names.get(uid) or f"#{uid}" for uid in approver_ids),
            "status": "waiting",
            "acted_by_name": None,
            "acted_at": None,
            "reason": None,
            "acted_as_override": False,
        }
        if rec is not None:
            step["status"] = rec.action.value
            step["acted_by_name"] = names.get(rec.acted_by_id)
            step["acted_at"] = rec.acted_at
            step["reason"] = rec.reason
            step["acted_as_override"] = rec.acted_as_override
        steps.append(step)
    return steps


# ───────────────────────── ผู้อนุมัติ Level ปัจจุบัน (View Access + Attachment) ─────────────────────────
def is_current_level_approver(db: Session, pr: PurchasingRequisition, actor: User) -> bool:
    """actor เป็นผู้อนุมัติ Level ที่กำลังรอตัดสินใจอยู่ ณ ขณะนี้ของ PR ใบนี้หรือไม่ — ใช้
    ทั้งตอนเช็คสิทธิ์ "ดู" PR ของคนอื่น (Phase 11: ต่างจาก Scope Revision Phase 9 เดิมที่
    ไม่มีใครนอกจากเจ้าของ/Admin ต้องดู PR ของคนอื่นเลย — ตอนนี้ผู้อนุมัติมีเหตุผลชอบธรรม
    ต้องดูแล้ว ดู _check_pr_view_access ใน purchasing_requisitions.py) และตอนเช็คสิทธิ์
    แนบเอกสารเพิ่ม (can_upload_attachment ด้านล่าง)"""
    bc = pr.budget_control
    if (
        bc is not None
        and bc.budget_approval_status == PRBudgetApprovalStatus.PENDING
        and bc.current_approval_level is not None
        and bc.budget_department
    ):
        levels = get_department_levels(db, bc.budget_department)
        current_group = [lv for lv in levels if lv.level_no == bc.current_approval_level]
        return any(lv.approver_user_id == actor.id for lv in current_group)
    return False


# ───────────────────────── PR Attachments ─────────────────────────
def can_upload_attachment(db: Session, pr: PurchasingRequisition, actor: User) -> bool:
    """ใครแนบเอกสารเพิ่มได้บ้าง — Pattern เดียวกับ can_upload_attachment ของ AR: เจ้าของ
    PR, Admin เสมอ, หรือผู้อนุมัติ Level ปัจจุบันที่กำลังรอตัดสินใจอยู่ ณ ขณะนั้น"""
    if actor.id == pr.requested_by_id or actor.is_admin:
        return True
    return is_current_level_approver(db, pr, actor)
