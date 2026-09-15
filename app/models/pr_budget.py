"""PR Budget Approval — Level Management + Audit Trail (Phase 11, 2026-09-15)

Business Decision 2026-09-15: นำ Workflow อนุมัติของ PR กลับมาเป็น Digital ผ่าน
Budget Approval Level แบบเดียวกับ AR (ยืดหยุ่นต่อแผนก, หลายคนต่อ Level แบบ OR — ดู
Docstring ของ app/models/budget.py: BudgetApprovalLevel สำหรับที่มาของ Pattern OR
นี้) แต่ **แยกตารางออกจาก AR เต็มรูปแบบ** ("pr_approval_levels" / "pr_budget_approvals"
ไม่ใช้ร่วมกับ "budget_approval_levels" / "ar_budget_approvals" เลย) ตามที่ผู้ใช้
ยืนยันชัดเจน (ต้องแยกเมนู "Approval Level-PR" ออกจาก "Approval Level-AR" ในหน้าเว็บ
และไม่ต้องการให้การเปลี่ยนแปลง Level ของ PR กระทบระบบ AR ที่ใช้งานจริงอยู่แล้วเลย)

ต่างจาก AR 2 จุด (ยืนยันแล้ว 2026-09-15):
1. ไม่มี FA Acknowledge — Level สุดท้ายอนุมัติผ่าน = หักงบจริงทันที (ดู
   PRBudgetApprovalStatus ใน purchasing_requisition.py: ไม่มี pending_fa_acknowledge)
   จึงไม่ต้องมีคอลัมน์ step_type ใน pr_budget_approvals เหมือน ar_budget_approvals
   (ทุกแถวเป็น "level" เสมอ)
2. ไม่มีขั้น Received แยกต่างหาก — จบ Workflow ที่ Level สุดท้าย

action (Approved/Rejected) ใช้ Enum Type เดียวกับ AR ("budget_approval_action" — Reuse
ตรงๆ ไม่สร้าง Type ใหม่ซ้ำ เพราะเป็นแนวคิดเดียวกันจริงๆ ไม่ใช่ Field เฉพาะ AR) ดู
Migration ...pr_approval_workflow.py: สร้างด้วย create_type=False เพราะ Type นี้มีอยู่
แล้วจาก Migration a7d3f9c1b4e8 ของ AR

Budget Pool: ใช้ร่วมกับ AR จริง (ผ่าน budget_master_id ที่ชี้ไป budget_master แถว
เดียวกัน ถ้า PR/AR อ้าง Budget No. เดียวกัน) — Business Logic การหักยอดจริง (Atomic
UPDATE บน BudgetMaster.used_amount) เป็น Phase 2 ของรอบนี้ ไม่ใช่ไฟล์นี้
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.budget import BudgetApprovalAction


class PRApprovalLevel(Base):
    """Level Management ของ PR — โครงสร้างเดียวกับ BudgetApprovalLevel (app/models/
    budget.py) ของ AR ทุกประการ แต่แยกตารางเต็มรูปแบบ (ดู Docstring บนสุดของไฟล์นี้)"""

    __tablename__ = "pr_approval_levels"
    __table_args__ = (
        UniqueConstraint(
            "department",
            "level_no",
            "approver_user_id",
            name="uq_pr_level_dept_level_no_approver",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    level_no: Mapped[int] = mapped_column(Integer, nullable=False)
    level_name: Mapped[str] = mapped_column(String(100), nullable=False)
    approver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PRBudgetApproval(Base):
    """Audit Trail การอนุมัติ/ปฏิเสธของแต่ละ Level ของ PR — Structure เดียวกับ
    ARBudgetApproval แต่ไม่มี step_type (ทุกแถวเป็น Level เสมอ ไม่มี FA Acknowledge)"""

    __tablename__ = "pr_budget_approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    pr_id: Mapped[int] = mapped_column(
        ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level_no: Mapped[int] = mapped_column(Integer, nullable=False)
    level_name_snapshot: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[BudgetApprovalAction] = mapped_column(
        # Reuse Enum Type เดียวกับ AR ("budget_approval_action") — ดู Docstring บนสุด
        SAEnum(
            BudgetApprovalAction,
            name="budget_approval_action",
            native_enum=True,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    acted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    acted_as_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    acted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pr = relationship(
        "PurchasingRequisition",
        primaryjoin="PRBudgetApproval.pr_id==PurchasingRequisition.id",
        viewonly=True,
    )
