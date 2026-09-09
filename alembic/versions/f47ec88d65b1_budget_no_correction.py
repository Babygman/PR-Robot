"""budget master: budget_no correction

Correction ต่อจาก a7d3f9c1b4e8 (Business Decision v4.1) — พบว่าออกแบบผิด: สมมติว่า
`account_code` คือ Key เดียวกับช่อง "Budget No." ในฟอร์ม AR ทั้งที่จริงเป็นคนละแนวคิด
(ผู้ใช้ยืนยันด้วยตัวอย่างข้อมูลจริง 2026-09-09: account_code เช่น 5100 ใช้ซ้ำได้หลาย
แถวงบประมาณ เช่น BG0001/BG0002 มี account_code=5100 เหมือนกันแต่เป็นคนละรายการงบ)

การเปลี่ยนแปลง:
1. เพิ่มคอลัมน์ `budget_no` ใน budget_master — Key จริงที่ไม่ซ้ำกัน (Global ไม่ผูก
   แผนก) ตรงกับช่อง "Budget No." ของ AR แบบ 1:1 ตรงๆ (แทน account_code เดิม)
2. ยกเลิก Unique Constraint เดิม (department+budget_type+account_code+period) —
   account_code ไม่ใช่ Key อีกต่อไป เป็นแค่รหัสบัญชี/หมวดหมู่ ซ้ำกันได้ตามจริง
3. เพิ่ม Unique Constraint + Index บน budget_no เดี่ยว
4. เพิ่ม Index ธรรมดาบน account_code (ยังใช้ค้นหา/กรองบ่อยแม้ไม่ใช่ Key แล้ว)

ตาราง budget_master ยังว่างอยู่จริงในทุก Environment ที่ Deploy ไปแล้ว (Feature เพิ่ง
ขึ้น UAT ไม่กี่นาทีก่อนพบปัญหานี้ ยังไม่มีใคร Upload Excel จริง) แต่ Migration นี้ยัง
เขียนแบบปลอดภัยรองรับกรณีมีแถวหลงเหลืออยู่ (Backfill ก่อน Set Not Null)

Revision ID: f47ec88d65b1
Revises: a7d3f9c1b4e8
Create Date: 2026-09-09
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f47ec88d65b1"
down_revision = "a7d3f9c1b4e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) เพิ่มคอลัมน์แบบ Nullable ก่อน (ตารางว่างอยู่จริง แต่เขียนแบบปลอดภัยไว้ก่อน)
    op.add_column("budget_master", sa.Column("budget_no", sa.String(50), nullable=True))

    # 2) Backfill กันพลาด เผื่อมีแถวทดสอบหลงเหลืออยู่จริง (ไม่ควรมี) — ใช้ id เป็น
    #    Placeholder ชั่วคราว ผู้ดูแลต้องแก้เป็นเลขจริงเองถ้าเจอกรณีนี้
    bind.execute(
        sa.text(
            "UPDATE budget_master SET budget_no = 'LEGACY-' || id::text WHERE budget_no IS NULL"
        )
    )

    # 3) ยกเลิก Unique Constraint เดิมที่ผูก account_code (ไม่ใช่ Key อีกต่อไป)
    op.drop_constraint("uq_budget_master_dept_type_code_period", "budget_master", type_="unique")

    # 4) budget_no เป็น Key ตัวจริง — Not Null + Unique + Index
    op.alter_column("budget_master", "budget_no", nullable=False)
    op.create_unique_constraint("uq_budget_master_budget_no", "budget_master", ["budget_no"])
    op.create_index("ix_budget_master_budget_no", "budget_master", ["budget_no"])

    # 5) account_code ไม่ใช่ Key แล้ว แต่ยังค้นหา/กรองบ่อย เพิ่ม Index ธรรมดา
    op.create_index("ix_budget_master_account_code", "budget_master", ["account_code"])


def downgrade() -> None:
    op.drop_index("ix_budget_master_account_code", table_name="budget_master")
    op.drop_index("ix_budget_master_budget_no", table_name="budget_master")
    op.drop_constraint("uq_budget_master_budget_no", "budget_master", type_="unique")
    op.create_unique_constraint(
        "uq_budget_master_dept_type_code_period",
        "budget_master",
        ["department", "budget_type", "account_code", "period_start", "period_end"],
    )
    op.drop_column("budget_master", "budget_no")
