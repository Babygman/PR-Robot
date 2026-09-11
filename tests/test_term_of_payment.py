"""Test Term of Payment Master Data (AR Redesign, 2026-09-11) — CRUD Admin เท่านั้น
GET เปิดให้ Login แล้วเรียกได้ทุกคน (User ทั่วไปต้องอ่านรายการนี้ได้ตอนสร้าง AR)"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import TermOfPaymentOption, User

_PASSWORD = "password123456"


def _make_admin(db_session: Session) -> User:
    user = User(
        name="Admin",
        email="tp-admin@example.com",
        password_hash=hash_password(_PASSWORD),
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_as(client: TestClient, email: str, password: str = _PASSWORD) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def test_list_requires_login(client: TestClient):
    res = client.get("/term-of-payment-options")
    assert res.status_code == 401


def test_plain_user_can_list_active_options(
    client: TestClient, db_session: Session, plain_user: User
):
    db_session.add(TermOfPaymentOption(name="Credit 30 Days", is_active=True))
    db_session.add(TermOfPaymentOption(name="Cash", is_active=False))
    db_session.commit()

    _login_as(client, plain_user.email, "plainpass123")
    res = client.get("/term-of-payment-options", params={"active_only": True})
    assert res.status_code == 200, res.text
    names = [o["name"] for o in res.json()]
    assert names == ["Credit 30 Days"]


def test_plain_user_cannot_create(client: TestClient, plain_user: User):
    _login_as(client, plain_user.email, "plainpass123")
    res = client.post("/term-of-payment-options", json={"name": "Cash"})
    assert res.status_code == 403


def test_admin_create_update_delete_flow(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    res = client.post("/term-of-payment-options", json={"name": "50% Advance"})
    assert res.status_code == 201, res.text
    option_id = res.json()["id"]
    assert res.json()["is_active"] is True

    dup = client.post("/term-of-payment-options", json={"name": "50% Advance"})
    assert dup.status_code == 409

    patched = client.patch(f"/term-of-payment-options/{option_id}", json={"is_active": False})
    assert patched.status_code == 200
    assert patched.json()["is_active"] is False

    deleted = client.delete(f"/term-of-payment-options/{option_id}")
    assert deleted.status_code == 204
    assert db_session.get(TermOfPaymentOption, option_id) is None


def test_delete_not_found(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)
    res = client.delete("/term-of-payment-options/999999")
    assert res.status_code == 404
