"""บันทึก PR + Generate PDF ตาม Template จริง (Phase 5)

Requested by = ผู้ใช้ที่ Login ตอนสร้าง PR เสมอ (Business Decision 2026-09-01)
Reviewed/Approved/Received by ยังเป็น null จนกว่าจะถึง Workflow อนุมัติ (Phase 6)

Flow:
1. POST /prs -> สร้าง PR ใหม่ (Status = draft) พร้อม Item และ Budget Control จองเลขที่ PR
   (pr_no) แบบต่อเนื่องอัตโนมัติ ผูก source_document_ids (ถ้ามี) เข้ากับ PR นี้
2. GET /prs, GET /prs/{id} -> ดูรายการ/รายละเอียด PR
3. PATCH /prs/{id} -> แก้ไขได้เฉพาะตอน Status = draft เท่านั้น
4. GET /prs/{id}/pdf -> Generate PDF ตาม Template จริงของฟอร์ม FM-PU-02
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.schemas.purchasing_requisition import PRCreate, PRListItem, PRRead, PRUpdate
from app.services.pr_numbering import allocate_pr_no
from app.services.pr_pdf import render_pr_pdf

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


@router.post("", response_model=PRRead, status_code=status.HTTP_201_CREATED)
def create_pr(
    body: PRCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PurchasingRequisition:
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
            detail={"pr_no": pr.pr_no},
        )
    )
    db.commit()
    db.refresh(pr)
    return pr


@router.get("", response_model=list[PRListItem])
def list_prs(
    status_filter: PRStatus | None = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[PurchasingRequisition]:
    query = db.query(PurchasingRequisition)
    if status_filter is not None:
        query = query.filter(PurchasingRequisition.status == status_filter)
    return query.order_by(PurchasingRequisition.pr_no.desc()).all()


@router.get("/{pr_id}", response_model=PRRead)
def get_pr(
    pr_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> PurchasingRequisition:
    return _get_pr_or_404(db, pr_id)


@router.patch("/{pr_id}", response_model=PRRead)
def update_pr(
    pr_id: int,
    body: PRUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PurchasingRequisition:
    pr = _get_pr_or_404(db, pr_id)
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "แก้ไขได้เฉพาะ PR ที่ยังเป็นสถานะ Draft เท่านั้น"
        )

    _apply_items_and_budget(pr, body)
    db.add(
        AuditLog(pr_id=pr.id, action="pr.updated", actor_id=current_user.id, detail=None)
    )
    db.commit()
    db.refresh(pr)
    return pr


@router.get("/{pr_id}/pdf")
def get_pr_pdf(
    pr_id: int, db: Session = Depends(get_db), _current_user: User = Depends(get_current_user)
) -> Response:
    pr = _get_pr_or_404(db, pr_id)
    pdf_bytes = render_pr_pdf(db, pr)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="PR-{pr.pr_no}.pdf"'},
    )
