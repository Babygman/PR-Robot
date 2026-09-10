"""split can_view_all pr ar

Full RBAC Correction 2 (แยก can_view_all ตาม PR/AR, 2026-09-10) — ผู้ใช้แจ้งว่า Field
`can_view_all` เดียวรวม PR+AR สับสน "ต้องแยก PR และ AR ออกจากกันด้วย" — แยกเป็น 2 Field:
- `can_view_all_pr`: เห็น PR ของทุกคน (ขอบเขตเดิมของ can_view_all ฝั่ง PR)
- `can_view_all_ar`: เห็น AR List ของทุกคน (ขอบเขตเดิมของ can_view_all ฝั่ง AR)

Data Migration: คัดลอกค่า `can_view_all` เดิมของทุกแถวไปยังทั้ง 2 Field ใหม่เหมือนกันทุก
ประการ (รักษาพฤติกรรมเดิมทุกคนที่ Admin เคยติ๊ก "เห็นทั้งหมด" ไว้แล้วบน UAT ให้เห็นทั้ง PR
และ AR ทั้งหมดเหมือนเดิมหลัง Migrate — ไม่ตัดสิทธิ์ใครโดยไม่ตั้งใจ) Admin ไปแยกปรับละเอียด
เป็นรายคนทีหลังได้จากหน้า "จัดการ User"

Revision ID: f7b3e9c1a6d5
Revises: c3d7f1a9e4b2
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f7b3e9c1a6d5"
down_revision = "c3d7f1a9e4b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_view_all_pr", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("can_view_all_ar", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Data Migration: คัดลอกค่าเดิมของ can_view_all ไปยังทั้ง 2 Field ใหม่ — ดู Docstring
    # บนสุดของไฟล์นี้
    users_table = sa.table(
        "users",
        sa.column("can_view_all", sa.Boolean()),
        sa.column("can_view_all_pr", sa.Boolean()),
        sa.column("can_view_all_ar", sa.Boolean()),
    )
    op.execute(
        users_table.update().values(
            can_view_all_pr=users_table.c.can_view_all,
            can_view_all_ar=users_table.c.can_view_all,
        )
    )

    op.drop_column("users", "can_view_all")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_view_all", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    users_table = sa.table(
        "users",
        sa.column("can_view_all", sa.Boolean()),
        sa.column("can_view_all_pr", sa.Boolean()),
        sa.column("can_view_all_ar", sa.Boolean()),
    )
    # รวมกลับ: True ถ้าฝั่งใดฝั่งหนึ่งเคยเป็น True (ป้องกันข้อมูลหายตอน Downgrade)
    op.execute(
        users_table.update().values(
            can_view_all=sa.or_(users_table.c.can_view_all_pr, users_table.c.can_view_all_ar)
        )
    )
    op.drop_column("users", "can_view_all_ar")
    op.drop_column("users", "can_view_all_pr")
