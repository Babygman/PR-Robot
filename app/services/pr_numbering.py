"""จองเลขที่ PR (pr_no) ถัดไปแบบ Atomic

ใช้ UPDATE ... RETURNING บนแถวเดียวใน pr_number_counters (id=1) แทน SELECT ... FOR UPDATE
เพราะ UPDATE เป็น Statement เดียวจบในตัว — Database รับประกัน Isolation ของแถวที่ถูกแก้ไข
ระหว่าง Transaction พร้อมกันให้เองตาม MVCC (Postgres) โดยไม่ต้อง Lock แถวด้วยมือ
และไม่พึ่ง Syntax เฉพาะ Backend จึงพกพาข้าม Postgres/SQLite ได้ (ตรงข้ามกับ SELECT FOR UPDATE
ที่ SQLite ไม่รองรับ)

ตาม Business Decision 2026-09-01: pr_no เป็น Running Number ต่อเนื่องตลอดไป ไม่รีเซ็ตรายปี/แผนก
"""
from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.pr_number_counter import PRNumberCounter


def allocate_pr_no(db: Session) -> int:
    """จองเลขที่ PR ถัดไป — ต้องเรียกภายใน Transaction เดียวกับการสร้าง PR
    (ไม่ Commit เอง ที่นี่ ปล่อยให้ Caller เป็นคน Commit พร้อมกับ Insert PR จริง)
    """
    stmt = (
        update(PRNumberCounter)
        .where(PRNumberCounter.id == 1)
        .values(next_value=PRNumberCounter.next_value + 1)
        .returning(PRNumberCounter.next_value)
    )
    new_next_value = db.execute(stmt).scalar_one()
    return new_next_value - 1
