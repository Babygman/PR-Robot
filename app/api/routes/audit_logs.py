"""Log รวมกิจกรรม PR+AR ทั้งหมด (Full RBAC, 2026-09-10) — ผู้ใช้ขอเพิ่มเมนู "Log" ให้
Admin/FA/can_view_all ดูกิจกรรมทั้งหมดในระบบย้อนหลังได้ ดึงจากตาราง audit_log เดียวที่มี
อยู่แล้ว (ใช้ร่วมกับ /prs/{id}/history และ /ars/{id}/history) ไม่ต้อง Migrate Schema เพิ่ม

Filter ที่รองรับ: q (ค้นหาใน Action), doc_type (pr/ar), date_from/date_to, actor_id —
เรียงจากล่าสุดไปเก่าสุดเสมอ ดู Docstring app/core/deps.py:require_can_view_log สำหรับ Gate
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_can_view_log
from app.db.session import get_db
from app.models import ApprovalRequest, AuditLog, PurchasingRequisition, User
from app.schemas.audit_log import AuditLogListItem
from app.services.ar_numbering import format_ar_no
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("", response_model=list[AuditLogListItem])
def list_audit_logs(
    q: str | None = Query(default=None, description="ค้นหาใน Action"),
    doc_type: str | None = Query(default=None, pattern="^(pr|ar)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_can_view_log),
) -> list[AuditLogListItem]:
    query = db.query(AuditLog)
    if doc_type == "pr":
        query = query.filter(AuditLog.pr_id.isnot(None))
    elif doc_type == "ar":
        query = query.filter(AuditLog.ar_id.isnot(None))
    if q:
        query = query.filter(AuditLog.action.ilike(f"%{q}%"))
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if date_from is not None:
        query = query.filter(AuditLog.timestamp >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.filter(AuditLog.timestamp <= datetime.combine(date_to, datetime.max.time()))

    logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()

    pr_ids = {log.pr_id for log in logs if log.pr_id}
    ar_ids = {log.ar_id for log in logs if log.ar_id}
    prs = (
        {
            pr.id: pr
            for pr in db.query(PurchasingRequisition).filter(PurchasingRequisition.id.in_(pr_ids))
        }
        if pr_ids
        else {}
    )
    ars = (
        {ar.id: ar for ar in db.query(ApprovalRequest).filter(ApprovalRequest.id.in_(ar_ids))}
        if ar_ids
        else {}
    )
    names = resolve_user_names(db, {log.actor_id for log in logs if log.actor_id})

    result = []
    for log in logs:
        if log.pr_id and log.pr_id in prs:
            pr = prs[log.pr_id]
            doc_type_val = "pr"
            doc_no_display = f"PR-{pr.pr_no}" + (f" Rev.{pr.revision}" if pr.revision else "")
            doc_subject = pr.remark or f"{pr.section or ''} {pr.division or ''}".strip() or None
        elif log.ar_id and log.ar_id in ars:
            ar = ars[log.ar_id]
            doc_type_val = "ar"
            doc_no_display = format_ar_no(ar.ar_no) + (f" Rev.{ar.revision}" if ar.revision else "")
            doc_subject = ar.subject
        else:
            # เอกสารต้นทางถูกลบไปแล้ว (pr_id/ar_id เป็น NULL จาก ON DELETE SET NULL)
            if log.pr_id is not None:
                doc_type_val = "pr"
            elif log.ar_id is not None:
                doc_type_val = "ar"
            else:
                doc_type_val = "other"
            doc_no_display = None
            doc_subject = None

        result.append(
            AuditLogListItem(
                id=log.id,
                doc_type=doc_type_val,
                doc_id=log.pr_id or log.ar_id,
                doc_no_display=doc_no_display,
                doc_subject=doc_subject,
                action=log.action,
                actor_id=log.actor_id,
                actor_name=names.get(log.actor_id) if log.actor_id else None,
                timestamp=log.timestamp,
                detail=log.detail,
            )
        )
    return result
