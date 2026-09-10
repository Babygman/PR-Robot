"""ar attachments

Phase A (Correction 2026-09-10) — เพิ่มตาราง ar_attachments รองรับ Feature ใหม่
"เอกสารแนบของ Approval Request" ตาม Feedback จริงจากผู้ใช้: ต้อง Upload เอกสารแนบได้
ตอนสร้าง AR (PDF/Excel/รูปภาพ) และแนบเพิ่มได้ระหว่างขั้นตอนอนุมัติด้วย — ดู
app/models/ar_attachment.py สำหรับที่มา/เหตุผลของ Design (แยกจาก source_documents ของ
PR โดยเจตนา ไม่ผูกกับ Gemini AI Extraction)

Revision ID: a8cc4abbaa59
Revises: c58a1f0e93d2
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a8cc4abbaa59"
down_revision = "c58a1f0e93d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ar_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "ar_id",
            sa.Integer(),
            sa.ForeignKey("approval_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_ar_attachments_ar_id", "ar_attachments", ["ar_id"])


def downgrade() -> None:
    op.drop_index("ix_ar_attachments_ar_id", table_name="ar_attachments")
    op.drop_table("ar_attachments")
