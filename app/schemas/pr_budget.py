"""Schema สำหรับ PR Approval Level Workflow (Phase 11 Phase 2/3, 2026-09-15)

Pattern เดียวกับ Schema ที่เกี่ยวกับ Budget Control ของ AR (app/schemas/budget.py)
แต่แยกไฟล์ต่างหากเพราะ PR มีตาราง Level/Audit Trail แยกจาก AR เต็มรูปแบบ — Reuse
BudgetRejectBody ของ AR ตรงๆ (ไม่มี Field เฉพาะ AR อยู่แล้ว ไม่ต้องสร้างซ้ำ)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PRApprovalLevelCreate(BaseModel):
    department: str = Field(min_length=1, max_length=255)
    level_no: int = Field(gt=0)
    level_name: str = Field(min_length=1, max_length=100)
    approver_user_id: int


class PRApprovalLevelUpdate(BaseModel):
    level_name: str | None = Field(default=None, min_length=1, max_length=100)
    approver_user_id: int | None = None
    is_active: bool | None = None


class PRApprovalLevelRead(BaseModel):
    id: int
    department: str
    level_no: int
    level_name: str
    approver_user_id: int
    approver_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class PRSubmitBody(BaseModel):
    """ส่งมาตอนกด "ส่งขออนุมัติ" (submit-for-approval) — force ใช้เฉพาะกรณีแผนกไม่มี
    Level อนุมัติเลย (0 แถว) ซึ่งหักงบจริงทันทีในนี้เลย (ดู Docstring บนสุดของ
    pr_budget_workflow.py ข้อ 3) ถ้ายอดเกินงบคงเหลือต้องส่ง force=true มายืนยันซ้ำ
    เหมือน Level สุดท้ายปกติทุกประการ"""

    force: bool = False


class PRApproveLevelBody(BaseModel):
    """comment ไม่บังคับ (Pattern เดียวกับ BudgetApproveLevelBody ของ AR) — force ใช้
    เฉพาะตอนอนุมัติ Level สุดท้าย (จุดที่หักงบจริง) ถ้ายอดเกินงบคงเหลือ ต้องส่ง
    force=true มายืนยันซ้ำ (Pattern เดียวกับ BudgetFaAcknowledgeBody ของ AR แต่รวมมาไว้
    ในนี้เพราะ PR ไม่มี FA Acknowledge แยกขั้น — หักงบเกิดขึ้นใน approve-level เลย)"""

    comment: str | None = Field(default=None, max_length=2000)
    force: bool = False


class PRApprovalProgressStep(BaseModel):
    """1 แถวใน Stepper ของหน้า PR Detail — Pattern เดียวกับ ARApprovalProgressStep แต่
    ไม่มี step_type (ทุกแถวเป็น Level เสมอ ไม่มี FA Acknowledge ใน PR)"""

    level_no: int
    level_name: str
    approver_user_ids: list[int] = []
    approver_names: str | None
    status: str  # "waiting" | "approved" | "rejected"
    acted_by_name: str | None = None
    acted_at: datetime | None = None
    reason: str | None = None
    acted_as_override: bool = False
