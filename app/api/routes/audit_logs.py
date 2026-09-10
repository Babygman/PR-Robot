"""Log กิจกรรม PR / AR (Full RBAC, 2026-09-10; แยกเป็น 2 เมนูอิสระ — Correction 3,
2026-09-10) — เดิมเป็นเมนูเดียวรวม PR+AR ผู้ใช้แจ้งว่าต้องแยกสิทธิ์เห็น Log PR กับ Log AR
ออกจากกันให้ชัดเจนเหมือนเมนู PR/AR เอง (ตาม Matrix ที่ Confirm — ดู Docstring
app/core/deps.py: require_can_view_log_pr/require_can_view_log_ar) จึงแยกเป็น 2 Endpoint:
- GET /audit-logs/pr — เฉพาะกิจกรรม PR เท่านั้น
- GET /audit-logs/ar — เฉพาะกิจกรรม AR เท่านั้น

ดึงจากตาราง audit_log เดียวที่มีอยู่แล้ว (ใช้ร่วมกับ /prs/{id}/history และ
/ars/{id}/history) ไม่ต้อง Migrate Schema เพิ่ม

Filter ที่รองรับ: q (ค้นหาใน Action), date_from/date_to, actor_id — เรียงจากล่าสุดไปเก่า
สุดเสมอ
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.core.deps import require_can_view_log_ar, require_can_view_log_pr
from app.db.session import get_db
from app.models import ApprovalRequest, AuditLog, PurchasingRequisition, User
from app.schemas.audit_log import AuditLogListItem
from app.services.ar_numbering import format_ar_no
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def _query_logs(
    db: Session,
    *,
    doc_type: str,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    actor_id: int | None,
    limit: int,
    offset: int,
) -> list[AuditLog]:
    query: SAQuery = db.query(AuditLog)
    query = (
        query.filter(AuditLog.pr_id.isnot(None))
        if doc_type == "pr"
        else query.filter(AuditLog.ar_id.isnot(None))
    )
    if q:
        query = query.filter(AuditLog.action.ilike(f"%{q}%"))
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if date_from is not None:
        query = query.filter(AuditLog.timestamp >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.filter(AuditLog.timestamp <= datetime.combine(date_to, datetime.max.time()))
    return query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(limit).all()


def _to_list_items(db: Session, logs: list[AuditLog], doc_type: str) -> list[AuditLogListItem]:
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
        if doc_type == "pr" and log.pr_id and log.pr_id in prs:
            pr = prs[log.pr_id]
            doc_no_display = f"PR-{pr.pr_no}" + (f" Rev.{pr.revision}" if pr.revision else "")
            doc_subject = pr.remark or f"{pr.section or ''} {pr.division or ''}".strip() or None
        elif doc_type == "ar" and log.ar_id and log.ar_id in ars:
            ar = ars[log.ar_id]
            doc_no_display = format_ar_no(ar.ar_no) + (f" Rev.{ar.revision}" if ar.revision else "")
            doc_subject = ar.subject
        else:
            # เอกสารต้นทางถูกลบไปแล้ว (pr_id/ar_id เป็น NULL จาก ON DELETE SET NULL)
            doc_no_display = None
            doc_subject = None

        result.append(
            AuditLogListItem(
                id=log.id,
                doc_type=doc_type,
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


@router.get("/pr", response_model=list[AuditLogListItem])
def list_pr_audit_logs(
    q: str | None = Query(default=None, description="ค้นหาใน Action"),
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_can_view_log_pr),
) -> list[AuditLogListItem]:
    logs = _query_logs(
        db,
        doc_type="pr",
        q=q,
        date_from=date_from,
        date_to=date_to,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return _to_list_items(db, logs, "pr")


@router.get("/ar", response_model=list[AuditLogListItem])
def list_ar_audit_logs(
    q: str | None = Query(default=None, description="ค้นหาใน Action"),
    date_from: date | None = None,
    date_to: date | None = None,
    actor_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_can_view_log_ar),
) -> list[AuditLogListItem]:
    logs = _query_logs(
        db,
        doc_type="ar",
        q=q,
        date_from=date_from,
        date_to=date_to,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return _to_list_items(db, logs, "ar")
