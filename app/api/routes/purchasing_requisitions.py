"""บันทึก PR + Generate PDF (Phase 5) + ประวัติ/ค้นหา (Phase 6)

Requested by = ผู้ใช้ที่ Login ตอนสร้าง PR เสมอ (Business Decision 2026-09-01)

Scope Revision (Phase 9, 2026-09-03): ตัด Workflow อนุมัติในระบบออกทั้งหมด (เดิม
draft->reviewed->approved->received) ตาม Feedback จริงจาก Product Owner ว่า Design
เดิมผิดตั้งแต่แรก — ดูตัวอย่าง PR จริงที่ส่งมาใน docs/00_KICKOFF_AND_DESIGN.md แล้ว
พบว่า Reviewed/Approved/Received by เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกไปใช้งานนอกระบบ
ล้วนๆ ไม่มีการอนุมัติในระบบเลย เหลือ 2 สถานะ: draft (แก้ไขได้) / finalized (ล็อกแล้ว)
เปลี่ยนอัตโนมัติตอนกดพิมพ์/ดาวน์โหลด PDF ครั้งแรก ไม่ต้องกดปุ่มแยก

Flow:
1. POST /prs -> สร้าง PR ใหม่ (Status = draft) รับ source_document_ids ได้หลายรายการ
   (AI สกัดจากหลายเอกสารมารวมเป็น Item เดียวกันได้ — Scope Revision Phase 9)
2. GET /prs (รองรับค้นหา/กรอง), GET /prs/{id} -> ดูรายการ/รายละเอียด PR
3. PATCH /prs/{id} -> แก้ไขได้เฉพาะตอน Status = draft เท่านั้น
4. GET /prs/{id}/pdf -> Generate PDF ตาม Template จริงของฟอร์ม FM-PU-02 — เปลี่ยน
   Status เป็น finalized อัตโนมัติถ้ายังเป็น draft (ล็อกแก้ไขไม่ได้อีกหลังจากนี้)
5. GET /prs/{id}/history -> ประวัติการกระทำทั้งหมดของ PR นี้จาก audit_log
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import (
    AuditLog,
    PRBudgetControl,
    PRItem,
    PRStatus,
    PurchasingRequisition,
    SourceDocument,
    User,
)
from app.schemas.purchasing_requisition import (
    AuditLogRead,
    PRCreate,
    PRListItem,
    PRRead,
    PRUpdate,
)
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
        if pr.budget_control is not None:
            # แก้ไขแถวเดิมแทนการสร้างใหม่ทับ — ถ้าสร้าง PRBudgetControl() ใหม่ทับตรงๆ
            # SQLAlchemy จะพยายาม Insert แถวใหม่ก่อน Delete แถวเก่า (Unique Constraint บน
            # pr_id ชนกันเอง) เพราะเป็นความสัมพันธ์แบบ One-to-One (uselist=False)
            pr.budget_control.account_code_1 = body.budget_control.account_code_1
            pr.budget_control.account_code_2 = body.budget_control.account_code_2
            pr.budget_control.budget = body.budget_control.budget
            pr.budget_control.used_before_amount = body.budget_control.used_before_amount
            pr.budget_control.this_application = body.budget_control.this_application
            pr.budget_control.balance = body.budget_control.balance
        else:
            pr.budget_control = PRBudgetControl(
                account_code_1=body.budget_control.account_code_1,
                account_code_2=body.budget_control.account_code_2,
                budget=body.budget_control.budget,
                used_before_amount=body.budget_control.used_before_amount,
                this_application=body.budget_control.this_application,
                balance=body.budget_control.balance,
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
    current_user: User = Depends(get_current_user),
) -> PRRead:
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
    current_user: User = Depends(get_current_user),
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

    return (
        query.order_by(
            PurchasingRequisition.pr_no.desc(), PurchasingRequisition.revision.desc()
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/{pr_id}", response_model=PRRead)
def get_pr(
    pr_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> PRRead:
    pr = _get_pr_or_404(db, pr_id)
    return _to_pr_read(db, pr)


@router.patch("/{pr_id}", response_model=PRRead)
def update_pr(
    pr_id: int,
    body: PRUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRRead:
    pr = _get_pr_or_404(db, pr_id)
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "แก้ไขได้เฉพาะ PR ที่ยังเป็นสถานะ Draft เท่านั้น (Finalized แล้วแก้ไม่ได้)"
        )

    _apply_items_and_budget(pr, body)
    db.add(AuditLog(pr_id=pr.id, action="pr.updated", actor_id=current_user.id, detail=None))
    db.commit()
    db.refresh(pr)
    return _to_pr_read(db, pr)


@router.post("/{pr_id}/revise", response_model=PRRead, status_code=status.HTTP_201_CREATED)
def revise_pr(
    pr_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PRRead:
    """สร้าง PR ใหม่สถานะ Draft คัดลอกข้อมูลจาก PR ต้นฉบับที่ Finalized แล้ว เพื่อแก้ไข
    ต่อโดยไม่ไปรื้อของเดิมที่พิมพ์/เซ็นกระดาษไปแล้ว (Feedback จริงจากผู้ใช้ 2026-09-03)

    เลข PR ใช้เลขเดิม + Rev ต่อท้าย (revision +1 จากฉบับล่าสุดของ pr_no นี้ — เผื่อกรณี
    Revise ซ้ำหลายรอบ) — requested_by คงเป็นคนเดิม (เป็น PR เดียวกันที่แก้ไข ไม่ใช่คำขอ
    ใหม่) ส่วนคนที่กด Revise จริงบันทึกแยกไว้ใน Audit Log (actor_id)
    """
    original = _get_pr_or_404(db, pr_id)
    if original.status != PRStatus.FINALIZED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Revise ได้เฉพาะ PR ที่ Finalized แล้วเท่านั้น"
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
    if original.budget_control is not None:
        bc = original.budget_control
        new_pr.budget_control = PRBudgetControl(
            account_code_1=bc.account_code_1,
            account_code_2=bc.account_code_2,
            budget=bc.budget,
            used_before_amount=bc.used_before_amount,
            this_application=bc.this_application,
            balance=bc.balance,
        )

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
    current_user: User = Depends(get_current_user),
) -> Response:
    pr = _get_pr_or_404(db, pr_id)
    pdf_bytes = render_pr_pdf(db, pr)

    # Scope Revision (Phase 9, 2026-09-03): กดพิมพ์/ดาวน์โหลด PDF ครั้งแรกคือจุดที่
    # ล็อก PR ไม่ให้แก้ไขได้อีก (แทน Workflow Review/Approve/Receive เดิม) — Generate
    # สำเร็จก่อนค่อย Finalize เพื่อไม่ให้ PR ถูกล็อกถ้า Render PDF พังกลางทาง
    if pr.status == PRStatus.DRAFT:
        pr.status = PRStatus.FINALIZED
        db.add(
            AuditLog(
                pr_id=pr.id,
                action="pr.finalized",
                actor_id=current_user.id,
                detail={"trigger": "pdf_download"},
            )
        )
        db.commit()

    rev_suffix = f"-Rev{pr.revision}" if pr.revision else ""
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="PR-{pr.pr_no}{rev_suffix}.pdf"'},
    )


@router.get("/{pr_id}/history", response_model=list[AuditLogRead])
def get_pr_history(
    pr_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> list[AuditLogRead]:
    _get_pr_or_404(db, pr_id)  # 404 ถ้าไม่มี PR นี้จริง
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.pr_id == pr_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )
    names = resolve_user_names(db, {log.actor_id for log in logs})
    return [
        AuditLogRead.model_validate(log, from_attributes=True).model_copy(
            update={"actor_name": names.get(log.actor_id) if log.actor_id else None}
        )
        for log in logs
    ]
