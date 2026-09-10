"""Pytest Fixtures ร่วม — ใช้ SQLite In-memory แทน Postgres สำหรับ Unit/Integration Test
(Schema ถูกทดสอบแยกด้วย Alembic Upgrade/Downgrade อยู่แล้ว ที่นี่ทดสอบ Business Logic)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import ARNumberCounter, PRNumberCounter, User


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    # Base.metadata.create_all() สร้างแค่ Schema ไม่รัน Data Seed ของ Alembic Migration
    # (pr_number_counters/ar_number_counters ต้องมีแถว id=1 เสมอในระบบจริง — ดู
    # alembic/versions/f6511609ec30_pr_number_counter.py และ
    # d4a8c2f1b6e3_approval_request.py) จำลองผลลัพธ์เดียวกันที่นี่
    session.add(PRNumberCounter(id=1, next_value=1))
    session.add(ARNumberCounter(id=1, next_value=1))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session) -> User:
    user = User(
        name="Admin",
        email="admin@example.com",
        password_hash=hash_password("adminpass123"),
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def plain_user(db_session: Session) -> User:
    # Budget Control (2026-09-09): ผู้สร้าง AR ต้องมี Department เสมอ (Design §2.1) —
    # ใส่ค่า Default ให้ Fixture นี้เพื่อไม่ให้ AR Test ทั้งชุดโดนบล็อกตอนสร้าง AR ใหม่
    # (Test ที่ต้องการยืนยัน Error กรณีไม่มี Department แยกสร้าง User เองโดยเฉพาะ)
    #
    # Full RBAC (Correction 2026-09-10): เพิ่ม can_view_pr/can_view_ar = True ให้ Fixture
    # นี้ (Default พนักงานทั่วไปที่ใช้ PR/AR ของตัวเองได้ปกติ — เหมือน Migration Default
    # ของ User จริงที่มีอยู่แล้วในระบบ) ไม่ใส่ can_view_all เพื่อให้ Test ที่ต้องการยืนยัน
    # Ownership Scoping (เห็นเฉพาะของตัวเอง) ยังทดสอบได้จริงด้วย Fixture นี้
    user = User(
        name="Plain User",
        email="plain@example.com",
        password_hash=hash_password("plainpass123"),
        department="Production",
        can_view_pr=True,
        can_view_ar=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
