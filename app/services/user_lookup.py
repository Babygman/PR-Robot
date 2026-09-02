"""Resolve User ID -> ชื่อที่แสดงผล ใช้ร่วมกันระหว่าง PR Detail Response, PDF, และ Audit History
(ไม่ใช้ SQLAlchemy relationship() เพราะ PurchasingRequisition มี FK ไปยัง users 4 ช่อง
ในตารางเดียวกัน — Query ตรงๆ แบบนี้ชัดเจนและง่ายต่อการทดสอบกว่า)
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import User


def resolve_user_names(db: Session, user_ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in user_ids if i is not None}
    if not ids:
        return {}
    return {u.id: u.name for u in db.query(User).filter(User.id.in_(ids)).all()}
