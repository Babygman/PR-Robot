"""บันทึก Approval Request (AR) + Generate PDF + ประวัติ/ค้นหา — Pattern เดียวกับ
app/api/routes/purchasing_requisitions.py ทุกประการ (Business Decision 2026-09-08)

Requested by = ผู้ใช้ที่ Login ตอนสร้าง AR เสมอ ไม่มี Workflow อนุมัติในระบบเลย
(ลายเซ็นสดบนกระดาษล้วนๆ ทั้ง 5 ช่อง: President/Director, General Manager, Senior
Manager, Manager, F&A) ไม่มี AI Autofill (ผู้ใช้กรอกเองทุกช่องตามที่อนุมัติ Design)

Flow:
1. POST /ars -> สร้าง AR ใหม่ (Status = draft)
2. GET /ars (รองรับค้นหา/กรอง), GET /ars/{id} -> ดูรายการ/รายละเอียด AR
3. PATCH /ars/{id} -> แก้ไขได้เฉพาะตอน Status = draft เท่านั้น
4. POST /ars/{id}/revise -> Revise AR ที่ Finalized แล้ว (คัดลอกข้อมูลเป็นฉบับ Draft ใหม่)
5. GET /ars/{id}/pdf -> Generate PDF ตาม Template จริงของฟอร์ม Approval Request —
   เปลี่ยน Status เป็น finalized อัตโนมัติถ้ายังเป็น draft (ล็อกแก้ไขไม่ได้อีกหลังจากนี้)
6. GET /ars/{id}/history -> ประวัติการกระทำทั้งหมดของ AR นี้จาก audit_log
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import ApprovalRequest, ARAmountItem, ARStatus, AuditLog, User
from app.schemas.approval_request import (
    ARCreate,
    ARListItem,
    ARRead,
    ARUpdate,
)
from app.schemas.purchasing_requisition import AuditLogRead
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
    ar = _get_ar_or_404(db, ar_id)
    if ar.status != ARStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "แก้ไขได้เฉพาะ Approval Request ที่ยังเป็นสถานะ Draft เท่านั้น (Finalized แล้วแก้ไม่ได้)",
        )

    _apply_items(ar, body)
    db.add(AuditLog(ar_id=ar.id, action="ar.updated", actor_id=current_user.id, detail=None))
    db.commit()
    db.refresh(ar)
    return _to_ar_read(db, ar)


@router.post("/{ar_id}/revise", response_model=ARRead, status_code=status.HTTP_201_CREATED)
def revise_ar(
    ar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ARRead:
    """สร้าง AR ใหม่สถานะ Draft คัดลอกข้อมูลจาก AR ต้นฉบับที่ Finalized แล้ว — Pattern
    เดียวกับ revise_pr ใน purchasing_requisitions.py ทุกประการ"""
    original = _get_ar_or_404(db, ar_id)
    if original.status != ARStatus.FINALIZED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Revise ได้เฉพาะ Approval Request ที่ Finalized แล้วเท่านั้น"
        )

    already_superseded = (
        db.query(ApprovalRequest.id)
        .filter(ApprovalRequest.revised_from_id == original.id)
        .first()
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


@router.get("/{ar_id}/pdf")
def get_ar_pdf(
    ar_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    ar = _get_ar_or_404(db, ar_id)
    pdf_bytes = render_ar_pdf(db, ar)

    # เหมือน PR: กดพิมพ์/ดาวน์โหลด PDF ครั้งแรกคือจุดที่ล็อก AR ไม่ให้แก้ไขได้อีก —
    # Generate สำเร็จก่อนค่อย Finalize เพื่อไม่ให้ AR ถูกล็อกถ้า Render PDF พังกลางทาง
    if ar.status == ARStatus.DRAFT:
        ar.status = ARStatus.FINALIZED
        db.add(
            AuditLog(
                ar_id=ar.id,
                action="ar.finalized",
                actor_id=current_user.id,
                detail={"trigger": "pdf_download"},
            )
        )
        db.commit()

    rev_suffix = f"-Rev{ar.revision}" if ar.revision else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{format_ar_no(ar.ar_no)}{rev_suffix}.pdf"'
        },
    )


@router.get("/{ar_id}/history", response_model=list[AuditLogRead])
def get_ar_history(
    ar_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[AuditLogRead]:
    _get_ar_or_404(db, ar_id)  # 404 ถ้าไม่มี AR นี้จริง
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.ar_id == ar_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )
    names = resolve_user_names(db, {log.actor_id for log in logs if log.actor_id})
    return [
        AuditLogRead.model_validate(log, from_attributes=True).model_copy(
            update={"actor_name": names.get(log.actor_id) if log.actor_id else None}
        )
        for log in logs
    ]
