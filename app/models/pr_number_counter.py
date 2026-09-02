"""ตัวนับเลขที่ PR (Running Number ต่อเนื่องตลอดไป ไม่รีเซ็ตรายปี/แผนก)
ตาม Business Decision 2026-09-01 — มีแถวเดียวเสมอ (id=1) จองเลขถัดไปแบบ Atomic
ผ่าน UPDATE ... RETURNING (ดู app/services/pr_numbering.py) — Portable ทั้ง Postgres และ SQLite
ไม่ต้องพึ่ง SELECT ... FOR UPDATE ซึ่งบาง Backend ไม่รองรับ
"""
from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PRNumberCounter(Base):
    __tablename__ = "pr_number_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
