"""System Log — หน้ารวมทุกการเปลี่ยนแปลงในระบบ (2026-09-12, Admin เท่านั้น)

รวมข้อมูลจาก 2 ตาราง แสดงเป็นรายการเดียวกัน เรียงจากล่าสุดไปเก่าสุด:
1. system_logs (ใหม่) — Login/Logout, User/Budget/Budget Level/Term of Payment CRUD
   และอื่นๆ ที่เพิ่มเข้ามาในอนาคต (ดู app/services/system_log.py)
2. audit_log (เดิม) — เฉพาะ PR/AR (Schema เดิมมี pr_id/ar_id ตรงๆ ไม่ใช่ entity_type
   Generic เหมือนตารางใหม่ — คงไว้เหมือนเดิมไม่ Migrate เพราะ Log PR/Log AR ยังใช้อยู่)

Filter ที่รองรับ: q (ค้นหาใน Action), entity_type, actor_id, date_from/date_to —
Merge แล้ว Sort/Paginate ฝั่ง Python เพราะเป็นคนละตารางกัน (Volume ของระบบภายในนี้
ไม่ได้ใหญ่มาก ยอมรับแนวทางนี้ได้ ไม่ต้องทำ UNION query ข้าม Dialect ให้ซับซ้อน)"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models import ApprovalRequest, AuditLog, PurchasingRequisition, SystemLog, User
from app.schemas.system_log import SystemLogListItem
from app.services.ar_numbering import format_ar_no
from app.services.user_lookup import resolve_user_names

router = APIRouter(prefix="/system-log", tags=["system-log"])

_FETCH_MULTIPLIER = 3  # ดึงมาเกิน offset+limit ไว้ก่อน Merge กันกรณีฝั่งใดฝั่งหนึ่งมีรายการ
# เยอะกว่าอีกฝั่งมากในช่วงเวลาเดียวกัน (ยอมรับ Trade-off นี้แทนการทำ UNION Query จริง)


def _entity_label_for_system_log(entry: SystemLog) -> str | None:
    detail = entry.detail or {}
    if entry.entity_type == "user":
        return detail.get("email") or detail.get("name")
    if entry.entity_type == "budget":
        return detail.get("budget_no") or detail.get("filename")
    if entry.entity_type == "budget_level":
        dept = detail.get("department")
        level_no = detail.get("level_no")
        return f"{dept} — Level {level_no}" if dept and level_no is not None else dept
    if entry.entity_type == "term_of_payment":
        return detail.get("name")
    return None


def _query_system_rows(
    db: Session,
    *,
    q: str | None,
    entity_type: str | None,
    actor_id: int | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[SystemLog]:
    query = db.query(SystemLog)
    if entity_type is not None and entity_type not in ("pr", "ar"):
        query = query.filter(SystemLog.entity_type == entity_type)
    elif entity_type in ("pr", "ar"):
        # PR/AR อยู่ในตาราง audit_log เท่านั้น ไม่มีทางอยู่ใน system_logs เลย
        return []
    if q:
        query = query.filter(SystemLog.action.ilike(f"%{q}%"))
    if actor_id is not None:
        query = query.filter(SystemLog.actor_id == actor_id)
    if date_from is not None:
        dt_from = datetime.combine(date_from, datetime.min.time())
        query = query.filter(SystemLog.created_at >= dt_from)
    if date_to is not None:
        dt_to = datetime.combine(date_to, datetime.max.time())
        query = query.filter(SystemLog.created_at <= dt_to)
    return query.order_by(SystemLog.created_at.desc()).limit(limit).all()


def _query_audit_rows(
    db: Session,
    *,
    q: str | None,
    entity_type: str | None,
    actor_id: int | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
) -> list[AuditLog]:
    if entity_type is not None and entity_type not in ("pr", "ar"):
        return []
    query = db.query(AuditLog)
    if entity_type == "pr":
        query = query.filter(AuditLog.pr_id.isnot(None))
    elif entity_type == "ar":
        query = query.filter(AuditLog.ar_id.isnot(None))
    if q:
        query = query.filter(AuditLog.action.ilike(f"%{q}%"))
    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if date_from is not None:
        query = query.filter(AuditLog.timestamp >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        query = query.filter(AuditLog.timestamp <= datetime.combine(date_to, datetime.max.time()))
    return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()


@router.get("", response_model=list[SystemLogListItem])
def list_system_logs(
    q: str | None = Query(default=None, description="ค้นหาใน Action"),
    entity_type: str | None = Query(
        default=None,
        description="user | budget | budget_level | term_of_payment | pr | ar",
    ),
    actor_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[SystemLogListItem]:
    fetch_n = (offset + limit) * _FETCH_MULTIPLIER

    system_rows = _query_system_rows(
        db, q=q, entity_type=entity_type, actor_id=actor_id, date_from=date_from, date_to=date_to,
        limit=fetch_n,
    )
    audit_rows = _query_audit_rows(
        db, q=q, entity_type=entity_type, actor_id=actor_id, date_from=date_from, date_to=date_to,
        limit=fetch_n,
    )

    pr_ids = {r.pr_id for r in audit_rows if r.pr_id}
    ar_ids = {r.ar_id for r in audit_rows if r.ar_id}
    pr_query = db.query(PurchasingRequisition).filter(PurchasingRequisition.id.in_(pr_ids))
    prs = {pr.id: pr for pr in pr_query} if pr_ids else {}
    ars = (
        {ar.id: ar for ar in db.query(ApprovalRequest).filter(ApprovalRequest.id.in_(ar_ids))}
        if ar_ids
        else {}
    )
    all_actor_ids = {r.actor_id for r in system_rows if r.actor_id} | {
        r.actor_id for r in audit_rows if r.actor_id
    }
    names = resolve_user_names(db, all_actor_ids)

    merged: list[SystemLogListItem] = []
    for r in system_rows:
        merged.append(
            SystemLogListItem(
                id=f"sys-{r.id}",
                source="system",
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                entity_label=_entity_label_for_system_log(r),
                actor_id=r.actor_id,
                actor_name=names.get(r.actor_id) if r.actor_id else None,
                detail=r.detail,
                ip_address=r.ip_address,
                created_at=r.created_at,
            )
        )
    for r in audit_rows:
        if r.pr_id and r.pr_id in prs:
            pr = prs[r.pr_id]
            label = f"PR-{pr.pr_no}" + (f" Rev.{pr.revision}" if pr.revision else "")
            etype, eid = "pr", r.pr_id
        elif r.ar_id and r.ar_id in ars:
            ar = ars[r.ar_id]
            label = format_ar_no(ar.ar_no) + (f" Rev.{ar.revision}" if ar.revision else "")
            etype, eid = "ar", r.ar_id
        else:
            label = None
            etype = "pr" if r.pr_id else ("ar" if r.ar_id else None)
            eid = r.pr_id or r.ar_id
        merged.append(
            SystemLogListItem(
                id=f"audit-{r.id}",
                source="audit",
                action=r.action,
                entity_type=etype,
                entity_id=eid,
                entity_label=label,
                actor_id=r.actor_id,
                actor_name=names.get(r.actor_id) if r.actor_id else None,
                detail=r.detail,
                created_at=r.timestamp,
            )
        )

    merged.sort(key=lambda item: item.created_at, reverse=True)
    return merged[offset : offset + limit]
