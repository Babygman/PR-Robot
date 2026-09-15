"""pr approval workflow

Business Decision 2026-09-15: นำ Workflow อนุมัติของ PR กลับมาเป็น Digital ผ่าน Budget
Approval Level แบบเดียวกับ AR (ยืดหยุ่นต่อแผนก, หลายคนต่อ Level แบบ OR) แต่แยกตาราง
Level ออกจาก AR เต็มรูปแบบ (pr_approval_levels/pr_budget_approvals ไม่ใช้ร่วมกับ
budget_approval_levels/ar_budget_approvals เลย) — ไม่มี FA Acknowledge (Level สุดท้าย
อนุมัติ = หักงบจริงทันที) และไม่มีขั้น Received แยก — ดู Docstring เต็มใน
app/models/purchasing_requisition.py และ app/models/pr_budget.py

**ก่อนรัน Migration นี้บน Server จริง ต้องลบข้อมูล PR เก่าทั้งหมดก่อน** (คำสั่งแยกที่
Server — purchasing_requisitions/pr_items/pr_budget_control/source_documents ที่ผูกกับ
PR เหล่านั้น) ตามที่ผู้ใช้อนุมัติไว้ (2026-09-15) เพราะ Schema ของ pr_budget_control
เปลี่ยนความหมายไปเยอะ (account_code_1/2/budget/used_before_amount/balance ถูกลบทิ้ง)
ไม่คุ้มที่จะพยายาม Backward-compat ข้อมูลเก่า — Migration นี้เอง "ไม่ได้" ลบข้อมูลอัตโนมัติ
(เพื่อความปลอดภัย ให้ Rachin สั่งลบเองแยกต่างหากก่อน Deploy เท่านั้น)

การเปลี่ยนแปลง:
1. pr_budget_control: ลบคอลัมน์ account_code_1, account_code_2, budget,
   used_before_amount, balance (แทนที่ด้วยการอ่านสดจาก budget_master ผ่าน
   budget_master_id ตอนแสดงผล) — เพิ่ม budget_no, account_code (Snapshot),
   budget_master_id (FK), budget_department (Snapshot), budget_approval_status
   (Enum ใหม่ pr_budget_approval_status), current_approval_level,
   budget_deducted_amount, budget_overridden — this_application คงเดิมไม่เปลี่ยน
2. เพิ่มตาราง pr_approval_levels (Structure เดียวกับ budget_approval_levels ของ AR)
3. เพิ่มตาราง pr_budget_approvals (Audit Trail — Reuse Enum budget_approval_action
   เดิมของ AR ตรงๆ ไม่สร้าง Type ใหม่ซ้ำ เพราะมีอยู่แล้วจาก a7d3f9c1b4e8)
4. เพิ่มตาราง pr_attachments (Structure เดียวกับ ar_attachments ของ AR)

Enum Type ใหม่ที่สร้างใน Migration นี้: เฉพาะ pr_budget_approval_status ตัวเดียว
(budget_approval_action Reuse ของเดิม สร้างด้วย create_type=False)

Revision ID: b3e7f2a9c5d1
Revises: a9c3e5f7b1d2
Create Date: 2026-09-15
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b3e7f2a9c5d1"
down_revision = "a9c3e5f7b1d2"
branch_labels = None
depends_on = None

pr_budget_approval_status_enum = sa.Enum(
    "not_submitted",
    "pending",
    "approved",
    "rejected",
    name="pr_budget_approval_status",
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1) pr_budget_control: ลบคอลัมน์เก่า + เพิ่มคอลัมน์ใหม่ ──
    op.drop_column("pr_budget_control", "account_code_1")
    op.drop_column("pr_budget_control", "account_code_2")
    op.drop_column("pr_budget_control", "budget")
    op.drop_column("pr_budget_control", "used_before_amount")
    op.drop_column("pr_budget_control", "balance")

    op.add_column("pr_budget_control", sa.Column("budget_no", sa.String(50), nullable=True))
    op.add_column("pr_budget_control", sa.Column("account_code", sa.String(100), nullable=True))
    op.add_column(
        "pr_budget_control",
        sa.Column(
            "budget_master_id",
            sa.Integer(),
            sa.ForeignKey("budget_master.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("pr_budget_control", sa.Column("budget_department", sa.String(255), nullable=True))

    pr_budget_approval_status_enum.create(bind, checkfirst=True)
    pr_budget_approval_status_col = postgresql.ENUM(
        "not_submitted",
        "pending",
        "approved",
        "rejected",
        name="pr_budget_approval_status",
        create_type=False,
    )
    op.add_column(
        "pr_budget_control",
        sa.Column(
            "budget_approval_status",
            pr_budget_approval_status_col,
            nullable=False,
            server_default="not_submitted",
        ),
    )
    op.add_column(
        "pr_budget_control", sa.Column("current_approval_level", sa.Integer(), nullable=True)
    )
    op.add_column(
        "pr_budget_control", sa.Column("budget_deducted_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "pr_budget_control",
        sa.Column("budget_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ── 2) pr_approval_levels ──
    op.create_table(
        "pr_approval_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(255), nullable=False),
        sa.Column("level_no", sa.Integer(), nullable=False),
        sa.Column("level_name", sa.String(100), nullable=False),
        sa.Column("approver_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint(
            "department", "level_no", "approver_user_id", name="uq_pr_level_dept_level_no_approver"
        ),
    )
    op.create_index("ix_pr_approval_levels_department", "pr_approval_levels", ["department"])

    # ── 3) pr_budget_approvals ── (Reuse Enum budget_approval_action เดิมของ AR)
    action_col = postgresql.ENUM("approved", "rejected", name="budget_approval_action", create_type=False)
    op.create_table(
        "pr_budget_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level_no", sa.Integer(), nullable=False),
        sa.Column("level_name_snapshot", sa.String(100), nullable=True),
        sa.Column("action", action_col, nullable=False),
        sa.Column("acted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acted_as_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pr_budget_approvals_pr_id", "pr_budget_approvals", ["pr_id"])

    # ── 4) pr_attachments ──
    op.create_table(
        "pr_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_table("pr_attachments")

    op.drop_index("ix_pr_budget_approvals_pr_id", table_name="pr_budget_approvals")
    op.drop_table("pr_budget_approvals")

    op.drop_index("ix_pr_approval_levels_department", table_name="pr_approval_levels")
    op.drop_table("pr_approval_levels")

    op.drop_column("pr_budget_control", "budget_overridden")
    op.drop_column("pr_budget_control", "budget_deducted_amount")
    op.drop_column("pr_budget_control", "current_approval_level")
    op.drop_column("pr_budget_control", "budget_approval_status")
    pr_budget_approval_status_enum.drop(bind, checkfirst=True)
    op.drop_column("pr_budget_control", "budget_department")
    op.drop_column("pr_budget_control", "budget_master_id")
    op.drop_column("pr_budget_control", "account_code")
    op.drop_column("pr_budget_control", "budget_no")

    op.add_column("pr_budget_control", sa.Column("balance", sa.Numeric(14, 2), nullable=True))
    op.add_column("pr_budget_control", sa.Column("used_before_amount", sa.Numeric(14, 2), nullable=True))
    op.add_column("pr_budget_control", sa.Column("budget", sa.Numeric(14, 2), nullable=True))
    op.add_column("pr_budget_control", sa.Column("account_code_2", sa.String(100), nullable=True))
    op.add_column("pr_budget_control", sa.Column("account_code_1", sa.String(100), nullable=True))
