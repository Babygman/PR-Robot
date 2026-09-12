"""System Log — Helper เดียวเรียกใช้ทุกจุดที่ต้อง Log (2026-09-12)

Pattern เดียวกับ AuditLog ที่ใช้อยู่แล้วใน purchasing_requisitions.py/approval_requests.py:
db.add(...) เฉยๆ ไม่ Commit เอง — ให้ Caller Commit พร้อมกับ Transaction หลักของตัวเอง
เพื่อให้ Log กับการเปลี่ยนแปลงจริงเป็น Atomic เดียวกัน (ถ้า Commit ล้มเหลว Log ก็ไม่ถูก
บันทึกไปด้วย ไม่เกิด Log ค้างที่ไม่ตรงกับข้อมูลจริง)

เพิ่ม ip_address (2026-09-12, Feedback จริง: Log ต้องบอก "ใคร ทำอะไร ที่ไหน อย่างไร" —
"ที่ไหน" หมายถึง IP ที่กระทำ) — ดึงผ่าน get_client_ip() ด้านล่าง"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import SystemLog


def get_client_ip(request: Request) -> str | None:
    """คืน IP จริงของผู้กระทำ — ระบบนี้รันหลัง Nginx Proxy Manager เสมอ (ดู
    docs/00_KICKOFF_AND_DESIGN.md ข้อ 3.3) ดังนั้น request.client.host จะเป็น IP ของ
    Proxy Container ไม่ใช่ผู้ใช้จริง ต้องอ่านจาก X-Forwarded-For ก่อน (NPM/Nginx ใส่ให้
    อัตโนมัติเสมอ) — ถ้าไม่มี Header นี้เลย (เช่น เรียกตรงไม่ผ่าน Proxy ตอน Dev/Test)
    Fallback ไปใช้ request.client.host ตรงๆ"""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # อาจมีหลายค่าคั่นด้วย , ถ้าผ่านหลาย Proxy ต่อกัน — ตัวแรกสุดคือ Client ตัวจริง
        return forwarded_for.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else None


def stringify_changes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, str]:
    """แปลง Field ที่เปลี่ยนจริง (ค่าก่อน != ค่าหลัง) เป็น "ค่าเดิม -> ค่าใหม่" อ่านง่าย —
    ใช้ str() ตรงๆ กับทุก Type (Decimal/date/bool/None) เพื่อให้เก็บลง JSON Column ได้
    แน่นอนไม่มี Serialize Error (ตอบ "อย่างไร" ใน Log — ไม่ใช่แค่รายชื่อ Field ที่เปลี่ยน)"""
    changes: dict[str, str] = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value == new_value:
            continue
        old_str = "-" if old_value is None else str(old_value)
        new_str = "-" if new_value is None else str(new_value)
        changes[key] = f"{old_str} -> {new_str}"
    return changes


def log_event(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        SystemLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=ip_address,
        )
    )
