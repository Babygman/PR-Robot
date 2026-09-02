"""Schema สำหรับบันทึก PR (Phase 5)

Requested/Reviewed/Approved/Received by ไม่มีในนี้โดยเจตนา — เป็นผู้ใช้ที่ Login ตอนทำ
Action นั้นเสมอ (Business Decision 2026-09-01) ไม่ใช่ข้อมูลที่รับจาก Client
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.purchasing_requisition import PRStatus


class PRItemCreate(BaseModel):
    """ไม่มี item_no ในนี้โดยเจตนา — Server กำหนดลำดับตามตำแหน่งใน List ให้เอง (1..N)"""

    account_code: str | None = None
    description: str
    quantity: str | None = None
    required_date: date | None = None
    reason: str | None = None
    ref_po: str | None = None


class PRBudgetControlCreate(BaseModel):
    account_code_1: str | None = None
    account_code_2: str | None = None
    budget: Decimal | None = None
    used_before_amount: Decimal | None = None
    this_application: Decimal | None = None
    balance: Decimal | None = None


class PRCreate(BaseModel):
    section: str
    division: str
    doc_date: date
    items: list[PRItemCreate] = Field(min_length=1)
    budget_control: PRBudgetControlCreate | None = None
    remark: str | None = None
    source_document_ids: list[int] = Field(default_factory=list)


class PRUpdate(BaseModel):
    """แก้ไขได้เฉพาะตอน Status = draft เท่านั้น — แทนที่ items/budget_control ทั้งชุด"""

    section: str
    division: str
    doc_date: date
    items: list[PRItemCreate] = Field(min_length=1)
    budget_control: PRBudgetControlCreate | None = None
    remark: str | None = None


class PRItemRead(BaseModel):
    id: int
    item_no: int
    account_code: str | None
    description: str
    quantity: str | None
    required_date: date | None
    reason: str | None
    ref_po: str | None

    model_config = {"from_attributes": True}


class PRBudgetControlRead(BaseModel):
    account_code_1: str | None
    account_code_2: str | None
    budget: Decimal | None
    used_before_amount: Decimal | None
    this_application: Decimal | None
    balance: Decimal | None

    model_config = {"from_attributes": True}


class PRRead(BaseModel):
    id: int
    pr_no: int
    section: str
    division: str
    doc_date: date
    status: PRStatus
    requested_by_id: int
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    approved_by_id: int | None
    approved_at: datetime | None
    received_by_id: int | None
    received_at: datetime | None
    remark: str | None
    items: list[PRItemRead]
    budget_control: PRBudgetControlRead | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PRListItem(BaseModel):
    id: int
    pr_no: int
    section: str
    division: str
    doc_date: date
    status: PRStatus
    requested_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
