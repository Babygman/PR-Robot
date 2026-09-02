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
from app.models import PRNumberCounter, User


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
    # (pr_number_counters ต้องมีแถว id=1 เสมอในระบบจริง — ดู
    # alembic/versions/f6511609ec30_pr_number_counter.py) จำลองผลลัพธ์เดียวกันที่นี่
    session.add(PRNumberCounter(id=1, next_value=1))
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
        can_review=True,
        can_approve=True,
        can_receive=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def plain_user(db_session: Session) -> User:
    user = User(
        name="Plain User",
        email="plain@example.com",
        password_hash=hash_password("plainpass123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
