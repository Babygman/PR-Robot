"""user division field

User Management Redesign (2026-09-11) — เพิ่ม Field "Division" ใหม่จริงๆ (ยืนยันจาก
ผู้ใช้ว่าไม่ใช่แค่เปลี่ยนชื่อ Department เดิม) — เก็บ Pattern เดียวกับ department/
position ทุกประการ (Nullable, ไม่มีผลต่อ Logic ใดๆ แค่แสดงผล/กรอกข้อมูลเพิ่มเติม)

Revision ID: a2f4c8d1e6b3
Revises: f7b3e9c1a6d5
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a2f4c8d1e6b3"
down_revision = "f7b3e9c1a6d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("division", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "division")
