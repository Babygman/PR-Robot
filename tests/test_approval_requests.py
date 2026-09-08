"""Test บันทึก Approval Request (AR) + Generate PDF — Pattern เดียวกับ
tests/test_purchasing_requisitions.py ทุกประการ (Business Decision 2026-09-08)
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ApprovalRequest, ARStatus, User
from app.services.ar_pdf import render_ar_html


def _login(client: TestClient) -> None:
    client.post("/auth/login", json={"email": "plain@example.com", "password": "plainpass123"})


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


def test_get_ar_pdf_auto_finalizes_on_first_download(
    client: TestClient, plain_user: User, db_session: Session
):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    ar = db_session.get(ApprovalRequest, created["id"])
    assert ar.status == ARStatus.DRAFT

    res = client.get(f"/ars/{created['id']}/pdf")
    assert res.status_code == 200

    db_session.refresh(ar)
    assert ar.status == ARStatus.FINALIZED

    res2 = client.get(f"/ars/{created['id']}/pdf")
    assert res2.status_code == 200


def test_finalized_ar_rejects_edit(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()
    client.get(f"/ars/{created['id']}/pdf")

    res = client.patch(f"/ars/{created['id']}", json=_sample_ar_body(subject="แก้ไม่ได้แล้ว"))
    assert res.status_code == 409


# ── Revise (Pattern เดียวกับ PR) ──────────────────────────────────────────


def test_revise_draft_ar_rejected(client: TestClient, plain_user: User):
    _login(client)
    created = client.post("/ars", json=_sample_ar_body()).json()

    res = client.post(f"/ars/{created['id']}/revise")
    assert res.status_code == 409


def test_revise_finalized_ar_creates_draft_copy(client: TestClient, plain_user: User):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    client.get(f"/ars/{original['id']}/pdf")

    res = client.post(f"/ars/{original['id']}/revise")
    assert res.status_code == 201
    revised = res.json()

    assert revised["id"] != original["id"]
    assert revised["ar_no"] == original["ar_no"]
    assert revised["revision"] == 1
    assert revised["revised_from_id"] == original["id"]
    assert revised["status"] == "draft"
    assert revised["requested_by_id"] == original["requested_by_id"]
    assert revised["subject"] == original["subject"]
    assert revised["amount_items"][0]["label"] == original["amount_items"][0]["label"]

    orig_after = client.get(f"/ars/{original['id']}").json()
    assert orig_after["status"] == "finalized"
    assert orig_after["superseded_by_id"] == revised["id"]


def test_revise_already_superseded_ar_rejected(client: TestClient, plain_user: User):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    client.get(f"/ars/{original['id']}/pdf")
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
    client.get(f"/ars/{created['id']}/pdf")

    res = client.get(f"/ars/{created['id']}/history")
    assert res.status_code == 200
    actions = [log["action"] for log in res.json()]
    assert "ar.created" in actions
    assert "ar.finalized" in actions


def test_revised_ar_html_renders_rev_suffix(
    client: TestClient, plain_user: User, db_session: Session
):
    _login(client)
    original = client.post("/ars", json=_sample_ar_body()).json()
    client.get(f"/ars/{original['id']}/pdf")
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
