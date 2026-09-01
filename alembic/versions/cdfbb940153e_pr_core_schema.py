"""pr core schema

Revision ID: cdfbb940153e
Revises: 3e95cf5ab690
Create Date: 2026-09-01 11:23:16.932038

Business Decisions ที่มีผลต่อ Schema นี้ (2026-09-01):
- ใช้เฉพาะฟิลด์หน้า 1/3 ของฟอร์ม Sunstar FM-PU-02 (ยังไม่มีหน้า 2-3)
- pr_no เป็น Running Number ต่อเนื่องตลอด (Unique Integer, วิธี Generate เป็น
  Business Logic ชั้น Application ใน Phase 4-5 ไม่ใช่ DB Sequence ที่นี่
  เพื่อให้ Migration พกพาข้าม Postgres/SQLite ได้ตรงกันสำหรับ Smoke Test)
- Requested/Reviewed/Approved/Received by = FK ไปยัง users (คนที่ Login ทำ Action)
  ไม่ใช่ช่องกรอกข้อความอิสระ
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cdfbb940153e'
down_revision = '3e95cf5ab690'
branch_labels = None
depends_on = None


PR_STATUS_VALUES = ("draft", "reviewed", "approved", "received")
SOURCE_DOC_TYPE_VALUES = ("quotation", "receiving_note", "other")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_approve", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_receive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    pr_status = sa.Enum(*PR_STATUS_VALUES, name="pr_status")
    pr_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "purchasing_requisitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pr_no", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=255), nullable=False),
        sa.Column("division", sa.String(length=255), nullable=False),
        sa.Column("doc_date", sa.Date(), nullable=False),
        sa.Column("status", pr_status, nullable=False, server_default="draft"),
        sa.Column("requested_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_purchasing_requisitions_pr_no", "purchasing_requisitions", ["pr_no"], unique=True
    )

    op.create_table(
        "pr_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_no", sa.Integer(), nullable=False),
        sa.Column("account_code", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.String(length=50), nullable=True),
        sa.Column("required_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("ref_po", sa.String(length=100), nullable=True),
    )
    op.create_index("ix_pr_items_pr_id", "pr_items", ["pr_id"])

    op.create_table(
        "pr_budget_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("account_code_1", sa.String(length=100), nullable=True),
        sa.Column("account_code_2", sa.String(length=100), nullable=True),
        sa.Column("budget", sa.Numeric(14, 2), nullable=True),
        sa.Column("used_before_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("this_application", sa.Numeric(14, 2), nullable=True),
        sa.Column("balance", sa.Numeric(14, 2), nullable=True),
    )

    source_doc_type = sa.Enum(*SOURCE_DOC_TYPE_VALUES, name="source_doc_type")
    source_doc_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("doc_type", source_doc_type, nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ai_extraction_raw_json", sa.JSON(), nullable=True),
        sa.Column("ai_confidence", sa.Numeric(5, 4), nullable=True),
    )
    op.create_index("ix_source_documents_pr_id", "source_documents", ["pr_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "pr_id",
            sa.Integer(),
            sa.ForeignKey("purchasing_requisitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_log_pr_id", "audit_log", ["pr_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("source_documents")
    sa.Enum(*SOURCE_DOC_TYPE_VALUES, name="source_doc_type").drop(op.get_bind(), checkfirst=True)
    op.drop_table("pr_budget_control")
    op.drop_table("pr_items")
    op.drop_table("purchasing_requisitions")
    sa.Enum(*PR_STATUS_VALUES, name="pr_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("users")
