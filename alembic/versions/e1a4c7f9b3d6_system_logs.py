"""system logs table

System Log (2026-09-12) — ตารางใหม่ system_logs สำหรับเก็บ Log ทุกการเปลี่ยนแปลงใน
ระบบที่ audit_log เดิม (Schema เฉพาะ PR/AR) ไม่ครอบคลุม: Login/Logout, User CRUD +
Password Reset, Budget CRUD/Upload, Budget Approval Level CRUD, Term of Payment CRUD
ฯลฯ ใช้ entity_type/entity_id แบบ Generic แทนคอลัมน์เฉพาะเจาะจงแบบ audit_log เพราะ
Entity ที่ต้อง Log มีหลายชนิดและเพิ่มได้เรื่อยๆ ในอนาคต — หน้า "System Log" (Admin
เท่านั้น) จะ Query ตารางนี้รวมกับ audit_log เดิมมาแสดงเป็นรายการเดียว

Revision ID: e1a4c7f9b3d6
Revises: c6f1a4e8b2d9
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1a4c7f9b3d6"
down_revision = "c6f1a4e8b2d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"])
    op.create_index("ix_system_logs_entity_type", "system_logs", ["entity_type"])


def downgrade() -> None:
    op.drop_index("ix_system_logs_entity_type", table_name="system_logs")
    op.drop_index("ix_system_logs_created_at", table_name="system_logs")
    op.drop_table("system_logs")
