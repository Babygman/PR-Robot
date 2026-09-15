"""split can_view_approvals pr ar

Feedback ผู้ใช้ระหว่างรีวิว Phase 4 (PR Approval Level, 2026-09-15): เดิม Flag เดียว
`can_view_approvals` เปิดทั้งเมนู "My AR Approvals" และ "My PR Approvals" พร้อมกันเสมอ
(Reuse ตัวเดียวกันตอนสร้าง PR My Approvals — ดู Docstring app.js เดิม) — ผู้ใช้แจ้งว่า
"ต้องมีเรื่องสิทธ์ Approve PR, Approve AR แยกกัน" (ผู้อนุมัติ Level ของ PR กับ AR อาจเป็น
คนละคนกัน ไม่ควรผูกสิทธิ์เข้าเมนูรวมกันไว้ Field เดียว — Pattern เดียวกับที่เคยแยก
can_view_all -> can_view_all_pr/can_view_all_ar มาก่อนแล้ว) แยกเป็น 2 Field:
- `can_view_pr_approvals`: เปิดเมนู "My PR Approvals" ให้เห็น (Gate จริงที่
  require_can_view_pr_approvals ใน app/core/deps.py)
- `can_view_ar_approvals`: เปิดเมนู "My AR Approvals" ให้เห็น (Gate จริงที่
  require_can_view_ar_approvals ใน app/core/deps.py) — is_fa ยังคงเห็นเมนูนี้ได้เองถ้าติ๊ก
  Field นี้เพิ่ม (ไม่เกี่ยวกับ is_fa โดยตรง เหมือนเดิม)

Data Migration: คัดลอกค่าเดิมของ can_view_approvals ไปยังทั้ง 2 Field ใหม่เหมือนกันทุก
ประการ (รักษาพฤติกรรมเดิมทุกคนที่ Admin เคยติ๊ก "Approve" ไว้แล้วบน UAT ให้เห็นทั้ง My AR
Approvals และ My PR Approvals เหมือนเดิมหลัง Migrate — ไม่ตัดสิทธิ์ใครโดยไม่ตั้งใจ) Admin
ไปแยกปรับละเอียดเป็นรายคนทีหลังได้จากหน้า "จัดการ User"

Revision ID: d4f8a2c6e9b3
Revises: b3e7f2a9c5d1
Create Date: 2026-09-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f8a2c6e9b3"
down_revision = "b3e7f2a9c5d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_view_pr_approvals", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("can_view_ar_approvals", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Data Migration: คัดลอกค่าเดิมของ can_view_approvals ไปยังทั้ง 2 Field ใหม่ — ดู
    # Docstring บนสุดของไฟล์นี้
    users_table = sa.table(
        "users",
        sa.column("can_view_approvals", sa.Boolean()),
        sa.column("can_view_pr_approvals", sa.Boolean()),
        sa.column("can_view_ar_approvals", sa.Boolean()),
    )
    op.execute(
        users_table.update().values(
            can_view_pr_approvals=users_table.c.can_view_approvals,
            can_view_ar_approvals=users_table.c.can_view_approvals,
        )
    )

    op.drop_column("users", "can_view_approvals")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_view_approvals", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    users_table = sa.table(
        "users",
        sa.column("can_view_approvals", sa.Boolean()),
        sa.column("can_view_pr_approvals", sa.Boolean()),
        sa.column("can_view_ar_approvals", sa.Boolean()),
    )
    # รวมกลับ: True ถ้าฝั่งใดฝั่งหนึ่งเคยเป็น True (ป้องกันข้อมูลหายตอน Downgrade)
    op.execute(
        users_table.update().values(
            can_view_approvals=sa.or_(
                users_table.c.can_view_pr_approvals, users_table.c.can_view_ar_approvals
            )
        )
    )
    op.drop_column("users", "can_view_ar_approvals")
    op.drop_column("users", "can_view_pr_approvals")
