"""Purchasing Requisition — เฉพาะฟิลด์หน้า 1/3 ของฟอร์ม Sunstar FM-PU-02
(หน้า 2-3 ไม่มี ใช้หน้า 1 ไปก่อนตาม Business Decision 2026-09-01 — อาจ Redesign ทีหลัง)

Scope Revision (Phase 9, 2026-09-03): ตัด Workflow อนุมัติในระบบออกทั้งหมดตาม
Feedback จริงจาก Product Owner (Design เดิมผิดตั้งแต่แรก — Reviewed/Approved/
Received by เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกไปใช้งานนอกระบบ ไม่มีการอนุมัติ
ในระบบเลย) เหลือ Requested by (ผู้สร้าง PR) อย่างเดียวที่ Track ในระบบจริง —
ดูตัวอย่าง PR จริงที่ Product Owner ส่งมาใน docs/00_KICKOFF_AND_DESIGN.md

pr_no = Running Number ต่อเนื่องตลอด ไม่รีเซ็ตรายปี/แผนก (Business Decision 2026-09-01)
วิธี Generate เลขถัดไปเป็นเรื่อง Business Logic ของ Phase 4-5 ไม่ใช่ระดับ Schema
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PRStatus(str, enum.Enum):
    """Scope Revision (Phase 9, 2026-09-03): เหลือ 2 สถานะง่ายๆ ตัด Workflow ทิ้ง —
    DRAFT = แก้ไขได้ปกติ, FINALIZED = ล็อกแก้ไขไม่ได้แล้ว (Trigger อัตโนมัติตอนกด
    พิมพ์/ดาวน์โหลด PDF ครั้งแรก ดู GET /prs/{id}/pdf)"""

    DRAFT = "draft"
    FINALIZED = "finalized"


class PurchasingRequisition(Base):
    __tablename__ = "purchasing_requisitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_no: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)

    section: Mapped[str] = mapped_column(String(255), nullable=False)
    division: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[PRStatus] = mapped_column(
        # values_callable: บังคับให้เก็บ .value ("draft") ลง DB ไม่ใช่ .name ("DRAFT")
        # ที่เป็น Default ของ SQLAlchemy — ต้องตรงกับค่าที่ Alembic Migration
        # (cdfbb940153e_pr_core_schema.py) สร้าง Native Enum Type ไว้จริงบน PostgreSQL
        # (พบ Mismatch นี้ระหว่าง Deploy UAT ครั้งแรก 2026-09-02 — pytest Suite ใช้
        # Base.metadata.create_all() สร้าง Schema จาก Model ตรงๆ ไม่ผ่าน Alembic เลย
        # ไม่เคยเจอ Mismatch ระหว่างสองฝั่งนี้มาก่อน — ยืนยันแก้ถูกจริงด้วย Insert/Update
        # จริงผ่าน PostgreSQL 16)
        SAEnum(
            PRStatus,
            name="pr_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=PRStatus.DRAFT,
        nullable=False,
    )

    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    remark: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list[PRItem]] = relationship(
        back_populates="requisition", cascade="all, delete-orphan"
    )
    budget_control: Mapped[PRBudgetControl | None] = relationship(
        back_populates="requisition", cascade="all, delete-orphan", uselist=False
    )


class PRItem(Base):
    __tablename__ = "pr_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"), nullable=False
    )
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    account_code: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(50))
    required_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    ref_po: Mapped[str | None] = mapped_column(String(100))

    requisition: Mapped[PurchasingRequisition] = relationship(back_populates="items")


class PRBudgetControl(Base):
    __tablename__ = "pr_budget_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    account_code_1: Mapped[str | None] = mapped_column(String(100))
    account_code_2: Mapped[str | None] = mapped_column(String(100))
    budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    used_before_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    this_application: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    requisition: Mapped[PurchasingRequisition] = relationship(back_populates="budget_control")
