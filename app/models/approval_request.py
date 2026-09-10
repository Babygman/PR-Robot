"""Approval Request (AR) — ฟอร์ม "APPROVAL REQUEST" ของ Sunstar Chemical Thailand
(Template Version "20220404_rev.2") — โมดูลใหม่ใน PR-Robot เดิม (Business Decision
2026-09-08 ตามที่ผู้ใช้อนุมัติ Design ไว้)

หน้าที่ของระบบคือ "ให้ User Key ข้อมูลทุกอย่างที่จำเป็นในแต่ละช่องเพื่อปริ้น เอาไป
ใช้งานการเซ็นภายนอก" ล้วนๆ — ไม่มี Workflow อนุมัติในระบบ (จนถึง Budget Control
Phase 10 ด้านล่าง), ไม่มี AI Autofill — เดิม Total/VAT/Grand Total/Balance ผู้ใช้
กรอกเองทุกช่อง (Business Decision 2026-09-08) แต่ถูกย้อนกลับบางส่วนแล้วโดย
Correction 2026-09-10 (ดู app/templates/ar_edit.html): Total ยังกรอกเองเหมือนเดิม
แต่ VAT เปลี่ยนเป็นเลือก % (7/3/0/กรอกเอง) คำนวณ VAT Amount ให้, Grand Total คำนวณ
Auto จาก Total+VAT เสมอ (Readonly), This Application คำนวณ Auto = Grand Total
เสมอ (Readonly — กันพิมพ์เลขไม่ตรงกับที่หักงบจริงตอน FA Acknowledge), Balance
Simulate Auto จาก Budget for the Year − Amount Used Before − This Application แต่
ยังแก้ไขเองได้ (เป็นแค่ Field แสดงผล Preview ไม่ได้ใช้หักงบจริง) — ช่องลายเซ็น 5 ช่อง
(President/Director, General Manager, Senior Manager, Manager, F&A) ว่างเสมอใน
ระบบเดิม เซ็น/กรอกสดบนกระดาษหลังพิมพ์ทั้งหมด (รวมถึง F&A ที่ในตัวอย่างจริงมีชื่อคน
พิมพ์ไว้ล่วงหน้า แต่ผู้ใช้ยืนยันให้ปฏิบัติเหมือนช่องเซ็นสดอื่นๆ) — จนกระทั่ง Budget
Control Phase 10 ด้านล่างเปลี่ยนให้ Auto-fill จริงตอน Level อนุมัติผ่าน

Pattern เดียวกับ PurchasingRequisition (purchasing_requisition.py) เกือบทุกประการ:
สถานะ 2 ค่า (draft/finalized) และ revision/revised_from_id (สร้างฉบับ Draft ใหม่
คัดลอกข้อมูลมาแก้ไขต่อ ไม่แตะต้นฉบับเดิม) — ยกเว้น "จุด Trigger Finalize" กับ "เงื่อนไข
Revise" ที่ Correction 2026-09-10 แก้ใหม่เฉพาะ AR แล้ว (ดู Docstring ของ ARStatus
ด้านล่าง): ไม่ใช่พิมพ์/ดาวน์โหลด PDF ครั้งแรกอีกต่อไป (เหมือน PR เดิม) แต่เป็น Level
แรกอนุมัติผ่าน และ Revise ได้เฉพาะฉบับที่ถูก Reject มาเท่านั้น ไม่ใช่ฉบับ Finalized
ทุกฉบับเหมือน PR

ตารางอ้างอิงสถิต (Limit of Authority, EVENTS Example, Flowchart, ชื่อบริษัท) ไม่มี
คอลัมน์ในนี้เลย — พิมพ์ตายตัวเหมือนกันทุกฉบับใน Print Template (ar_form.html)

Budget Control (Phase 10, 2026-09-09, Business Decision v4.1): ย้อนกลับหมายเหตุ
ด้านบนเฉพาะจุด — ช่องลายเซ็นทั้ง 5 ช่อง (President/Director, General Manager, Senior
Manager, Manager, F&A) ไม่ได้ว่างเปล่ารอเซ็นสดอีกต่อไป แต่ Auto-fill ชื่อผู้อนุมัติ+
วันที่ทันทีที่แต่ละ Level (ดู app/models/budget.py: BudgetApprovalLevel) อนุมัติผ่าน
จริงในระบบ — เพิ่ม Field ใหม่ 4 ตัวด้านล่างเพื่อติดตามสถานะ Workflow อนุมัติหักงบ
ประมาณนี้ (แยกจาก `status` Draft/Finalized เดิมโดยสิ้นเชิง — เอกสารยัง Lock ตอน
Finalize/พิมพ์ครั้งแรกเหมือนเดิมทุกประการ ไม่เกี่ยวกับ Workflow อนุมัติหักงบเลย)
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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

if TYPE_CHECKING:
    # หลีกเลี่ยง Circular Import จริง (budget.py Import ARBudgetType จากไฟล์นี้อยู่แล้ว)
    # — Import แค่ตอน Type-check เท่านั้น ตอน Runtime ใช้ String Forward-ref ในตัว
    # relationship() ข้างล่างแทน (SQLAlchemy Resolve ผ่าน Registry ตอน Mapper Configure)
    from app.models.ar_attachment import ARAttachment
    from app.models.budget import ARBudgetApproval


class ARStatus(str, enum.Enum):
    """DRAFT = แก้ไขได้, FINALIZED = ล็อกแล้ว — Correction 2026-09-10 (เฉพาะ AR, PR ยัง
    เหมือน PRStatus เดิมทุกประการคือ Trigger ตอนพิมพ์/ดาวน์โหลด PDF ครั้งแรก): AR ไม่ใช้
    Pattern นั้นอีกต่อไป พิมพ์/ดาวน์โหลด PDF ไม่มีผลข้างเคียงแล้ว (ดู
    app/api/routes/approval_requests.py: get_ar_pdf) Trigger จริงคือ Level แรกของ
    Workflow อนุมัติหักงบอนุมัติผ่าน (ดู app/services/budget_workflow.py:
    approve_level) — ยกเว้นแผนกไม่มี Level อนุมัติเลยจะ Finalized ทันทีตอนกด "ส่งขอ
    อนุมัติ" (ดู submit_ar_for_approval) เพราะไม่มี Level ให้รอ"""

    DRAFT = "draft"
    FINALIZED = "finalized"


class ARBudgetType(str, enum.Enum):
    """ตรงกับช่องติ๊ก "( / )" ของ EXPENSES/ASSETS ในฟอร์มต้นฉบับ — เลือกได้อย่างเดียว"""

    EXPENSES = "expenses"
    ASSETS = "assets"


class ARBudgetApprovalStatus(str, enum.Enum):
    """สถานะ Workflow อนุมัติหักงบประมาณ (Budget Control, แยกจาก ARStatus
    Draft/Finalized โดยสิ้นเชิง) — ดู app/services/budget_workflow.py สำหรับ Logic
    การเปลี่ยนสถานะทั้งหมด"""

    NOT_SUBMITTED = "not_submitted"  # ยังไม่ Finalize หรือ Revise ใหม่ (รีเซ็ตเสมอ)
    PENDING = "pending"  # รอ Level ใดๆ (ดู current_approval_level) อนุมัติ/ปฏิเสธ
    PENDING_FA_ACKNOWLEDGE = "pending_fa_acknowledge"  # Level ครบแล้ว รอ FA Acknowledge
    APPROVED = "approved"  # FA Acknowledge ผ่านแล้ว หักยอดงบจริงแล้ว
    REJECTED = "rejected"  # ถูกปฏิเสธจาก Level ใดก็ได้ (รวม FA) — แก้ไขผ่าน Revise เท่านั้น


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
    # รหัส/เลขที่บัญชีงบประมาณ (Feedback จริงจากผู้ใช้ 2026-09-08 หลังทดสอบใช้งานจริง —
    # ฟอร์มตัวอย่างต้นฉบับไม่มีช่องนี้แยกจาก Expenses/Assets แต่ผู้ใช้ต้องการ Field
    # แยกสำหรับกรอกรหัสบัญชีงบประมาณ เช่น "5100-01")
    budget_no: Mapped[str | None] = mapped_column(String(100))
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
    # เดิมเป็นช่อง Text เดียว "Schedule Start - Finish" — แยกเป็น 2 ช่องวันที่ (Feedback
    # จริงจากผู้ใช้ 2026-09-08: ต้องการ Date Picker เลือกวันที่แยก Start/Finish แบบ
    # dd/mm/yyyy เหมือนช่องวันที่อื่นในระบบ ไม่ใช่พิมพ์ข้อความอิสระ)
    schedule_start: Mapped[date | None] = mapped_column(Date)
    schedule_finish: Mapped[date | None] = mapped_column(Date)

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

    # --- Budget Control (Phase 10, 2026-09-09) — ดู Docstring บนสุดของไฟล์ ---
    # Snapshot Department ของผู้สร้าง ณ ตอน Finalize (ไม่ใช่ Live-lookup จาก User.department
    # ทุกครั้ง) — กัน Bug ถ้า Admin แก้ Department ของ User คนนั้นระหว่างที่ AR ยังอยู่
    # ระหว่างขั้นตอนอนุมัติ (Level ที่ Query ไปแล้วต้องนิ่ง ไม่เปลี่ยนกลางทาง)
    budget_department: Mapped[str | None] = mapped_column(String(255))
    budget_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_master.id", ondelete="SET NULL")
    )
    budget_approval_status: Mapped[ARBudgetApprovalStatus] = mapped_column(
        SAEnum(
            ARBudgetApprovalStatus,
            name="ar_budget_approval_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=ARBudgetApprovalStatus.NOT_SUBMITTED,
        server_default=ARBudgetApprovalStatus.NOT_SUBMITTED.value,
        nullable=False,
    )
    # Level (level_no ใน BudgetApprovalLevel) ที่กำลังรอการอนุมัติอยู่ตอนนี้ — มีค่า
    # เฉพาะตอน budget_approval_status = pending เท่านั้น
    current_approval_level: Mapped[int | None] = mapped_column(Integer)
    # จำนวนที่หักไปจริงตอน FA Acknowledge (เก็บไว้คืนยอดตอน Revise — ไม่คำนวณใหม่จาก
    # this_application ที่อาจถูกแก้ไปแล้วหลัง Approved)
    budget_deducted_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    # Mark ไว้ว่า FA Acknowledge ทั้งที่เกินงบ (Force) — โชว์ชัดใน UI/Report
    budget_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    amount_items: Mapped[list[ARAmountItem]] = relationship(
        back_populates="ar", cascade="all, delete-orphan"
    )
    budget_approvals: Mapped[list[ARBudgetApproval]] = relationship(
        "ARBudgetApproval",
        primaryjoin="ApprovalRequest.id==ARBudgetApproval.ar_id",
        cascade="all, delete-orphan",
        order_by="ARBudgetApproval.acted_at",
        viewonly=False,
    )
    # AR Attachments (Phase A, 2026-09-10) — ดู Docstring บนสุดของ app/models/ar_attachment.py
    attachments: Mapped[list[ARAttachment]] = relationship(
        "ARAttachment",
        back_populates="ar",
        cascade="all, delete-orphan",
        order_by="ARAttachment.uploaded_at",
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
