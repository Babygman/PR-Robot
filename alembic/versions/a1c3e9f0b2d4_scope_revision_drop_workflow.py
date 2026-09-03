"""scope revision phase 9: drop approval workflow, simplify statuses, add doc types

Revision ID: a1c3e9f0b2d4
Revises: f6511609ec30
Create Date: 2026-09-03 00:00:00.000000

Business Decision (2026-09-03): Product Owner Feedback ว่า Design เดิม (Workflow
Review->Approve->Receive ในระบบ) ผิดตั้งแต่แรก — ดูตัวอย่าง PR จริงที่ส่งมาแล้วพบว่า
Reviewed/Approved/Received by เป็นลายเซ็นสดบนกระดาษที่พิมพ์ออกไปใช้งานนอกระบบล้วนๆ
ไม่มีการอนุมัติในระบบเลย ดู docs/00_KICKOFF_AND_DESIGN.md ข้อ 4g สำหรับรายละเอียดเต็ม

การเปลี่ยนแปลง:
1. pr_status: 4 ค่า (draft/reviewed/approved/received) -> 2 ค่า (draft/finalized)
   ข้อมูลเดิมที่ไม่ใช่ draft ทั้งหมด Map เป็น finalized (Migrate ข้อมูลจริง ไม่ทิ้ง)
2. purchasing_requisitions: Drop reviewed_by_id/at, approved_by_id/at, received_by_id/at
3. users: Drop can_review, can_approve, can_receive (เหลือ is_admin)
4. source_doc_type: เพิ่ม borrow_note (ใบยืมสินค้า), delivery_note (ใบส่งสินค้า)
5. source_documents.doc_type: เปลี่ยนเป็น Nullable (AI เดาเองหลัง Extract ไม่บังคับ
   เลือกตอน Upload แล้ว)

Downgrade เป็น Best-Effort เท่านั้น (Map finalized กลับเป็น approved ซึ่งไม่แม่นยำ
100% เพราะข้อมูลเดิมว่าเคยเป็น reviewed/approved/received สูญหายไปแล้วตอน Upgrade)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1c3e9f0b2d4"
down_revision = "f6511609ec30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1) source_doc_type: เพิ่มค่าใหม่ (Backward-Compatible, ไม่กระทบข้อมูลเดิม) ──
    op.execute("ALTER TYPE source_doc_type ADD VALUE IF NOT EXISTS 'borrow_note'")
    op.execute("ALTER TYPE source_doc_type ADD VALUE IF NOT EXISTS 'delivery_note'")

    # ── 2) source_documents.doc_type -> Nullable ──
    op.alter_column("source_documents", "doc_type", nullable=True)

    # ── 3) pr_status: 4 ค่า -> 2 ค่า พร้อม Migrate ข้อมูลเดิม ──
    # ต้อง Drop Default เดิมก่อน (Default ผูกกับ Type เก่าอยู่ — 'draft'::pr_status
    # อ้าง OID ของ Type เดิม Cast อัตโนมัติไปหา Type ใหม่ไม่ได้แม้ค่า String จะตรงกัน)
    op.execute("ALTER TABLE purchasing_requisitions ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE pr_status RENAME TO pr_status_old")
    op.execute("CREATE TYPE pr_status AS ENUM ('draft', 'finalized')")
    op.execute(
        """
        ALTER TABLE purchasing_requisitions
        ALTER COLUMN status TYPE pr_status
        USING (CASE WHEN status::text = 'draft' THEN 'draft' ELSE 'finalized' END)::pr_status
        """
    )
    op.alter_column("purchasing_requisitions", "status", server_default="draft")
    op.execute("DROP TYPE pr_status_old")

    # ── 4) purchasing_requisitions: Drop Workflow Columns ──
    op.drop_column("purchasing_requisitions", "reviewed_by_id")
    op.drop_column("purchasing_requisitions", "reviewed_at")
    op.drop_column("purchasing_requisitions", "approved_by_id")
    op.drop_column("purchasing_requisitions", "approved_at")
    op.drop_column("purchasing_requisitions", "received_by_id")
    op.drop_column("purchasing_requisitions", "received_at")

    # ── 5) users: Drop RBAC Columns เดิม ──
    op.drop_column("users", "can_review")
    op.drop_column("users", "can_approve")
    op.drop_column("users", "can_receive")


def downgrade() -> None:
    # RBAC columns กลับมา (Default False ทั้งหมด — สิทธิ์เดิมของ User สูญหายไปแล้ว)
    op.add_column(
        "users", sa.Column("can_review", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "users", sa.Column("can_approve", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "users", sa.Column("can_receive", sa.Boolean(), nullable=False, server_default=sa.false())
    )

    op.add_column(
        "purchasing_requisitions", sa.Column("reviewed_by_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "purchasing_requisitions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "purchasing_requisitions", sa.Column("approved_by_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "purchasing_requisitions",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "purchasing_requisitions", sa.Column("received_by_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "purchasing_requisitions",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "purchasing_requisitions_reviewed_by_id_fkey",
        "purchasing_requisitions",
        "users",
        ["reviewed_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "purchasing_requisitions_approved_by_id_fkey",
        "purchasing_requisitions",
        "users",
        ["approved_by_id"],
        ["id"],
    )
    op.create_foreign_key(
        "purchasing_requisitions_received_by_id_fkey",
        "purchasing_requisitions",
        "users",
        ["received_by_id"],
        ["id"],
    )

    # pr_status: finalized ทั้งหมด Map กลับเป็น approved (Best-Effort — ไม่ทราบว่า
    # เคยเป็น reviewed/approved/received จริงๆ อันไหน เพราะข้อมูลนั้นสูญหายตอน Upgrade)
    op.execute("ALTER TABLE purchasing_requisitions ALTER COLUMN status DROP DEFAULT")
    op.execute("ALTER TYPE pr_status RENAME TO pr_status_new")
    op.execute("CREATE TYPE pr_status AS ENUM ('draft', 'reviewed', 'approved', 'received')")
    op.execute(
        """
        ALTER TABLE purchasing_requisitions
        ALTER COLUMN status TYPE pr_status
        USING (CASE WHEN status::text = 'draft' THEN 'draft' ELSE 'approved' END)::pr_status
        """
    )
    op.alter_column("purchasing_requisitions", "status", server_default="draft")
    op.execute("DROP TYPE pr_status_new")

    # source_documents.doc_type -> กลับเป็น NOT NULL (ต้องมั่นใจว่าไม่มีค่า NULL ค้างอยู่
    # ก่อน Downgrade จริง — เติมค่า 'other' ให้แถวที่เป็น NULL ป้องกัน Downgrade พัง)
    op.execute("UPDATE source_documents SET doc_type = 'other' WHERE doc_type IS NULL")
    op.alter_column("source_documents", "doc_type", nullable=False)

    # หมายเหตุ: Postgres ไม่รองรับ DROP VALUE จาก Enum Type ตรงๆ (ต้องสร้าง Type ใหม่
    # เหมือนที่ทำกับ pr_status ด้านบน) — ไม่ทำที่นี่เพราะ borrow_note/delivery_note ไม่
    # กระทบ Schema เดิม ปล่อยค่าเหล่านี้ค้างใน Type ไว้ปลอดภัยกว่า
