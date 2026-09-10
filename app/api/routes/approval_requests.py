"""บันทึก Approval Request (AR) + Generate PDF + ประวัติ/ค้นหา — เดิม Pattern เดียวกับ
app/api/routes/purchasing_requisitions.py ทุกประการ (Business Decision 2026-09-08)
แต่ Flow Finalize/Revise ถูกแก้ใหม่เฉพาะ AR แล้ว (Correction 2026-09-10 — ดูด้านล่าง
PR ยังคงใช้ Pattern เดิม พิมพ์/ดาวน์โหลดครั้งแรก = Finalize ทันที ไม่ได้แก้)

Requested by = ผู้ใช้ที่ Login ตอนสร้าง AR เสมอ

Flow (Correction 2026-09-10 — ผู้ใช้แจ้งว่าพิมพ์/ดาวน์โหลด PDF ต้องไม่มีผลข้างเคียง
อีกต่อไป แยก "เริ่ม Workflow อนุมัติ" ออกจาก "พิมพ์ดูเอกสาร" เป็นคนละ Action กัน):
1. POST /ars -> สร้าง AR ใหม่ (Status = draft)
2. GET /ars (รองรับค้นหา/กรอง), GET /ars/{id} -> ดูรายการ/รายละเอียด AR
3. PATCH /ars/{id} -> แก้ไขได้เฉพาะตอน Status = draft และไม่ได้ถูก Reject มา — ถ้ากำลัง
   รอ Level อนุมัติอยู่ (pending) การแก้ไขจะยกเลิกคำขออนุมัติที่ค้างอยู่อัตโนมัติ
4. POST /ars/{id}/submit-for-approval -> เริ่ม Workflow อนุมัติหักงบ (Resolve Level 1)
   AR ยังเป็น Draft แก้ไขได้อยู่ — จะ Finalized (ล็อก) ก็ต่อเมื่อ Level แรกอนุมัติผ่าน
   จริง (ดู budget_workflow.approve_level) ยกเว้นแผนกไม่มี Level เลยจะ Finalized ทันที
5. GET /ars/{id}/pdf -> Generate PDF อย่างเดียว ไม่มีผลข้างเคียงใดๆ พิมพ์ดูกี่ครั้งก็ได้
6. POST /ars/{id}/revise -> Revise ได้เฉพาะ AR ที่ถูกปฏิเสธ (budget_approval_status ==
   rejected) แล้วเท่านั้น ไม่เกี่ยวกับว่า Finalized ไปแล้วหรือยัง (คัดลอกข้อมูลเป็นฉบับ
   Draft ใหม่)
7. GET /ars/{id}/history -> ประวัติการกระทำทั้งหมดของ AR นี้จาก audit_log
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, require_can_view_approvals
from app.db.session import get_db
from app.models import (
    ApprovalRequest,
    ARAmountItem,
    ARBudgetApprovalStatus,
    ARStatus,
    AuditLog,
    User,
)
from app.schemas.approval_request import (
    ARCreate,
    ARListItem,
    ARRead,
    ARUpdate,
)
from app.schemas.budget import (
    ARApprovalProgressStep,
    BudgetApproveLevelBody,
    BudgetFaAcknowledgeBody,
    BudgetRejectBody,
    MyApprovalCounts,
    MyApprovalItem,
)
from app.schemas.purchasing_requisition import AuditLogRead
from app.services import budget_workflow
from app.services.ar_numbering import allocate_ar_no, format_ar_no
from app.services.ar_pdf import render_ar_pdf
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/ars", tags=["approval-requests"])


def _apply_items(ar: ApprovalRequest, body: ARCreate | ARUpdate) -> None:
    ar.application_date = body.application_date
    ar.subject = body.subject
    ar.budget_type = body.budget_type
    ar.budget_no = body.budget_no
    ar.budget_sub_category = body.budget_sub_category
    ar.budget_name = body.budget_name
    ar.budget_for_year = body.budget_for_year
    ar.amount_used_before = body.amount_used_before
    ar.this_application = body.this_application
    ar.balance = body.balance
    ar.description = body.description
    ar.total = body.total
    ar.vat_amount = body.vat_amount
    ar.grand_total = body.grand_total
    ar.suppliers = body.suppliers
    ar.term_of_payment = body.term_of_payment
    ar.schedule_start = body.schedule_start
    ar.schedule_finish = body.schedule_finish
    ar.amount_items = [
        ARAmountItem(item_no=index, label=item.label, amount=item.amount)
        for index, item in enumerate(body.amount_items, start=1)
    ]


def _get_ar_or_404(db: Session, ar_id: int) -> ApprovalRequest:
    ar = (
        db.query(ApprovalRequest)
        .options(selectinload(ApprovalRequest.amount_items))
        .filter(ApprovalRequest.id == ar_id)
        .first()
    )
    if ar is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ Approval Request")
    return ar


def _to_ar_read(db: Session, ar: ApprovalRequest) -> ARRead:
    names = resolve_user_names(db, {ar.requested_by_id})
    superseded_by = (
        db.query(ApprovalRequest.id)
        .filter(ApprovalRequest.revised_from_id == ar.id)
        .order_by(ApprovalRequest.revision.desc())
        .first()
    )
    data = ARRead.model_validate(ar, from_attributes=True)
    return data.model_copy(
        update={
            "ar_no_display": format_ar_no(ar.ar_no),
            "requested_by_name": names.get(ar.requested_by_id),
            "superseded_by_id": superseded_by[0] if superseded_by else None,
        }
    )


@router.post("", response_model=ARRead, status_code=status.HTTP_201_CREATED)
def create_ar(
    body: ARCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    # Budget Control (2026-09-09, Design §2.1): ผู้สร้าง AR ต้องมี Department เสมอ —
    # Validate ที่นี่ (Application-level) ไม่ใช่ DB Constraint เพราะผู้อนุมัติบาง Level
    # ไม่มี Department ได้ (Cross-department) — กฎนี้บังคับเฉพาะตอน "สร้าง AR" เท่านั้น
    if not current_user.department:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "บัญชีของคุณยังไม่ได้ระบุ Department — กรุณาติดต่อ Admin ให้กรอกก่อนสร้าง Approval Request",
        )
    ar = ApprovalRequest(
        ar_no=allocate_ar_no(db),
        status=ARStatus.DRAFT,
        requested_by_id=current_user.id,
    )
    _apply_items(ar, body)
    db.add(ar)
    db.flush()  # ให้ ar.id พร้อมใช้ก่อน Commit

    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.created",
            actor_id=current_user.id,
            detail={"ar_no": ar.ar_no},
        )
    )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.get("", response_model=list[ARListItem])
def list_ars(
    status_filter: ARStatus | None = None,
    ar_no: int | None = None,
    q: str | None = Query(default=None, description="ค้นหาใน Subject"),
    app_date_from: date | None = None,
    app_date_to: date | None = None,
    requested_by_me: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ARListItem]:
    query = db.query(ApprovalRequest)
    if status_filter is not None:
        query = query.filter(ApprovalRequest.status == status_filter)
    if ar_no is not None:
        query = query.filter(ApprovalRequest.ar_no == ar_no)
    if q:
        query = query.filter(ApprovalRequest.subject.ilike(f"%{q}%"))
    if app_date_from is not None:
        query = query.filter(ApprovalRequest.application_date >= app_date_from)
    if app_date_to is not None:
        query = query.filter(ApprovalRequest.application_date <= app_date_to)
    if requested_by_me:
        query = query.filter(ApprovalRequest.requested_by_id == current_user.id)

    ars = (
        query.order_by(ApprovalRequest.ar_no.desc(), ApprovalRequest.revision.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = []
    for ar in ars:
        item = ARListItem.model_validate(ar, from_attributes=True)
        result.append(item.model_copy(update={"ar_no_display": format_ar_no(ar.ar_no)}))
    return result


@router.get("/my-approvals/counts", response_model=MyApprovalCounts)
def get_my_approval_counts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_approvals),
) -> MyApprovalCounts:
    """เติมเลข Badge ทั้ง 4 หมวดที่ Sidebar Submenu (base.html) — เรียกทุกหน้าที่มีเมนูนี้
    โชว์อยู่ ไม่ใช่แค่หน้า My Approvals เอง"""
    return MyApprovalCounts(**budget_workflow.count_my_approvals(db, current_user))


def _to_my_approval_item(
    db: Session, ar: ApprovalRequest, names: dict[int, str], actor: User
) -> MyApprovalItem:
    level_name = None
    if ar.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE:
        level_name = "FA Acknowledge"
    elif ar.current_approval_level is not None and ar.budget_department:
        levels = budget_workflow.get_department_levels(db, ar.budget_department)
        match = next((lv for lv in levels if lv.level_no == ar.current_approval_level), None)
        level_name = match.level_name if match else None

    item = MyApprovalItem.model_validate(ar, from_attributes=True)
    return item.model_copy(
        update={
            "ar_no_display": format_ar_no(ar.ar_no),
            "current_level_name": level_name,
            "requested_by_name": names.get(ar.requested_by_id),
            "actionable": budget_workflow.is_ar_actionable_by(db, ar, actor),
        }
    )


@router.get("/my-approvals", response_model=list[MyApprovalItem])
def list_my_approvals_route(
    bucket: str = Query(..., pattern="^(waiting|mine|history|returned)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_can_view_approvals),
) -> list[MyApprovalItem]:
    ars = budget_workflow.list_my_approvals(db, current_user, bucket)
    page = ars[offset : offset + limit]
    names = resolve_user_names(db, {ar.requested_by_id for ar in page})
    return [_to_my_approval_item(db, ar, names, current_user) for ar in page]


@router.get("/{ar_id}", response_model=ARRead)
def get_ar(
    ar_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> ARRead:
    ar = _get_ar_or_404(db, ar_id)
    return _to_ar_read(db, ar)


@router.patch("/{ar_id}", response_model=ARRead)
def update_ar(
    ar_id: int,
    body: ARUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    """แก้ไข AR — Correction 2026-09-10: พิมพ์/ดาวน์โหลด PDF ไม่ Lock อีกต่อไป (ดู
    get_ar_pdf) เอกสารจึงแก้ได้ตราบใดที่ยังเป็น Draft และไม่ได้ถูก Reject มา (Reject
    แล้วต้องผ่าน Revise เท่านั้น — ดู revise_ar) ถ้ากำลังรอ Level อนุมัติอยู่ตอนแก้
    (budget_approval_status == pending) ถือว่ายกเลิกคำขออนุมัติที่ค้างอยู่โดยอัตโนมัติ
    กัน Level เห็นข้อมูลเก่าที่ถูกแก้ไปแล้วโดยไม่รู้ตัว — ต้องกด "ส่งขออนุมัติ" ใหม่"""
    ar = _get_ar_or_404(db, ar_id)
    if ar.status != ARStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "แก้ไขได้เฉพาะ Approval Request ที่ยังเป็นสถานะ Draft เท่านั้น (Finalized แล้วแก้ไม่ได้)",
        )
    if ar.budget_approval_status == ARBudgetApprovalStatus.REJECTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            'Approval Request นี้ถูกปฏิเสธไปแล้ว แก้ไขตรงๆ ไม่ได้ — กรุณาใช้ปุ่ม "สร้าง Revision" แทน',
        )

    approval_cancelled = ar.budget_approval_status == ARBudgetApprovalStatus.PENDING
    if approval_cancelled:
        budget_workflow.reset_for_new_draft(ar)

    _apply_items(ar, body)
    db.add(AuditLog(ar_id=ar.id, action="ar.updated", actor_id=current_user.id, detail=None))
    if approval_cancelled:
        db.add(
            AuditLog(
                ar_id=ar.id,
                action="ar.approval_cancelled_by_edit",
                actor_id=current_user.id,
                detail={"reason": "แก้ไข AR ระหว่างรอ Level อนุมัติ — ยกเลิกคำขออนุมัติที่ค้างอยู่อัตโนมัติ"},
            )
        )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.post("/{ar_id}/revise", response_model=ARRead, status_code=status.HTTP_201_CREATED)
def revise_ar(
    ar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    """สร้าง AR ใหม่สถานะ Draft คัดลอกข้อมูลจาก AR ต้นฉบับ — Correction 2026-09-10: เดิม
    Gate ด้วย status == Finalized (พิมพ์แล้ว) เปลี่ยนเป็น Gate ด้วย budget_approval_status
    == Rejected แทน (ตาม Business Rule ใหม่: Revise ได้ก็ต่อเมื่อถูก Level ใดก็ได้ Reject
    มาเท่านั้น ไม่เกี่ยวกับว่าพิมพ์/ดาวน์โหลด PDF ไปแล้วหรือยัง — ดู update_ar/get_ar_pdf)"""
    original = _get_ar_or_404(db, ar_id)
    if original.budget_approval_status != ARBudgetApprovalStatus.REJECTED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Revise ได้เฉพาะ Approval Request ที่ถูกปฏิเสธ (Rejected) แล้วเท่านั้น"
        )

    already_superseded = (
        db.query(ApprovalRequest.id).filter(ApprovalRequest.revised_from_id == original.id).first()
    )
    if already_superseded:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Approval Request นี้ถูก Revise ไปแล้ว กรุณา Revise จากฉบับล่าสุดแทน",
        )

    max_revision = (
        db.query(func.max(ApprovalRequest.revision))
        .filter(ApprovalRequest.ar_no == original.ar_no)
        .scalar()
        or 0
    )

    new_ar = ApprovalRequest(
        ar_no=original.ar_no,
        revision=max_revision + 1,
        revised_from_id=original.id,
        status=ARStatus.DRAFT,
        requested_by_id=original.requested_by_id,
        application_date=original.application_date,
        subject=original.subject,
        budget_type=original.budget_type,
        budget_no=original.budget_no,
        budget_sub_category=original.budget_sub_category,
        budget_name=original.budget_name,
        budget_for_year=original.budget_for_year,
        amount_used_before=original.amount_used_before,
        this_application=original.this_application,
        balance=original.balance,
        description=original.description,
        total=original.total,
        vat_amount=original.vat_amount,
        grand_total=original.grand_total,
        suppliers=original.suppliers,
        term_of_payment=original.term_of_payment,
        schedule_start=original.schedule_start,
        schedule_finish=original.schedule_finish,
    )
    new_ar.amount_items = [
        ARAmountItem(item_no=item.item_no, label=item.label, amount=item.amount)
        for item in original.amount_items
    ]
    # Budget Control (2026-09-09): คืนยอดงบทันทีถ้าต้นฉบับเคย Approved แล้ว (หักยอดไป
    # แล้วจริง) + Reset Field Budget Control ทั้งหมดของฉบับ Draft ใหม่ให้เริ่มนับ Level
    # 1 ใหม่ทั้งหมดตอน Finalize ครั้งถัดไป (ไม่ข้าม Level ที่เคยผ่านมาก่อน Revise)
    budget_workflow.refund_on_revise(db, original)
    budget_workflow.reset_for_new_draft(new_ar)

    db.add(new_ar)
    db.flush()  # ให้ new_ar.id พร้อมใช้ก่อน Commit

    db.add(
        AuditLog(
            ar_id=new_ar.id,
            action="ar.revised",
            actor_id=current_user.id,
            detail={
                "revised_from_id": original.id,
                "ar_no": new_ar.ar_no,
                "revision": new_ar.revision,
            },
        )
    )
    db.add(
        AuditLog(
            ar_id=original.id,
            action="ar.revision_created",
            actor_id=current_user.id,
            detail={"new_ar_id": new_ar.id, "revision": new_ar.revision},
        )
    )
    db.commit()
    db.refresh(new_ar)
    return _to_ar_read(db, new_ar)


@router.post("/{ar_id}/submit-for-approval", response_model=ARRead)
def submit_ar_for_approval(
    ar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    """Correction 2026-09-10: จุดเริ่ม Workflow อนุมัติหักงบ — เดิมผูกกับการพิมพ์/
    ดาวน์โหลด PDF ครั้งแรก (ดู get_ar_pdf เดิม) ผู้ใช้แจ้งว่าพิมพ์/ดาวน์โหลดต้องไม่มีผล
    ข้างเคียงอีกต่อไป (พิมพ์ดูกี่ครั้งก็ได้ตราบใดที่ยังไม่ Finalized) จึงแยก Endpoint
    ใหม่นี้ออกมาเป็นจุดเริ่ม Workflow แทน — AR ยังเป็น Draft แก้ไขได้อยู่หลังกดปุ่มนี้
    (ดู update_ar สำหรับ Logic ยกเลิกคำขออนุมัติอัตโนมัติถ้าแก้ระหว่างรออยู่) จะ
    Finalized (ล็อกแก้ไข) ก็ต่อเมื่อ Level แรกอนุมัติผ่านจริง (ดู budget_workflow.
    approve_level) — ยกเว้นแผนกยังไม่ได้ตั้ง Level อนุมัติเลยสักคน (ข้ามตรงไป FA
    Acknowledge ทันที) กรณีนี้ไม่มี Level ให้รอจึง Finalized ทันทีตอนกดปุ่มนี้เลย"""
    ar = _get_ar_or_404(db, ar_id)
    if ar.status != ARStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval Request นี้ Finalized ไปแล้ว")
    if ar.budget_approval_status != ARBudgetApprovalStatus.NOT_SUBMITTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Approval Request นี้ถูกส่งขออนุมัติไปแล้ว")

    requester = db.get(User, ar.requested_by_id)
    budget_workflow.start_budget_workflow(db, ar, requester)

    detail = {"trigger": "submit_for_approval"}
    if ar.budget_approval_status == ARBudgetApprovalStatus.PENDING_FA_ACKNOWLEDGE:
        # แผนกนี้ไม่มี Level อนุมัติเลย (ข้ามตรงไป FA Acknowledge) — ไม่มี Level 1 ให้รอ
        # จึง Finalize ทันที (ดู Docstring บนสุดของฟังก์ชันนี้)
        ar.status = ARStatus.FINALIZED
        detail["auto_finalized"] = "no_levels_configured"

    db.add(
        AuditLog(
            ar_id=ar.id, action="ar.submitted_for_approval", actor_id=current_user.id, detail=detail
        )
    )
    if ar.status == ARStatus.FINALIZED:
        # Log แยก "ar.finalized" ไว้ให้เห็นชัดในประวัติเหมือน Path ที่ Finalize ผ่านการ
        # อนุมัติ Level (ดู approve_ar_level) — Consistency ของ Audit Trail ทั้ง 2 ทาง
        db.add(
            AuditLog(
                ar_id=ar.id,
                action="ar.finalized",
                actor_id=current_user.id,
                detail={"trigger": "submit_for_approval", "reason": "no_levels_configured"},
            )
        )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.get("/{ar_id}/pdf")
def get_ar_pdf(
    ar_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Response:
    """Correction 2026-09-10: พิมพ์/ดาวน์โหลด PDF ไม่มีผลข้างเคียงต่อ AR อีกต่อไป (เดิม
    Finalize + เริ่ม Workflow ให้อัตโนมัติตอนพิมพ์ครั้งแรก — ย้ายไป submit_ar_for_approval
    แทนแล้ว) พิมพ์ดูกี่ครั้งก็ได้ไม่ว่าจะสถานะไหน"""
    ar = _get_ar_or_404(db, ar_id)
    pdf_bytes = render_ar_pdf(db, ar)

    rev_suffix = f"-Rev{ar.revision}" if ar.revision else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{format_ar_no(ar.ar_no)}{rev_suffix}.pdf"'
        },
    )


@router.get("/{ar_id}/approval-progress", response_model=list[ARApprovalProgressStep])
def get_ar_approval_progress(
    ar_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[ARApprovalProgressStep]:
    ar = _get_ar_or_404(db, ar_id)
    steps = budget_workflow.build_approval_progress(db, ar)
    return [ARApprovalProgressStep(**s) for s in steps]


@router.post("/{ar_id}/approve-level", response_model=ARRead)
def approve_ar_level(
    ar_id: int,
    body: BudgetApproveLevelBody = BudgetApproveLevelBody(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    ar = _get_ar_or_404(db, ar_id)
    level_before = ar.current_approval_level
    was_draft = ar.status == ARStatus.DRAFT
    budget_workflow.approve_level(db, ar, current_user, comment=body.comment)
    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.budget_level_approved",
            actor_id=current_user.id,
            detail={"level_no": level_before, "comment": body.comment},
        )
    )
    if was_draft and ar.status == ARStatus.FINALIZED:
        # Correction 2026-09-10: Level แรกอนุมัติผ่าน = จุด Finalize (ดู
        # budget_workflow.approve_level) — Log แยกไว้ให้เห็นชัดในประวัติเหมือนเดิม
        db.add(
            AuditLog(
                ar_id=ar.id,
                action="ar.finalized",
                actor_id=current_user.id,
                detail={"trigger": "level_approved", "level_no": level_before},
            )
        )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.post("/{ar_id}/reject-level", response_model=ARRead)
def reject_ar_level(
    ar_id: int,
    body: BudgetRejectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    ar = _get_ar_or_404(db, ar_id)
    level_before = ar.current_approval_level
    budget_workflow.reject_level(db, ar, current_user, body.reason)
    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.budget_level_rejected",
            actor_id=current_user.id,
            detail={"level_no": level_before, "reason": body.reason},
        )
    )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.post("/{ar_id}/fa-acknowledge", response_model=ARRead)
def fa_acknowledge_ar(
    ar_id: int,
    body: BudgetFaAcknowledgeBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    ar = _get_ar_or_404(db, ar_id)
    budget_workflow.fa_acknowledge(db, ar, current_user, force=body.force, comment=body.comment)
    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.budget_fa_acknowledged",
            actor_id=current_user.id,
            detail={
                "deducted_amount": str(ar.budget_deducted_amount)
                if ar.budget_deducted_amount
                else None,
                "overridden": ar.budget_overridden,
                "comment": body.comment,
            },
        )
    )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.post("/{ar_id}/reject-fa", response_model=ARRead)
def reject_ar_fa(
    ar_id: int,
    body: BudgetRejectBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    ar = _get_ar_or_404(db, ar_id)
    budget_workflow.reject_fa(db, ar, current_user, body.reason)
    db.add(
        AuditLog(
            ar_id=ar.id,
            action="ar.budget_fa_rejected",
            actor_id=current_user.id,
            detail={"reason": body.reason},
        )
    )
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.get("/{ar_id}/history", response_model=list[AuditLogRead])
def get_ar_history(
    ar_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[AuditLogRead]:
    _get_ar_or_404(db, ar_id)  # 404 ถ้าไม่มี AR นี้จริง
    logs = (
        db.query(AuditLog).filter(AuditLog.ar_id == ar_id).order_by(AuditLog.timestamp.asc()).all()
    )
    names = resolve_user_names(db, {log.actor_id for log in logs if log.actor_id})
    return [
        AuditLogRead.model_validate(log, from_attributes=True).model_copy(
            update={"actor_name": names.get(log.actor_id) if log.actor_id else None}
        )
        for log in logs
    ]
