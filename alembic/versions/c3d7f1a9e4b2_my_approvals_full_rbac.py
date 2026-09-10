"""my approvals full rbac

Full RBAC (Correction 2026-09-10) — ขยายจาก Phase B/2 เดิมเป็นระบบสิทธิ์เต็มรูปแบบตาม
Matrix Admin/FA/Approve/PR/AR/ALL ที่ผู้ใช้ยืนยัน (ดู Docstring app/models/user.py สำหรับ
ความหมายแต่ละ Field):
- ตัด `approver_only` ออก (ไม่ได้ใช้แล้ว — Mockup ล่าสุดไม่มีคอลัมน์นี้)
- เพิ่ม `can_view_pr`, `can_view_ar`, `can_view_all`

Data Migration: User Active เดิมทุกคนได้ can_view_pr/can_view_ar/can_view_all = True ให้
อัตโนมัติ เพราะระบบเดิมไม่เคยมีการจำกัดขอบเขต PR/AR เลย (ทุกคนเห็นของทุกคนอยู่แล้ว) —
ป้องกันไม่ให้ Deploy ครั้งนี้ตัดสิทธิ์ที่ทุกคนใช้งานอยู่ทันที Admin ไปติ๊กเอาออกทีหลังสำหรับ
คนที่ต้องการจำกัดให้เห็นแค่ของตัวเอง — User ที่ไม่ Active จะไม่ได้ 3 สิทธิ์นี้ (ไม่มีผล
ต่อการใช้งานอยู่แล้วเพราะ Login ไม่ได้)

Revision ID: c3d7f1a9e4b2
Revises: b1f4e6a2c9d7
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d7f1a9e4b2"
down_revision = "b1f4e6a2c9d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "approver_only")

    op.add_column(
        "users",
        sa.Column("can_view_pr", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("can_view_ar", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "users",
        sa.Column("can_view_all", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Data Migration: รักษาพฤติกรรมเดิม (เห็น PR/AR ของทุกคน) ให้ User Active ทุกคนที่มีอยู่
    # แล้วก่อน Deploy ครั้งนี้ — ดู Docstring บนสุดของไฟล์นี้
    users_table = sa.table(
        "users",
        sa.column("is_active", sa.Boolean()),
        sa.column("can_view_pr", sa.Boolean()),
        sa.column("can_view_ar", sa.Boolean()),
        sa.column("can_view_all", sa.Boolean()),
    )
    op.execute(
        users_table.update()
        .where(users_table.c.is_active.is_(True))
        .values(can_view_pr=True, can_view_ar=True, can_view_all=True)
    )


def downgrade() -> None:
    op.drop_column("users", "can_view_all")
    op.drop_column("users", "can_view_ar")
    op.drop_column("users", "can_view_pr")
    op.add_column(
        "users",
        sa.Column("approver_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
