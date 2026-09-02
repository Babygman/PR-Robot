"""pr number counter

เพิ่มตาราง pr_number_counters สำหรับจองเลขที่ PR แบบ Running Number ต่อเนื่อง
(Business Decision 2026-09-01: ไม่รีเซ็ตรายปี/แผนก) — มีแถวเดียวเสมอ (id=1)
Seed แถวแรกด้วย next_value=1 ในตัว Migration นี้เลย

Revision ID: f6511609ec30
Revises: f2b89a3880f2
Create Date: 2026-09-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f6511609ec30"
down_revision = "f2b89a3880f2"
branch_labels = None
depends_on = None

pr_number_counters = sa.table(
    "pr_number_counters",
    sa.column("id", sa.Integer),
    sa.column("next_value", sa.Integer),
)


def upgrade() -> None:
    op.create_table(
        "pr_number_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("next_value", sa.Integer(), nullable=False),
    )
    op.bulk_insert(pr_number_counters, [{"id": 1, "next_value": 1}])


def downgrade() -> None:
    op.drop_table("pr_number_counters")
