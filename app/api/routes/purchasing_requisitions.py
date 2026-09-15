"""บันทึก PR + Generate PDF (Phase 5) + ประวัติ/ค้นหา (Phase 6)

Requested by = ผู้ใช้ที่ Login ตอนสร้าง PR เสมอ (Business Decision 2026-09-01)

Scope Revision (Phase 9, 2026-09-03): ตัด Workflow อนุมัติในระบบออกทั้งหมด (เดิม
draft->reviewed->approved->received) ตาม Feedback จริงจาก Product Owner ว่า Design
เดิมผิดตั้งแต่แรก — เหลือ 2 สถานะ: draft (แก้ไขได้) / finalized (ล็อกแล้ว)

PR Approval Level (Phase 11, 2026-09-15): กลับมามี Workflow อนุมัติงบในระบบอีกครั้ง —
Pattern เดียวกับ AR (app/services/budget_workflow.py) แต่แยกตาราง Level/Audit Trail
เต็มรูปแบบ (PRApprovalLevel/PRBudgetApproval ไม่ใช่ BudgetApprovalLevel/ARBudgetApproval
ของ AR) และต่าง 3 จุดตามที่ยืนยันกับผู้ใช้แล้ว (ดู Docstring บนสุดของ
app/services/pr_budget_workflow.py): ไม่มี FA Acknowledge, ไม่มีขั้น Received แยก, PR
ที่ไม่มี budget_control เลย Finalize ทันทีตอนกด "ส่งขออนุมัติ" ไม่มี Workflow เลย

Flow:
1. POST /prs -> สร้าง PR ใหม่ (Status = draft) รับ source_document_ids ได้หลายรายการ
   (AI สกัดจากหลายเอกสารมารวมเป็น Item เดียวกันได้ — Scope Revision Phase 9)
2. GET /prs (รองรับค้นหา/กรอง), GET /prs/{id} -> ดูรายการ/รายละเอียด PR
3. PATCH /prs/{id} -> แก้ไขได้เฉพาะตอน Status = draft และไม่ได้ถูก Reject มา (Phase 11) —
   ถ้ากำลังรอ Level อนุมัติอยู่ (pending) การแก้ไขจะยกเลิกคำขออนุมัติที่ค้างอยู่อัตโนมัติ
4. POST /prs/{id}/submit-for-approval -> (Phase 11, ใหม่) เริ่ม Workflow อนุมัติงบ ถ้าไม่มี
   budget_control เลย Finalize ทันที ถ้ามีแต่แผนกไม่มี Level ตั้งไว้ หักงบจริงทันที +
   Finalize เช่นกัน (ไม่มี FA Acknowledge คั่นแบบ AR) นอกนั้นเข้าคิวรอ Level 1
5. GET /prs/{id}/pdf -> Generate PDF อย่างเดียว ไม่มีผลข้างเคียงใดๆ อีกต่อไป (Phase 11 —
   เดิม Finalize อัตโนมัติตอนพิมพ์ครั้งแรก ย้ายไป submit-for-approval แทนแล้ว เหมือน AR
   Correction 2026-09-10)
6. POST /prs/{id}/revise -> Revise ได้ 2 กรณี (Phase 11 Hybrid Gate — ดู revise_pr):
   PR ที่ไม่เคยมี budget_control เลย ยังคง Gate ด้วย status == Finalized แบบเดิม ส่วน PR
   ที่มี budget_control ต้อง Gate ด้วย budget_approval_status == Rejected แทน (ไม่เกี่ยว
   กับ pr.status อีกต่อไป เพราะถูก Reject ที่ Level แรกอาจไม่เคยถึง Finalized เลยก็ได้)
7. GET /prs/{id}/history -> ประวัติการกระทำทั้งหมดของ PR นี้จาก audit_log

Full RBAC (Correction 2026-09-10, ขยาย Phase 11): ผู้ใช้ที่ติ๊ก can_view_pr เห็น/แก้ไข/
พิมพ์ได้เฉพาะ PR ที่ตัวเองสร้าง (requested_by_id ตรงกับตัวเอง) เท่านั้น — can_view_all_pr
ขยายให้เห็นทั้งหมด แต่ไม่ได้แปลว่าสร้าง PR ใหม่ได้ (create_pr ต้อง is_admin หรือ
can_view_pr เท่านั้น) Phase 11 เพิ่มเหตุผลชอบธรรมใหม่อีกข้อ: ผู้อนุมัติ Level ปัจจุบันที่
กำลังรอ PR ใบนั้นอยู่ ดูได้แม้ไม่มี can_view_pr/can_view_all_pr เลยก็ตาม (ดู
_check_pr_view_access) — แต่ไม่ได้ทำให้ RBAC ของ PR เปิดกว้างเท่า AR (ที่ไม่เช็ค Ownership
เลย) ยังคงจำกัดเฉพาะเจ้าของ/Admin/can_view_all_pr/ผู้อนุมัติ Level ปัจจุบันเท่านั้น

Correction 2 (แยก ALL ตาม PR/AR, 2026-09-10): "เห็นทั้งหมด" ไม่ได้แปลว่า "แก้ไขทั้งหมด" —
แยก Access เป็น 2 ระดับ:
- _check_pr_view_access: Admin, can_view_all_pr, เจ้าของ, หรือผู้อนุมัติ Level ปัจจุบัน
  (Phase 11) — ใช้กับ get_pr/get_pr_history/get_pr_approval_progress (แค่ "ดู" อย่างเดียว)
- _check_pr_edit_access: Admin หรือเจ้าของเท่านั้น (ไม่รวม can_view_all_pr/ผู้อนุมัติ) —
  ใช้กับ update_pr/revise_pr/get_pr_pdf/submit_pr_for_approval (แก้ไข/สร้าง Revision/
  พิมพ์/เริ่ม Workflow ถือเป็นการกระทำต่อ PR โดยตรง ไม่ใช่แค่ดูเฉยๆ)
- approve_pr_level/reject_pr_level: ไม่เช็คทั้งสองแบบข้างบน (ผู้อนุมัติ Level อาจไม่มี
  can_view_pr/can_view_all_pr เลยก็ได้ — เป็นคนละ Role กัน) ใช้แค่ Login (get_current_user)
  แล้วปล่อยให้ pr_budget_workflow._check_level_actor เช็ค Authorization เอง (Pattern
  เดียวกับ approve_ar_level/reject_ar_level ของ AR ทุกประการ)
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, require_can_view_pr, require_can_view_pr_approvals
from app.db.session import get_db
from app.models import (
    AuditLog,
    PRBudgetApprovalStatus,
    PRBudgetControl,
    PRItem,
    PRStatus,
    PurchasingRequisition,
    SourceDocument,
    User,
)
from app.schemas.budget import BudgetRejectBody
from app.schemas.pr_budget import (
    PRApprovalProgressStep,
    PRApproveLevelBody,
    PRMyApprovalCounts,
    PRMyApprovalItem,
    PRSubmitBody,
)
from app.schemas.purchasing_requisition import (
    AuditLogRead,
    PRCreate,
    PRListItem,
    PRRead,
    PRUpdate,
)
from app.services import pr_budget_workflow
from app.services.pr_numbering import allocate_pr_no
from app.services.pr_pdf import render_pr_pdf
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/prs", tags=["purchasing-requisitions"])


def _apply_items_and_budget(pr: PurchasingRequisition, body: PRCreate | PRUpdate) -> None:
    pr.section = body.section
    pr.division = body.division
    pr.doc_date = body.doc_date
    pr.remark = body.remark
    pr.items = [
        PRItem(
            item_no=index,
            account_code=item.account_code,
            description=item.description,
            quantity=item.quantity,
            required_date=item.required_date,
            reason=item.reason,
            ref_po=item.ref_po,
        )
        for index, item in enumerate(body.items, start=1)
    ]
    if body.budget_control is not None:
        # Phase 11 (2026-09-15): account_code เป็นค่า Snapshot ที่ Server เติมให้เอง
        # (ไม่รับจาก Client) — ยังไม่ Resolve budget_master_id จริงตอนนี้ (เป็น Phase 2
        # ของรอบนี้ — ตอน Submit เข้า Workflow อนุมัติค่อย Resolve จาก budget_no)
        if pr.budget_control is not None:
            # แก้ไขแถวเดิมแทนการสร้างใหม่ทับ — ถ้าสร้าง PRBudgetControl() ใหม่ทับตรงๆ
            # SQLAlchemy จะพยายาม Insert แถวใหม่ก่อน Delete แถวเก่า (Unique Constraint บน
            # pr_id ชนกันเอง) เพราะเป็นความสัมพันธ์แบบ One-to-One (uselist=False)
            pr.budget_control.budget_no = body.budget_control.budget_no
            pr.budget_control.this_application = body.budget_control.this_application
        else:
            pr.budget_control = PRBudgetControl(
                budget_no=body.budget_control.budget_no,
                this_application=body.budget_control.this_application,
            )
    else:
        pr.budget_control = None


def _get_pr_or_404(db: Session, pr_id: int) -> PurchasingRequisition:
    pr = (
        db.query(PurchasingRequisition)
        .options(selectinload(PurchasingRequisition.items))
        .filter(PurchasingRequisition.id == pr_id)
        .first()
    )
    if pr is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ PR")
    return pr


def _check_pr_view_access(db: Session, pr: PurchasingRequisition, user: User) -> None:
    """ดู PR ได้ — Admin, can_view_all_pr (เห็น PR ทั้งหมด), เจ้าของ, หรือ (Phase 11)
    ผู้อนุมัติ Level ปัจจุบันที่กำลังรอ PR ใบนี้อยู่ (ดู Docstring บนสุดของไฟล์นี้:
    Correction 2 — "เห็นทั้งหมด" ครอบคลุมแค่การ "ดู" เท่านั้น)"""
    if user.is_admin or user.can_view_all_pr:
        return
    if pr.requested_by_id == user.id:
        return
    if pr_budget_workflow.is_current_level_approver(db, pr, user):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "คุณไม่มีสิทธิ์เข้าถึง PR ฉบับนี้ (เห็นได้เฉพาะ PR ที่ตัวเองสร้าง หรือที่รอตัวเองอนุมัติ)",
    )


def _check_pr_edit_access(pr: PurchasingRequisition, user: User) -> None:
    """แก้ไข/Revise/พิมพ์ PR ได้ — Admin หรือเจ้าของเท่านั้น (ไม่รวม can_view_all_pr — ดู
    Docstring บนสุดของไฟล์นี้: Correction 2 — เห็นทั้งหมด ไม่ได้แปลว่าแก้ไขทั้งหมด)"""
    if user.is_admin:
        return
    if pr.requested_by_id != user.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "คุณไม่มีสิทธิ์แก้ไข PR ฉบับนี้ (แก้ไข/พิมพ์ได้เฉพาะ PR ที่ตัวเองสร้าง)",
        )


def _to_pr_read(db: Session, pr: PurchasingRequisition) -> PRRead:
    names = resolve_user_names(db, {pr.requested_by_id})
    # หา PR ที่ Revise ต่อจากฉบับนี้แล้ว (ถ้ามี) — ไม่ใช่คอลัมน์จริง ต้อง Query ย้อนกลับ
    # จาก revised_from_id ของฉบับอื่น เพื่อเตือนไม่ให้หยิบฉบับเก่าไปใช้ผิด
    superseded_by = (
        db.query(PurchasingRequisition.id)
        .filter(PurchasingRequisition.revised_from_id == pr.id)
        .order_by(PurchasingRequisition.revision.desc())
        .first()
    )
    data = PRRead.model_validate(pr, from_attributes=True)
    return data.model_copy(
        update={
            "requested_by_name": names.get(pr.requested_by_id),
            "superseded_by_id": superseded_by[0] if superseded_by else None,
        }
    )


@router.post("", response_model=PRRead, status_code=status.HTTP_201_CREATED)
def create_pr(
    body: PRCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> PRRead:
    # can_view_all คือสิทธิ์ดูภาพรวมอย่างเดียว ไม่ได้แปลว่าสร้าง PR แทนคนอื่นได้ — ต้องมี
    # can_view_pr (หรือ Admin) จริงๆ เท่านั้นถึงจะสร้างได้ (ดู Docstring บนสุดของไฟล์นี้)
    if not (current_user.is_admin or current_user.can_view_pr):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ต้องมีสิทธิ์ PR ถึงจะสร้าง PR ใหม่ได้")
    if body.source_document_ids:
        found = (
            db.query(SourceDocument.id)
            .filter(SourceDocument.id.in_(body.source_document_ids))
            .all()
        )
        found_ids = {row[0] for row in found}
        missing = set(body.source_document_ids) - found_ids
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"ไม่พบเอกสารต้นทาง ID: {sorted(missing)}"
            )

    pr = PurchasingRequisition(
        pr_no=allocate_pr_no(db),
        status=PRStatus.DRAFT,
        requested_by_id=current_user.id,
    )
    _apply_items_and_budget(pr, body)
    db.add(pr)
    db.flush()  # ให้ pr.id พร้อมใช้ก่อน Commit

    if body.source_document_ids:
        db.query(SourceDocument).filter(SourceDocument.id.in_(body.source_document_ids)).update(
            {"pr_id": pr.id}, synchronize_session=False
        )

    db.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.created",
            actor_id=current_user.id,
            detail={"pr_no": pr.pr_no, "source_document_ids": body.source_document_ids or None},
        )
    )
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.get("", response_model=list[PRListItem])
def list_prs(
    status_filter: PRStatus | None = None,
    pr_no: int | None = None,
    q: str | None = Query(default=None, description="ค้นหาใน Section/Division/Remark"),
    doc_date_from: date | None = None,
    doc_date_to: date | None = None,
    requested_by_me: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> list[PurchasingRequisition]:
    query = db.query(PurchasingRequisition)
    if status_filter is not None:
        query = query.filter(PurchasingRequisition.status == status_filter)
    if pr_no is not None:
        query = query.filter(PurchasingRequisition.pr_no == pr_no)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                PurchasingRequisition.section.ilike(like),
                PurchasingRequisition.division.ilike(like),
                PurchasingRequisition.remark.ilike(like),
            )
        )
    if doc_date_from is not None:
        query = query.filter(PurchasingRequisition.doc_date >= doc_date_from)
    if doc_date_to is not None:
        query = query.filter(PurchasingRequisition.doc_date <= doc_date_to)
    if requested_by_me:
        query = query.filter(PurchasingRequisition.requested_by_id == current_user.id)

    # Full RBAC (Correction 2026-09-10): บังคับเห็นเฉพาะ PR ของตัวเอง เว้นแต่ Admin หรือ
    # can_view_all_pr (เห็นภาพรวม) — ไม่ใช่แค่ requested_by_me แบบ Opt-in อีกต่อไป
    if not (current_user.is_admin or current_user.can_view_all_pr):
        query = query.filter(PurchasingRequisition.requested_by_id == current_user.id)

    return (
        query.order_by(PurchasingRequisition.pr_no.desc(), PurchasingRequisition.revision.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/my-approvals/counts", response_model=PRMyApprovalCounts)
def get_my_pr_approval_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr_approvals),
) -> PRMyApprovalCounts:
    """เติมเลข Badge ทั้ง 4 หมวดที่ Sidebar Submenu "My PR Approvals" (base.html) — เรียก
    ทุกหน้าที่มีเมนูนี้โชว์อยู่ ไม่ใช่แค่หน้า PR My Approvals เอง (Pattern เดียวกับ
    get_my_approval_counts ของ AR)"""
    return PRMyApprovalCounts(**pr_budget_workflow.count_my_approvals(db, current_user))


def _to_pr_my_approval_item(
    db: Session, pr: PurchasingRequisition, names: dict[int, str], actor: User
) -> PRMyApprovalItem:
    bc = pr.budget_control
    level_name = pr_budget_workflow.resolve_current_level_name(db, bc) if bc else None
    pr_no_display = f"{pr.pr_no} Rev.{pr.revision}" if pr.revision else str(pr.pr_no)

    return PRMyApprovalItem(
        id=pr.id,
        pr_no=pr.pr_no,
        pr_no_display=pr_no_display,
        revision=pr.revision,
        section=pr.section,
        division=pr.division,
        doc_date=pr.doc_date,
        budget_department=bc.budget_department if bc else None,
        budget_approval_status=bc.budget_approval_status
        if bc
        else PRBudgetApprovalStatus.NOT_SUBMITTED,
        current_approval_level=bc.current_approval_level if bc else None,
        current_level_name=level_name,
        requested_by_id=pr.requested_by_id,
        requested_by_name=names.get(pr.requested_by_id),
        actionable=pr_budget_workflow.is_pr_actionable_by(db, pr, actor),
        created_at=pr.created_at,
    )


@router.get("/my-approvals", response_model=list[PRMyApprovalItem])
def list_my_pr_approvals_route(
    bucket: str = Query(..., pattern="^(waiting|mine|history|returned)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr_approvals),
) -> list[PRMyApprovalItem]:
    prs = pr_budget_workflow.list_my_approvals(db, current_user, bucket)
    page = prs[offset : offset + limit]
    names = resolve_user_names(db, {pr.requested_by_id for pr in page})
    return [_to_pr_my_approval_item(db, pr, names, current_user) for pr in page]


@router.get("/{pr_id}", response_model=PRRead)
def get_pr(
    pr_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PRRead:
    """Phase 11 (2026-09-15): เปลี่ยนจาก require_can_view_pr เป็น get_current_user เฉยๆ —
    ผู้อนุมัติ Level ปัจจุบันอาจไม่มี can_view_pr/can_view_all_pr เลยก็ได้ (เป็นคนละ Role
    กัน) ถ้ายังใช้ require_can_view_pr อยู่จะโดนบล็อกตั้งแต่ Dependency ก่อนถึง
    _check_pr_view_access ที่ Extend ไว้ให้แล้วด้วยซ้ำ — Authorization จริงทำใน
    _check_pr_view_access ทั้งหมด (Pattern เดียวกับ get_ar ของ AR)"""
    pr = _get_pr_or_404(db, pr_id)
    _check_pr_view_access(db, pr, current_user)
    return _to_pr_read(db, pr)


@router.patch("/{pr_id}", response_model=PRRead)
def update_pr(
    pr_id: int,
    body: PRUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> PRRead:
    """แก้ไข PR — Phase 11 (2026-09-15): พิมพ์/ดาวน์โหลด PDF ไม่ Lock อีกต่อไป (ดู
    get_pr_pdf) เอกสารจึงแก้ได้ตราบใดที่ยังเป็น Draft และไม่ได้ถูก Reject มา (Reject
    แล้วต้องผ่าน Revise เท่านั้น — ดู revise_pr) ถ้ากำลังรอ Level อนุมัติอยู่ตอนแก้
    (budget_approval_status == pending) ถือว่ายกเลิกคำขออนุมัติที่ค้างอยู่โดยอัตโนมัติ
    กัน Level เห็นข้อมูลเก่าที่ถูกแก้ไปแล้วโดยไม่รู้ตัว — ต้องกด "ส่งขออนุมัติ" ใหม่
    (Pattern เดียวกับ update_ar ของ AR ทุกประการ)"""
    pr = _get_pr_or_404(db, pr_id)
    _check_pr_edit_access(pr, current_user)
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "แก้ไขได้เฉพาะ PR ที่ยังเป็นสถานะ Draft เท่านั้น (Finalized แล้วแก้ไม่ได้)"
        )
    bc = pr.budget_control
    if bc is not None and bc.budget_approval_status == PRBudgetApprovalStatus.REJECTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            'PR นี้ถูกปฏิเสธไปแล้ว แก้ไขตรงๆ ไม่ได้ — กรุณาใช้ปุ่ม "สร้าง Revision" แทน',
        )

    approval_cancelled = (
        bc is not None and bc.budget_approval_status == PRBudgetApprovalStatus.PENDING
    )
    if approval_cancelled:
        pr_budget_workflow.reset_for_new_draft(bc)

    _apply_items_and_budget(pr, body)
    db.add(AuditLog(pr_id=pr.id, action="pr.updated", actor_id=current_user.id, detail=None))
    if approval_cancelled:
        db.add(
            AuditLog(
                pr_id=pr.id,
                action="pr.approval_cancelled_by_edit",
                actor_id=current_user.id,
                detail={"reason": "แก้ไข PR ระหว่างรอ Level อนุมัติ — ยกเลิกคำขออนุมัติที่ค้างอยู่อัตโนมัติ"},
            )
        )
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.post("/{pr_id}/revise", response_model=PRRead, status_code=status.HTTP_201_CREATED)
def revise_pr(
    pr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> PRRead:
    """สร้าง PR ใหม่สถานะ Draft คัดลอกข้อมูลจาก PR ต้นฉบับ เพื่อแก้ไขต่อโดยไม่ไปรื้อของเดิม
    (Feedback จริงจากผู้ใช้ 2026-09-03)

    เลข PR ใช้เลขเดิม + Rev ต่อท้าย (revision +1 จากฉบับล่าสุดของ pr_no นี้ — เผื่อกรณี
    Revise ซ้ำหลายรอบ) — requested_by คงเป็นคนเดิม (เป็น PR เดียวกันที่แก้ไข ไม่ใช่คำขอ
    ใหม่) ส่วนคนที่กด Revise จริงบันทึกแยกไว้ใน Audit Log (actor_id)

    Hybrid Gate (Phase 11, 2026-09-15): PR ที่ไม่เคยมี budget_control เลย (ไม่เคยติ๊ก
    "Has Budget Control") ไม่เคยผ่าน Workflow อนุมัติใดๆ เลย — คง Gate เดิมไว้คือ Revise
    ได้ต่อเมื่อ status == Finalized (พิมพ์แล้ว) เท่านั้น ส่วน PR ที่มี budget_control ต้อง
    Gate ด้วย budget_approval_status == Rejected แทน (Pattern เดียวกับ revise_ar) เพราะ
    ถูก Level ไหนก็ได้ Reject มา ไม่จำเป็นต้องเคยถึง Finalized เลยก็ได้ (approve_level
    เท่านั้นที่ทำให้ pr.status เป็น Finalized ไม่ใช่ reject_level)"""
    original = _get_pr_or_404(db, pr_id)
    _check_pr_edit_access(original, current_user)
    bc = original.budget_control
    if bc is None:
        if original.status != PRStatus.FINALIZED:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Revise ได้เฉพาะ PR ที่ Finalized แล้วเท่านั้น"
            )
    elif bc.budget_approval_status != PRBudgetApprovalStatus.REJECTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Revise ได้เฉพาะ PR ที่ถูกปฏิเสธ (Rejected) แล้วเท่านั้น"
        )

    already_superseded = (
        db.query(PurchasingRequisition.id)
        .filter(PurchasingRequisition.revised_from_id == original.id)
        .first()
    )
    if already_superseded:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "PR นี้ถูก Revise ไปแล้ว กรุณา Revise จากฉบับล่าสุดแทน",
        )

    max_revision = (
        db.query(func.max(PurchasingRequisition.revision))
        .filter(PurchasingRequisition.pr_no == original.pr_no)
        .scalar()
        or 0
    )

    new_pr = PurchasingRequisition(
        pr_no=original.pr_no,
        revision=max_revision + 1,
        revised_from_id=original.id,
        status=PRStatus.DRAFT,
        requested_by_id=original.requested_by_id,
        section=original.section,
        division=original.division,
        doc_date=original.doc_date,
        remark=original.remark,
    )
    new_pr.items = [
        PRItem(
            item_no=item.item_no,
            account_code=item.account_code,
            description=item.description,
            quantity=item.quantity,
            required_date=item.required_date,
            reason=item.reason,
            ref_po=item.ref_po,
        )
        for item in original.items
    ]
    if bc is not None:
        # Phase 11 (2026-09-15): คัดลอกแค่ budget_no/this_application (Input เดิมของ
        # ผู้ใช้) — Field Workflow อนุมัติ (budget_approval_status/account_code/
        # budget_master_id/ฯลฯ) รีเซ็ตเป็นค่าเริ่มต้นเสมอ (Pattern เดียวกับ AR
        # reset_for_new_draft: Revise ต้องเข้าคิว Level 1 ใหม่หมด ไม่ข้าม Level เดิม) —
        # คืนยอดงบทันทีถ้าต้นฉบับเคย Approved แล้ว (หักยอดไปแล้วจริง)
        pr_budget_workflow.refund_on_revise(db, original)
        new_bc = PRBudgetControl(
            budget_no=bc.budget_no,
            this_application=bc.this_application,
        )
        pr_budget_workflow.reset_for_new_draft(new_bc)
        new_pr.budget_control = new_bc

    db.add(new_pr)
    db.flush()  # ให้ new_pr.id พร้อมใช้ก่อน Commit

    db.add(
        AuditLog(
            pr_id=new_pr.id,
            action="pr.revised",
            actor_id=current_user.id,
            detail={
                "revised_from_id": original.id,
                "pr_no": new_pr.pr_no,
                "revision": new_pr.revision,
            },
        )
    )
    db.add(
        AuditLog(
            pr_id=original.id,
            action="pr.revision_created",
            actor_id=current_user.id,
            detail={"new_pr_id": new_pr.id, "revision": new_pr.revision},
        )
    )
    db.commit()
    db.refresh(new_pr)
    return _to_pr_read(db, new_pr)


@router.get("/{pr_id}/pdf")
def get_pr_pdf(
    pr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> Response:
    """Phase 11 (2026-09-15): พิมพ์/ดาวน์โหลด PDF ไม่มีผลข้างเคียงต่อ PR อีกต่อไป (เดิม
    Finalize อัตโนมัติตอนพิมพ์ครั้งแรก — ย้ายไป submit_pr_for_approval แทนแล้ว Pattern
    เดียวกับ AR Correction 2026-09-10 ทุกประการ) พิมพ์ดูกี่ครั้งก็ได้ไม่ว่าจะสถานะไหน"""
    pr = _get_pr_or_404(db, pr_id)
    _check_pr_edit_access(pr, current_user)
    pdf_bytes = render_pr_pdf(db, pr)

    rev_suffix = f"-Rev{pr.revision}" if pr.revision else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="PR-{pr.pr_no}{rev_suffix}.pdf"'},
    )


@router.post("/{pr_id}/submit-for-approval", response_model=PRRead)
def submit_pr_for_approval(
    pr_id: int,
    body: PRSubmitBody = PRSubmitBody(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_pr),
) -> PRRead:
    """Phase 11 (2026-09-15): จุดเริ่ม Workflow อนุมัติงบ — PR ยังเป็น Draft แก้ไขได้อยู่
    หลังกดปุ่มนี้ (ดู update_pr สำหรับ Logic ยกเลิกคำขออนุมัติอัตโนมัติถ้าแก้ระหว่างรออยู่)
    จะ Finalized (ล็อกแก้ไข) ก็ต่อเมื่อ Level แรกอนุมัติผ่านจริง (ดู
    pr_budget_workflow.approve_level) ยกเว้น 2 กรณี Finalize ทันทีตอนกดปุ่มนี้เลย: (1) PR
    นี้ไม่มี budget_control เลย (ไม่เคยติ๊ก "Has Budget Control") หรือ (2) แผนกยังไม่ได้
    ตั้ง Level อนุมัติเลยสักคน (หักงบจริงทันทีในนี้เลย — ไม่มี FA Acknowledge คั่นแบบ AR)"""
    pr = _get_pr_or_404(db, pr_id)
    _check_pr_edit_access(pr, current_user)
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "PR นี้ Finalized ไปแล้ว")

    bc = pr.budget_control
    detail: dict = {"trigger": "submit_for_approval"}

    if bc is None or not bc.budget_no:
        # ไม่มี budget_control เลย — Finalize ทันที ไม่มี Workflow อนุมัติ (ยืนยันกับ
        # ผู้ใช้แล้ว 2026-09-15 — ดู Docstring บนสุดของ pr_budget_workflow.py ข้อ 3)
        pr.status = PRStatus.FINALIZED
        detail["auto_finalized"] = "no_budget_control"
    else:
        if bc.budget_approval_status != PRBudgetApprovalStatus.NOT_SUBMITTED:
            raise HTTPException(status.HTTP_409_CONFLICT, "PR นี้ถูกส่งขออนุมัติไปแล้ว")
        requester = db.get(User, pr.requested_by_id)
        pr_budget_workflow.start_budget_workflow(
            db, bc, requester, pr.doc_date or date.today(), force=body.force
        )
        if bc.budget_approval_status == PRBudgetApprovalStatus.APPROVED:
            # แผนกนี้ไม่มี Level อนุมัติเลย — หักงบจริงทันทีใน start_budget_workflow แล้ว
            # ไม่มี Level 1 ให้รอ จึง Finalize ทันที (ดู Docstring บนสุดของฟังก์ชันนี้)
            pr.status = PRStatus.FINALIZED
            detail["auto_finalized"] = "no_levels_configured"

    db.add(
        AuditLog(
            pr_id=pr.id, action="pr.submitted_for_approval", actor_id=current_user.id, detail=detail
        )
    )
    if pr.status == PRStatus.FINALIZED:
        # Log แยก "pr.finalized" ไว้ให้เห็นชัดในประวัติเหมือน Path ที่ Finalize ผ่านการ
        # อนุมัติ Level (ดู approve_pr_level) — Consistency ของ Audit Trail ทั้ง 2 ทาง
        db.add(
            AuditLog(
                pr_id=pr.id,
                action="pr.finalized",
                actor_id=current_user.id,
                detail={"trigger": "submit_for_approval", "reason": detail.get("auto_finalized")},
            )
        )
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.get("/{pr_id}/approval-progress", response_model=list[PRApprovalProgressStep])
def get_pr_approval_progress(
    pr_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[PRApprovalProgressStep]:
    pr = _get_pr_or_404(db, pr_id)
    _check_pr_view_access(db, pr, current_user)
    steps = pr_budget_workflow.build_approval_progress(db, pr)
    return [PRApprovalProgressStep(**s) for s in steps]


@router.post("/{pr_id}/approve-level", response_model=PRRead)
def approve_pr_level(
    pr_id: int,
    body: PRApproveLevelBody = PRApproveLevelBody(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRRead:
    """ไม่เช็ค _check_pr_view_access/_check_pr_edit_access — ผู้อนุมัติ Level อาจไม่มี
    can_view_pr/can_view_all_pr เลยก็ได้ (เป็นคนละ Role กัน) ปล่อยให้
    pr_budget_workflow._check_level_actor เช็ค Authorization เอง (Pattern เดียวกับ
    approve_ar_level ของ AR ทุกประการ)"""
    pr = _get_pr_or_404(db, pr_id)
    level_before = pr.budget_control.current_approval_level if pr.budget_control else None
    was_draft = pr.status == PRStatus.DRAFT
    pr_budget_workflow.approve_level(db, pr, current_user, comment=body.comment, force=body.force)
    db.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.budget_level_approved",
            actor_id=current_user.id,
            detail={"level_no": level_before, "comment": body.comment},
        )
    )
    if was_draft and pr.status == PRStatus.FINALIZED:
        db.add(
            AuditLog(
                pr_id=pr.id,
                action="pr.finalized",
                actor_id=current_user.id,
                detail={"trigger": "level_approved", "level_no": level_before},
            )
        )
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.post("/{pr_id}/reject-level", response_model=PRRead)
def reject_pr_level(
    pr_id: int,
    body: BudgetRejectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRRead:
    pr = _get_pr_or_404(db, pr_id)
    level_before = pr.budget_control.current_approval_level if pr.budget_control else None
    pr_budget_workflow.reject_level(db, pr, current_user, body.reason)
    db.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.budget_level_rejected",
            actor_id=current_user.id,
            detail={"level_no": level_before, "reason": body.reason},
        )
    )
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.get("/{pr_id}/history", response_model=list[AuditLogRead])
def get_pr_history(
    pr_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[AuditLogRead]:
    pr = _get_pr_or_404(db, pr_id)  # 404 ถ้าไม่มี PR นี้จริง
    _check_pr_view_access(db, pr, current_user)
    logs = (
        db.query(AuditLog).filter(AuditLog.pr_id == pr_id).order_by(AuditLog.timestamp.asc()).all()
    )
    names = resolve_user_names(db, {log.actor_id for log in logs})
    return [
        AuditLogRead.model_validate(log, from_attributes=True).model_copy(
            update={"actor_name": names.get(log.actor_id) if log.actor_id else None}
        )
        for log in logs
    ]
