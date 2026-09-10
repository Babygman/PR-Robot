"""Schema สำหรับหน้า "Log" รวม (Full RBAC, 2026-09-10) — ดึงจากตาราง audit_log เดียวที่ใช้
ร่วมกันระหว่าง PR และ AR อยู่แล้ว (ดู app/models/audit_log.py) ไม่ต้อง Migrate Schema เพิ่ม
เพิ่ม Field แสดงผลที่ไม่ได้อยู่ใน AuditLog ตรงๆ (doc_type/doc_no_display/doc_subject/
actor_name) ให้ Route ประกอบให้จาก PurchasingRequisition/ApprovalRequest ที่เกี่ยวข้อง"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuditLogListItem(BaseModel):
    id: int
    doc_type: str  # "pr" | "ar"
    doc_id: int | None
    doc_no_display: str | None
    doc_subject: str | None
    action: str
    actor_id: int | None
    actor_name: str | None = None
    timestamp: datetime
    detail: dict | None

    model_config = {"from_attributes": True}
