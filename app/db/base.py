"""SQLAlchemy Declarative Base.

Model ทุกตัว (Phase 2) ต้อง inherit จาก Base นี้ เพื่อให้ Alembic
autogenerate เห็น Metadata ครบ ห้ามสร้าง declarative_base() ซ้ำที่อื่น
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
