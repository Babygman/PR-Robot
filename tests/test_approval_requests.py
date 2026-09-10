"""Test บันทึก Approval Request (AR) + Generate PDF — Pattern เดียวกับ
tests/test_purchasing_requisitions.py เกือบทุกประการ (Business Decision 2026-09-08)
ยกเว้น Flow Finalize/Revise ที่ถูกแก้ใหม่เฉพาะ AR แล้ว (Correction 2026-09-10 — ดู
Docstring บนสุดของ app/api/routes/approval_requests.py): พิมพ์/ดาวน์โหลด PDF ไม่มีผล
ข้างเคียงอีกต่อไป, มี Endpoint ใหม่ POST /ars/{id}/submit-for-approval เป็นจุดเริ่ม
Workflow อนุมัติหักงบ, Revise ได้เฉพาะฉบับที่ถูก Reject มาเท่านั้น

Test ในไฟล์นี้ทั้งหมดใช้ plain_user (Department "Production") ที่ไม่มีการตั้ง
BudgetApprovalLevel ไว้เลยในแต่ละ Test (DB In-memory ใหม่ทุก Test) จึง
submit-for-approval จะ Finalize ทันที (ข้ามตรงไป FA Acknowledge — ไม่มี Level ให้รอ)
เสมอในไฟล์นี้ — Test ที่ต้องมี Level หลายขั้นจริง (Pending รอ Level, PATCH ยกเลิก
คำขออนุมัติอัตโนมัติ ฯลฯ) อยู่ใน tests/test_budget_control.py แทน (มี Helper ตั้ง
Level ให้พร้อมอยู่แล้ว)
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ApprovalRequest, ARStatus, User
from app.services.ar_pdf import render_ar_html


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


def _login_as(client: TestClient, email: str, password: str) -> None:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text


def _sample_ar_body(**overrides) -> dict:
    body = {
        "application_date": "2026-09-08",
        "subject": "Expense for Maintenance Car Camry 4บภ4865 (Check 130,000 km.)",
        "budget_type": "expenses",
        "budget_no": "5100-01",
        "budget_sub_category": "Mnt. Motor",
        "budget_name": "Vehicle Maintenance Budget 2026",
        "budget_for_year": "17100.00",
        "amount_used_before": None,
        "this_application": "9327.10",
        "balance": "7772.90",
        "description": "Expense for Maintenance Car Camry 4บภ4865 (Check 130,000 km.)",
        "amount_items": [
            {"label": "Check 130,000 km.", "amount": "4058.70"},
            {"label": "Othe Mnt.", "amount": "5268.40"},
        ],
        "total": "9327.10",
        "vat_amount": "652.90",
        "grand_total": "9980.00",
        "suppliers": "Vorachak Yont Co., Ltd. (Tel. 02-743-9555 / Fax. 02-743-9502)",
        "term_of_payment": "Credit 30 Days",
        "schedule_start": "2026-09-03",
        "schedule_finish": "2026-09-15",
    }
    body.update(overrides)
    return body


def test_create_ar_requires_login(client: TestClient):
    res = client.post("/ars", json=_sample_ar_body())
    assert res.status_code == 401


def test_create_ar_success(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/ars", json=_sample_ar_body())
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "draft"
    assert body["requested_by_id"] == plain_user.id
    assert len(body["amount_items"]) == 2
    assert body["amount_items"][0]["item_no"] == 1
    assert body["budget_type"] == "expenses"
    assert body["budget_no"] == "5100-01"
    assert body["schedule_start"] == "2026-09-03"
    assert body["schedule_finish"] == "2026-09-15"
    assert isinstance(body["ar_no"], int)
    assert body["ar_no_display"] == f"AR-{body['ar_no']:04d}"


def test_create_ar_allocates_sequential_numbers(client: TestClient, plain_user: User):
    _login(client)
    res1 = client.post("/ars", json=_sample_ar_body())
    res2 = client.post("/ars", json=_sample_ar_body())
    assert res2.json()["ar_no"] == res1.json()["ar_no"] + 1


def test_create_ar_allows_empty_amount_items(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/ars", json=_sample_ar_body(amount_items=[]))
    assert res.status_code == 201
    assert res.json()["amount_items"] == []


def test_get_ar_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.get("/ars/9999")
    assert res.status_code == 404


def test_list_ars_returns_created(client: TestClient, plain_user: User):
    _login(client)
    client.post("/ars", json=_sample_ar_body())
    res = client.get("/ars")
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_update_draft_ar_success(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    updated_body = _sample_ar_body(subject="แก้ไขแล้ว")
    updated_body["amount_items"].append({"label": "ค่าซ่อมเพิ่มเติม", "amount": "500.00"})
    res = client.patch(f"/ars/{created['id']}", json=updated_body)
    assert res.status_code == 200
    body = res.json()
    assert body["subject"] == "แก้ไขแล้ว"
    assert len(body["amount_items"]) == 3
    assert [i["item_no"] for i in body["amount_items"]] == [1, 2, 3]


def test_update_non_draft_ar_rejected(client: TestClient, plain_user: User, db_session: Session):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    ar = db_session.get(ApprovalRequest, created["id"])
    ar.status = ARStatus.FINALIZED
    db_session.commit()

    res = client.patch(f"/ars/{created['id']}", json=_sample_ar_body())
    assert res.status_code == 409


def test_get_ar_pdf_returns_valid_pdf(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    res = client.get(f"/ars/{created['id']}/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"
    assert len(res.content) > 1000


def test_get_ar_pdf_has_no_side_effects(
    client: TestClient, plain_user: User, db_session: Session
):
    """Correction 2026-09-10: พิมพ์/ดาวน์โหลด PDF ไม่ Finalize อีกต่อไป — พิมพ์ดูกี่ครั้ง
    ก็ได้ตราบใดที่ยังไม่กด "ส่งขออนุมัติ" (ดู test_submit_for_approval_* ด้านล่าง)"""
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    ar = db_session.get(ApprovalRequest, created["id"])
    assert ar.status == ARStatus.DRAFT

    res = client.get(f"/ars/{created['id']}/pdf")
    assert res.status_code == 200

    db_session.refresh(ar)
    assert ar.status == ARStatus.DRAFT  # ยังไม่ Finalize แค่เพราะพิมพ์

    res2 = client.get(f"/ars/{created['id']}/pdf")
    assert res2.status_code == 200

    db_session.refresh(ar)
    assert ar.status == ARStatus.DRAFT  # พิมพ์ซ้ำกี่ครั้งก็ยังไม่ Finalize

    # ยังแก้ไขได้ตามปกติเพราะยังเป็น Draft อยู่
    edited = client.patch(f"/ars/{created['id']}", json=_sample_ar_body(subject="แก้ได้"))
    assert edited.status_code == 200


# ── Submit for Approval (Correction 2026-09-10) ──────────────────────────


def test_submit_for_approval_requires_login(client: TestClient):
    res = client.post("/ars/1/submit-for-approval")
    assert res.status_code == 401


def test_submit_for_approval_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/ars/9999/submit-for-approval")
    assert res.status_code == 404


def test_submit_for_approval_auto_finalizes_when_no_levels_configured(
    client: TestClient, plain_user: User
):
    """Department "Production" ไม่มีการตั้ง BudgetApprovalLevel เลยในไฟล์นี้ — ไม่มี
    Level ให้รอจึง Finalize ทันทีตอนกด "ส่งขออนุมัติ" (ข้ามตรงไป FA Acknowledge)"""
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    res = client.post(f"/ars/{created['id']}/submit-for-approval")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "finalized"
    assert body["budget_approval_status"] == "pending_fa_acknowledge"

    history = client.get(f"/ars/{created['id']}/history").json()
    actions = [log["action"] for log in history]
    assert "ar.submitted_for_approval" in actions
    assert "ar.finalized" in actions


def test_submit_for_approval_twice_rejected(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    first = client.post(f"/ars/{created['id']}/submit-for-approval")
    assert first.status_code == 200

    # ครั้งที่ 2: Finalized ไปแล้วตั้งแต่ครั้งแรก (ไม่มี Level) จึงโดน Gate สถานะ Draft
    second = client.post(f"/ars/{created['id']}/submit-for-approval")
    assert second.status_code == 409


def test_finalized_ar_rejects_edit(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    client.post(f"/ars/{created['id']}/submit-for-approval")

    res = client.patch(f"/ars/{created['id']}", json=_sample_ar_body(subject="แก้ไม่ได้แล้ว"))
    assert res.status_code == 409


def test_update_ar_after_reject_requires_revise(
    client: TestClient, plain_user: User, admin_user: User
):
    """Correction 2026-09-10: AR ที่ถูก Reject ไปแล้วแก้ตรงๆ ผ่าน PATCH ไม่ได้อีกต่อไป
    ต้องใช้ปุ่ม "สร้าง Revision" แทนเท่านั้น"""
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    client.post(f"/ars/{created['id']}/submit-for-approval")  # -> pending_fa_acknowledge

    _login_as(client, admin_user.email, "adminpass123")  # Admin Override ได้ทุก Level รวม FA
    rejected = client.post(f"/ars/{created['id']}/reject-fa", json={"reason": "ข้อมูลไม่ครบ"})
    assert rejected.status_code == 200
    assert rejected.json()["budget_approval_status"] == "rejected"

    res = client.patch(f"/ars/{created['id']}", json=_sample_ar_body(subject="แก้ตรงๆ ไม่ได้"))
    assert res.status_code == 409


# ── Revise — Correction 2026-09-10: Gate ด้วย budget_approval_status == rejected
# เท่านั้น (ไม่เกี่ยวกับ status Finalized เหมือนเดิม/เหมือน PR อีกต่อไป) ────────────


def _reject_via_fa(client: TestClient, admin_user: User, ar_id: int) -> dict:
    """Helper: Submit-for-approval (Production ไม่มี Level -> Finalize+PENDING_FA_ACK
    ทันที) แล้ว Reject ที่ขั้น FA Acknowledge ด้วย Admin Override — ทางลัดที่สุดในไฟล์
    นี้เพื่อให้ AR เข้าสถานะ Rejected (เงื่อนไขเดียวที่ Revise ได้ตาม Correction นี้)"""
    client.post(f"/ars/{ar_id}/submit-for-approval")
    _login_as(client, admin_user.email, "adminpass123")
    res = client.post(f"/ars/{ar_id}/reject-fa", json={"reason": "ทดสอบ Reject"})
    assert res.status_code == 200, res.text
    assert res.json()["budget_approval_status"] == "rejected"
    return res.json()


def test_revise_draft_ar_rejected(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    res = client.post(f"/ars/{created['id']}/revise")
    assert res.status_code == 409


def test_revise_rejected_ar_creates_draft_copy(
    client: TestClient, plain_user: User, admin_user: User
):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    _reject_via_fa(client, admin_user, original["id"])

    _login(client)  # กลับมาเป็นผู้สร้าง AR เพื่อกด Revise
    res = client.post(f"/ars/{original['id']}/revise")
    assert res.status_code == 201
    revised = res.json()

    assert revised["id"] != original["id"]
    assert revised["ar_no"] == original["ar_no"]
    assert revised["revision"] == 1
    assert revised["revised_from_id"] == original["id"]
    assert revised["status"] == "draft"
    assert revised["budget_approval_status"] == "not_submitted"
    assert revised["requested_by_id"] == original["requested_by_id"]
    assert revised["subject"] == original["subject"]
    assert revised["amount_items"][0]["label"] == original["amount_items"][0]["label"]

    orig_after = client.get(f"/ars/{original['id']}").json()
    assert orig_after["status"] == "finalized"  # ต้นฉบับยัง Finalized เหมือนเดิม ไม่ถูกแตะ
    assert orig_after["budget_approval_status"] == "rejected"
    assert orig_after["superseded_by_id"] == revised["id"]


def test_revise_rejected_while_still_draft_creates_draft_copy(
    client: TestClient, plain_user: User, db_session: Session
):
    """เคสที่ Level ปฏิเสธก่อนมี Level ไหนอนุมัติผ่านเลยสักครั้ง — ar.status ยังเป็น
    Draft อยู่ (ไม่เคย Finalize ตาม budget_workflow.approve_level) แต่
    budget_approval_status กลาย เป็น rejected แล้ว — Revise ต้องยังใช้ได้เพราะ Gate
    เช็คแค่ budget_approval_status เท่านั้น ไม่เกี่ยวกับ ar.status"""
    from tests.test_budget_control import _make_level, _make_user

    manager = _make_user(
        db_session, name="Reject Mgr", email="rejectmgr@example.com", department="Production"
    )
    _make_level(
        db_session,
        department="Production",
        level_no=1,
        level_name="Manager",
        approver_user_id=manager.id,
    )

    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    submitted = client.post(f"/ars/{created['id']}/submit-for-approval").json()
    assert submitted["status"] == "draft"  # มี Level ให้รอ -> ยังไม่ Finalize
    assert submitted["budget_approval_status"] == "pending"

    _login_as(client, manager.email, "password123456")
    rejected = client.post(f"/ars/{created['id']}/reject-level", json={"reason": "ไม่อนุมัติ"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "draft"  # ยัง Draft อยู่ ไม่เคย Finalize เลย
    assert rejected.json()["budget_approval_status"] == "rejected"

    _login(client)
    res = client.post(f"/ars/{created['id']}/revise")
    assert res.status_code == 201
    assert res.json()["status"] == "draft"


def test_revise_already_superseded_ar_rejected(
    client: TestClient, plain_user: User, admin_user: User
):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    _reject_via_fa(client, admin_user, original["id"])
    _login(client)
    client.post(f"/ars/{original['id']}/revise")

    res = client.post(f"/ars/{original['id']}/revise")
    assert res.status_code == 409


def test_revise_not_found(client: TestClient, plain_user: User):
    _login(client)
    res = client.post("/ars/9999/revise")
    assert res.status_code == 404


def test_revise_requires_login(client: TestClient):
    res = client.post("/ars/1/revise")
    assert res.status_code == 401


def test_ar_history_records_lifecycle(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    client.post(f"/ars/{created['id']}/submit-for-approval")

    res = client.get(f"/ars/{created['id']}/history")
    assert res.status_code == 200
    actions = [log["action"] for log in res.json()]
    assert "ar.created" in actions
    assert "ar.submitted_for_approval" in actions
    assert "ar.finalized" in actions


def test_revised_ar_html_renders_rev_suffix(
    client: TestClient, plain_user: User, admin_user: User, db_session: Session
):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    _reject_via_fa(client, admin_user, original["id"])
    _login(client)
    revised = client.post(f"/ars/{original['id']}/revise").json()

    orig_ar = db_session.get(ApprovalRequest, original["id"])
    revised_ar = db_session.get(ApprovalRequest, revised["id"])

    orig_html = render_ar_html(db_session, orig_ar)
    revised_html = render_ar_html(db_session, revised_ar)

    assert "Rev." not in orig_html
    assert "Rev.1" in revised_html


def test_ar_html_renders_summary_totals_and_new_fields(
    client: TestClient, plain_user: User, db_session: Session
):
    """Regression Test สำหรับบั๊กจริงที่ผู้ใช้เจอบน UAT (2026-09-08) — Total/Vat/Grand
    Total เคยหายไปจาก PDF เงียบๆ เพราะ WeasyPrint Clip เนื้อหาส่วนท้ายของ .items-wrap
    (flex:1, overflow:hidden) ทิ้งตอนพื้นที่ไม่พอ (ดู ar_form.html — ย้ายมาไว้ใน
    .bottom-block ที่เป็น Fixed Height แทนแล้ว) — Test นี้ตรวจ String ตรงๆ ใน HTML ที่
    Render จริง (ก่อนส่งต่อให้ WeasyPrint แปลงเป็น PDF) กัน Regression ไม่ให้ค่าพวกนี้
    หายไปเงียบๆ อีก พร้อมกันตรวจ Field ใหม่ (budget_no, schedule_start/finish) ที่เพิ่ม
    ตาม Feedback รอบเดียวกัน"""
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    ar = db_session.get(ApprovalRequest, created["id"])

    html = render_ar_html(db_session, ar)

    assert ">Total<" in html
    assert "9,327.10" in html  # total
    assert ">Vat<" in html
    assert "Vat 7%" not in html  # เปลี่ยนคำตามที่ผู้ใช้ขอ
    assert "652.90" in html  # vat_amount
    assert ">Grand Total<" in html
    assert "9,980.00" in html  # grand_total
    assert "5100-01" in html  # budget_no
    assert "03/09/2026 - 15/09/2026" in html  # schedule_start - schedule_finish


def test_ar_html_with_many_items_does_not_silently_drop_rows(
    client: TestClient, plain_user: User, db_session: Session
):
    """Regression Test สำหรับบั๊กที่พบระหว่างแก้ Feedback รอบ 2026-09-08 (คนละตัวกับ
    Total/Vat/Grand Total ด้านบน แต่มีสาเหตุร่วม) — ยืนยันจริงด้วย WeasyPrint Render +
    pdfplumber วัดตำแหน่ง Text ตรงๆ ว่า .items-wrap (flex:1, overflow:hidden) รองรับ
    "รายการที่มีข้อความจริง" ได้แค่ไม่กี่แถวก่อนโดนตัดทิ้งเงียบๆ (Div ว่างที่ Pad ไม่กิน
    พื้นที่จริง ต่างจาก Div ที่มีข้อความ) — แก้โดยตัดสิน Tier (Fixed 1 หน้า vs Overflow
    ปล่อยไหลข้ามหน้า) จาก real_item_count (จำนวนรายการจริงก่อน Pad) แทนความยาว List
    หลัง Pad — Test นี้ตรวจว่า Label ของทุกรายการ (รวมรายการที่ 12) ยังอยู่ใน HTML ที่
    Render จริงเสมอ ไม่ว่าจะมีกี่รายการก็ตาม"""
    _login(client)
    many_items = [{"label": f"Item number {i + 1}", "amount": "1000.00"} for i in range(12)]
    created = client.post("/ars", json=_sample_ar_body(amount_items=many_items)).json()
    ar = db_session.get(ApprovalRequest, created["id"])

    html = render_ar_html(db_session, ar)

    for i in range(12):
        assert f"Item number {i + 1}" in html, f"รายการที่ {i + 1} หายไปจาก HTML"
    assert ">Total<" in html
    assert ">Grand Total<" in html
