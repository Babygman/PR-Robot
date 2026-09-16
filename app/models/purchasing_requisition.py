"""Purchasing Requisition — เฉพาะฟิลด์หน้า 1/3 ของฟอร์ม Sunstar FM-PU-02
(หน้า 2-3 ไม่มี ใช้หน้า 1 ไปก่อนตาม Business Decision 2026-09-01 — อาจ Redesign ทีหลัง)

Scope Revision (Phase 9, 2026-09-03): ตัด Workflow อนุมัติในระบบออกทั้งหมดตาม
Feedback จริงจาก Product Owner (Design เดิมผิดตั้งแต่แรก — Reviewed/Approved/
Received by เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกไปใช้งานนอกระบบ ไม่มีการอนุมัติ
ในระบบเลย) เหลือ Requested by (ผู้สร้าง PR) อย่างเดียวที่ Track ในระบบจริง —
ดูตัวอย่าง PR จริงที่ Product Owner ส่งมาใน docs/00_KICKOFF_AND_DESIGN.md

pr_no = Running Number ต่อเนื่องตลอด ไม่รีเซ็ตรายปี/แผนก (Business Decision 2026-09-01)
วิธี Generate เลขถัดไปเป็นเรื่อง Business Logic ของ Phase 4-5 ไม่ใช่ระดับ Schema

Scope Revision (Phase 11, 2026-09-15, Business Decision): นำ Workflow อนุมัติกลับมา
เป็น Digital เต็มรูปแบบอีกครั้ง — Feedback จริงจากผู้ใช้ว่า Design ของ Phase 9 (พิมพ์
เซ็นมือล้วนๆ) ไม่พอแล้ว ต้องการ Budget Approval Level แบบเดียวกับ AR (ยืดหยุ่นต่อ
แผนก หลายคนต่อ Level แบบ OR) แต่แยกตาราง Level ("pr_approval_levels") ออกจาก AR
("budget_approval_levels") เต็มรูปแบบ ไม่ใช้ร่วมกันเลย (ดู app/models/pr_budget.py)
— ต่างจาก AR 2 จุด (ยืนยันกับผู้ใช้แล้ว 2026-09-15): (1) ไม่มี FA Acknowledge, Level
สุดท้ายอนุมัติ = หักงบจริงทันที (2) ไม่มีขั้น Received แยก จบที่ Level สุดท้ายเลย — ส่วน
Business Logic จริง (Submit/Approve/Reject) เป็น Phase 2 ของรอบนี้ ไฟล์นี้มีแค่ Schema
รองรับ (Field ใหม่บน PRBudgetControl) พฤติกรรม Finalize (ตอนพิมพ์/ดาวน์โหลด PDF
ครั้งแรก) ยังไม่เปลี่ยนจนกว่า Phase 2 จะย้ายไปผูกกับ Level แรกอนุมัติผ่านแทน (Pattern
เดียวกับที่ AR เปลี่ยนตอน Correction 2026-09-10)

PR เก่าทั้งหมดก่อนรอบนี้ถูกลบทิ้งตามคำสั่งผู้ใช้ (2026-09-15) ก่อน Deploy Migration นี้
— ไม่ต้องมี Backward-compat ใดๆ สำหรับข้อมูลเก่า
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
    # หลีกเลี่ยง Circular Import จริง (pr_budget.py Import PurchasingRequisition อยู่แล้ว)
    from app.models.pr_attachment import PRAttachment
    from app.models.pr_budget import PRBudgetApproval


class PRStatus(str, enum.Enum):
    """Scope Revision (Phase 9, 2026-09-03): เหลือ 2 สถานะง่ายๆ ตัด Workflow ทิ้ง —
    DRAFT = แก้ไขได้ปกติ, FINALIZED = ล็อกแก้ไขไม่ได้แล้ว (Trigger อัตโนมัติตอนกด
    พิมพ์/ดาวน์โหลด PDF ครั้งแรก ดู GET /prs/{id}/pdf) — Phase 11: Trigger นี้จะย้ายไป
    ผูกกับ Level แรกอนุมัติผ่านแทนตอน Business Logic (Phase 2) เสร็จ ยังไม่เปลี่ยนตอนนี้"""

    DRAFT = "draft"
    FINALIZED = "finalized"


class PRBudgetApprovalStatus(str, enum.Enum):
    """สถานะ Workflow อนุมัติหักงบประมาณของ PR (Phase 11, 2026-09-15) — Pattern เดียวกับ
    ARBudgetApprovalStatus แต่ไม่มี pending_fa_acknowledge (ไม่มี FA Acknowledge สำหรับ
    PR ตามที่ยืนยันกับผู้ใช้) — Level สุดท้ายอนุมัติผ่าน = APPROVED ทันที (หักงบจริงด้วย)"""

    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PurchasingRequisition(Base):
    """Revise (2026-09-03): PR ที่ Finalized แล้วแก้ไขไม่ได้อีก แต่ "Revise" ได้ —
    สร้างแถวใหม่สถานะ Draft คัดลอกข้อมูลจากต้นฉบับมาเป็นจุดเริ่มต้นให้แก้ไขต่อ
    ต้นฉบับเดิมไม่ถูกแตะ ยังพิมพ์/ดูย้อนหลังได้เหมือนเดิม เพื่อไม่ทำลาย Audit Trail —

    เลข pr_no ใช้ซ้ำกันได้ระหว่าง PR ต้นฉบับกับฉบับ Revise ของมัน (ต่างกันที่ revision:
    0 = ต้นฉบับ, 1/2/3/... = Revise ครั้งที่เท่าไร แสดงเป็น "Rev.N" ต่อท้ายเลข PR)
    ดังนั้น Unique Constraint จึงต้องเป็นคู่ (pr_no, revision) แทนที่จะเป็น pr_no เดี่ยว
    เหมือนก่อนหน้านี้ — ดู Migration ...revise_pr_add_revision.py
    """

    __tablename__ = "purchasing_requisitions"
    __table_args__ = (UniqueConstraint("pr_no", "revision", name="uq_pr_no_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_no: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    revised_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchasing_requisitions.id"), nullable=True
    )

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

    # --- Sealed PDF (Electronic Signature Hardening Phase C, 2026-09-16, Design §3.2.3) ---
    # เขียนครั้งเดียวตอน pr.status เปลี่ยนเป็น FINALIZED จริง (ดู
    # app/services/pdf_sealing.py::seal_pr) — หลังจากนั้น GET /prs/{id}/pdf คืนไฟล์นี้
    # เสมอ ไม่ Re-render จาก Template ปัจจุบันอีก กัน Template เปลี่ยนภายหลังแล้วเอกสารที่
    # เคย Finalized หน้าตาเปลี่ยนตาม — sealed_pdf_path เป็น Path สัมพัทธ์กับ
    # settings.generated_dir (เช่น "pr-123.pdf") ไม่ใช่ Path เต็ม
    sealed_pdf_path: Mapped[str | None] = mapped_column(String(255))
    sealed_pdf_hash: Mapped[str | None] = mapped_column(String(64))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    budget_approvals: Mapped[list[PRBudgetApproval]] = relationship(
        "PRBudgetApproval",
        primaryjoin="PurchasingRequisition.id==PRBudgetApproval.pr_id",
        cascade="all, delete-orphan",
        order_by="PRBudgetApproval.acted_at",
        viewonly=False,
    )
    # PR Attachments (Phase 11, 2026-09-15) — ดู Docstring บนสุดของ app/models/pr_attachment.py
    attachments: Mapped[list[PRAttachment]] = relationship(
        "PRAttachment",
        back_populates="pr",
        cascade="all, delete-orphan",
        order_by="PRAttachment.uploaded_at",
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
    """Phase 11 (2026-09-15): เปลี่ยนจากช่องกรอกมือล้วนๆ (account_code_1/2, budget,
    used_before_amount, balance) มาต่อกับ BudgetMaster จริงแทน (Pattern เดียวกับ AR
    Phase 10) — ผู้ใช้เลือก budget_no ช่องเดียว (Match กับ BudgetMaster.budget_no ที่ไม่
    ซ้ำกัน Global — ไม่ต้องมี budget_type แบบ AR เพราะ PR ไม่มีแนวคิด Expenses/Assets)
    แล้ว account_code จะ Auto-fill/Snapshot จาก BudgetMaster ที่ Match ได้ (Business
    Decision 2026-09-15: 1 Account Code มีได้หลาย Budget No. จึงต้องมีช่องนี้แสดงแยก
    ไม่ใช่ให้ผู้ใช้พิมพ์เอง) — budget/used_before_amount/balance ไม่ Denormalize เก็บไว้
    ในนี้แล้ว อ่านสดจาก budget_master ผ่าน budget_master_id ตอนแสดงผลแทน (ดู
    app/services/pr_pdf.py) — this_application ยังเป็นช่องกรอกมือเหมือนเดิม (จำนวนเงิน
    ที่ขอใช้ของ PR ใบนี้ ไม่มีทางคำนวณ Auto ได้เพราะ PRItem ไม่มีช่องราคา)

    budget_approval_status/current_approval_level/budget_deducted_amount/
    budget_overridden: Field Workflow อนุมัติหักงบ (Pattern เดียวกับ ApprovalRequest
    ของ AR แต่ไม่มี pending_fa_acknowledge) — Business Logic การเดิน Workflow จริงเป็น
    Phase 2 ของรอบนี้ ตอนนี้มีแค่ Schema รองรับ ค่าเริ่มต้นคือ not_submitted เสมอ

    budget_department: Snapshot Department ของผู้สร้าง PR ณ ตอน Submit เข้า Workflow
    จริง (ไม่ใช่ Live-lookup จาก User.department) — เหตุผลเดียวกับ AR: กัน Level ที่
    Query ไปแล้วเปลี่ยนกลางทางถ้า Admin แก้ Department ของผู้สร้างระหว่างรออนุมัติ"""

    __tablename__ = "pr_budget_control"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    budget_no: Mapped[str | None] = mapped_column(String(50))
    account_code: Mapped[str | None] = mapped_column(String(100))
    budget_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_master.id", ondelete="SET NULL")
    )
    this_application: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    budget_department: Mapped[str | None] = mapped_column(String(255))
    budget_approval_status: Mapped[PRBudgetApprovalStatus] = mapped_column(
        SAEnum(
            PRBudgetApprovalStatus,
            name="pr_budget_approval_status",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=PRBudgetApprovalStatus.NOT_SUBMITTED,
        server_default=PRBudgetApprovalStatus.NOT_SUBMITTED.value,
        nullable=False,
    )
    current_approval_level: Mapped[int | None] = mapped_column(Integer)
    budget_deducted_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    budget_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    requisition: Mapped[PurchasingRequisition] = relationship(back_populates="budget_control")
