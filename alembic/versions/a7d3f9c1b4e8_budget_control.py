"""budget control

เพิ่มโมดูล Budget Control ใหม่ทั้งหมด — Business Decision 2026-09-09 (v4.1) ตามที่
ผู้ใช้อนุมัติ Design ไว้ (ดู docs/drafts/budget_control_design_draft.md) ขอบเขต:
เฉพาะ Approval Request (AR) เท่านั้น ไม่แตะ PR เลย

การเปลี่ยนแปลง:
1. users: เพิ่ม position (String, Nullable), is_fa (Boolean, default False)
2. เพิ่มตาราง budget_upload_batches / budget_upload_row_errors (Log การ Upload Excel)
3. เพิ่มตาราง budget_master (ยอดงบประมาณจาก Excel — used_amount หักด้วย Atomic
   UPDATE เท่านั้น)
4. เพิ่มตาราง budget_approval_levels (Level Management — ยืดหยุ่นต่อแผนก ผู้อนุมัติ
   ผูกกับบุคคลเจาะจง)
5. approval_requests: เพิ่ม budget_master_id (FK), budget_approval_status (Enum),
   current_approval_level (Integer), budget_deducted_amount (Numeric),
   budget_overridden (Boolean)
6. เพิ่มตาราง ar_budget_approvals (Audit Trail การอนุมัติ/ปฏิเสธแต่ละ Level + FA
   Acknowledge — ใช้ Auto-fill ตาราง Authority/ช่อง F&A ใน PDF ด้วย)

Migration นี้สร้าง Enum Type ใหม่ 3 ตัว (ar_budget_approval_status,
budget_approval_step_type, budget_approval_action) — ตาม Pattern เดียวกับ
d4a8c2f1b6e3 ทุกประการ (สร้าง Enum แยกก่อนด้วย checkfirst=True แล้วปิด Auto-Create
ตอน op.create_table/add_column ด้วย create_type=False กัน DuplicateObject บน
PostgreSQL จริง — ยืนยันด้วย `alembic upgrade head --sql` เป็น Dry-run เสมอ)

Revision ID: a7d3f9c1b4e8
Revises: e9c4b7d2a5f8
Create Date: 2026-09-09
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a7d3f9c1b4e8"
down_revision = "e9c4b7d2a5f8"
branch_labels = None
depends_on = None

ar_budget_type_col = postgresql.ENUM("expenses", "assets", name="ar_budget_type", create_type=False)

ar_budget_approval_status_enum = sa.Enum(
    "not_submitted",
    "pending",
    "pending_fa_acknowledge",
    "approved",
    "rejected",
    name="ar_budget_approval_status",
)
budget_approval_step_type_enum = sa.Enum("level", "fa_acknowledge", name="budget_approval_step_type")
budget_approval_action_enum = sa.Enum("approved", "rejected", name="budget_approval_action")


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1) users: position / is_fa ──
    op.add_column("users", sa.Column("position", sa.String(100), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_fa", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ── 2) budget_upload_batches ──
    op.create_table(
        "budget_upload_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column(
            "uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
    )

    # ── 3) budget_upload_row_errors ──
    op.create_table(
        "budget_upload_row_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("budget_upload_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
    )

    # ── 4) budget_master ── (ใช้ Enum ar_budget_type ที่มีอยู่แล้วจาก d4a8c2f1b6e3)
    op.create_table(
        "budget_master",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(255), nullable=False),
        sa.Column("budget_type", ar_budget_type_col, nullable=False),
        sa.Column("account_code", sa.String(100), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("budget_name", sa.String(255), nullable=True),
        sa.Column("budgeted_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("used_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column(
            "updated_by_batch_id",
            sa.Integer(),
            sa.ForeignKey("budget_upload_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint(
            "department",
            "budget_type",
            "account_code",
            "period_start",
            "period_end",
            name="uq_budget_master_dept_type_code_period",
        ),
    )
    op.create_index("ix_budget_master_department", "budget_master", ["department"])

    # ── 5) budget_approval_levels ──
    op.create_table(
        "budget_approval_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(255), nullable=False),
        sa.Column("level_no", sa.Integer(), nullable=False),
        sa.Column("level_name", sa.String(100), nullable=False),
        sa.Column("approver_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("department", "level_no", name="uq_budget_level_dept_level_no"),
    )
    op.create_index("ix_budget_approval_levels_department", "budget_approval_levels", ["department"])

    # ── 6) approval_requests: Field ใหม่ 5 ตัว ──
    ar_budget_approval_status_enum.create(bind, checkfirst=True)
    ar_budget_approval_status_col = postgresql.ENUM(
        "not_submitted",
        "pending",
        "pending_fa_acknowledge",
        "approved",
        "rejected",
        name="ar_budget_approval_status",
        create_type=False,
    )
    op.add_column("approval_requests", sa.Column("budget_department", sa.String(255), nullable=True))
    op.add_column(
        "approval_requests",
        sa.Column(
            "budget_master_id",
            sa.Integer(),
            sa.ForeignKey("budget_master.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column(
            "budget_approval_status",
            ar_budget_approval_status_col,
            nullable=False,
            server_default="not_submitted",
        ),
    )
    op.add_column("approval_requests", sa.Column("current_approval_level", sa.Integer(), nullable=True))
    op.add_column(
        "approval_requests", sa.Column("budget_deducted_amount", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column(
        "approval_requests",
        sa.Column("budget_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # ── 7) ar_budget_approvals ──
    budget_approval_step_type_enum.create(bind, checkfirst=True)
    budget_approval_action_enum.create(bind, checkfirst=True)
    step_type_col = postgresql.ENUM(
        "level", "fa_acknowledge", name="budget_approval_step_type", create_type=False
    )
    action_col = postgresql.ENUM("approved", "rejected", name="budget_approval_action", create_type=False)
    op.create_table(
        "ar_budget_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ar_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_type", step_type_col, nullable=False),
        sa.Column("level_no", sa.Integer(), nullable=True),
        sa.Column("level_name_snapshot", sa.String(100), nullable=True),
        sa.Column("action", action_col, nullable=False),
        sa.Column("acted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("acted_as_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ar_budget_approvals_ar_id", "ar_budget_approvals", ["ar_id"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_ar_budget_approvals_ar_id", table_name="ar_budget_approvals")
    op.drop_table("ar_budget_approvals")
    budget_approval_action_enum.drop(bind, checkfirst=True)
    budget_approval_step_type_enum.drop(bind, checkfirst=True)

    op.drop_column("approval_requests", "budget_overridden")
    op.drop_column("approval_requests", "budget_deducted_amount")
    op.drop_column("approval_requests", "current_approval_level")
    op.drop_column("approval_requests", "budget_approval_status")
    ar_budget_approval_status_enum.drop(bind, checkfirst=True)
    op.drop_column("approval_requests", "budget_master_id")
    op.drop_column("approval_requests", "budget_department")

    op.drop_index("ix_budget_approval_levels_department", table_name="budget_approval_levels")
    op.drop_table("budget_approval_levels")

    op.drop_index("ix_budget_master_department", table_name="budget_master")
    op.drop_table("budget_master")

    op.drop_table("budget_upload_row_errors")
    op.drop_table("budget_upload_batches")

    op.drop_column("users", "is_fa")
    op.drop_column("users", "position")
