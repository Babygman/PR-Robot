"""audit log ip address

Electronic Signature Hardening (Design §3.2, 2026-09-15) — audit_log เดิม (PR/AR)
ยังไม่มี ip_address ต่างจาก system_logs ที่เพิ่มไปแล้ว (Migration f2b8d4a6c1e7) เพิ่ม
คอลัมน์เดียวกันให้ audit_log ด้วย เพื่อบันทึก "ที่ไหน" ของทุกจุดที่เป็นการ "เซ็น" จริง
(PR: submitted_for_approval/budget_level_approved/budget_level_rejected/finalized, AR:
submitted_for_approval/budget_level_approved/budget_level_rejected/finalized/
budget_fa_acknowledged/budget_fa_rejected — ดู app/api/routes/purchasing_requisitions.py,
app/api/routes/approval_requests.py) จุดอื่นที่เขียน audit_log (Attachment, Updated Log
ทั่วไป) ยังคง NULL ตามเดิม ไม่ได้ Backfill ย้อนหลัง (ไม่มีข้อมูล IP ของอดีตให้ Backfill)

Revision ID: a7c3f1e9b5d2
Revises: d4f8a2c6e9b3
Create Date: 2026-09-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c3f1e9b5d2"
down_revision = "d4f8a2c6e9b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("ip_address", sa.String(length=45), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_log", "ip_address")
