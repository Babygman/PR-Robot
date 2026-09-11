"""source document ar_id

AI Extract for AR (2026-09-11) — เพิ่มคอลัมน์ ar_id (Nullable คู่กับ pr_id เดิม) ใน
source_documents รองรับการอัปโหลดเอกสารต้นทาง (ใบเสนอราคา) แล้วให้ AI สกัดข้อมูลไป
สร้าง Approval Request ได้เหมือน PR เดิมทุกประการ (Schema เดียวกัน ใช้ร่วมกัน) —
แถวหนึ่งผูกกับ pr_id หรือ ar_id อย่างใดอย่างหนึ่งเท่านั้น (Pattern เดียวกับ audit_log
ที่มี pr_id/ar_id คู่กันอยู่แล้ว)

Revision ID: c6f1a4e8b2d9
Revises: b5e9d3a7c1f4
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c6f1a4e8b2d9"
down_revision = "b5e9d3a7c1f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column(
            "ar_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "ar_id")
