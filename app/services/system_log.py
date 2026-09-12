"""System Log — Helper เดียวเรียกใช้ทุกจุดที่ต้อง Log (2026-09-12)

Pattern เดียวกับ AuditLog ที่ใช้อยู่แล้วใน purchasing_requisitions.py/approval_requests.py:
db.add(...) เฉยๆ ไม่ Commit เอง — ให้ Caller Commit พร้อมกับ Transaction หลักของตัวเอง
เพื่อให้ Log กับการเปลี่ยนแปลงจริงเป็น Atomic เดียวกัน (ถ้า Commit ล้มเหลว Log ก็ไม่ถูก
บันทึกไปด้วย ไม่เกิด Log ค้างที่ไม่ตรงกับข้อมูลจริง)"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import SystemLog


def log_event(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        SystemLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
        )
    )
