"""Test หน้า "การอนุมัติของฉัน" (My Approvals, Phase B/2, 2026-09-10)

ครอบคลุม Logic ที่เสี่ยงที่สุดตาม Docstring ท้ายไฟล์ app/services/budget_workflow.py:
- Permission Gate ของเมนู (is_admin/is_fa เห็นเสมอ, คนอื่นต้องเปิด can_view_approvals)
- Bucket "waiting" (กว้าง — ทุก Level ในแผนกที่เกี่ยวข้อง) เทียบกับ "mine" (แคบ — เฉพาะ
  Level ปัจจุบันตรงกับ actor เป๊ะ) ต้องไม่เท่ากันเมื่อมีหลาย Level
- Admin เห็นทุกใบทั้งระบบใน waiting/mine/returned (ไม่ต้องเป็นผู้อนุมัติที่ Config ไว้จริง)
  แต่ history ยังเป็น Log ส่วนตัว (เฉพาะที่ Admin กดเองจริง)
- FA เกี่ยวข้องเฉพาะ AR ที่ขึ้นถึงขั้น FA Acknowledge แล้วจริง (ไม่ใช่ทุกใบทั้งระบบ) —
  โดยเฉพาะ Bucket "returned" ต้องไม่รวม AR ที่ถูกปฏิเสธตั้งแต่ Level ก่อนหน้า FA
- Field "actionable" ต้องตรงกับ Bucket "mine" เป๊ะ (True เฉพาะที่กดอนุมัติได้จริงตอนนี้)
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.test_approval_requests import _sample_ar_body
from tests.test_budget_control import _login_as, _make_level, _make_user, _submit_for_approval


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


def _create_ar(client: TestClient) -> int:
    return client.post("/ars", json=_sample_ar_body()).json()["id"]


def _ids(items: list[dict]) -> set[int]:
    return {i["id"] for i in items}


# ───────────────────────── Permission Gate ─────────────────────────
def test_counts_and_list_require_login(client: TestClient):
    assert client.get("/ars/my-approvals/counts").status_code == 401
    assert client.get("/ars/my-approvals?bucket=waiting").status_code == 401


def test_plain_user_without_flag_forbidden(client: TestClient, plain_user: User):
    _login(client)
    assert client.get("/ars/my-approvals/counts").status_code == 403
    assert client.get("/ars/my-approvals?bucket=waiting").status_code == 403


def test_admin_and_fa_always_allowed_without_flag(
    client: TestClient, admin_user: User, db_session: Session
):
    fa = _make_user(db_session, name="FA MA", email="fama@example.com", is_fa=True)
    _login_as(client, admin_user.email, "adminpass123")
    assert client.get("/ars/my-approvals/counts").status_code == 200
    _login_as(client, fa.email)
    assert client.get("/ars/my-approvals/counts").status_code == 200


def test_can_view_approvals_flag_grants_access(client: TestClient, db_session: Session):
    approver = _make_user(
        db_session,
        name="Approver Only",
        email="apponly@example.com",
        department="Production",
        can_view_approvals=True,
    )
    _login_as(client, approver.email)
    assert client.get("/ars/my-approvals/counts").status_code == 200


def test_invalid_bucket_rejected(client: TestClient, db_session: Session):
    user = _make_user(db_session, name="U", email="u1@example.com", can_view_approvals=True)
    _login_as(client, user.email)
    res = client.get("/ars/my-approvals?bucket=not-a-real-bucket")
    assert res.status_code == 422


# ───────────────────────── waiting vs mine ─────────────────────────
def test_waiting_is_broader_than_mine_across_levels(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session,
        name="Manager MA",
        email="mgrma@example.com",
        department="Production",
        can_view_approvals=True,
    )
    gm = _make_user(
        db_session,
        name="GM MA",
        email="gmma@example.com",
        department="Production",
        can_view_approvals=True,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_level(
        db_session, department="Production", level_no=2, level_name="GM", approver_user_id=gm.id
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)  # pending, current_approval_level = 1

    _login_as(client, manager.email)
    waiting = client.get("/ars/my-approvals?bucket=waiting").json()
    mine = client.get("/ars/my-approvals?bucket=mine").json()
    assert ar_id in _ids(waiting)
    assert ar_id in _ids(mine)
    assert next(i for i in mine if i["id"] == ar_id)["actionable"] is True

    # GM เป็นผู้อนุมัติ Level 2 ของแผนกเดียวกัน — เห็นใน waiting (เกี่ยวข้องกับแผนกนี้)
    # แต่ยังไม่ถึงคิว (current_approval_level ยังเป็น 1) จึงไม่อยู่ใน mine
    _login_as(client, gm.email)
    waiting_gm = client.get("/ars/my-approvals?bucket=waiting").json()
    mine_gm = client.get("/ars/my-approvals?bucket=mine").json()
    assert ar_id in _ids(waiting_gm)
    assert ar_id not in _ids(mine_gm)


def test_unrelated_department_approver_sees_nothing(
    client: TestClient, plain_user: User, db_session: Session
):
    other = _make_user(
        db_session,
        name="Other Dept",
        email="otherdept@example.com",
        department="QC",
        can_view_approvals=True,
    )
    _make_level(
        db_session, department="QC", level_no=1, level_name="QC Manager", approver_user_id=other.id
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)  # แผนก Production ไม่มี Level -> ข้ามไป FA ทันที

    _login_as(client, other.email)
    assert ar_id not in _ids(client.get("/ars/my-approvals?bucket=waiting").json())
    assert ar_id not in _ids(client.get("/ars/my-approvals?bucket=mine").json())


# ───────────────────────── Admin sees everything ─────────────────────────
def test_admin_sees_all_pending_without_being_configured_approver(
    client: TestClient, plain_user: User, admin_user: User, db_session: Session
):
    manager = _make_user(db_session, name="Mgr2", email="mgr2@example.com", department="Production")
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)

    _login_as(client, admin_user.email, "adminpass123")
    counts = client.get("/ars/my-approvals/counts").json()
    assert counts["waiting"] >= 1
    assert counts["mine"] >= 1
    waiting = client.get("/ars/my-approvals?bucket=waiting").json()
    mine = client.get("/ars/my-approvals?bucket=mine").json()
    assert ar_id in _ids(waiting)
    assert ar_id in _ids(mine)
    assert next(i for i in mine if i["id"] == ar_id)["actionable"] is True


def test_admin_history_is_personal_not_system_wide(
    client: TestClient, plain_user: User, admin_user: User, db_session: Session
):
    manager = _make_user(
        db_session,
        name="Mgr3",
        email="mgr3@example.com",
        department="Production",
        can_view_approvals=True,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)

    _login_as(client, manager.email)
    res = client.post(f"/ars/{ar_id}/approve-level", json={"comment": "ok"})
    assert res.status_code == 200, res.text

    # Admin ไม่ได้เป็นคนกดอนุมัติเอง — ไม่ควรโผล่ใน history ส่วนตัวของ Admin
    _login_as(client, admin_user.email, "adminpass123")
    admin_history = client.get("/ars/my-approvals?bucket=history").json()
    assert ar_id not in _ids(admin_history)

    # แต่ Manager ที่กดเองต้องเห็นใน history ของตัวเอง
    _login_as(client, manager.email)
    mgr_history = client.get("/ars/my-approvals?bucket=history").json()
    assert ar_id in _ids(mgr_history)


# ───────────────────────── FA involvement ─────────────────────────
def test_fa_waiting_only_when_reached_fa_stage(
    client: TestClient, plain_user: User, db_session: Session
):
    fa = _make_user(db_session, name="FA2", email="fa2@example.com", is_fa=True)

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)  # แผนก Production ไม่มี Level -> ข้ามไป FA ทันที

    _login_as(client, fa.email)
    waiting = client.get("/ars/my-approvals?bucket=waiting").json()
    mine = client.get("/ars/my-approvals?bucket=mine").json()
    assert ar_id in _ids(waiting)
    assert ar_id in _ids(mine)
    assert next(i for i in mine if i["id"] == ar_id)["actionable"] is True


def test_fa_returned_excludes_rejected_before_reaching_fa(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(db_session, name="Mgr4", email="mgr4@example.com", department="Production")
    fa = _make_user(db_session, name="FA3", email="fa3@example.com", is_fa=True)
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)

    _login_as(client, manager.email)
    res = client.post(f"/ars/{ar_id}/reject-level", json={"reason": "ข้อมูลไม่ครบ"})
    assert res.status_code == 200, res.text

    # ถูกปฏิเสธตั้งแต่ Level 1 — ยังไม่เคยถึงขั้น FA เลย FA จึงไม่ควรเห็นใน returned
    _login_as(client, fa.email)
    fa_returned = client.get("/ars/my-approvals?bucket=returned").json()
    assert ar_id not in _ids(fa_returned)


def test_returned_bucket_shows_rejected_ar_to_involved_approver(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session,
        name="Mgr5",
        email="mgr5@example.com",
        department="Production",
        can_view_approvals=True,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    ar_id = _create_ar(client)
    _submit_for_approval(client, ar_id)

    _login_as(client, manager.email)
    res = client.post(f"/ars/{ar_id}/reject-level", json={"reason": "ข้อมูลไม่ครบ"})
    assert res.status_code == 200, res.text

    returned = client.get("/ars/my-approvals?bucket=returned").json()
    assert ar_id in _ids(returned)
    # ถูกปฏิเสธแล้ว ไม่ใช่คิวที่ต้องกดอะไรต่อ (รอผู้ขอ Revise เอง) — actionable ต้องเป็น False
    assert next(i for i in returned if i["id"] == ar_id)["actionable"] is False
    # หลุดจาก waiting/mine แล้วเช่นกันหลังถูกปฏิเสธ
    assert ar_id not in _ids(client.get("/ars/my-approvals?bucket=waiting").json())
    assert ar_id not in _ids(client.get("/ars/my-approvals?bucket=mine").json())


# ───────────────────────── counts endpoint ─────────────────────────
def test_counts_match_list_lengths(client: TestClient, plain_user: User, db_session: Session):
    manager = _make_user(
        db_session,
        name="Mgr6",
        email="mgr6@example.com",
        department="Production",
        can_view_approvals=True,
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    _submit_for_approval(client, _create_ar(client))
    _submit_for_approval(client, _create_ar(client))

    _login_as(client, manager.email)
    counts = client.get("/ars/my-approvals/counts").json()
    for bucket in ("waiting", "mine", "history", "returned"):
        items = client.get(f"/ars/my-approvals?bucket={bucket}").json()
        assert counts[bucket] == len(items), f"bucket={bucket}"
