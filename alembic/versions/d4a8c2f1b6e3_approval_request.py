"""approval request module

เพิ่มโมดูล Approval Request (AR) ใหม่ทั้งหมด — Business Decision 2026-09-08 ตามที่
ผู้ใช้อนุมัติ Design ไว้ (ฟอร์ม "APPROVAL REQUEST" ของ Sunstar Chemical Thailand,
Template Version "20220404_rev.2")

การเปลี่ยนแปลง:
1. เพิ่มตาราง ar_number_counters (Running Number ต่อเนื่อง, Seed next_value=1)
2. เพิ่มตาราง approval_requests (Header) + ar_amount_items (รายการ Amount & Quantity)
3. เพิ่ม Enum Type ar_status (draft/finalized) และ ar_budget_type (expenses/assets)
4. เพิ่มคอลัมน์ audit_log.ar_id (Nullable, คู่กับ pr_id เดิม — ตารางเดียวใช้ร่วมกัน)

Revision ID: d4a8c2f1b6e3
Revises: c7f2a4b9e1d6
Create Date: 2026-09-08
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d4a8c2f1b6e3"
down_revision = "c7f2a4b9e1d6"
branch_labels = None
depends_on = None

ar_number_counters = sa.table(
    "ar_number_counters",
    sa.column("id", sa.Integer),
    sa.column("next_value", sa.Integer),
)

ar_status_enum = sa.Enum("draft", "finalized", name="ar_status")
ar_budget_type_enum = sa.Enum("expenses", "assets", name="ar_budget_type")


def upgrade() -> None:
    # ── 1) ar_number_counters ──
    op.create_table(
        "ar_number_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
    )
    op.bulk_insert(ar_number_counters, [{"id": 1, "next_value": 1}])

    # ── 2) approval_requests ──
    # สร้าง Enum Type ก่อนแยกต่างหาก แล้วปิด Auto-Create ตอน op.create_table ด้วย
    # create_type=False — Gotcha เดียวกับที่พบตอนสร้าง pr_status ใน
    # cdfbb940153e_pr_core_schema.py (ถ้าไม่ปิด op.create_table จะพยายาม CREATE TYPE
    # ซ้ำกับที่สร้างไปแล้วข้างบน แล้วชน DuplicateObject บน PostgreSQL จริง — pytest
    # Suite รันบน SQLite ซึ่งไม่มี Native ENUM เลยไม่มีทางจับบั๊กนี้ได้ ต้องยืนยันด้วย
    # `alembic upgrade head --sql` แล้วอ่าน SQL ที่ Generate ออกมาตรงๆ เท่านั้น)
    bind = op.get_bind()
    ar_status_enum.create(bind, checkfirst=True)
    ar_budget_type_enum.create(bind, checkfirst=True)
    ar_status_col = postgresql.ENUM("draft", "finalized", name="ar_status", create_type=False)
    ar_budget_type_col = postgresql.ENUM(
        "expenses", "assets", name="ar_budget_type", create_type=False
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ar_no", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "revised_from_id", sa.Integer(), sa.ForeignKey("approval_requests.id"), nullable=True
        ),
        sa.Column("application_date", sa.Date(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("budget_type", ar_budget_type_col, nullable=False),
        sa.Column("budget_sub_category", sa.String(255), nullable=True),
        sa.Column("budget_name", sa.String(255), nullable=True),
        sa.Column("budget_for_year", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_used_before", sa.Numeric(14, 2), nullable=True),
        sa.Column("this_application", sa.Numeric(14, 2), nullable=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("total", sa.Numeric(14, 2), nullable=True),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("grand_total", sa.Numeric(14, 2), nullable=True),
        sa.Column("suppliers", sa.Text(), nullable=True),
        sa.Column("term_of_payment", sa.Text(), nullable=True),
        sa.Column("schedule", sa.Text(), nullable=True),
        sa.Column("status", ar_status_col, nullable=False, server_default="draft"),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
        ),
        sa.UniqueConstraint("ar_no", "revision", name="uq_ar_no_revision"),
    )
    op.create_index("ix_approval_requests_ar_no", "approval_requests", ["ar_no"])

    # ── 3) ar_amount_items ──
    op.create_table(
        "ar_amount_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ar_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_no", sa.Integer(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
    )

    # ── 4) audit_log.ar_id ──
    op.add_column(
        "audit_log",
        sa.Column(
            "ar_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("audit_log", "ar_id")
    op.drop_table("ar_amount_items")
    op.drop_index("ix_approval_requests_ar_no", table_name="approval_requests")
    op.drop_table("approval_requests")

    bind = op.get_bind()
    ar_budget_type_enum.drop(bind, checkfirst=True)
    ar_status_enum.drop(bind, checkfirst=True)

    op.drop_table("ar_number_counters")
