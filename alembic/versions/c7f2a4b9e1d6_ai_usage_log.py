"""add ai_usage_logs table for "ค่าใช้จ่าย AI" page

Revision ID: c7f2a4b9e1d6
Revises: b3e7a1c9d5f2
Create Date: 2026-09-04 00:00:00.000000

Feedback จริงจากผู้ใช้ (2026-09-04, หลัง Upgrade ออกจาก Gemini Free Tier): อยากเห็น
ค่าใช้จ่าย AI แยกรายรายการ/รายวัน/รายเดือนในระบบ — เพิ่มตาราง ai_usage_logs เก็บ Log
การเรียก Gemini API แต่ละครั้ง (สำเร็จ/ไม่สำเร็จ, จำนวน Token, ค่าใช้จ่ายประมาณการ
USD/THB) ดู app/models/ai_usage_log.py สำหรับรายละเอียดการออกแบบ

document_id/uploaded_by_id เป็น ON DELETE SET NULL เพราะเอกสาร/User อาจถูกลบทีหลัง
แต่ประวัติค่าใช้จ่ายต้องอยู่ต่อ (เก็บ file_name Snapshot แยกไว้แล้วในตัวตาราง)

ข้อมูลย้อนหลังก่อนหน้านี้ไม่มี Token/ค่าใช้จ่ายให้ย้อนเก็บ — เริ่มนับจาก Transaction
แรกหลัง Deploy Migration นี้เท่านั้น
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c7f2a4b9e1d6"
down_revision = "b3e7a1c9d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("prompt_token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("cost_thb", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("usd_to_thb_rate", sa.Numeric(8, 4), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["source_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_ai_usage_logs_created_at", "ai_usage_logs", ["created_at"], unique=False
    )
    op.create_index(
        "ix_ai_usage_logs_document_id", "ai_usage_logs", ["document_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_ai_usage_logs_document_id", table_name="ai_usage_logs")
    op.drop_index("ix_ai_usage_logs_created_at", table_name="ai_usage_logs")
    op.drop_table("ai_usage_logs")
