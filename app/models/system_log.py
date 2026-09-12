"""System Log (2026-09-12) — บันทึกทุกการเปลี่ยนแปลงในระบบที่ audit_log เดิมไม่ครอบคลุม
(audit_log เดิมมี Schema เฉพาะ PR/AR เท่านั้น ผูกกับ pr_id/ar_id ตรงๆ) ตารางนี้เป็น
Generic Log สำหรับ Entity อื่นทั้งหมด: Login/Logout, User CRUD + Password Reset,
Budget CRUD/Upload, Budget Approval Level CRUD, Term of Payment CRUD และอื่นๆ ที่
เพิ่มในอนาคต — ใช้ entity_type/entity_id แทนคอลัมน์เฉพาะแบบ audit_log เพราะ Entity
มีหลายชนิดไม่คงที่

หน้า "System Log" (Admin เท่านั้น) รวมข้อมูลจากตารางนี้ + audit_log เดิมมาแสดงเป็น
รายการเดียวกัน (ดู app/api/routes/system_log.py) เพื่อให้เห็นภาพรวมทุกการเปลี่ยนแปลง
ในระบบจากจุดเดียว โดยไม่ต้อง Migrate/รื้อ audit_log เดิมที่ Log PR/Log AR ใช้อยู่"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    detail: Mapped[dict | None] = mapped_column(JSON)
    # IP ของผู้กระทำ — เก็บเป็น String รองรับทั้ง IPv4/IPv6 (2026-09-12, ดู
    # app/services/system_log.py::get_client_ip สำหรับวิธีดึงค่าจริงผ่าน Reverse Proxy)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
