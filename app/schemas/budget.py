"""Schema สำหรับ Budget Control (Phase 10, 2026-09-09, Business Decision v4.1)

ครอบคลุม: Budget Master (ยอดงบจาก Excel), Budget Upload (Preview/Confirm/History),
Level Management, และผลลัพธ์ Audit การอนุมัติแต่ละ Level/FA Acknowledge
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.approval_request import ARBudgetType
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
    """Body ว่างเปล่าได้ (ไม่มี Field บังคับ) — เผื่ออนาคตอยากแนบ Comment ก็ขยายตรงนี้"""

    pass


class BudgetFaAcknowledgeBody(BaseModel):
    force: bool = False
