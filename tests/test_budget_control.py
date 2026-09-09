"""Test Budget Control — Multi-Level Approval + FA Acknowledge + Level Management +
Excel Upload (Phase 10, 2026-09-09, Business Decision v4.1)

ครอบคลุม Logic ที่เสี่ยงที่สุดตาม Design: การเรียง Level (ข้ามลำดับไม่ได้), จุดหักยอด
งบมีจุดเดียว (FA Acknowledge เท่านั้น), Revise คืนยอด+Reset กลับ Level 1 ใหม่เสมอ, สิทธิ์
(ผู้อนุมัติเจาะจงคน + Admin Override), แผนกไม่มี Level ข้ามตรงไป FA, เกินงบ (Block/Force)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import openpyxl
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import ApprovalRequest, ARBudgetType, BudgetApprovalLevel, BudgetMaster, User
from app.services.ar_pdf import render_ar_html
from tests.test_approval_requests import _sample_ar_body

_PASSWORD = "password123456"


def _make_user(db_session: Session, **kwargs) -> User:
    kwargs.setdefault("password_hash", hash_password(_PASSWORD))
    user = User(**kwargs)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login_as(client: TestClient, email: str, password: str = _PASSWORD) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def _make_budget_master(db_session: Session, **kwargs) -> BudgetMaster:
    defaults = dict(
        department="Production",
        budget_type="expenses",
        account_code="5100-01",
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        budgeted_amount=Decimal("10000.00"),
        used_amount=Decimal("0.00"),
    )
    defaults.update(kwargs)
    defaults["budget_type"] = ARBudgetType(defaults["budget_type"])
    row = BudgetMaster(**defaults)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _make_level(db_session: Session, **kwargs) -> BudgetApprovalLevel:
    row = BudgetApprovalLevel(**kwargs)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _finalize(client: TestClient, ar_id: int) -> dict:
    res = client.get(f"/ars/{ar_id}/pdf")
    assert res.status_code == 200
    return client.get(f"/ars/{ar_id}").json()


# ───────────────────────── Level Management CRUD ─────────────────────────
def test_level_management_requires_admin(client: TestClient, plain_user: User):
    _login_as(client, plain_user.email, "plainpass123")
    res = client.post(
        "/budget-approval-levels",
        json={
            "department": "Production",
            "level_no": 1,
            "level_name": "Manager",
            "approver_user_id": plain_user.id,
        },
    )
    assert res.status_code == 403


def test_level_management_crud(client: TestClient, admin_user: User, db_session: Session):
    manager = _make_user(
        db_session, name="Manager A", email="mgr@example.com", department="Production"
    )
    _login_as(client, admin_user.email, "adminpass123")

    res = client.post(
        "/budget-approval-levels",
        json={
            "department": "Production",
            "level_no": 1,
            "level_name": "Manager",
            "approver_user_id": manager.id,
        },
    )
    assert res.status_code == 201, res.text
    level = res.json()
    assert level["approver_name"] == "Manager A"

    # ห้ามซ้ำ level_no เดิมของแผนกเดียวกัน
    dup = client.post(
        "/budget-approval-levels",
        json={
            "department": "Production",
            "level_no": 1,
            "level_name": "Manager (dup)",
            "approver_user_id": manager.id,
        },
    )
    assert dup.status_code == 409

    patched = client.patch(
        f"/budget-approval-levels/{level['id']}", json={"level_name": "Manager Approve"}
    )
    assert patched.status_code == 200
    assert patched.json()["level_name"] == "Manager Approve"

    deleted = client.delete(f"/budget-approval-levels/{level['id']}")
    assert deleted.status_code == 204
    listed = client.get("/budget-approval-levels", params={"department": "Production"}).json()
    assert listed[0]["is_active"] is False


# ───────────────────────── Requester ต้องมี Department ─────────────────────────
def test_create_ar_requires_department(client: TestClient, db_session: Session):
    no_dept_user = _make_user(
        db_session, name="No Dept", email="nodept@example.com", department=None
    )
    _login_as(client, no_dept_user.email)
    res = client.post("/ars", json=_sample_ar_body())
    assert res.status_code == 400


# ───────────────────────── Multi-Level -> FA Acknowledge (Happy Path) ─────────────────────────
def test_two_level_then_fa_acknowledge_deducts_budget_once(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session, name="Manager A", email="mgr2@example.com", department="Production"
    )
    gm = _make_user(db_session, name="GM A", email="gm2@example.com", department="Production")
    fa = _make_user(db_session, name="FA A", email="fa2@example.com", is_fa=True)
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=2,
        level_name="General Manager",
        approver_user_id=gm.id,
    )
    master = _make_budget_master(db_session)

    _login_as(client, plain_user.email, "plainpass123")
    created = client.post("/ars", json=_sample_ar_body()).json()
    ar_id = created["id"]

    ar_after_finalize = _finalize(client, ar_id)
    assert ar_after_finalize["budget_approval_status"] == "pending"
    assert ar_after_finalize["current_approval_level"] == 1
    assert ar_after_finalize["budget_master_id"] == master.id

    # plain_user (ไม่ใช่ผู้อนุมัติ Level 1) กด Approve ไม่ได้
    forbidden = client.post(f"/ars/{ar_id}/approve-level")
    assert forbidden.status_code == 403

    _login_as(client, manager.email)
    step1 = client.post(f"/ars/{ar_id}/approve-level")
    assert step1.status_code == 200, step1.text
    assert step1.json()["current_approval_level"] == 2
    assert step1.json()["budget_approval_status"] == "pending"

    # ข้าม Level ไม่ได้ — gm ต้องรอจนกว่าจะถึงคิวตัวเอง (แต่ในเคสนี้ถึงคิวแล้วพอดี) ลอง
    # ให้ Manager กด Approve ซ้ำ (ไม่ใช่ผู้อนุมัติ Level ปัจจุบันอีกแล้ว) ต้องโดนบล็อก
    _login_as(client, manager.email)
    stale = client.post(f"/ars/{ar_id}/approve-level")
    assert stale.status_code == 403

    _login_as(client, gm.email)
    step2 = client.post(f"/ars/{ar_id}/approve-level")
    assert step2.status_code == 200, step2.text
    assert step2.json()["budget_approval_status"] == "pending_fa_acknowledge"
    assert step2.json()["current_approval_level"] is None

    _login_as(client, plain_user.email, "plainpass123")
    forbidden_fa = client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": False})
    assert forbidden_fa.status_code == 403

    _login_as(client, fa.email)
    ack = client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": False})
    assert ack.status_code == 200, ack.text
    body = ack.json()
    assert body["budget_approval_status"] == "approved"
    assert Decimal(str(body["budget_deducted_amount"])) == Decimal("9327.10")
    assert body["budget_overridden"] is False

    db_session.refresh(master)
    assert master.used_amount == Decimal("9327.10")

    progress = client.get(f"/ars/{ar_id}/approval-progress").json()
    assert [s["status"] for s in progress] == ["approved", "approved", "approved"]
    assert progress[-1]["step_type"] == "fa_acknowledge"

    # PDF Auto-fill: ชื่อผู้อนุมัติต้องปรากฏใน HTML ที่ Render จริง (ตาราง Authority + F&A)
    ar_obj = db_session.get(ApprovalRequest, ar_id)
    html = render_ar_html(db_session, ar_obj)
    assert "Manager A" in html
    assert "GM A" in html
    assert "FA A" in html


# ───────────────────────── Admin Override ─────────────────────────
def test_admin_can_override_level_approval(
    client: TestClient, plain_user: User, admin_user: User, db_session: Session
):
    manager = _make_user(
        db_session, name="Manager B", email="mgr3@example.com", department="Production"
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_budget_master(db_session)

    _login_as(client, plain_user.email, "plainpass123")
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]
    _finalize(client, ar_id)

    _login_as(client, admin_user.email, "adminpass123")
    res = client.post(f"/ars/{ar_id}/approve-level")
    assert res.status_code == 200

    progress = client.get(f"/ars/{ar_id}/approval-progress").json()
    assert progress[0]["acted_as_override"] is True
    assert progress[0]["acted_by_name"] == admin_user.name


# ───────────────────────── Reject -> Revise -> เข้าคิว Level 1 ใหม่ ─────────────────────────
def test_reject_then_revise_resets_to_level_one(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session, name="Manager C", email="mgr4@example.com", department="Production"
    )
    gm = _make_user(db_session, name="GM C", email="gm4@example.com", department="Production")
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=2,
        level_name="General Manager",
        approver_user_id=gm.id,
    )
    _make_budget_master(db_session)

    _login_as(client, plain_user.email, "plainpass123")
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]
    _finalize(client, ar_id)

    _login_as(client, manager.email)
    client.post(f"/ars/{ar_id}/approve-level")

    _login_as(client, gm.email)
    rejected = client.post(f"/ars/{ar_id}/reject-level", json={"reason": "ยอดไม่ตรงกับใบเสนอราคา"})
    assert rejected.status_code == 200
    assert rejected.json()["budget_approval_status"] == "rejected"

    _login_as(client, plain_user.email, "plainpass123")
    revised = client.post(f"/ars/{ar_id}/revise")
    assert revised.status_code == 201
    revised_body = revised.json()
    assert revised_body["budget_approval_status"] == "not_submitted"
    assert revised_body["current_approval_level"] is None

    # Finalize ฉบับ Revise แล้ว — ต้องเริ่มที่ Level 1 ใหม่ (ไม่ข้ามไป Level 2 เพราะ
    # Level 1 เคยผ่านมาก่อนหน้า Reject)
    ar_after = _finalize(client, revised_body["id"])
    assert ar_after["budget_approval_status"] == "pending"
    assert ar_after["current_approval_level"] == 1


# ───────────────────────── แผนกไม่มี Level -> ข้ามตรงไป FA ─────────────────────────
def test_department_with_no_levels_skips_straight_to_fa(client: TestClient, db_session: Session):
    fa = _make_user(db_session, name="FA Sales", email="fasales@example.com", is_fa=True)
    requester = _make_user(
        db_session, name="Sales Req", email="salesreq@example.com", department="Sales"
    )
    _make_budget_master(db_session, department="Sales", account_code="6100-01")

    _login_as(client, requester.email)
    ar_id = client.post("/ars", json=_sample_ar_body(budget_no="6100-01")).json()["id"]
    ar_after = _finalize(client, ar_id)
    assert ar_after["budget_approval_status"] == "pending_fa_acknowledge"
    assert ar_after["current_approval_level"] is None

    _login_as(client, fa.email)
    ack = client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": False})
    assert ack.status_code == 200
    assert ack.json()["budget_approval_status"] == "approved"


# ───────────────────────── เกินงบ: Block ไม่ Force / Force สำเร็จ ─────────────────────────
def test_fa_acknowledge_over_budget_blocked_unless_forced(client: TestClient, db_session: Session):
    fa = _make_user(db_session, name="FA Tight", email="fatight@example.com", is_fa=True)
    requester = _make_user(
        db_session, name="Tight Req", email="tightreq@example.com", department="Tight"
    )
    _make_budget_master(
        db_session, department="Tight", account_code="7100-01", budgeted_amount=Decimal("1000.00")
    )

    _login_as(client, requester.email)
    ar_id = client.post(
        "/ars", json=_sample_ar_body(budget_no="7100-01", this_application="9327.10")
    ).json()["id"]
    _finalize(client, ar_id)

    _login_as(client, fa.email)
    blocked = client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": False})
    assert blocked.status_code == 409

    forced = client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": True})
    assert forced.status_code == 200
    body = forced.json()
    assert body["budget_overridden"] is True
    assert Decimal(str(body["budget_deducted_amount"])) == Decimal("9327.10")


# ───────────────────────── Revise หลัง Approved -> คืนยอดจริง ─────────────────────────
def test_revise_after_approved_refunds_budget(
    client: TestClient, plain_user: User, db_session: Session
):
    fa = _make_user(db_session, name="FA Refund", email="farefund@example.com", is_fa=True)
    master = _make_budget_master(db_session, department="Production", account_code="5100-01")

    _login_as(client, plain_user.email, "plainpass123")
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]
    _finalize(client, ar_id)  # ไม่มี Level Setup ให้ Production ในเทสนี้ -> ตรงไป FA เลย

    _login_as(client, fa.email)
    client.post(f"/ars/{ar_id}/fa-acknowledge", json={"force": False})
    db_session.refresh(master)
    assert master.used_amount == Decimal("9327.10")

    _login_as(client, plain_user.email, "plainpass123")
    revised = client.post(f"/ars/{ar_id}/revise")
    assert revised.status_code == 201

    db_session.refresh(master)
    assert master.used_amount == Decimal("0.00")


# ───────────────────────── Excel Upload ─────────────────────────
def _build_xlsx_bytes(rows: list[list]) -> bytes:
    import io

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "department",
            "budget_type",
            "account_code",
            "period_start",
            "period_end",
            "budget_name",
            "budgeted_amount",
        ]
    )
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_upload_requires_fa_or_admin(client: TestClient, plain_user: User):
    _login_as(client, plain_user.email, "plainpass123")
    content = _build_xlsx_bytes([])
    res = client.post(
        "/budget/upload",
        files={
            "file": (
                "budget.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 403


def test_excel_upload_partial_success_and_reupload_merge(client: TestClient, db_session: Session):
    fa = _make_user(db_session, name="FA Upload", email="faupload@example.com", is_fa=True)
    _login_as(client, fa.email)

    content = _build_xlsx_bytes(
        [
            [
                "Warehouse",
                "expenses",
                "8100-01",
                "01/01/2026",
                "31/12/2026",
                "Warehouse Budget",
                50000,
            ],
            [
                "Warehouse",
                "expenses",
                "8100-02",
                "01/01/2026",
                "31/12/2026",
                None,
                -100,
            ],  # ผิด: ติดลบ
            [
                "Warehouse",
                "assets",
                "8200-01",
                "31/12/2026",
                "01/01/2026",
                None,
                1000,
            ],  # ผิด: start > end
        ]
    )
    res = client.post(
        "/budget/upload",
        files={
            "file": (
                "budget.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["total_rows"] == 3
    assert body["success_rows"] == 1
    assert body["error_rows"] == 2

    listed = client.get("/budget", params={"department": "Warehouse"}).json()
    assert len(listed) == 1
    assert listed[0]["budgeted_amount"] == "50000.00" or Decimal(
        str(listed[0]["budgeted_amount"])
    ) == Decimal("50000.00")

    # Re-upload เดิม แต่เปลี่ยน budgeted_amount — ต้อง Merge/Update แถวเดิม ไม่สร้างซ้ำ
    content2 = _build_xlsx_bytes(
        [
            [
                "Warehouse",
                "expenses",
                "8100-01",
                "01/01/2026",
                "31/12/2026",
                "Warehouse Budget 2",
                60000,
            ]
        ]
    )
    res2 = client.post(
        "/budget/upload",
        files={
            "file": (
                "budget2.xlsx",
                content2,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert res2.status_code == 201
    assert res2.json()["success_rows"] == 1

    listed2 = client.get(
        "/budget", params={"department": "Warehouse", "account_code": "8100-01"}
    ).json()
    assert len(listed2) == 1
    assert Decimal(str(listed2[0]["budgeted_amount"])) == Decimal("60000.00")
