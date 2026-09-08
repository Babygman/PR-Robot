"""Schema สำหรับบันทึก Approval Request (AR) — Pattern เดียวกับ
app/schemas/purchasing_requisition.py ทุกประการ

Requested by ไม่มีในนี้โดยเจตนา — เป็นผู้ใช้ที่ Login ตอนสร้าง AR เสมอ (Pattern
เดียวกับ PR — Business Decision 2026-09-01 ที่ยึดถือมาตลอด) ไม่ใช่ข้อมูลที่รับจาก
Client — ช่องลายเซ็น/อนุมัติทั้ง 5 ช่อง (President/Director, General Manager,
Senior Manager, Manager, F&A) ก็ไม่มีในนี้เช่นกัน เพราะเป็นลายเซ็นสดบนกระดาษล้วนๆ
ไม่ผูกกับข้อมูลในระบบ (ดู ar_form.html)
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.approval_request import ARBudgetType, ARStatus


class ARAmountItemCreate(BaseModel):
    """ไม่มี item_no ในนี้โดยเจตนา — Server กำหนดลำดับตามตำแหน่งใน List ให้เอง (1..N)
    เหมือน PRItemCreate"""

    label: str
    amount: Decimal | None = None


class ARCreate(BaseModel):
    application_date: date
    subject: str
    budget_type: ARBudgetType
    budget_sub_category: str | None = None
    budget_name: str | None = None
    budget_for_year: Decimal | None = None
    amount_used_before: Decimal | None = None
    this_application: Decimal | None = None
    balance: Decimal | None = None
    description: str | None = None
    amount_items: list[ARAmountItemCreate] = Field(default_factory=list)
    total: Decimal | None = None
    vat_amount: Decimal | None = None
    grand_total: Decimal | None = None
    suppliers: str | None = None
    term_of_payment: str | None = None
    schedule: str | None = None


class ARUpdate(BaseModel):
    """แก้ไขได้เฉพาะตอน Status = draft เท่านั้น — แทนที่ amount_items ทั้งชุด (Pattern
    เดียวกับ PRUpdate)"""

    application_date: date
    subject: str
    budget_type: ARBudgetType
    budget_sub_category: str | None = None
    budget_name: str | None = None
    budget_for_year: Decimal | None = None
    amount_used_before: Decimal | None = None
    this_application: Decimal | None = None
    balance: Decimal | None = None
    description: str | None = None
    amount_items: list[ARAmountItemCreate] = Field(default_factory=list)
    total: Decimal | None = None
    vat_amount: Decimal | None = None
    grand_total: Decimal | None = None
    suppliers: str | None = None
    term_of_payment: str | None = None
    schedule: str | None = None


class ARAmountItemRead(BaseModel):
    id: int
    item_no: int
    label: str
    amount: Decimal | None

    model_config = {"from_attributes": True}


class ARRead(BaseModel):
    id: int
    ar_no: int
    ar_no_display: str = ""  # เติมใน Route (ไม่ใช่คอลัมน์จริง) — รูปแบบ "AR-0001"
    revision: int
    revised_from_id: int | None = None
    superseded_by_id: int | None = None
    application_date: date
    subject: str
    budget_type: ARBudgetType
    budget_sub_category: str | None
    budget_name: str | None
    budget_for_year: Decimal | None
    amount_used_before: Decimal | None
    this_application: Decimal | None
    balance: Decimal | None
    description: str | None
    amount_items: list[ARAmountItemRead]
    total: Decimal | None
    vat_amount: Decimal | None
    grand_total: Decimal | None
    suppliers: str | None
    term_of_payment: str | None
    schedule: str | None
    status: ARStatus
    requested_by_id: int
    requested_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ARListItem(BaseModel):
    id: int
    ar_no: int
    ar_no_display: str = ""
    revision: int
    subject: str
    application_date: date
    status: ARStatus
    requested_by_id: int
    created_at: datetime

    model_config = {"from_attributes": True}
