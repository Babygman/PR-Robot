"""sealed pdf columns (pr + ar)

Electronic Signature Hardening Phase C (Design §3.2.3, 2026-09-16) — เพิ่มคอลัมน์เก็บ
Path/Hash ของ PDF ที่ Seal ไว้ครั้งเดียวตอนเอกสารถึงจุด Finalized จริง (PR: Level
สุดท้ายอนุมัติผ่าน/ไม่มี Level เลย, AR: FA Acknowledge ผ่าน — ไม่ใช่แค่ ar.status =
FINALIZED ซึ่งเร็วกว่านั้น ดู Docstring ใหม่บน ApprovalRequest.sealed_pdf_path) — เขียน
โดย app/services/pdf_sealing.py หลังจาก Migration นี้ Deploy แล้วเท่านั้น (PR/AR เก่าที่
Finalized ไปแล้วก่อนหน้านี้จะมีคอลัมน์เหล่านี้เป็น NULL ต่อไป — ยังคง Re-render สดตาม
Template ปัจจุบันเหมือนเดิมทุกครั้งที่ดู/ดาวน์โหลด ไม่ Backfill ย้อนหลัง เพราะไม่มี
PDF Bytes ต้นฉบับ ณ ตอน Finalize จริงเก็บไว้ให้ Seal ย้อนหลังได้ถูกต้อง)

Revision ID: bab4fcc72aee
Revises: b9d4e6f2a8c7
Create Date: 2026-09-16
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "bab4fcc72aee"
down_revision = "b9d4e6f2a8c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("purchasing_requisitions", "approval_requests"):
        op.add_column(table, sa.Column("sealed_pdf_path", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("sealed_pdf_hash", sa.String(length=64), nullable=True))
        op.add_column(
            table, sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    for table in ("purchasing_requisitions", "approval_requests"):
        op.drop_column(table, "sealed_at")
        op.drop_column(table, "sealed_pdf_hash")
        op.drop_column(table, "sealed_pdf_path")
