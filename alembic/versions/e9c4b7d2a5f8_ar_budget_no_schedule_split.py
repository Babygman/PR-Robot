"""ar budget no schedule split

Feedback จริงจากผู้ใช้หลังทดสอบใช้งาน Approval Request บน UAT ครั้งแรก (2026-09-08):
1. เพิ่มคอลัมน์ approval_requests.budget_no (รหัส/เลขที่บัญชีงบประมาณ — Text กรอกอิสระ
   ไม่บังคับ ไม่มีในฟอร์มตัวอย่างต้นฉบับแยกจาก Expenses/Assets แต่ผู้ใช้ต้องการ Field
   แยกต่างหาก)
2. เดิม approval_requests.schedule เป็นช่อง Text เดียว "Schedule Start - Finish" —
   ผู้ใช้ต้องการแยกเป็น 2 ช่องวันที่ (Date Picker) แทน ยกเลิกคอลัมน์เดิม เพิ่ม
   schedule_start / schedule_finish

Migration นี้ไม่แตะ Enum Type ใดๆ เลย (budget_no/schedule_start/schedule_finish เป็น
String/Date ธรรมดา) จึงไม่มีความเสี่ยงจากบั๊ก Duplicate CREATE TYPE ที่เจอตอนสร้าง
d4a8c2f1b6e3 — แต่ก็ยังตรวจสอบด้วย `alembic upgrade --sql` เป็น Dry-run ก่อน Deploy
จริงเสมอ (Lesson จากบั๊กนั้น)

Revision ID: e9c4b7d2a5f8
Revises: d4a8c2f1b6e3
Create Date: 2026-09-08
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e9c4b7d2a5f8"
down_revision = "d4a8c2f1b6e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("budget_no", sa.String(100), nullable=True))
    op.add_column("approval_requests", sa.Column("schedule_start", sa.Date(), nullable=True))
    op.add_column("approval_requests", sa.Column("schedule_finish", sa.Date(), nullable=True))
    op.drop_column("approval_requests", "schedule")


def downgrade() -> None:
    op.add_column("approval_requests", sa.Column("schedule", sa.Text(), nullable=True))
    op.drop_column("approval_requests", "schedule_finish")
    op.drop_column("approval_requests", "schedule_start")
    op.drop_column("approval_requests", "budget_no")
