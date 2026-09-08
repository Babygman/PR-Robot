"""จองเลขที่ Approval Request (ar_no) ถัดไปแบบ Atomic — Pattern เดียวกับ
app/services/pr_numbering.py ทุกประการ (UPDATE ... RETURNING บนแถวเดียวใน
ar_number_counters แทน SELECT ... FOR UPDATE เพื่อพกพาข้าม Postgres/SQLite ได้)

Business Decision (2026-09-08): เลขที่ AR เป็น Running Number ต่อเนื่องธรรมดา
แสดงผลเป็น "AR-0001" (Zero-pad 4 หลัก) — ไม่ลอกรูปแบบเข้ารหัสซับซ้อนจากตัวอย่างจริง
(เช่น "GA202609014MT") ตามที่ผู้ใช้เลือกไว้ตอนอนุมัติ Design
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.ar_number_counter import ARNumberCounter


def allocate_ar_no(db: Session) -> int:
    """จองเลขที่ AR ถัดไป — ต้องเรียกภายใน Transaction เดียวกับการสร้าง AR
    (ไม่ Commit เอง ที่นี่ ปล่อยให้ Caller เป็นคน Commit พร้อมกับ Insert AR จริง)
    """
    stmt = (
        update(ARNumberCounter)
        .where(ARNumberCounter.id == 1)
        .values(next_value=ARNumberCounter.next_value + 1)
        .returning(ARNumberCounter.next_value)
    )
    new_next_value = db.execute(stmt).scalar_one()
    return new_next_value - 1


def format_ar_no(ar_no: int) -> str:
    """แสดงผลเลขที่ AR แบบ Zero-pad 4 หลัก เช่น 1 -> "AR-0001" """
    return f"AR-{ar_no:04d}"
