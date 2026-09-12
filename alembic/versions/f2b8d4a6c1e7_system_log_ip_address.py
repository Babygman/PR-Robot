"""system log ip address

System Log ไม่ตอบโจทย์ "ที่ไหน" (Feedback จริงจากผู้ใช้ 2026-09-12 — เปลี่ยนสิทธิ์+Reset
Password ให้ User คนหนึ่งแล้ว Log ไม่บอกว่าทำอะไรกับใครชัดเจน และไม่มีร่องรอยว่ากระทำจาก
ที่ไหน) เพิ่มคอลัมน์ ip_address เก็บ IP ของผู้กระทำ (จาก X-Forwarded-For ผ่าน Nginx Proxy
Manager หรือ request.client.host ตรงๆ ถ้าไม่มี Proxy) — audit_log เดิม (PR/AR) ไม่มี
คอลัมน์นี้ ยังคงไม่แตะเหมือนเดิม (แถวรวมจาก audit_log ในหน้า System Log จะแสดง IP ว่าง)

Revision ID: f2b8d4a6c1e7
Revises: e1a4c7f9b3d6
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b8d4a6c1e7"
down_revision = "e1a4c7f9b3d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_logs", sa.Column("ip_address", sa.String(length=45), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("system_logs", "ip_address")
