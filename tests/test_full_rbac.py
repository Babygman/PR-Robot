"""Test Full RBAC (Correction 2026-09-10, ขยาย Correction 2/3 — แยก can_view_all ตาม PR/AR
และแยกเมนู Log PR/Log AR) — 10 เมนูตาม Matrix ที่ผู้ใช้ยืนยัน ครอบคลุม:
- can_view_pr / can_view_ar: เปิดเมนู PR List/New PR และ Approval Request ตามลำดับ —
  ไม่เปิด = 403 ทั้ง Create/List
- Ownership Scoping: ติ๊ก can_view_pr/can_view_ar อย่างเดียว เห็นเฉพาะ PR/AR ของตัวเอง —
  can_view_all_pr/can_view_all_ar ขยายให้ "เห็น" ทั้งหมด แต่ไม่ได้แปลว่าสร้างใหม่ได้ (ยังต้อง
  มี can_view_pr/ar) และไม่ได้แปลว่าแก้ไข/พิมพ์/ลบของคนอื่นได้ (PR: can_view_all_pr เห็น/
  History ได้ทุกใบ แต่ Update/Revise/PDF เฉพาะของตัวเองเท่านั้น)
- PR ไม่มีผู้อนุมัติในระบบ (Scope Revision Phase 9) — บังคับ Owner-only ทุก Endpoint จริง
  เว้นแต่ Admin (แก้ไข) หรือ Admin/can_view_all_pr (ดูอย่างเดียว)
- AR มีผู้อนุมัติ Level ตามแผนก — Endpoint รายละเอียด (get/pdf/history/approval-progress)
  ต้องไม่ถูกจำกัดด้วย can_view_ar/Ownership (Authorization จริงอยู่ที่ budget_workflow แยก
  ต่างหาก) — Ownership Scoping มีผลแค่ list_ars เมนู "Approval Request" เท่านั้น
- Log PR (/audit-logs/pr): Admin/can_view_all_pr เท่านั้น
- Log AR (/audit-logs/ar): Admin/FA/can_view_all_ar เท่านั้น
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User
from tests.test_approval_requests import _sample_ar_body
from tests.test_budget_control import _login_as, _make_user
from tests.test_purchasing_requisitions import _sample_pr_body


# ───────────────────────── PR: Permission Gate ─────────────────────────
def test_pr_routes_require_can_view_pr(client: TestClient, db_session: Session):
    no_pr = _make_user(
        db_session,
        name="No PR",
        email="nopr@example.com",
        department="Production",
        can_view_pr=False,
        can_view_ar=False,
    )
    _login_as(client, no_pr.email)
    assert client.post("/prs", json=_sample_pr_body()).status_code == 403
    assert client.get("/prs").status_code == 403


def test_can_view_all_pr_alone_cannot_create_pr(client: TestClient, db_session: Session):
    """can_view_all_pr คือสิทธิ์ดูภาพรวมอย่างเดียว ไม่ได้แปลว่าสร้าง PR แทนคนอื่นได้"""
    viewer = _make_user(
        db_session,
        name="Viewer PR",
        email="viewerpr@example.com",
        can_view_pr=False,
        can_view_ar=False,
        can_view_all_pr=True,
    )
    _login_as(client, viewer.email)
    res = client.post("/prs", json=_sample_pr_body())
    assert res.status_code == 403
    # แต่เข้าเมนู (List) ได้ปกติเพราะ can_view_all_pr ขยายสิทธิ์ดูให้
    assert client.get("/prs").status_code == 200


# ───────────────────────── PR: Ownership Scoping ─────────────────────────
def test_pr_ownership_scoping_list_and_detail(client: TestClient, db_session: Session):
    owner = _make_user(db_session, name="PR Owner", email="prowner@example.com", department="A")
    other = _make_user(db_session, name="PR Other", email="prother@example.com", department="B")

    _login_as(client, owner.email)
    pr_id = client.post("/prs", json=_sample_pr_body()).json()["id"]

    # เจ้าของเห็น PR ตัวเองใน List และเปิด Detail ได้
    listed = client.get("/prs").json()
    assert any(p["id"] == pr_id for p in listed)
    assert client.get(f"/prs/{pr_id}").status_code == 200

    # คนอื่นที่มีแค่ can_view_pr ไม่เห็น PR นี้ใน List และเปิด Detail ตรงๆ ไม่ได้ (403)
    _login_as(client, other.email)
    listed_other = client.get("/prs").json()
    assert not any(p["id"] == pr_id for p in listed_other)
    res = client.get(f"/prs/{pr_id}")
    assert res.status_code == 403
    assert client.patch(f"/prs/{pr_id}", json=_sample_pr_body()).status_code == 403
    assert client.get(f"/prs/{pr_id}/history").status_code == 403


def test_pr_can_view_all_pr_sees_everyone(client: TestClient, db_session: Session):
    owner = _make_user(db_session, name="PR Owner2", email="prowner2@example.com", department="A")
    viewer = _make_user(
        db_session,
        name="PR ViewAll",
        email="prviewall@example.com",
        can_view_pr=False,
        can_view_all_pr=True,
    )

    _login_as(client, owner.email)
    pr_id = client.post("/prs", json=_sample_pr_body()).json()["id"]

    _login_as(client, viewer.email)
    listed = client.get("/prs").json()
    assert any(p["id"] == pr_id for p in listed)
    assert client.get(f"/prs/{pr_id}").status_code == 200
    assert client.get(f"/prs/{pr_id}/history").status_code == 200


def test_pr_can_view_all_pr_cannot_edit_others(client: TestClient, db_session: Session):
    """Correction 2 (2026-09-10): "เห็นทั้งหมด" ครอบคลุมแค่การดู — แก้ไข/Revise/พิมพ์ PR
    ของคนอื่นยังคงทำไม่ได้แม้ติ๊ก can_view_all_pr (ต้องเป็นเจ้าของหรือ Admin เท่านั้น)"""
    owner = _make_user(db_session, name="PR Owner3", email="prowner3@example.com", department="A")
    viewer = _make_user(
        db_session,
        name="PR ViewAll2",
        email="prviewall2@example.com",
        can_view_all_pr=True,
    )

    _login_as(client, owner.email)
    pr_id = client.post("/prs", json=_sample_pr_body()).json()["id"]

    _login_as(client, viewer.email)
    assert client.patch(f"/prs/{pr_id}", json=_sample_pr_body()).status_code == 403
    assert client.get(f"/prs/{pr_id}/pdf").status_code == 403


# ───────────────────────── AR: Permission Gate ─────────────────────────
def test_ar_routes_require_can_view_ar(client: TestClient, db_session: Session):
    no_ar = _make_user(
        db_session,
        name="No AR",
        email="noar@example.com",
        department="Production",
        can_view_pr=False,
        can_view_ar=False,
    )
    _login_as(client, no_ar.email)
    assert client.post("/ars", json=_sample_ar_body()).status_code == 403
    assert client.get("/ars").status_code == 403


def test_can_view_all_ar_alone_cannot_create_ar(client: TestClient, db_session: Session):
    viewer = _make_user(
        db_session,
        name="Viewer AR",
        email="viewerar@example.com",
        department="Production",
        can_view_pr=False,
        can_view_ar=False,
        can_view_all_ar=True,
    )
    _login_as(client, viewer.email)
    res = client.post("/ars", json=_sample_ar_body())
    assert res.status_code == 403
    assert client.get("/ars").status_code == 200


# ───────────────────────── AR: Ownership Scoping (List เท่านั้น) ─────────────────────────
def test_ar_list_ownership_scoping(client: TestClient, db_session: Session):
    owner = _make_user(db_session, name="AR Owner", email="arowner@example.com", department="A")
    other = _make_user(db_session, name="AR Other", email="arother@example.com", department="B")

    _login_as(client, owner.email)
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]

    listed_owner = client.get("/ars").json()
    assert any(a["id"] == ar_id for a in listed_owner)

    _login_as(client, other.email)
    listed_other = client.get("/ars").json()
    assert not any(a["id"] == ar_id for a in listed_other)


def test_ar_can_view_all_ar_sees_everyone_in_list(client: TestClient, db_session: Session):
    owner = _make_user(db_session, name="AR Owner2", email="arowner2@example.com", department="A")
    viewer = _make_user(
        db_session,
        name="AR ViewAll",
        email="arviewall@example.com",
        department="B",
        can_view_ar=False,
        can_view_all_ar=True,
    )

    _login_as(client, owner.email)
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]

    _login_as(client, viewer.email)
    listed = client.get("/ars").json()
    assert any(a["id"] == ar_id for a in listed)


def test_ar_detail_routes_not_restricted_by_ownership_or_can_view_ar(
    client: TestClient, db_session: Session
):
    """ต่างจาก PR — AR มีผู้อนุมัติ Level ตามแผนกที่ต้องเปิดดู/พิมพ์/ดูประวัติ AR ของคนอื่น
    ที่รอตัวเองอยู่ได้โดยชอบธรรม (Authorization จริงอยู่ที่ budget_workflow แยกต่างหาก ไม่ใช่
    can_view_ar) — Endpoint รายละเอียดจึงต้องเปิดให้ Login แล้วเรียกได้เหมือนเดิมทั้งหมด
    ไม่ว่าจะเป็นเจ้าของหรือไม่ก็ตาม"""
    owner = _make_user(db_session, name="AR Owner3", email="arowner3@example.com", department="A")
    bystander = _make_user(
        db_session,
        name="AR Bystander",
        email="arbystander@example.com",
        can_view_ar=False,
        can_view_pr=False,
    )

    _login_as(client, owner.email)
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]

    _login_as(client, bystander.email)
    assert client.get(f"/ars/{ar_id}").status_code == 200
    assert client.get(f"/ars/{ar_id}/pdf").status_code == 200
    assert client.get(f"/ars/{ar_id}/history").status_code == 200
    assert client.get(f"/ars/{ar_id}/approval-progress").status_code == 200


# ───────────────────────── Log PR (/audit-logs/pr) ─────────────────────────
def test_audit_logs_pr_require_login(client: TestClient):
    assert client.get("/audit-logs/pr").status_code == 401


def test_audit_logs_pr_forbidden_for_plain_user_and_fa(client: TestClient, db_session: Session):
    user = _make_user(
        db_session,
        name="No LogPR",
        email="nologpr@example.com",
        can_view_pr=True,
        can_view_ar=True,
        can_view_all_pr=False,
    )
    _login_as(client, user.email)
    assert client.get("/audit-logs/pr").status_code == 403

    # FA ไม่เกี่ยวกับ Log PR เลย (ต่างจาก Log AR) — ดู Docstring app/models/user.py
    # Correction 3
    fa = _make_user(db_session, name="FA NoLogPR", email="fanologpr@example.com", is_fa=True)
    _login_as(client, fa.email)
    assert client.get("/audit-logs/pr").status_code == 403


def test_audit_logs_pr_allowed_for_admin_and_can_view_all_pr(
    client: TestClient, admin_user: User, db_session: Session
):
    viewer = _make_user(
        db_session,
        name="ViewAllPR Log",
        email="viewallprlog@example.com",
        can_view_pr=False,
        can_view_ar=False,
        can_view_all_pr=True,
    )

    _login_as(client, admin_user.email, "adminpass123")
    assert client.get("/audit-logs/pr").status_code == 200
    _login_as(client, viewer.email)
    assert client.get("/audit-logs/pr").status_code == 200


def test_audit_logs_pr_only_contains_pr_activity(
    client: TestClient, admin_user: User, db_session: Session
):
    owner = _make_user(db_session, name="Log Owner", email="logowner@example.com", department="A")

    _login_as(client, owner.email)
    pr_id = client.post("/prs", json=_sample_pr_body()).json()["id"]
    client.post("/ars", json=_sample_ar_body())

    _login_as(client, admin_user.email, "adminpass123")
    logs = client.get("/audit-logs/pr").json()
    assert all(log["doc_type"] == "pr" for log in logs)

    pr_log = next(log for log in logs if log["doc_id"] == pr_id)
    assert pr_log["action"] == "pr.created"
    assert pr_log["doc_no_display"] is not None


# ───────────────────────── Log AR (/audit-logs/ar) ─────────────────────────
def test_audit_logs_ar_require_login(client: TestClient):
    assert client.get("/audit-logs/ar").status_code == 401


def test_audit_logs_ar_forbidden_for_plain_user(client: TestClient, db_session: Session):
    user = _make_user(
        db_session,
        name="No LogAR",
        email="nologar@example.com",
        can_view_pr=True,
        can_view_ar=True,
        can_view_all_ar=False,
    )
    _login_as(client, user.email)
    assert client.get("/audit-logs/ar").status_code == 403


def test_audit_logs_ar_allowed_for_admin_fa_and_can_view_all_ar(
    client: TestClient, admin_user: User, db_session: Session
):
    fa = _make_user(db_session, name="FA LogAR", email="falogar@example.com", is_fa=True)
    viewer = _make_user(
        db_session,
        name="ViewAllAR Log",
        email="viewallarlog@example.com",
        can_view_pr=False,
        can_view_ar=False,
        can_view_all_ar=True,
    )

    _login_as(client, admin_user.email, "adminpass123")
    assert client.get("/audit-logs/ar").status_code == 200
    _login_as(client, fa.email)
    assert client.get("/audit-logs/ar").status_code == 200
    _login_as(client, viewer.email)
    assert client.get("/audit-logs/ar").status_code == 200


def test_audit_logs_ar_only_contains_ar_activity(
    client: TestClient, admin_user: User, db_session: Session
):
    owner = _make_user(db_session, name="Log Owner2", email="logowner2@example.com", department="A")

    _login_as(client, owner.email)
    client.post("/prs", json=_sample_pr_body())
    ar_id = client.post("/ars", json=_sample_ar_body()).json()["id"]

    _login_as(client, admin_user.email, "adminpass123")
    logs = client.get("/audit-logs/ar").json()
    assert all(log["doc_type"] == "ar" for log in logs)

    ar_log = next(log for log in logs if log["doc_id"] == ar_id)
    assert ar_log["action"] == "ar.created"
    assert ar_log["doc_subject"] == _sample_ar_body()["subject"]
