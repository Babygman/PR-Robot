"""ตัวนับเลขที่ Approval Request (Running Number ต่อเนื่องตลอดไป ไม่รีเซ็ตรายปี/แผนก)
มีแถวเดียวเสมอ (id=1) จองเลขถัดไปแบบ Atomic ผ่าน UPDATE ... RETURNING (ดู
app/services/ar_numbering.py) — Pattern เดียวกับ PRNumberCounter (pr_number_counter.py)
ทุกประการ แค่แยกตารางเพราะเป็นเลขที่คนละชุดเอกสาร (AR ไม่ใช่ PR)
"""
from __future__ import annotations

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ARNumberCounter(Base):
    __tablename__ = "ar_number_counters"

    id: Mapped[int] = mapped_column(primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
