"""Test PR Approval Level Workflow (Phase 11 Phase 2/3, 2026-09-15)

Pattern เดียวกับ tests/test_budget_control.py (AR) แต่ปรับให้ตรงกับ 3 จุดที่ PR ต่างจาก
AR ตามที่ยืนยันกับผู้ใช้แล้ว: ไม่มี FA Acknowledge (Level สุดท้ายอนุมัติ = หักงบจริงทันที),
ไม่มีขั้น Received แยก, PR ที่ไม่มี budget_control เลย Finalize ทันทีตอน Submit ไม่มี
Workflow เลย — และ budget_control อยู่ Nested ใต้ pr["budget_control"] ไม่ใช่ Field
แบนราบบน PR โดยตรงแบบ AR (ดู app/models/purchasing_requisition.py::PRBudgetControl)
"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import PRApprovalLevel, User
from tests.test_budget_control import _make_budget_master, _make_user
from tests.test_purchasing_requisitions import _login, _sample_pr_body

_PASSWORD = "password123456"


def _login_as(client: TestClient, email: str, password: str = _PASSWORD) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def _make_pr_level(db_session: Session, **kwargs) -> PRApprovalLevel:
    row = PRApprovalLevel(**kwargs)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _pr_budget_master(db_session: Session, **kwargs) -> None:
    kwargs.setdefault("budget_no", "BG0001")
    kwargs.setdefault("department", "Production")
    return _make_budget_master(db_session, **kwargs)


# ───────────────────────── Level Management CRUD (แยกจาก AR เต็มรูปแบบ) ─────────────────────────
def test_pr_level_management_requires_admin(client: TestClient, plain_user: User):
    _login(client)
    res = client.post(
        "/pr-approval-levels",
        json={
            "department": "Production",
            "level_no": 1,
            "level_name": "Manager",
            "approver_user_id": plain_user.id,
        },
    )
    assert res.status_code == 403


def test_pr_level_management_crud(client: TestClient, admin_user: User, db_session: Session):
    manager = _make_user(
        db_session, name="PR Manager", email="prmgr@example.com", department="Production"
    )
    _login_as(client, admin_user.email, "adminpass123")

    res = client.post(
        "/pr-approval-levels",
        json={
            "department": "Production",
            "level_no": 1,
            "level_name": "Manager",
            "approver_user_id": manager.id,
        },
    )
    assert res.status_code == 201, res.text
    level = res.json()
    assert level["approver_name"] == "PR Manager"

    patched = client.patch(
        f"/pr-approval-levels/{level['id']}", json={"level_name": "Manager Approve"}
    )
    assert patched.status_code == 200
    assert patched.json()["level_name"] == "Manager Approve"

    deleted = client.delete(f"/pr-approval-levels/{level['id']}")
    assert deleted.status_code == 204
    listed = client.get("/pr-approval-levels", params={"department": "Production"}).json()
    assert listed[0]["is_active"] is False


# ───────────────────────── Submit for Approval ─────────────────────────
def test_submit_for_approval_without_budget_control_finalizes_immediately(
    client: TestClient, plain_user: User
):
    """PR ที่ไม่เคยติ๊ก "Has Budget Control" เลย — Finalize ทันทีตอนกด "ส่งขออนุมัติ" ไม่มี
    Workflow อนุมัติใดๆ เลย (ยืนยันกับผู้ใช้แล้ว 2026-09-15)"""
    _login(client)
    created = client.post("/prs", json=_sample_pr_body(budget_control=None)).json()

    res = client.post(f"/prs/{created['id']}/submit-for-approval")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "finalized"
    assert body["budget_control"] is None

    history = client.get(f"/prs/{created['id']}/history").json()
    actions = [log["action"] for log in history]
    assert "pr.submitted_for_approval" in actions
    assert "pr.finalized" in actions


def test_submit_for_approval_no_levels_configured_deducts_and_finalizes(
    client: TestClient, plain_user: User, db_session: Session
):
    """แผนก Production ไม่มีการตั้ง PRApprovalLevel เลยในเทสนี้ — ไม่มี Level ให้รอ จึง
    หักงบจริงทันที + Finalize ทันที (ต่างจาก AR ตรงที่ไม่มี FA Acknowledge คั่น)"""
    master = _pr_budget_master(db_session)
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    res = client.post(f"/prs/{created['id']}/submit-for-approval")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "finalized"
    bc = body["budget_control"]
    assert bc["budget_approval_status"] == "approved"
    assert bc["budget_master_id"] == master.id
    assert bc["account_code"] == master.account_code
    assert Decimal(bc["budget_deducted_amount"]) == Decimal("1500.00")

    db_session.refresh(master)
    assert master.used_amount == Decimal("1500.00")


def test_submit_for_approval_twice_rejected(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/prs", json=_sample_pr_body(budget_control=None)).json()
    first = client.post(f"/prs/{created['id']}/submit-for-approval")
    assert first.status_code == 200

    second = client.post(f"/prs/{created['id']}/submit-for-approval")
    assert second.status_code == 409


def test_submit_for_approval_requires_login(client: TestClient):
    res = client.post("/prs/1/submit-for-approval")
    assert res.status_code == 401


def test_submit_for_approval_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/prs/9999/submit-for-approval")
    assert res.status_code == 404


# ───────────────────────── Multi-Level -> หักงบที่ Level สุดท้ายเลย (ไม่มี FA) ─────────────────────────
def test_two_level_final_approval_deducts_budget(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session, name="PR Manager2", email="prmgr2@example.com", department="Production"
    )
    gm = _make_user(db_session, name="PR GM2", email="prgm2@example.com", department="Production")
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=2,
        level_name="General Manager",
        approver_user_id=gm.id,
    )
    master = _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    pr_id = created["id"]

    submitted = client.post(f"/prs/{pr_id}/submit-for-approval").json()
    assert submitted["status"] == "draft"  # มี Level ให้รอ -> ยังไม่ Finalize
    assert submitted["budget_control"]["budget_approval_status"] == "pending"
    assert submitted["budget_control"]["current_approval_level"] == 1

    # plain_user (เจ้าของ PR เอง แต่ไม่ใช่ผู้อนุมัติ Level 1) กด Approve ไม่ได้
    forbidden = client.post(f"/prs/{pr_id}/approve-level")
    assert forbidden.status_code == 403

    _login_as(client, manager.email)
    step1 = client.post(f"/prs/{pr_id}/approve-level")
    assert step1.status_code == 200, step1.text
    step1_body = step1.json()
    assert step1_body["status"] == "finalized"  # Level แรกอนุมัติผ่าน = Finalize (Correction)
    assert step1_body["budget_control"]["current_approval_level"] == 2
    assert step1_body["budget_control"]["budget_approval_status"] == "pending"

    _login_as(client, gm.email)
    step2 = client.post(f"/prs/{pr_id}/approve-level")
    assert step2.status_code == 200, step2.text
    step2_body = step2.json()
    bc = step2_body["budget_control"]
    assert bc["budget_approval_status"] == "approved"
    assert bc["current_approval_level"] is None
    assert Decimal(bc["budget_deducted_amount"]) == Decimal("1500.00")

    db_session.refresh(master)
    assert master.used_amount == Decimal("1500.00")

    # gm เพิ่งอนุมัติ Level สุดท้ายไป — Workflow จบแล้ว (current_approval_level เป็น None)
    # ไม่ใช่ "ผู้อนุมัติ Level ปัจจุบัน" อีกต่อไป ต้องกลับมาเป็นเจ้าของ PR ถึงจะดู Progress
    # ต่อได้ (Phase 11 — ดู is_current_level_approver: เช็คแค่ Level ที่ "กำลัง" รออยู่)
    _login(client)
    progress = client.get(f"/prs/{pr_id}/approval-progress").json()
    assert [s["status"] for s in progress] == ["approved", "approved"]


def test_over_budget_requires_force(client: TestClient, plain_user: User, db_session: Session):
    _pr_budget_master(db_session, budgeted_amount=Decimal("1000.00"))
    _login(client)
    created = client.post(
        "/prs",
        json=_sample_pr_body(
            budget_control={"budget_no": "BG0001", "this_application": "5000.00"}
        ),
    ).json()

    blocked = client.post(f"/prs/{created['id']}/submit-for-approval")
    assert blocked.status_code == 409

    forced = client.post(f"/prs/{created['id']}/submit-for-approval", json={"force": True})
    assert forced.status_code == 200, forced.text
    bc = forced.json()["budget_control"]
    assert bc["budget_overridden"] is True


# ───────────────────────── Reject + Revise (Hybrid Gate) ─────────────────────────
def test_reject_level_allows_revise(client: TestClient, plain_user: User, db_session: Session):
    manager = _make_user(
        db_session, name="Reject Mgr PR", email="rejectmgrpr@example.com", department="Production"
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    submitted = client.post(f"/prs/{created['id']}/submit-for-approval").json()
    assert submitted["status"] == "draft"

    _login_as(client, manager.email)
    rejected = client.post(f"/prs/{created['id']}/reject-level", json={"reason": "ไม่อนุมัติ"})
    assert rejected.status_code == 200
    rejected_body = rejected.json()
    assert rejected_body["status"] == "draft"  # ไม่เคย Finalize เลย (Reject ที่ Level 1)
    assert rejected_body["budget_control"]["budget_approval_status"] == "rejected"

    # PR ที่มี budget_control ต้อง Gate ด้วย Rejected เท่านั้น (Hybrid Gate) — แก้ตรงๆ
    # ผ่าน PATCH ไม่ได้อีกต่อไป (กลับมาเป็นเจ้าของ PR ก่อน — Manager ไม่มีสิทธิ์แก้ไข PR
    # ของคนอื่นอยู่แล้วไม่ว่าสถานะไหน ต้องล็อกอินเป็นเจ้าของถึงจะเจอ 409 ตัวจริง)
    _login(client)
    edit_blocked = client.patch(f"/prs/{created['id']}", json=_sample_pr_body(remark="แก้ตรงๆ"))
    assert edit_blocked.status_code == 409

    # กลับมาเป็นเจ้าของ PR เพื่อกด Revise
    revised = client.post(f"/prs/{created['id']}/revise")
    assert revised.status_code == 201
    revised_body = revised.json()
    assert revised_body["status"] == "draft"
    assert revised_body["budget_control"]["budget_approval_status"] == "not_submitted"

    orig_after = client.get(f"/prs/{created['id']}").json()
    assert orig_after["budget_control"]["budget_approval_status"] == "rejected"
    assert orig_after["superseded_by_id"] == revised_body["id"]


def test_revise_approved_pr_with_budget_control_rejected(
    client: TestClient, plain_user: User, db_session: Session
):
    """PR ที่มี budget_control แล้ว Approved ไปแล้ว (หักงบไปแล้วจริง) Revise ตรงๆ ไม่ได้
    อีกต่อไป (ต่างจาก Scope Revision Phase 9 เดิมที่ Gate แค่ status == Finalized) — ต้อง
    Gate ด้วย budget_approval_status == Rejected เท่านั้น (Pattern เดียวกับ AR)"""
    _pr_budget_master(db_session)
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{created['id']}/submit-for-approval")  # ไม่มี Level -> Approved ทันที

    res = client.post(f"/prs/{created['id']}/revise")
    assert res.status_code == 409


def test_edit_during_pending_level_auto_cancels_approval(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session, name="Cancel Mgr PR", email="cancelmgrpr@example.com", department="Production"
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    submitted = client.post(f"/prs/{created['id']}/submit-for-approval").json()
    assert submitted["budget_control"]["budget_approval_status"] == "pending"

    edited = client.patch(f"/prs/{created['id']}", json=_sample_pr_body(remark="แก้ระหว่างรอ"))
    assert edited.status_code == 200
    assert edited.json()["budget_control"]["budget_approval_status"] == "not_submitted"

    history = client.get(f"/prs/{created['id']}/history").json()
    actions = [log["action"] for log in history]
    assert "pr.approval_cancelled_by_edit" in actions


# ───────────────────────── View Access ผู้อนุมัติ Level ปัจจุบัน (Phase 11) ─────────────────────────
def test_current_level_approver_can_view_pr_without_can_view_pr_flag(
    client: TestClient, plain_user: User, db_session: Session
):
    """ผู้อนุมัติ Level ปัจจุบันดู PR ของคนอื่นที่รอตัวเองอยู่ได้ แม้ไม่มี can_view_pr/
    can_view_all_pr เลยก็ตาม (Phase 11 — ขยายจาก Scope Revision Phase 9 เดิม)"""
    approver = _make_user(
        db_session,
        name="Approver No Flag",
        email="approvernoflag@example.com",
        department="Production",
        can_view_pr=False,
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=approver.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{created['id']}/submit-for-approval")

    _login_as(client, approver.email)
    res = client.get(f"/prs/{created['id']}")
    assert res.status_code == 200


def test_unrelated_user_still_cannot_view_pr(
    client: TestClient, plain_user: User, db_session: Session
):
    other = _make_user(
        db_session, name="Unrelated", email="unrelated@example.com", department="Sales"
    )
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    _login_as(client, other.email)
    res = client.get(f"/prs/{created['id']}")
    assert res.status_code == 403


# ───────────────────────── PR Attachments ─────────────────────────
def test_current_level_approver_can_upload_attachment(
    client: TestClient, plain_user: User, db_session: Session
):
    approver = _make_user(
        db_session,
        name="Attach Approver",
        email="attachapprover@example.com",
        department="Production",
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=approver.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{created['id']}/submit-for-approval")

    _login_as(client, approver.email)
    res = client.post(
        f"/prs/{created['id']}/attachments",
        files={"file": ("quote.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert res.status_code == 201, res.text
    assert res.json()["uploaded_by_name"] == "Attach Approver"


def test_unrelated_user_cannot_upload_attachment(
    client: TestClient, plain_user: User, db_session: Session
):
    other = _make_user(
        db_session, name="Unrelated Attach", email="unrelatedattach@example.com"
    )
    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()

    _login_as(client, other.email)
    res = client.post(
        f"/prs/{created['id']}/attachments",
        files={"file": ("quote.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert res.status_code == 403


# ───────────────────────── My PR Approvals (Phase 11 Phase 4, 2026-09-15) ─────────────────────────
def test_my_pr_approvals_requires_can_view_pr_approvals(client: TestClient, plain_user: User):
    """plain_user Default ไม่มี can_view_pr_approvals (ดู conftest.plain_user) — ต้องโดน 403
    เหมือน My Approvals ของ AR ทุกประการ (Reuse Flag เดียวกัน)"""
    _login(client)
    res = client.get("/prs/my-approvals", params={"bucket": "waiting"})
    assert res.status_code == 403
    counts = client.get("/prs/my-approvals/counts")
    assert counts.status_code == 403


def test_my_pr_approvals_buckets_and_counts(
    client: TestClient, plain_user: User, db_session: Session
):
    """Bucket waiting/mine/history เดินตาม Level จริง — Join PRBudgetControl (Nested
    Relation ไม่ใช่ Flat Field แบบ AR) ต้องได้ผลถูกต้องเหมือนกันทุกประการ"""
    manager = _make_user(
        db_session,
        name="MyApprovals Mgr",
        email="myapprovalsmgr@example.com",
        department="Production",
        can_view_pr_approvals=True,
    )
    gm = _make_user(
        db_session,
        name="MyApprovals GM",
        email="myapprovalsgm@example.com",
        department="Production",
        can_view_pr_approvals=True,
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=2,
        level_name="General Manager",
        approver_user_id=gm.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    pr_id = created["id"]
    client.post(f"/prs/{pr_id}/submit-for-approval")

    # Manager: PR นี้ต้องอยู่ทั้ง waiting และ mine (Level ปัจจุบันตรงกับตัวเอง) ยังไม่เคย
    # อยู่ใน history/returned เลย
    _login_as(client, manager.email)
    counts = client.get("/prs/my-approvals/counts").json()
    assert counts == {"waiting": 1, "mine": 1, "history": 0, "returned": 0}

    waiting = client.get("/prs/my-approvals", params={"bucket": "waiting"}).json()
    assert len(waiting) == 1
    item = waiting[0]
    assert item["id"] == pr_id
    assert item["pr_no_display"] == str(created["pr_no"])
    assert item["current_level_name"] == "Manager"
    assert item["actionable"] is True
    assert item["requested_by_name"] == "Plain User"

    mine = client.get("/prs/my-approvals", params={"bucket": "mine"}).json()
    assert [i["id"] for i in mine] == [pr_id]

    # GM ยังไม่ถึงคิว (Level 1 ยังไม่ผ่าน) — ไม่ควรเห็นใน mine เลย
    _login_as(client, gm.email)
    gm_mine = client.get("/prs/my-approvals", params={"bucket": "mine"}).json()
    assert gm_mine == []

    # Manager อนุมัติ Level 1 ผ่าน -> ย้ายไป history ของ Manager, ขึ้น mine ของ GM แทน
    _login_as(client, manager.email)
    client.post(f"/prs/{pr_id}/approve-level")

    mgr_counts = client.get("/prs/my-approvals/counts").json()
    assert mgr_counts == {"waiting": 1, "mine": 0, "history": 1, "returned": 0}
    mgr_history = client.get("/prs/my-approvals", params={"bucket": "history"}).json()
    assert [i["id"] for i in mgr_history] == [pr_id]

    _login_as(client, gm.email)
    gm_mine_after = client.get("/prs/my-approvals", params={"bucket": "mine"}).json()
    assert [i["id"] for i in gm_mine_after] == [pr_id]
    assert gm_mine_after[0]["current_level_name"] == "General Manager"


def test_my_pr_approvals_returned_bucket(
    client: TestClient, plain_user: User, db_session: Session
):
    manager = _make_user(
        db_session,
        name="Returned Mgr PR",
        email="returnedmgrpr@example.com",
        department="Production",
        can_view_pr_approvals=True,
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{created['id']}/submit-for-approval")

    _login_as(client, manager.email)
    client.post(f"/prs/{created['id']}/reject-level", json={"reason": "ไม่อนุมัติ"})

    counts = client.get("/prs/my-approvals/counts").json()
    assert counts == {"waiting": 0, "mine": 0, "history": 0, "returned": 1}
    returned = client.get("/prs/my-approvals", params={"bucket": "returned"}).json()
    assert [i["id"] for i in returned] == [created["id"]]
    assert returned[0]["budget_approval_status"] == "rejected"


def test_admin_sees_all_pending_in_my_pr_approvals_waiting(
    client: TestClient, admin_user: User, plain_user: User, db_session: Session
):
    """Admin เห็น Bucket waiting/returned ทั้งระบบเสมอ ไม่ต้องมี Level ผูกกับแผนกไหนเลย
    (Pattern เดียวกับ AR)"""
    manager = _make_user(
        db_session,
        name="Admin Scope Mgr PR",
        email="adminscopemgrpr@example.com",
        department="Production",
    )
    _make_pr_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )
    _pr_budget_master(db_session)

    _login(client)
    created = client.post("/prs", json=_sample_pr_body()).json()
    client.post(f"/prs/{created['id']}/submit-for-approval")

    _login_as(client, admin_user.email, "adminpass123")
    waiting = client.get("/prs/my-approvals", params={"bucket": "waiting"}).json()
    assert [i["id"] for i in waiting] == [created["id"]]
    counts = client.get("/prs/my-approvals/counts").json()
    assert counts["waiting"] == 1
