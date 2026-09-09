"""Budget Control — Model ทั้งหมด (Phase 10, 2026-09-09, Business Decision v4.1)

ขอบเขต: เฉพาะ Approval Request (AR) เท่านั้น ไม่แตะ PR เลย (ดู
docs/drafts/budget_control_design_draft.md สำหรับ Design เต็ม)

โครงสร้างหลัก:
- `BudgetMaster` — ยอดงบประมาณจาก Excel ที่ Admin/FA Upload เข้ามา หนึ่งแถวต่อหนึ่ง
  "รายการงบ" — Key จริงที่ไม่ซ้ำกันคือ `budget_no` (เช่น BG0001, BG0002, ... เลขวิ่ง
  Global ไม่ผูกแผนก) ซึ่งคือค่าเดียวกับช่อง "Budget No." ในฟอร์ม AR แบบ 1:1 ตรงๆ —
  แก้ไขจาก Business Decision v4.1 เดิมที่เข้าใจผิดว่า `account_code` คือ Key เดียวกับ
  Budget No. (Correction 2026-09-09 หลังผู้ใช้ส่งตัวอย่างข้อมูลจริง): `account_code`
  เป็นแค่รหัสบัญชี/หมวดหมู่ (เช่น 5100, 1600) ซ้ำกันได้หลายแถว/หลาย Budget No. ตามจริง
  ไม่ใช่ Key — `used_amount` เป็น Counter บวกสะสมจริง หักด้วย Atomic UPDATE เท่านั้น
  (Pattern เดียวกับ ar_numbering.py) ห้ามอ่านมาลบในโค้ด Python เด็ดขาด (เสี่ยง Race
  Condition ตอนอนุมัติพร้อมกัน)
- `BudgetUploadBatch` / `BudgetUploadRowError` — Log การ Upload Excel แต่ละครั้ง
  (ใคร/เมื่อไหร่/กี่แถวสำเร็จ/กี่แถว Error) — Import แบบ Partial-success
- `BudgetApprovalLevel` — Level Management: แต่ละแผนกกำหนดเองว่ามีกี่ Level อะไรบ้าง
  (ยืดหยุ่น ไม่ Fix 5 Level เท่ากันทุกแผนก) ผู้อนุมัติผูกกับบุคคลเจาะจง (ไม่ผูก Position)
  — Step สุดท้าย "FA Acknowledge" ไม่มีแถวในตารางนี้เพราะเป็น Role กลาง (User.is_fa)
  ไม่ผูกแผนก รันอัตโนมัติหลัง Level สุดท้ายของแผนกอนุมัติผ่านครบ
- `ARBudgetApproval` — Audit Trail การอนุมัติ/ปฏิเสธของแต่ละ Level (รวม FA
  Acknowledge) แยกเป็นแถว ใช้แสดงประวัติ + Auto-fill ตาราง "Authority"/"F&A" ใน PDF
  (ar_form.html) — เก็บ `level_name_snapshot` กันปัญหาถ้า Admin แก้ชื่อ Level ทีหลัง
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
from app.models.approval_request import ARBudgetType


class BudgetApprovalStepType(str, enum.Enum):
    LEVEL = "level"
    FA_ACKNOWLEDGE = "fa_acknowledge"


class BudgetApprovalAction(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class BudgetMaster(Base):
    __tablename__ = "budget_master"
    __table_args__ = (UniqueConstraint("budget_no", name="uq_budget_master_budget_no"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Key จริงที่ไม่ซ้ำกัน (Global — ไม่ผูกแผนก) ตรงกับช่อง "Budget No." ของ AR แบบ 1:1
    # — ใช้ Match ตอน Finalize AR (ดู budget_workflow.resolve_budget_master) และใช้เป็น
    # Key จับคู่ตอน Re-upload Excel (ดู budget_excel.py) แทน Composite Field เดิม
    budget_no: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    department: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    budget_type: Mapped[ARBudgetType] = mapped_column(
        SAEnum(
            ARBudgetType,
            name="ar_budget_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    # รหัสบัญชี/หมวดหมู่ (Classification) — "ไม่ใช่" Key ไม่ Unique ซ้ำกันได้หลายแถว/
    # หลาย budget_no ตามจริง (เช่น account_code=5100 มีทั้ง BG0001 กับ BG0002)
    account_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    budget_name: Mapped[str | None] = mapped_column(String(255))
    budgeted_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # หักด้วย Atomic UPDATE เท่านั้น (ดู app/services/budget_workflow.py) — ห้าม
    # Read-modify-write ในโค้ด Python เด็ดขาด (Race Condition ตอนอนุมัติพร้อมกัน)
    used_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    updated_by_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("budget_upload_batches.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BudgetUploadBatch(Base):
    __tablename__ = "budget_upload_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    row_errors: Mapped[list[BudgetUploadRowError]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class BudgetUploadRowError(Base):
    __tablename__ = "budget_upload_row_errors"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("budget_upload_batches.id", ondelete="CASCADE"), nullable=False
    )
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    batch: Mapped[BudgetUploadBatch] = relationship(back_populates="row_errors")


class BudgetApprovalLevel(Base):
    """Level Management — โครงสร้าง Level การอนุมัติของแต่ละแผนก ยืดหยุ่นได้อิสระ
    (แผนกไหนมีกี่ Level อะไรบ้าง กำหนดเองทั้งหมด) ผู้อนุมัติผูกกับบุคคลเจาะจง

    Correction 2026-09-09 (Multi-approver per Level, OR): 1 แถว = 1 คนใน 1 Level ไม่ใช่
    1 แถว = 1 Level อีกต่อไป — Level เดียวกัน (department+level_no) มีได้หลายแถวหลายคน
    (เช่น Level "President or Director" มี 3 คน) ใครก็ได้ในกลุ่มอนุมัติ/ปฏิเสธก่อน ถือว่า
    Level นั้นจบ (OR ไม่ใช่ AND) — ดูตัวอย่าง Approve Flow จริงที่ผู้ใช้ส่งมา 2026-09-09
    (Level 4 มี Hori/Ochi/Ukai พร้อมกัน) ทุกแถวในกลุ่มเดียวกัน (department+level_no) ต้อง
    มี level_name ตรงกันเป๊ะเสมอ (บังคับ Sync ที่ Route Layer — ดู budget_levels.py) กัน
    Audit Trail สับสนว่า Level ไหนชื่ออะไรกันแน่"""

    __tablename__ = "budget_approval_levels"
    __table_args__ = (
        UniqueConstraint(
            "department",
            "level_no",
            "approver_user_id",
            name="uq_budget_level_dept_level_no_approver",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # แผนกที่ Level นี้เป็นส่วนหนึ่งของสาย = Department ของผู้สร้าง AR (ไม่ใช่ของ
    # ผู้อนุมัติ — ผู้อนุมัติเอง "ไม่จำเป็น" ต้องมี Department เดียวกัน หรือมี Department
    # เลยก็ได้ — รองรับผู้อนุมัติ Cross-department ตามตัวอย่างจริงที่แนบมา)
    department: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    level_no: Mapped[int] = mapped_column(Integer, nullable=False)
    level_name: Mapped[str] = mapped_column(String(100), nullable=False)
    approver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ARBudgetApproval(Base):
    """Audit Trail การอนุมัติ/ปฏิเสธของแต่ละ Level + FA Acknowledge — แหล่งข้อมูล
    เดียวสำหรับ "ใครอนุมัติ Level ไหน เมื่อไหร่" ใช้ทั้งแสดงประวัติในหน้า AR Detail
    และ Auto-fill ตาราง Authority/ช่อง F&A ใน PDF (ar_form.html / ar_pdf.py)"""

    __tablename__ = "ar_budget_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    ar_id: Mapped[int] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_type: Mapped[BudgetApprovalStepType] = mapped_column(
        SAEnum(
            BudgetApprovalStepType,
            name="budget_approval_step_type",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    level_no: Mapped[int | None] = mapped_column(Integer)
    level_name_snapshot: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[BudgetApprovalAction] = mapped_column(
        SAEnum(
            BudgetApprovalAction,
            name="budget_approval_action",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    acted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # True ถ้า Admin กดแทนผู้อนุมัติตัวจริง (approver_user_id ของ Level นั้น) — แสดงชัด
    # ใน Audit ว่าไม่ใช่คนที่ถูกกำหนดไว้ (กรณีคนจริงติดธุระ/ลาออกยังไม่ทันตั้งคนใหม่)
    acted_as_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)  # บังคับกรอกถ้า action = rejected

    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
