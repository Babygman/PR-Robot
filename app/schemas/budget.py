"""Schema สำหรับ Budget Control (Phase 10, 2026-09-09, Business Decision v4.1)

ครอบคลุม: Budget Master (ยอดงบจาก Excel), Budget Upload (Preview/Confirm/History),
Level Management, และผลลัพธ์ Audit การอนุมัติแต่ละ Level/FA Acknowledge
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.approval_request import ARBudgetApprovalStatus, ARBudgetType
from app.models.budget import BudgetApprovalAction, BudgetApprovalStepType


# ───────────────────────── Budget Master ─────────────────────────
class BudgetMasterRead(BaseModel):
    id: int
    budget_no: str
    department: str
    budget_type: ARBudgetType
    account_code: str
    period_start: date
    period_end: date
    budget_name: str | None
    budgeted_amount: Decimal
    used_amount: Decimal
    balance: Decimal = Decimal("0")  # เติมใน Route (ไม่ใช่คอลัมน์จริง) = budgeted - used
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BudgetMasterCreate(BaseModel):
    """POST /budget — เพิ่มรายการ Budget เองทีละแถว (ไม่ผ่าน Excel) — Correction
    2026-09-11 (User Feedback: "Budget ต้องสามารถเพิ่มรายการใหม่ได้ ไม่ใช่จากการ
    upload ได้อย่างเดียว") ใช้กฎ Validate เดียวกับ Excel Upload — budget_no ซ้ำกับ
    ที่มีอยู่แล้ว Route จะปฏิเสธด้วย 409 (ต่างจาก Excel Upload ที่ Upsert ทับให้เลย
    เพราะการเพิ่มทีละแถวแบบนี้ไม่มีขั้นตอน Confirm ก่อนเหมือน Batch Upload)"""

    budget_no: str = Field(min_length=1, max_length=50)
    department: str = Field(min_length=1, max_length=255)
    budget_type: ARBudgetType
    account_code: str = Field(min_length=1, max_length=100)
    period_start: date
    period_end: date
    budgeted_amount: Decimal = Field(ge=0)
    budget_name: str | None = Field(default=None, max_length=255)


class BudgetMasterUpdate(BaseModel):
    """PATCH /budget/{id} — แก้ไขรายการ Budget ที่มีอยู่แล้วโดยตรงจากหน้าเว็บ
    (Correction 2026-09-11) ทุก Field Optional — ส่งมาเฉพาะที่จะเปลี่ยน (Pattern
    เดียวกับ UserUpdate) — "budget_no" และ "used_amount" ไม่อยู่ใน Schema นี้โดย
    เจตนา: budget_no เป็น Key หลักที่ผูกกับ AR แล้วห้ามแก้, used_amount เป็นยอดที่
    ระบบหักอัตโนมัติจากการอนุมัติ AR เท่านั้น แก้มือไม่ได้เด็ดขาด"""

    department: str | None = Field(default=None, min_length=1, max_length=255)
    budget_type: ARBudgetType | None = None
    account_code: str | None = Field(default=None, min_length=1, max_length=100)
    period_start: date | None = None
    period_end: date | None = None
    budgeted_amount: Decimal | None = Field(default=None, ge=0)
    budget_name: str | None = Field(default=None, max_length=255)


# ───────────────────────── Excel Upload ─────────────────────────
class BudgetUploadRowResult(BaseModel):
    row_no: int
    ok: bool
    message: str
    department: str | None = None
    account_code: str | None = None


class BudgetUploadResult(BaseModel):
    batch_id: int
    filename: str
    total_rows: int
    success_rows: int
    error_rows: int
    rows: list[BudgetUploadRowResult]


class BudgetUploadBatchRead(BaseModel):
    id: int
    filename: str
    uploaded_by_id: int | None
    uploaded_by_name: str | None = None
    uploaded_at: datetime
    total_rows: int
    success_rows: int
    error_rows: int

    model_config = {"from_attributes": True}


# ───────────────────────── Level Management ─────────────────────────
class BudgetApprovalLevelCreate(BaseModel):
    department: str = Field(min_length=1, max_length=255)
    level_no: int = Field(ge=1)
    level_name: str = Field(min_length=1, max_length=100)
    approver_user_id: int


class BudgetApprovalLevelUpdate(BaseModel):
    """ทุก Field Optional — ส่งมาเฉพาะที่จะเปลี่ยน (level_no เปลี่ยนได้เพื่อ Reorder)"""

    level_no: int | None = Field(default=None, ge=1)
    level_name: str | None = Field(default=None, min_length=1, max_length=100)
    approver_user_id: int | None = None
    is_active: bool | None = None


class BudgetApprovalLevelRead(BaseModel):
    id: int
    department: str
    level_no: int
    level_name: str
    approver_user_id: int
    approver_name: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


# ───────────────────────── Approval Audit / Progress ─────────────────────────
class ARBudgetApprovalRead(BaseModel):
    id: int
    step_type: BudgetApprovalStepType
    level_no: int | None
    level_name_snapshot: str | None
    action: BudgetApprovalAction
    acted_by_id: int
    acted_by_name: str | None = None
    acted_as_override: bool
    reason: str | None
    acted_at: datetime

    model_config = {"from_attributes": True}


class ARApprovalProgressStep(BaseModel):
    """1 แถวใน Stepper ของหน้า AR Detail — รวม Level ที่ Config ไว้ (BudgetApprovalLevel)
    เข้ากับผลจริง (ARBudgetApproval ถ้ามี) ให้ Client Render ง่ายๆ ไม่ต้อง Join เอง

    Correction 2026-09-09 (Multi-approver per Level, OR): approver_user_id/approver_name
    (เดี่ยว) เปลี่ยนเป็น approver_user_ids/approver_names (รายชื่อ) เพราะ 1 Level มีผู้มี
    สิทธิ์อนุมัติได้มากกว่า 1 คนแล้ว — ดู app/models/budget.py Docstring BudgetApprovalLevel"""

    step_type: BudgetApprovalStepType
    level_no: int | None
    level_name: str
    approver_user_ids: list[int] = []  # ว่างเฉพาะ fa_acknowledge (ไม่ผูกคนเจาะจง เป็น Role กลาง)
    approver_names: str | None  # ชื่อทุกคนในกลุ่ม คั่นด้วย ", " เช่น "Hori, Ochi, Ukai"
    status: str  # "waiting" | "approved" | "rejected"
    acted_by_name: str | None = None
    acted_at: datetime | None = None
    reason: str | None = None
    acted_as_override: bool = False


class BudgetRejectBody(BaseModel):
    reason: str = Field(min_length=1)


class BudgetApproveLevelBody(BaseModel):
    """Correction 2026-09-10 (Phase A): เพิ่ม Comment ไม่บังคับตามที่ Docstring เดิมของ
    Field นี้เตรียมไว้ — เก็บลงคอลัมน์ ARBudgetApproval.reason เดิม (Reuse เดียวกับที่ใช้
    เก็บเหตุผลตอนปฏิเสธ) ไม่ต้องเพิ่มคอลัมน์ใหม่"""

    comment: str | None = Field(default=None, max_length=2000)


class BudgetFaAcknowledgeBody(BaseModel):
    force: bool = False
    comment: str | None = Field(default=None, max_length=2000)


# ───────────────────────── My Approvals (Phase B/2, 2026-09-10) ─────────────────────────
class MyApprovalItem(BaseModel):
    """1 แถวในตารางหน้า "การอนุมัติของฉัน" — ดู Docstring
    app/services/budget_workflow.py (ท้ายไฟล์) สำหรับนิยามแต่ละหมวด (Bucket)"""

    id: int
    ar_no: int
    ar_no_display: str = ""  # เติมใน Route
    revision: int
    subject: str
    application_date: date
    budget_department: str | None
    budget_approval_status: ARBudgetApprovalStatus
    current_approval_level: int | None
    current_level_name: str | None = None  # เติมใน Route — "FA Acknowledge" ถ้าถึงขั้น FA
    requested_by_id: int
    requested_by_name: str | None = None  # เติมใน Route
    actionable: bool = False  # เติมใน Route — โชว์/ซ่อนปุ่มอนุมัติ/ปฏิเสธที่ฝั่ง Client
    created_at: datetime

    model_config = {"from_attributes": True}


class MyApprovalCounts(BaseModel):
    waiting: int
    mine: int
    history: int
    returned: int
