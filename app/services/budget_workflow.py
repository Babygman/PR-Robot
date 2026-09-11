"""Budget Control — Workflow Engine (Phase 10, 2026-09-09, Business Decision v4.1)

Multi-Level Approval → FA Acknowledge → Reject ผ่าน Revise เดิม (ไม่มี Endpoint
Resubmit แยก) ดู docs/drafts/budget_control_design_draft.md §3 สำหรับ Diagram เต็ม

กติกาที่ต้องคุมให้แน่นในไฟล์นี้:
1. หัก/คืนยอด `budget_master.used_amount` ด้วย Atomic `UPDATE ... RETURNING` เท่านั้น
   (Pattern เดียวกับ app/services/ar_numbering.py) — ห้าม Read-modify-write ใน Python
2. จุดหักยอดงบมีจุดเดียว: FA Acknowledge (ไม่ใช่ Level 1..N ก่อนหน้า ซึ่งเป็นแค่สาย
   เซ็นอนุมัติผ่านตามผังจริงของบริษัท ไม่กระทบ Balance)
3. Revise เมื่อไหร่ก็ได้ (กลไกเดิม) ต้องคืนยอด (ถ้าเคย Approved แล้ว) + Reset
   budget_approval_status ของ AR ใหม่กลับเป็น not_submitted เสมอ (เข้าคิว Level 1 ใหม่
   ทั้งหมดตอน Finalize ครั้งถัดไป ไม่ข้าม Level ที่เคยผ่านมาก่อน)
4. is_admin Override ได้ทุกขั้น (ทุก Level + FA Acknowledge) — Audit ต้อง Mark
   acted_as_override=True ให้เห็นชัดว่าไม่ใช่คนที่ถูกกำหนดไว้จริง
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_, select, tuple_, update
from sqlalchemy.orm import Session

from app.models import (
    ApprovalRequest,
    ARBudgetApproval,
    ARBudgetApprovalStatus,
    ARStatus,
    BudgetApprovalAction,
    BudgetApprovalLevel,
    BudgetApprovalStepType,
    BudgetMaster,
    User,
)


# ───────────────────────── Lookup ─────────────────────────
def get_department_levels(db: Session, department: str) -> list[BudgetApprovalLevel]:
    """Level ที่ Active ของแผนกนี้ เรียงจาก Level แรกสุด (level_no น้อยสุด) ก่อน"""
    return list(
        db.execute(
            select(BudgetApprovalLevel)
            .where(
                BudgetApprovalLevel.department == department,
                BudgetApprovalLevel.is_active.is_(True),
            )
            .order_by(BudgetApprovalLevel.level_no)
        )
        .scalars()
        .all()
    )


def resolve_current_level_name(db: Session, ar: ApprovalRequest) -> str | None:
    """แปลง ar.current_approval_level (แค่ตัวเลข) เป็นชื่อ Level จริงๆ (เช่น "Manager",
    "General Manager") — ใช้ร่วมกันทั้งใน MyApprovalItem (app/api/routes/approval_requests.py
    _to_my_approval_item, ของเดิม) และ ARRead (_to_ar_read, เพิ่มใหม่ — Feedback ผู้ใช้
    2026-09-11: Badge "รออนุมัติ Level" เดิมไม่บอกว่ารอ Level ไหน ทำให้ไม่ชัดเจน)"""
    if ar.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE:
        return "FA Acknowledge"
    if ar.current_approval_level is not None and ar.budget_department:
        levels = get_department_levels(db, ar.budget_department)
        match = next((lv for lv in levels if lv.level_no == ar.current_approval_level), None)
        return match.level_name if match else None
    return None


def resolve_budget_master(
    db: Session,
    *,
    budget_no: str,
    department: str,
    budget_type,
    application_date: date,
) -> BudgetMaster | None:
    """หา budget_master ที่ budget_no ตรง (Key จริงที่ไม่ซ้ำกัน — ดู Docstring บนสุด
    ของ app/models/budget.py สำหรับ Correction 2026-09-09 ที่แก้จาก account_code เดิม)
    — ยังเช็ก department+budget_type+ช่วงเวลาประกอบด้วย เผื่อผู้สร้าง AR พิมพ์ Budget
    No. ผิด (เช่น ของแผนก/ประเภทอื่น หรือหมดอายุแล้ว) ถือว่าไม่ Match เหมือนไม่เจอเลย"""
    if not budget_no:
        return None
    return (
        db.execute(
            select(BudgetMaster).where(
                BudgetMaster.budget_no == budget_no,
                BudgetMaster.department == department,
                BudgetMaster.budget_type == budget_type,
                BudgetMaster.period_start <= application_date,
                BudgetMaster.period_end >= application_date,
            )
        )
        .scalars()
        .first()
    )


# ───────────────────────── Start Workflow (ตอน Finalize) ─────────────────────────
def start_budget_workflow(db: Session, ar: ApprovalRequest, requester: User) -> None:
    """เรียกตอน AR เปลี่ยนจาก draft -> finalized (ดู
    app/api/routes/approval_requests.py: get_ar_pdf) — Resolve Department Snapshot +
    Budget Master ที่อ้างอิง + ตั้งสถานะเริ่มต้นของ Workflow อนุมัติ ไม่ Commit เอง
    (ให้ Caller Commit พร้อมกับการเปลี่ยน ar.status เป็น finalized ใน Transaction เดียว)
    """
    ar.budget_department = requester.department
    ar.budget_master_id = None
    ar.budget_deducted_amount = None
    ar.budget_overridden = False

    if requester.department and ar.budget_no:
        master = resolve_budget_master(
            db,
            budget_no=ar.budget_no,
            department=requester.department,
            budget_type=ar.budget_type,
            application_date=ar.application_date,
        )
        ar.budget_master_id = master.id if master else None

    levels = get_department_levels(db, requester.department) if requester.department else []
    if levels:
        ar.budget_approval_status = ARBudgetApprovalStatus.PENDING
        ar.current_approval_level = levels[0].level_no
    else:
        # แผนกนี้ยังไม่ได้ Setup Level เลย (0 แถว) — ข้ามตรงไป FA Acknowledge ทันที
        ar.budget_approval_status = ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE
        ar.current_approval_level = None


# ───────────────────────── Permission Helper ─────────────────────────
def _current_level_group(db: Session, ar: ApprovalRequest) -> list[BudgetApprovalLevel]:
    """คืนทุกแถว (ทุกคน) ของ Level ปัจจุบันที่ยัง Active — Level เดียวกันมีได้หลายคน
    (OR — ใครก็ได้ในกลุ่มอนุมัติ/ปฏิเสธก่อน ถือว่า Level นั้นจบ) ดู Docstring
    BudgetApprovalLevel ใน app/models/budget.py สำหรับที่มาของ Correction นี้"""
    if ar.current_approval_level is None or not ar.budget_department:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval Request นี้ไม่ได้อยู่ระหว่างรอ Level อนุมัติ")
    group = list(
        db.execute(
            select(BudgetApprovalLevel).where(
                BudgetApprovalLevel.department == ar.budget_department,
                BudgetApprovalLevel.level_no == ar.current_approval_level,
                BudgetApprovalLevel.is_active.is_(True),
            )
        )
        .scalars()
        .all()
    )
    if not group:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"ไม่พบ Level {ar.current_approval_level} ที่ยัง Active ของแผนก {ar.budget_department} "
            "(อาจถูกลบ/ปิดใช้งานไปแล้ว — กรุณาติดต่อ Admin)",
        )
    return group


@dataclass
class _ActorCheck:
    is_override: bool


def _check_level_actor(group: list[BudgetApprovalLevel], actor: User) -> _ActorCheck:
    """เช็คว่า actor เป็นหนึ่งในกลุ่มผู้มีสิทธิ์อนุมัติ Level นี้หรือไม่ (OR — เป็นคน
    ไหนในกลุ่มก็ได้) ไม่ใช่แค่คนเดียวเป๊ะแบบเดิมก่อน Correction 2026-09-09"""
    approver_ids = {lv.approver_user_id for lv in group}
    if actor.id in approver_ids:
        return _ActorCheck(is_override=False)
    if actor.is_admin:
        return _ActorCheck(is_override=True)
    raise HTTPException(
        status.HTTP_403_FORBIDDEN, f'คุณไม่ใช่ผู้อนุมัติ Level "{group[0].level_name}" ของแผนกนี้'
    )


def _check_fa_actor(actor: User) -> _ActorCheck:
    if actor.is_fa:
        return _ActorCheck(is_override=False)
    if actor.is_admin:
        return _ActorCheck(is_override=True)
    raise HTTPException(status.HTTP_403_FORBIDDEN, "ต้องมีสิทธิ์ FA หรือ Admin เท่านั้น")


# ───────────────────────── Level ปกติ ─────────────────────────
def approve_level(
    db: Session, ar: ApprovalRequest, actor: User, *, comment: str | None = None
) -> ApprovalRequest:
    """Correction 2026-09-10: การอนุมัติ Level ครั้งแรกของ AR ใบนี้ (ไม่ว่าจะเป็น Level
    เลขอะไร) คือจุดที่ทำให้ AR เปลี่ยนจาก Draft -> Finalized (ล็อกแก้ไขไม่ได้อีก) — เดิม
    Lock ผูกกับการพิมพ์/ดาวน์โหลด PDF ครั้งแรก ย้ายมาผูกกับจุดนี้แทนตามคำขอ (ดู
    app/api/routes/approval_requests.py: submit_ar_for_approval/update_ar/get_ar_pdf)

    comment (Phase A, 2026-09-10): Comment ไม่บังคับที่ผู้อนุมัติกรอกตอนกด "อนุมัติ" —
    เก็บลงคอลัมน์ reason เดิม (Reuse ร่วมกับเหตุผลปฏิเสธ) โชว์ทั้งในตาราง Authority ของ
    PDF (ดู ar_pdf.py) และในหน้า AR Detail/ประวัติ"""
    if ar.budget_approval_status != ARBudgetApprovalStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approval Request นี้ไม่ได้อยู่ในสถานะรอ Level อนุมัติ"
        )

    group = _current_level_group(db, ar)
    check = _check_level_actor(group, actor)
    level = group[0]  # ทุกแถวในกลุ่มเดียวกันมี level_no/level_name ตรงกันเสมอ (บังคับ Sync ที่ Route Layer)

    if ar.status == ARStatus.DRAFT:
        ar.status = ARStatus.FINALIZED

    db.add(
        ARBudgetApproval(
            ar_id=ar.id,
            step_type=BudgetApprovalStepType.LEVEL,
            level_no=level.level_no,
            level_name_snapshot=level.level_name,
            action=BudgetApprovalAction.APPROVED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=comment or None,
        )
    )

    remaining_levels = get_department_levels(db, ar.budget_department)
    # level_no ซ้ำกันได้หลายแถวต่อกลุ่มแล้ว (Multi-approver) — ต้องหา level_no ถัดไปที่
    # "ไม่ซ้ำ" ตัวถัดจาก Level ปัจจุบัน ไม่ใช่แค่แถวถัดไปในลิสต์เฉยๆ
    next_level_nos = sorted(
        {lv.level_no for lv in remaining_levels if lv.level_no > level.level_no}
    )
    if next_level_nos:
        ar.current_approval_level = next_level_nos[0]
    else:
        ar.current_approval_level = None
        ar.budget_approval_status = ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE
    return ar


def reject_level(db: Session, ar: ApprovalRequest, actor: User, reason: str) -> ApprovalRequest:
    if ar.budget_approval_status != ARBudgetApprovalStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approval Request นี้ไม่ได้อยู่ในสถานะรอ Level อนุมัติ"
        )

    group = _current_level_group(db, ar)
    check = _check_level_actor(group, actor)
    level = group[0]

    db.add(
        ARBudgetApproval(
            ar_id=ar.id,
            step_type=BudgetApprovalStepType.LEVEL,
            level_no=level.level_no,
            level_name_snapshot=level.level_name,
            action=BudgetApprovalAction.REJECTED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=reason,
        )
    )
    ar.budget_approval_status = ARBudgetApprovalStatus.REJECTED
    ar.current_approval_level = None
    return ar


# ───────────────────────── FA Acknowledge (จุดหักยอดจริง) ─────────────────────────
def fa_acknowledge(
    db: Session, ar: ApprovalRequest, actor: User, *, force: bool, comment: str | None = None
) -> ApprovalRequest:
    if ar.budget_approval_status != ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approval Request นี้ไม่ได้อยู่ในสถานะรอ FA Acknowledge"
        )

    check = _check_fa_actor(actor)

    amount = ar.this_application or Decimal("0")
    overridden = False

    if ar.budget_master_id is not None:
        master = db.get(BudgetMaster, ar.budget_master_id)
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
            # Atomic UPDATE ... RETURNING (Pattern เดียวกับ ar_numbering.py) — ห้าม
            # อ่าน master.used_amount มาบวกในโค้ด Python เด็ดขาด (Race Condition ตอน
            # อนุมัติพร้อมกันหลายใบ)
            stmt = (
                update(BudgetMaster)
                .where(BudgetMaster.id == master.id)
                .values(used_amount=BudgetMaster.used_amount + amount)
                .returning(BudgetMaster.used_amount)
            )
            db.execute(stmt).scalar_one()

    db.add(
        ARBudgetApproval(
            ar_id=ar.id,
            step_type=BudgetApprovalStepType.FA_ACKNOWLEDGE,
            level_no=None,
            level_name_snapshot="FA Acknowledge",
            action=BudgetApprovalAction.APPROVED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=comment or None,
        )
    )
    ar.budget_approval_status = ARBudgetApprovalStatus.APPROVED
    ar.budget_deducted_amount = amount
    ar.budget_overridden = overridden
    return ar


def reject_fa(db: Session, ar: ApprovalRequest, actor: User, reason: str) -> ApprovalRequest:
    if ar.budget_approval_status != ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Approval Request นี้ไม่ได้อยู่ในสถานะรอ FA Acknowledge"
        )

    check = _check_fa_actor(actor)

    db.add(
        ARBudgetApproval(
            ar_id=ar.id,
            step_type=BudgetApprovalStepType.FA_ACKNOWLEDGE,
            level_no=None,
            level_name_snapshot="FA Acknowledge",
            action=BudgetApprovalAction.REJECTED,
            acted_by_id=actor.id,
            acted_as_override=check.is_override,
            reason=reason,
        )
    )
    ar.budget_approval_status = ARBudgetApprovalStatus.REJECTED
    return ar


# ───────────────────────── Revise: คืนยอด + Reset ─────────────────────────
def refund_on_revise(db: Session, original: ApprovalRequest) -> None:
    """เรียกตอน Revise AR ที่ Finalized แล้ว (revise_ar ใน approval_requests.py) — คืน
    ยอดงบทันทีถ้า AR ต้นฉบับเคย Approved แล้ว (หักยอดไปแล้วจริง) ไม่ทำอะไรถ้ายังไม่เคย
    Approved (pending/pending_fa_acknowledge/rejected/not_submitted — ไม่เคยหักยอดจึง
    ไม่มีอะไรต้องคืน)"""
    if (
        original.budget_approval_status == ARBudgetApprovalStatus.APPROVED
        and original.budget_master_id is not None
        and original.budget_deducted_amount is not None
    ):
        stmt = (
            update(BudgetMaster)
            .where(BudgetMaster.id == original.budget_master_id)
            .values(used_amount=BudgetMaster.used_amount - original.budget_deducted_amount)
            .returning(BudgetMaster.used_amount)
        )
        db.execute(stmt).scalar_one()


# ───────────────────────── Progress (AR Detail UI + PDF Auto-fill) ─────────────────────────
def build_approval_progress(db: Session, ar: ApprovalRequest) -> list[dict]:
    """สร้างรายการ Step ของ Stepper (Level 1..N + FA Acknowledge) รวมผลจริงจาก
    ar_budget_approvals เข้าด้วยกัน — ใช้ทั้งหน้า AR Detail (ผ่าน Schema
    ARApprovalProgressStep ใน app/schemas/budget.py) และ ar_pdf.py (Auto-fill ตาราง
    Authority/ช่อง F&A) คืนเป็น list[dict] ธรรมดา (ไม่ผูก Schema ตรงๆ) เพื่อให้ทั้ง 2
    ที่ใช้ร่วมกันได้โดยไม่ Import Pydantic Schema เข้ามาใน Service Layer"""
    from app.services.user_lookup import resolve_user_names  # กัน Circular Import

    levels = get_department_levels(db, ar.budget_department) if ar.budget_department else []
    approvals = {
        (a.step_type, a.level_no): a for a in sorted(ar.budget_approvals, key=lambda a: a.acted_at)
    }

    user_ids = {lv.approver_user_id for lv in levels}
    user_ids |= {a.acted_by_id for a in ar.budget_approvals}
    names = resolve_user_names(db, user_ids)

    # จัดกลุ่มตาม level_no (Multi-approver per Level — OR) — Level เดียวกันอาจมีหลาย
    # แถว/หลายคน ทุกแถวในกลุ่มเดียวกัน level_name ตรงกันเสมอ (บังคับ Sync ที่ Route Layer)
    groups: dict[int, list[BudgetApprovalLevel]] = {}
    for lv in levels:
        groups.setdefault(lv.level_no, []).append(lv)

    steps: list[dict] = []
    for level_no in sorted(groups):
        group = groups[level_no]
        rec = approvals.get((BudgetApprovalStepType.LEVEL, level_no))
        approver_ids = [lv.approver_user_id for lv in group]
        step = {
            "step_type": BudgetApprovalStepType.LEVEL,
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

    fa_rec = approvals.get((BudgetApprovalStepType.FA_ACKNOWLEDGE, None))
    fa_step = {
        "step_type": BudgetApprovalStepType.FA_ACKNOWLEDGE,
        "level_no": None,
        "level_name": "FA Acknowledge",
        "approver_user_ids": [],
        "approver_names": None,
        "status": "waiting",
        "acted_by_name": None,
        "acted_at": None,
        "reason": None,
        "acted_as_override": False,
    }
    if fa_rec is not None:
        fa_step["status"] = fa_rec.action.value
        fa_step["acted_by_name"] = names.get(fa_rec.acted_by_id)
        fa_step["acted_at"] = fa_rec.acted_at
        fa_step["reason"] = fa_rec.reason
        fa_step["acted_as_override"] = fa_rec.acted_as_override
    steps.append(fa_step)
    return steps


# ───────────────────────── AR Attachments (Phase A, 2026-09-10) ─────────────────────────
def can_upload_attachment(db: Session, ar: ApprovalRequest, actor: User) -> bool:
    """ใครแนบเอกสารเพิ่มได้บ้าง — Feedback จริงจากผู้ใช้: ต้อง Upload ได้ตอนสร้าง AR
    (เจ้าของ) และ "แทรกเอกสารเพิ่มเติมได้ระหว่าง Approval" (ผู้อนุมัติ Level ปัจจุบัน/FA
    ที่กำลังรอตัดสินใจอยู่ ณ ขณะนั้น) — Admin Override ได้เสมอเหมือน Action อื่นในไฟล์นี้

    ใช้ตัดสินทั้งตอน Upload และ Delete ที่ Route Layer (Delete เพิ่มเงื่อนไขว่าต้องเป็น
    คนอัปโหลดเองด้วย ไม่ใช่แค่มีสิทธิ์จัดการ AR ใบนี้ กันผู้อนุมัติคนอื่นลบเอกสารของคน
    อื่นในกลุ่มเดียวกันโดยไม่ตั้งใจ — ดู app/api/routes/ar_attachments.py)"""
    if actor.id == ar.requested_by_id or actor.is_admin:
        return True
    if (
        ar.budget_approval_status == ARBudgetApprovalStatus.PENDING
        and ar.current_approval_level is not None
        and ar.budget_department
    ):
        levels = get_department_levels(db, ar.budget_department)
        current_group = [lv for lv in levels if lv.level_no == ar.current_approval_level]
        if any(lv.approver_user_id == actor.id for lv in current_group):
            return True
    if ar.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE and actor.is_fa:
        return True
    return False


def reset_for_new_draft(ar: ApprovalRequest) -> None:
    """ตั้งค่า Field Budget Control ทั้งหมดของ AR (Draft) ใหม่ให้เป็นค่าเริ่มต้นเสมอ —
    ใช้ทั้งตอน Revise (คัดลอกจากต้นฉบับ) — ต้อง Finalize แล้วเข้าคิว Level 1 ใหม่หมด
    ทุกครั้ง ไม่ข้าม Level ที่เคยอนุมัติผ่านมาก่อนหน้า Revise"""
    ar.budget_department = None
    ar.budget_master_id = None
    ar.budget_approval_status = ARBudgetApprovalStatus.NOT_SUBMITTED
    ar.current_approval_level = None
    ar.budget_deducted_amount = None
    ar.budget_overridden = False


# ───────────────────────── My Approvals (Phase B/2, 2026-09-10) ─────────────────────────
# ดู Mockup v4 ที่ผู้ใช้ Confirm แล้ว ("เยี่ยมมาก ทำ phase2 เลย โดย Design นี้") — Sidebar
# Submenu ขยายลงจาก "การอนุมัติของฉัน" 4 หมวด:
#   1. waiting  ("กล่องรออนุมัติ")         = ทุก AR ที่ User "เกี่ยวข้อง" กำลังดำเนินอยู่
#   2. mine     ("รอการตัดสินใจของฉัน")    = Subset ของ (1) ที่ "ถึงคิว" User คนนี้ตัดสินใจ
#                                             ได้จริง ณ ตอนนี้ (Level ปัจจุบันตรงกับที่ User
#                                             เป็นผู้อนุมัติ หรือ FA รอ Acknowledge)
#   3. history  ("ประวัติการอนุมัติ")      = AR ที่ User "เคยอนุมัติ" (ไม่รวมปฏิเสธ) มาแล้ว
#   4. returned ("ส่งกลับแก้ไข")           = AR ที่ถูกปฏิเสธไปแล้ว ที่ User เกี่ยวข้องอยู่
#
# "เกี่ยวข้อง" นิยามคือ: (ก) Admin — เกี่ยวข้องกับทุกใบเสมอ (Feedback จริง: "Admin ต้อง
# เห็นทั้งหมด เพราะต้องตรวจสอบ") (ข) เป็นผู้อนุมัติ Level ใดก็ได้ (Active) ของแผนกนั้น
# (ค) เป็น FA — เกี่ยวข้องเฉพาะ AR ที่ขึ้นถึงขั้น FA Acknowledge แล้วจริง (ไม่ใช่ทุก AR ทุก
# แผนกที่ยังไม่ถึงคิว FA เลย ไม่งั้น Waiting ของ FA จะกว้างเกินจริง กลายเป็นทุกใบทั้งระบบ)
#
# หมายเหตุ Performance: Query คืน List ทั้งก้อนแล้วนับ len() เอา (ไม่แยก COUNT Query) —
# ขนาดข้อมูลจริงของ AR ในองค์กรนี้เล็ก (หลักร้อย/พันใบ) ไม่คุ้มเพิ่มความซับซ้อน Query แยก
MY_APPROVAL_BUCKETS = ("waiting", "mine", "history", "returned")


def _approver_departments(db: Session, actor: User) -> set[str]:
    """แผนกทั้งหมดที่ actor เป็นผู้อนุมัติ Level ใดก็ได้ (Active) — ใช้กับ Bucket
    "waiting"/"returned" (กว้างกว่า mine — ไม่สนว่า Level ปัจจุบันตรงกับ actor หรือไม่)"""
    rows = (
        db.execute(
            select(BudgetApprovalLevel.department)
            .where(
                BudgetApprovalLevel.approver_user_id == actor.id,
                BudgetApprovalLevel.is_active.is_(True),
            )
            .distinct()
        )
        .scalars()
        .all()
    )
    return set(rows)


def _approver_level_pairs(db: Session, actor: User) -> set[tuple[str, int]]:
    """คู่ (department, level_no) ที่ actor เป็นผู้อนุมัติจริง (Active) — ใช้กับ Bucket
    "mine" (ต้องตรง Level ปัจจุบันเป๊ะ ไม่ใช่แค่แผนกเดียวกัน)"""
    rows = db.execute(
        select(BudgetApprovalLevel.department, BudgetApprovalLevel.level_no).where(
            BudgetApprovalLevel.approver_user_id == actor.id,
            BudgetApprovalLevel.is_active.is_(True),
        )
    ).all()
    return {(r[0], r[1]) for r in rows}


def _fa_reached_ar_ids_subquery():
    """AR ที่มีบันทึก ar_budget_approvals ขั้น FA_ACKNOWLEDGE แล้วจริง (ไม่ว่าผล
    จะอนุมัติ/ปฏิเสธ) — ใช้กรอง Bucket "returned" ของ FA ไม่ให้กว้างเกินไปรวม AR ที่ถูก
    ปฏิเสธไปตั้งแต่ Level ก่อนหน้า ซึ่ง FA ไม่เคยเกี่ยวข้องด้วยเลย"""
    return (
        select(ARBudgetApproval.ar_id)
        .where(ARBudgetApproval.step_type == BudgetApprovalStepType.FA_ACKNOWLEDGE)
        .distinct()
        .scalar_subquery()
    )


def _order_and_run(db: Session, stmt) -> list[ApprovalRequest]:
    stmt = stmt.order_by(ApprovalRequest.ar_no.desc(), ApprovalRequest.revision.desc())
    return list(db.execute(stmt).scalars().all())


def _bucket_waiting(db: Session, actor: User) -> list[ApprovalRequest]:
    base = select(ApprovalRequest).where(
        ApprovalRequest.budget_approval_status.in_(
            [ARBudgetApprovalStatus.PENDING, ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE]
        )
    )
    if actor.is_admin:
        return _order_and_run(db, base)

    conditions = []
    depts = _approver_departments(db, actor)
    if depts:
        conditions.append(
            (ApprovalRequest.budget_approval_status == ARBudgetApprovalStatus.PENDING)
            & ApprovalRequest.budget_department.in_(depts)
        )
    if actor.is_fa:
        conditions.append(
            ApprovalRequest.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE
        )
    if not conditions:
        return []
    return _order_and_run(db, base.where(or_(*conditions)))


def _bucket_mine(db: Session, actor: User) -> list[ApprovalRequest]:
    if actor.is_admin:
        # Admin Override ได้ทุก Level/FA เสมอ (ดู _check_level_actor/_check_fa_actor) —
        # ทุกใบที่ค้างอยู่จึง "ถึงคิว" Admin ตัดสินใจได้จริงเท่ากับ Bucket waiting เป๊ะ
        return _bucket_waiting(db, actor)

    conditions = []
    pairs = _approver_level_pairs(db, actor)
    if pairs:
        conditions.append(
            (ApprovalRequest.budget_approval_status == ARBudgetApprovalStatus.PENDING)
            & tuple_(ApprovalRequest.budget_department, ApprovalRequest.current_approval_level).in_(
                pairs
            )
        )
    if actor.is_fa:
        conditions.append(
            ApprovalRequest.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE
        )
    if not conditions:
        return []
    return _order_and_run(db, select(ApprovalRequest).where(or_(*conditions)))


def _bucket_history(db: Session, actor: User) -> list[ApprovalRequest]:
    """AR ที่ actor เคย "อนุมัติ" (ไม่รวมปฏิเสธ — ปฏิเสธไปโผล่ Bucket "returned" แทน) มา
    แล้วอย่างน้อย 1 ครั้ง (Level ใดก็ได้ หรือ FA Acknowledge) — เป็น Log ส่วนบุคคลของ actor
    เอง แม้แต่ Admin ก็ดูเฉพาะที่ตัวเองกดจริง (ต่างจาก waiting/mine/returned ที่ Admin เห็น
    ทั้งระบบเพื่อตรวจสอบ — history คือ "ที่ฉันทำ" ไม่ใช่ "ที่ต้องตรวจ")"""
    ar_ids_subq = (
        select(ARBudgetApproval.ar_id)
        .where(
            ARBudgetApproval.acted_by_id == actor.id,
            ARBudgetApproval.action == BudgetApprovalAction.APPROVED,
        )
        .distinct()
        .scalar_subquery()
    )
    return _order_and_run(db, select(ApprovalRequest).where(ApprovalRequest.id.in_(ar_ids_subq)))


def _bucket_returned(db: Session, actor: User) -> list[ApprovalRequest]:
    base = select(ApprovalRequest).where(
        ApprovalRequest.budget_approval_status == ARBudgetApprovalStatus.REJECTED
    )
    if actor.is_admin:
        return _order_and_run(db, base)

    conditions = []
    depts = _approver_departments(db, actor)
    if depts:
        conditions.append(ApprovalRequest.budget_department.in_(depts))
    if actor.is_fa:
        conditions.append(ApprovalRequest.id.in_(_fa_reached_ar_ids_subquery()))
    if not conditions:
        return []
    return _order_and_run(db, base.where(or_(*conditions)))


_BUCKET_FUNCS = {
    "waiting": _bucket_waiting,
    "mine": _bucket_mine,
    "history": _bucket_history,
    "returned": _bucket_returned,
}


def list_my_approvals(db: Session, actor: User, bucket: str) -> list[ApprovalRequest]:
    fn = _BUCKET_FUNCS.get(bucket)
    if fn is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f'ไม่รู้จักหมวด "{bucket}"')
    return fn(db, actor)


def count_my_approvals(db: Session, actor: User) -> dict[str, int]:
    return {bucket: len(fn(db, actor)) for bucket, fn in _BUCKET_FUNCS.items()}


def is_ar_actionable_by(db: Session, ar: ApprovalRequest, actor: User) -> bool:
    """True ถ้า actor กด "อนุมัติ/ปฏิเสธ"/"FA Acknowledge" ใบนี้ได้จริง ณ ตอนนี้ (ใช้โชว์/
    ซ่อนปุ่ม Action ในหน้า My Approvals — Logic เดียวกับเงื่อนไขของ Bucket "mine" แต่เช็ค
    ทีละใบแทนการ Query ทั้งชุด)"""
    if actor.is_admin:
        return ar.budget_approval_status in (
            ARBudgetApprovalStatus.PENDING,
            ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE,
        )
    if (
        ar.budget_approval_status == ARBudgetApprovalStatus.PENDING
        and ar.current_approval_level is not None
        and ar.budget_department
    ):
        pairs = _approver_level_pairs(db, actor)
        if (ar.budget_department, ar.current_approval_level) in pairs:
            return True
    if ar.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE and actor.is_fa:
        return True
    return False
