"""Schema สำหรับ PR Approval Level Workflow (Phase 11 Phase 2/3, 2026-09-15)

Pattern เดียวกับ Schema ที่เกี่ยวกับ Budget Control ของ AR (app/schemas/budget.py)
แต่แยกไฟล์ต่างหากเพราะ PR มีตาราง Level/Audit Trail แยกจาก AR เต็มรูปแบบ — Reuse
BudgetRejectBody ของ AR ตรงๆ (ไม่มี Field เฉพาะ AR อยู่แล้ว ไม่ต้องสร้างซ้ำ)
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.models.purchasing_requisition import PRBudgetApprovalStatus


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


class PRMyApprovalItem(BaseModel):
    """1 แถวในตารางหน้า "การอนุมัติของฉัน" ของ PR (Phase 11 Phase 4, 2026-09-15) — แยก
    หน้าต่างหากจาก AR ตามที่ผู้ใช้ยืนยัน 2026-09-15 (ไม่รวม Inbox เดียวกัน) — PR ไม่มี
    Field "subject" แบบ AR จึงใช้ section/division แสดงแทน (Pattern เดียวกับที่
    dashboard.html/pr_detail.html ใช้อยู่แล้ว) — Field ระดับ Workflow (budget_approval_status/
    current_approval_level/budget_department) อยู่ใต้ pr.budget_control ที่เป็น Nested
    Relation ไม่ใช่ Flat Field แบบ ApprovalRequest ของ AR จึงต้องประกอบขึ้นเองในชั้น Route
    (_to_pr_my_approval_item) ไม่ใช้ model_validate(pr, from_attributes=True) ตรงๆ"""

    id: int
    pr_no: int
    pr_no_display: str = ""  # เติมใน Route — "3 Rev.1" ถ้าเป็นฉบับ Revise
    revision: int
    section: str
    division: str
    doc_date: date
    budget_department: str | None = None
    budget_approval_status: PRBudgetApprovalStatus
    current_approval_level: int | None = None
    current_level_name: str | None = None  # เติมใน Route
    requested_by_id: int
    requested_by_name: str | None = None  # เติมใน Route
    actionable: bool = False  # เติมใน Route — โชว์/ซ่อนปุ่มอนุมัติ/ปฏิเสธที่ฝั่ง Client
    created_at: datetime

    model_config = {"from_attributes": True}


class PRMyApprovalCounts(BaseModel):
    waiting: int
    mine: int
    history: int
    returned: int
