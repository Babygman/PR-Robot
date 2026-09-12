"""Schema สำหรับหน้า "System Log" (2026-09-12) — รวมข้อมูลจาก 2 ตาราง: system_logs
(Generic — Login/Logout, User/Budget/Budget Level/Term of Payment CRUD) และ audit_log
เดิม (Specific — PR/AR) มาแสดงเป็นรายการเดียวกัน ดู app/api/routes/system_log.py
สำหรับ Logic การรวม/เรียงลำดับ"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SystemLogListItem(BaseModel):
    id: str  # Prefix ด้วย "sys-"/"audit-" กัน ID ชนกันระหว่าง 2 ตารางต้นทาง
    source: str  # "system" | "audit"
    action: str
    entity_type: str | None
    entity_id: int | None
    entity_label: str | None = None  # เช่น "PR-0012 Rev.1" หรือ "somchai@example.com"
    actor_id: int | None
    actor_name: str | None = None
    detail: dict | None
    ip_address: str | None = None  # audit_log (Legacy PR/AR) ไม่มีคอลัมน์นี้ จะเป็น None เสมอ
    created_at: datetime

    model_config = {"from_attributes": True}
