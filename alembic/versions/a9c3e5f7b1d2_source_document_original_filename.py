"""source document original filename

Feedback จริงจากผู้ใช้ 2026-09-15: หน้าเลือกเอกสารก่อนสร้าง PR/AR โชว์ชื่อไฟล์แบบ UUID
ที่ระบบตั้งให้ตอนเก็บไฟล์ (เช่น "07980a34...9ae.pdf") ไม่ใช่ชื่อไฟล์เดิมที่อัปโหลดมา —
เพิ่มคอลัมน์ original_filename เก็บชื่อไฟล์จริงตอน Upload ไว้แสดงแทน

Revision ID: a9c3e5f7b1d2
Revises: f2b8d4a6c1e7
Create Date: 2026-09-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9c3e5f7b1d2"
down_revision = "f2b8d4a6c1e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_documents",
        sa.Column("original_filename", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_documents", "original_filename")
