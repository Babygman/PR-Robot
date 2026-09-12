"""Test System Log (2026-09-12) — รวม Log จาก system_logs (ใหม่) + audit_log (เดิม)
Admin เท่านั้นที่เข้าดูได้ ต้อง Filter/Search ได้ตามที่ระบุ"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import AuditLog, PRStatus, PurchasingRequisition, User

_PASSWORD = "password123456"


def _make_admin(db_session: Session, **kwargs) -> User:
    kwargs.setdefault("password_hash", hash_password(_PASSWORD))
    kwargs.setdefault("name", "Admin")
    kwargs.setdefault("email", "syslog-admin@example.com")
    kwargs.setdefault("is_admin", True)
    user = User(**kwargs)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_as(client: TestClient, email: str, password: str = _PASSWORD) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def test_login_writes_system_log_entry(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    res = client.get("/system-log")
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()]
    assert "auth.login" in actions


def test_logout_writes_system_log_entry(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    res = client.post("/auth/logout")
    assert res.status_code == 200, res.text

    _login_as(client, admin.email)
    res = client.get("/system-log")
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()]
    assert "auth.logout" in actions


def test_plain_user_cannot_view_system_log(client: TestClient, plain_user: User):
    _login_as(client, plain_user.email, "plainpass123")
    res = client.get("/system-log")
    assert res.status_code == 403


def test_requires_login(client: TestClient):
    res = client.get("/system-log")
    assert res.status_code == 401


def test_user_crud_writes_system_log_entries(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    created = client.post(
        "/users",
        json={
            "name": "Somchai",
            "email": "somchai-log@example.com",
            "password": "somchaipass123",
            "department": "Production",
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    patched = client.patch(f"/users/{user_id}", json={"division": "Quality Assurance"})
    assert patched.status_code == 200, patched.text

    deleted = client.delete(f"/users/{user_id}")
    assert deleted.status_code == 204, deleted.text

    res = client.get("/system-log", params={"entity_type": "user"})
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()]
    assert "user.created" in actions
    assert "user.updated" in actions
    assert "user.deleted" in actions
    # Log เก็บ Email ของ User ที่ถูกลบไว้ใน Detail เพราะ Join ชื่อกลับไม่ได้อีกแล้วหลังลบจริง
    deleted_row = next(row for row in res.json() if row["action"] == "user.deleted")
    assert deleted_row["detail"]["email"] == "somchai-log@example.com"


def test_entity_type_filter_excludes_other_types(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    client.post(
        "/users",
        json={
            "name": "Somchai",
            "email": "somchai-filter@example.com",
            "password": "somchaipass123",
            "department": "Production",
        },
    )

    res = client.get("/system-log", params={"entity_type": "budget"})
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()]
    assert "user.created" not in actions


def test_q_search_matches_action_substring(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)
    _login_as(client, admin.email)

    res = client.get("/system-log", params={"q": "auth.login"})
    assert res.status_code == 200, res.text
    actions = [row["action"] for row in res.json()]
    assert all("auth.login" in a for a in actions)
    assert "auth.login" in actions


def test_merges_legacy_audit_log_pr_entry(client: TestClient, db_session: Session):
    admin = _make_admin(db_session)

    pr = PurchasingRequisition(
        pr_no=1,
        section="Sec",
        division="Div",
        doc_date=date(2026, 9, 1),
        status=PRStatus.DRAFT,
        requested_by_id=admin.id,
    )
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)

    db_session.add(
        AuditLog(
            pr_id=pr.id,
            action="pr.created",
            actor_id=admin.id,
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()

    _login_as(client, admin.email)
    res = client.get("/system-log")
    assert res.status_code == 200, res.text
    rows = res.json()

    pr_row = next(row for row in rows if row["action"] == "pr.created")
    assert pr_row["source"] == "audit"
    assert pr_row["entity_type"] == "pr"
    assert pr_row["entity_label"] == "PR-1"

    # Merge แล้วต้อง Sort เรียงล่าสุดไปเก่าสุดข้ามทั้ง 2 ตาราง (auth.login เพิ่งเกิดตอน
    # Login ด้านบน ต้องมาก่อน pr.created ที่ตั้งเวลาไว้ 1 นาทีก่อนหน้า)
    login_index = next(i for i, row in enumerate(rows) if row["action"] == "auth.login")
    pr_index = next(i for i, row in enumerate(rows) if row["action"] == "pr.created")
    assert login_index < pr_index


def test_pr_entity_type_filter_only_returns_audit_log_rows(
    client: TestClient, db_session: Session
):
    admin = _make_admin(db_session)

    pr = PurchasingRequisition(
        pr_no=2,
        section="Sec",
        division="Div",
        doc_date=date(2026, 9, 1),
        status=PRStatus.DRAFT,
        requested_by_id=admin.id,
    )
    db_session.add(pr)
    db_session.commit()
    db_session.refresh(pr)
    db_session.add(AuditLog(pr_id=pr.id, action="pr.created", actor_id=admin.id))
    db_session.commit()

    _login_as(client, admin.email)
    res = client.get("/system-log", params={"entity_type": "pr"})
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["action"] == "pr.created"
    assert rows[0]["source"] == "audit"
