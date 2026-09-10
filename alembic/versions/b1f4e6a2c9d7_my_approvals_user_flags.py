"""my approvals user flags

Phase B/2 (2026-09-10) — เพิ่ม 2 Column ใน users รองรับเมนู "การอนุมัติของฉัน" (My
Approvals) ตาม Mockup v4 ที่ผู้ใช้ Confirm แล้ว — ดู Docstring app/models/user.py สำหรับ
ความหมายแต่ละ Field:
- can_view_approvals: เปิดเมนู "การอนุมัติของฉัน" ให้เห็น (is_admin/is_fa เห็นอยู่แล้ว
  เสมอโดยไม่ต้องเปิด Field นี้)
- approver_only: True = ซ่อนเมนูอื่นทั้งหมดใน Sidebar เหลือแค่เมนูนี้อย่างเดียว

Revision ID: b1f4e6a2c9d7
Revises: a8cc4abbaa59
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b1f4e6a2c9d7"
down_revision = "a8cc4abbaa59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_view_approvals", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("approver_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "approver_only")
    op.drop_column("users", "can_view_approvals")
