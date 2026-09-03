"""revise finalized pr: add revision + revised_from_id, pr_no+revision unique

Revision ID: b3e7a1c9d5f2
Revises: a1c3e9f0b2d4
Create Date: 2026-09-03 00:00:00.000000

Feedback จริงจากผู้ใช้ (2026-09-03): PR ที่ Finalized (พิมพ์ไปแล้ว) ทุกใบต้องมีทาง
แก้ไขต่อได้เมื่อพบข้อผิดพลาดทีหลัง โดยไม่ไปรื้อของเดิมที่เซ็นกระดาษไปแล้ว —
ตัดสินใจ (อนุมัติจากผู้ใช้): เลข PR ของฉบับ Revise ใช้เลขเดิม + Rev ต่อท้าย (เช่น
"PR 3 Rev.1") ไม่ใช่เลข PR ใหม่ทั้งหมด

การเปลี่ยนแปลง:
1. purchasing_requisitions.revision (Integer, Default 0) — 0 = ต้นฉบับ, 1/2/3/...
   = Revise ครั้งที่เท่าไร
2. purchasing_requisitions.revised_from_id (FK ชี้ตัวเอง, Nullable) — ต้นฉบับที่
   Revise ฉบับนี้มา (Null สำหรับ PR ต้นฉบับที่ไม่เคยถูก Revise มาจากอะไร)
3. Unique Constraint เปลี่ยนจาก pr_no เดี่ยว เป็นคู่ (pr_no, revision) — เพราะ pr_no
   ใช้ซ้ำกันได้ระหว่าง PR ต้นฉบับกับฉบับ Revise ของมันแล้ว

ข้อมูลเดิมทั้งหมดได้ revision=0 อัตโนมัติ (Server Default) ไม่กระทบ PR ที่มีอยู่แล้ว
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b3e7a1c9d5f2"
down_revision = "a1c3e9f0b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchasing_requisitions",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "purchasing_requisitions",
        sa.Column("revised_from_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "purchasing_requisitions_revised_from_id_fkey",
        "purchasing_requisitions",
        "purchasing_requisitions",
        ["revised_from_id"],
        ["id"],
    )

    # pr_no เดี่ยวเคย Unique — ตอนนี้ต้องใช้ซ้ำกันได้ระหว่าง PR ต้นฉบับกับฉบับ Revise
    # (revision ต่างกัน) จึงต้อง Drop Unique Index เดิม แล้วสร้างใหม่เป็น Plain Index
    # (คงไว้เพื่อ Performance การค้นหา) + Unique Constraint แบบคู่ (pr_no, revision) แทน
    op.drop_index("ix_purchasing_requisitions_pr_no", table_name="purchasing_requisitions")
    op.create_index(
        "ix_purchasing_requisitions_pr_no", "purchasing_requisitions", ["pr_no"], unique=False
    )
    op.create_unique_constraint(
        "uq_pr_no_revision", "purchasing_requisitions", ["pr_no", "revision"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_pr_no_revision", "purchasing_requisitions", type_="unique"
    )
    op.drop_index("ix_purchasing_requisitions_pr_no", table_name="purchasing_requisitions")
    op.create_index(
        "ix_purchasing_requisitions_pr_no", "purchasing_requisitions", ["pr_no"], unique=True
    )

    op.drop_constraint(
        "purchasing_requisitions_revised_from_id_fkey",
        "purchasing_requisitions",
        type_="foreignkey",
    )
    op.drop_column("purchasing_requisitions", "revised_from_id")
    op.drop_column("purchasing_requisitions", "revision")
