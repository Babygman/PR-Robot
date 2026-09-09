"""budget approval level: multi-approver per level (OR)

Correction ต่อจาก f47ec88d65b1 — ผู้ใช้ยืนยันด้วยตัวอย่าง Approve Flow จริงของบริษัท
(2026-09-09) ว่า Level เดียวกันมีผู้อนุมัติได้มากกว่า 1 คน (เช่น Level "President or
Director" ของทุกแผนกมี 3 คนพร้อมกัน: Hori, Ochi, Ukai) — ใครก็ได้ในกลุ่มอนุมัติผ่าน
ถือว่า Level นั้นจบ (OR ไม่ใช่ AND) ระบบเดิม (Business Decision v4.1) รองรับแค่ "1 คน
ต่อ 1 Level ต่อ 1 แผนก" เท่านั้น

การเปลี่ยนแปลง: ยกเลิก Unique Constraint เดิมบน (department, level_no) — ซึ่งบังคับ
ให้ 1 Level มีได้แค่ 1 แถว/1 คน — เปลี่ยนเป็น (department, level_no, approver_user_id)
แทน คือกันแค่ "คนเดียวกันซ้ำในกลุ่มเดียวกัน" ไม่ได้กัน "หลายคนในกลุ่มเดียวกัน" อีกต่อไป

ตาราง budget_approval_levels ยังว่างอยู่จริงทุก Environment (ยังไม่มีแผนกไหนตั้ง Level
อนุมัติเลยตาม Open Item ที่บันทึกไว้ตั้งแต่ Deploy Budget Control ครั้งแรก) จึงไม่ต้อง
Backfill ใดๆ

Revision ID: c58a1f0e93d2
Revises: f47ec88d65b1
Create Date: 2026-09-09
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "c58a1f0e93d2"
down_revision = "f47ec88d65b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_budget_level_dept_level_no", "budget_approval_levels", type_="unique")
    op.create_unique_constraint(
        "uq_budget_level_dept_level_no_approver",
        "budget_approval_levels",
        ["department", "level_no", "approver_user_id"],
    )


def downgrade() -> None:
    # หมายเหตุ: Downgrade จะ Fail ถ้ามี Level ไหนตั้งผู้อนุมัติมากกว่า 1 คนไว้แล้วจริง
    # (Unique Constraint เดิมไม่ยอมให้ department+level_no ซ้ำกัน) — เป็นผลที่ถูกต้องตาม
    # ธรรมชาติของการ Relax Constraint ไม่ใช่บั๊ก (Pattern เดียวกับ f47ec88d65b1)
    op.drop_constraint(
        "uq_budget_level_dept_level_no_approver", "budget_approval_levels", type_="unique"
    )
    op.create_unique_constraint(
        "uq_budget_level_dept_level_no", "budget_approval_levels", ["department", "level_no"]
    )
