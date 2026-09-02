"""document review fields

เพิ่มฟิลด์สำหรับ Phase 4 (Upload + AI Extraction) ในตาราง source_documents:
- extraction_error: ข้อความ Error กรณี Gemini สกัดข้อมูลไม่สำเร็จ
- reviewed_data / reviewed_by_id / reviewed_at: ข้อมูลที่ผู้ใช้ตรวจทาน/แก้ไขแล้ว
  แยกจาก ai_extraction_raw_json เดิม เพื่อรักษาผลดิบจาก AI ไว้เป็น Audit Trail เสมอ

หมายเหตุ: ใช้ op.batch_alter_table() ครอบทุก Operation แม้บน Postgres จะไม่จำเป็น
(Batch Mode เป็น No-op บน Backend ที่รองรับ ALTER ตามปกติอยู่แล้ว) แต่จำเป็นสำหรับ SQLite
ซึ่งไม่รองรับ ALTER TABLE เพิ่ม Foreign Key แบบตรงๆ — ทำให้ Migration นี้พกพาข้าม Dialect ได้จริง

Revision ID: f2b89a3880f2
Revises: cdfbb940153e
Create Date: 2026-09-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f2b89a3880f2"
down_revision = "cdfbb940153e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("source_documents") as batch_op:
        batch_op.add_column(
            sa.Column(
                "extraction_error",
                sa.Text(),
                nullable=True,
                comment="ข้อความ Error ถ้า Gemini สกัดข้อมูลไม่สำเร็จ (ai_extraction_raw_json จะเป็น null)",
            )
        )
        batch_op.add_column(sa.Column("reviewed_data", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_source_documents_reviewed_by_id_users",
            "users",
            ["reviewed_by_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("source_documents") as batch_op:
        batch_op.drop_constraint(
            "fk_source_documents_reviewed_by_id_users", type_="foreignkey"
        )
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("reviewed_by_id")
        batch_op.drop_column("reviewed_data")
        batch_op.drop_column("extraction_error")
