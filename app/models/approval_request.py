"""Approval Request (AR) — ฟอร์ม "APPROVAL REQUEST" ของ Sunstar Chemical Thailand
(Template Version "20220404_rev.2") — โมดูลใหม่ใน PR-Robot เดิม (Business Decision
2026-09-08 ตามที่ผู้ใช้อนุมัติ Design ไว้)

หน้าที่ของระบบคือ "ให้ User Key ข้อมูลทุกอย่างที่จำเป็นในแต่ละช่องเพื่อปริ้น เอาไป
ใช้งานการเซ็นภายนอก" ล้วนๆ — ไม่มี Workflow อนุมัติในระบบ, ไม่มี AI Autofill,
ไม่มีการคำนวณอัตโนมัติ (Total/VAT/Grand Total/Balance ผู้ใช้กรอกเองทุกช่อง — ผู้ใช้
เลือก Trade-off นี้เองตอนอนุมัติ Design แม้จะเสี่ยงคำนวณผิดโดยไม่มี Safeguard ในระบบ
ก็ตาม) — ช่องลายเซ็น 5 ช่อง (President/Director, General Manager, Senior Manager,
Manager, F&A) ว่างเสมอในระบบ เซ็น/กรอกสดบนกระดาษหลังพิมพ์ทั้งหมด (รวมถึง F&A ที่ใน
ตัวอย่างจริงมีชื่อคนพิมพ์ไว้ล่วงหน้า แต่ผู้ใช้ยืนยันให้ปฏิบัติเหมือนช่องเซ็นสดอื่นๆ)

Pattern เดียวกับ PurchasingRequisition (purchasing_requisition.py) ทุกประการ:
สถานะ 2 ค่า (draft/finalized, ล็อกอัตโนมัติตอนพิมพ์/ดาวน์โหลด PDF ครั้งแรก) และ
revision/revised_from_id (Revise ได้เฉพาะฉบับ Finalized สร้างฉบับ Draft ใหม่คัดลอก
ข้อมูลมาแก้ไขต่อ ไม่แตะต้นฉบับเดิม)

ตารางอ้างอิงสถิต (Limit of Authority, EVENTS Example, Flowchart, ชื่อบริษัท) ไม่มี
คอลัมน์ในนี้เลย — พิมพ์ตายตัวเหมือนกันทุกฉบับใน Print Template (ar_form.html)
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ARStatus(str, enum.Enum):
    """เหมือน PRStatus ทุกประการ — DRAFT = แก้ไขได้, FINALIZED = ล็อกแล้ว (Trigger
    อัตโนมัติตอนกดพิมพ์/ดาวน์โหลด PDF ครั้งแรก)"""

    DRAFT = "draft"
    FINALIZED = "finalized"


class ARBudgetType(str, enum.Enum):
    """ตรงกับช่องติ๊ก "( / )" ของ EXPENSES/ASSETS ในฟอร์มต้นฉบับ — เลือกได้อย่างเดียว"""

    EXPENSES = "expenses"
    ASSETS = "assets"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("ar_no", "revision", name="uq_ar_no_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ar_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    revised_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=True
    )

    application_date: Mapped[date] = mapped_column(Date, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)

    budget_type: Mapped[ARBudgetType] = mapped_column(
        # values_callable: เก็บ .value ("expenses"/"assets") ลง DB ไม่ใช่ .name — Pattern
        # เดียวกับ PRStatus (ดู purchasing_requisition.py บรรทัด 70-86 สำหรับที่มาของ
        # Gotcha นี้ ยืนยันแล้วจากบัค Production จริงตอน Deploy UAT ครั้งแรกของ PR)
        SAEnum(
            ARBudgetType,
            name="ar_budget_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    budget_sub_category: Mapped[str | None] = mapped_column(String(255))  # เช่น "Mnt. Motor"
    budget_name: Mapped[str | None] = mapped_column(String(255))
    budget_for_year: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    amount_used_before: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    this_application: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    description: Mapped[str | None] = mapped_column(Text)

    # Total/VAT/Grand Total: กรอกเองทั้งหมด ไม่คำนวณอัตโนมัติ (Business Decision
    # 2026-09-08 — ผู้ใช้เลือกเองตอนอนุมัติ Design)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    suppliers: Mapped[str | None] = mapped_column(Text)
    term_of_payment: Mapped[str | None] = mapped_column(Text)
    schedule: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ARStatus] = mapped_column(
        SAEnum(
            ARStatus,
            name="ar_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=ARStatus.DRAFT,
        nullable=False,
    )

    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    amount_items: Mapped[list[ARAmountItem]] = relationship(
        back_populates="ar", cascade="all, delete-orphan"
    )


class ARAmountItem(Base):
    """แถวรายการใน "AMOUNT & QUANTITY" — Dynamic Add/Remove เหมือน PRItem แต่มีแค่
    Label (คำอธิบายรายการ) + Amount (จำนวนเงิน) เพราะฟอร์มต้นฉบับมีแค่ 2 คอลัมน์นี้"""

    __tablename__ = "ar_amount_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    ar_id: Mapped[int] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False
    )
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    ar: Mapped[ApprovalRequest] = relationship(back_populates="amount_items")
