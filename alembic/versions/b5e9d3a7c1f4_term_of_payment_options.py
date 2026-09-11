"""term of payment options

AR Redesign (2026-09-11) — เพิ่มตาราง term_of_payment_options เป็น Master Data ให้
Admin จัดการรายการ Term of Payment เอง (เช่น "Credit 30 Days", "Cash", "50% Advance")
แทนช่องกรอกข้อความอิสระเดิมในฟอร์ม AR — ฟอร์ม AR เปลี่ยนเป็น Dropdown เลือกจากตาราง
นี้แล้ว (ยังเก็บค่าเป็น Text ธรรมดาใน approval_requests.term_of_payment เหมือนเดิม
ไม่ผูก Foreign Key เพราะเป็นแค่ค่าที่เลือก ณ ขณะนั้น ไม่ต้องคงความสัมพันธ์ถาวรกับ
รายการ Master — ผู้ใช้ยืนยันแล้วว่าไม่ต้อง AI Extract ช่องนี้)

Revision ID: b5e9d3a7c1f4
Revises: a2f4c8d1e6b3
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b5e9d3a7c1f4"
down_revision = "a2f4c8d1e6b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "term_of_payment_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("term_of_payment_options")
